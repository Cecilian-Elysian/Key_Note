"""SQLite 异步写入 + 聚合表 + 备份 + 保留策略 + 查询"""
from __future__ import annotations

import queue
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

DB_PATH = Path(__file__).parent / "keynote.db"
BACKUP_DIR = Path(__file__).parent / "backups"

_conn: Optional[sqlite3.Connection] = None
_writer_thread: Optional[threading.Thread] = None
_write_queue: Optional["queue.Queue"] = None
_shutdown_event = threading.Event()
_session_id: Optional[int] = None
_retention_days: int = 7

_INSERT_SQL = "INSERT INTO keypresses (ts, key, session_id) VALUES (?, ?, ?)"
_AGG_MINUTE_SQL = (
    "INSERT INTO agg_minute(minute_ts, count) VALUES (?, ?) "
    "ON CONFLICT(minute_ts) DO UPDATE SET count = count + excluded.count"
)
_AGG_HOUR_SQL = (
    "INSERT INTO agg_hour(hour_ts, count) VALUES (?, ?) "
    "ON CONFLICT(hour_ts) DO UPDATE SET count = count + excluded.count"
)
_AGG_KEY_SQL = (
    "INSERT INTO agg_key_total(key, count) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET count = count + excluded.count"
)
_AGG_DOW_HOUR_SQL = (
    "INSERT INTO agg_dow_hour(dow, hour, count) VALUES (?, ?, ?) "
    "ON CONFLICT(dow, hour) DO UPDATE SET count = count + excluded.count"
)

_LAST_CLEANUP_MONO = 0.0
_CLEANUP_INTERVAL_SEC = 24 * 3600


def init(cfg: Optional[dict] = None) -> sqlite3.Connection:
    """初始化 DB: PRAGMA + 迁移 + writer 线程 + 新 session + 自动备份"""
    global _conn, _writer_thread, _write_queue, _retention_days
    cfg = cfg or {}
    batch_size = int(cfg.get("db_flush_batch_size", 200))
    interval = float(cfg.get("db_flush_interval_sec", 1.0))
    _retention_days = int(cfg.get("db_retention_days", 7))
    auto_backup_days = int(cfg.get("db_auto_backup_days", 7))

    _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA synchronous=NORMAL")
    _conn.execute("PRAGMA temp_store=MEMORY")
    _conn.execute("PRAGMA cache_size=-65536")
    _conn.execute("PRAGMA mmap_size=268435456")
    _conn.execute("PRAGMA wal_autocheckpoint=1000")

    _run_migrations()

    _write_queue = queue.Queue(maxsize=100000)
    _shutdown_event.clear()
    _writer_thread = threading.Thread(
        target=_writer_loop,
        args=(batch_size, interval),
        daemon=True,
        name="db-writer",
    )
    _writer_thread.start()

    _start_session()

    _auto_backup_if_needed(auto_backup_days)

    return _conn


def _run_migrations() -> None:
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)"
    )
    cur = _conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
    current = cur.fetchone()[0]
    if current < 1:
        _migrate_to_v1()
    if current < 2:
        _migrate_to_v2()
    _conn.commit()


def _table_cols(name: str) -> set:
    return {r[1] for r in _conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _migrate_to_v1() -> None:
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "started_at INTEGER NOT NULL, "
        "ended_at INTEGER"
        ")"
    )
    cols = _table_cols("keypresses")
    if "session_id" not in cols:
        _conn.execute(
            "ALTER TABLE keypresses ADD COLUMN session_id INTEGER REFERENCES sessions(id)"
        )
    _conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_ts ON keypresses(session_id, ts)"
    )
    _conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ts_key ON keypresses(ts, key)"
    )
    _conn.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (1, ?)",
        (int(time.time() * 1000),),
    )


def _migrate_to_v2() -> None:
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS agg_minute ("
        "minute_ts INTEGER PRIMARY KEY, "
        "count INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS agg_hour ("
        "hour_ts INTEGER PRIMARY KEY, "
        "count INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS agg_dow_hour ("
        "dow INTEGER NOT NULL, "
        "hour INTEGER NOT NULL, "
        "count INTEGER NOT NULL DEFAULT 0, "
        "PRIMARY KEY (dow, hour)"
        ")"
    )
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS agg_key_total ("
        "key TEXT PRIMARY KEY, "
        "count INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    _conn.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (2, ?)",
        (int(time.time() * 1000),),
    )


def _start_session() -> None:
    global _session_id
    ts = int(time.time() * 1000)
    cur = _conn.execute("INSERT INTO sessions(started_at) VALUES (?)", (ts,))
    _session_id = cur.lastrowid
    _conn.commit()


def _end_session() -> None:
    global _session_id
    if _session_id is None:
        return
    _conn.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?",
        (int(time.time() * 1000), _session_id),
    )
    _conn.commit()
    _session_id = None


def enqueue(key: str) -> None:
    """非阻塞入队,由 listener 在按键线程调用"""
    if _write_queue is None or _shutdown_event.is_set():
        return
    try:
        _write_queue.put_nowait((time.time(), key))
    except queue.Full:
        pass


def _writer_loop(batch_size: int, interval: float) -> None:
    global _LAST_CLEANUP_MONO
    _LAST_CLEANUP_MONO = time.monotonic()
    while not _shutdown_event.is_set():
        batch = _collect_batch(batch_size, interval)
        if batch:
            _flush_batch(batch)
            _maybe_cleanup()
    final = []
    while True:
        try:
            final.append(_write_queue.get_nowait())
        except queue.Empty:
            break
    if final:
        _flush_batch(final)


def _collect_batch(batch_size: int, interval: float) -> list:
    batch: list = []
    deadline = time.monotonic() + interval
    while len(batch) < batch_size:
        if _shutdown_event.is_set():
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            item = _write_queue.get(timeout=min(remaining, 0.05))
            batch.append(item)
        except queue.Empty:
            if batch:
                break
    return batch


def _flush_batch(batch: list) -> None:
    try:
        rows = []
        minute_buckets: dict = {}
        hour_buckets: dict = {}
        dow_hour_buckets: dict = {}
        key_buckets: dict = {}
        for ts_sec, key in batch:
            ts_ms = int(ts_sec * 1000)
            rows.append((ts_ms, key, _session_id))
            minute_ts = (ts_ms // 60000) * 60000
            hour_ts = (ts_ms // 3600000) * 3600000
            minute_buckets[minute_ts] = minute_buckets.get(minute_ts, 0) + 1
            hour_buckets[hour_ts] = hour_buckets.get(hour_ts, 0) + 1
            dt = datetime.fromtimestamp(ts_sec)
            dh = (dt.weekday(), dt.hour)
            dow_hour_buckets[dh] = dow_hour_buckets.get(dh, 0) + 1
            key_buckets[key] = key_buckets.get(key, 0) + 1

        _conn.execute("BEGIN")
        _conn.executemany(_INSERT_SQL, rows)
        _conn.executemany(_AGG_MINUTE_SQL, list(minute_buckets.items()))
        _conn.executemany(_AGG_HOUR_SQL, list(hour_buckets.items()))
        _conn.executemany(
            _AGG_DOW_HOUR_SQL,
            [(d, h, c) for (d, h), c in dow_hour_buckets.items()],
        )
        _conn.executemany(_AGG_KEY_SQL, list(key_buckets.items()))
        _conn.execute("COMMIT")
    except sqlite3.Error as e:
        print(f"DB write error: {e}")
        try:
            _conn.execute("ROLLBACK")
        except Exception:
            pass


def _maybe_cleanup() -> None:
    global _LAST_CLEANUP_MONO
    now = time.monotonic()
    if now - _LAST_CLEANUP_MONO < _CLEANUP_INTERVAL_SEC:
        return
    _LAST_CLEANUP_MONO = now
    if _retention_days <= 0:
        return
    cutoff_ms = int(time.time() * 1000) - _retention_days * 86400000
    try:
        _conn.execute("DELETE FROM keypresses WHERE ts < ?", (cutoff_ms,))
        _conn.execute(
            "DELETE FROM sessions WHERE ended_at IS NOT NULL AND ended_at < ?",
            (cutoff_ms,),
        )
        _conn.commit()
    except sqlite3.Error as e:
        print(f"DB cleanup error: {e}")


def set_retention_days(days: int) -> None:
    """运行时更新保留天数,0 = 永久"""
    global _retention_days
    _retention_days = max(0, int(days))


def close():
    """排空队列 + 关闭 session + checkpoint + 关闭连接"""
    global _conn, _writer_thread, _write_queue, _session_id
    _shutdown_event.set()
    if _writer_thread is not None:
        _writer_thread.join(timeout=5)
        _writer_thread = None
    _write_queue = None
    _end_session()
    if _conn is not None:
        try:
            _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        _conn.close()
        _conn = None
    _session_id = None


def count_today() -> int:
    if _conn is None:
        return 0
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ts = int(midnight.timestamp() * 1000)
    cur = _conn.execute("SELECT COUNT(*) FROM keypresses WHERE ts >= ?", (ts,))
    return cur.fetchone()[0]


def count_total() -> int:
    if _conn is None:
        return 0
    cur = _conn.execute("SELECT COALESCE(SUM(count), 0) FROM agg_minute")
    return cur.fetchone()[0]


def top_keys(n: int = 20) -> list:
    if _conn is None:
        return []
    return _conn.execute(
        "SELECT key, count FROM agg_key_total ORDER BY count DESC LIMIT ?",
        (n,),
    ).fetchall()


def rate_series(hours: int = 24) -> list:
    if _conn is None:
        return []
    since = int((time.time() - hours * 3600) * 1000)
    return _conn.execute(
        "SELECT minute_ts, count FROM agg_minute "
        "WHERE minute_ts >= ? ORDER BY minute_ts",
        (since,),
    ).fetchall()


def heatmap_data(days: int = 7) -> np.ndarray:
    if _conn is None:
        return np.zeros((7, 24), dtype=int)
    since = int((time.time() - days * 86400) * 1000)
    grid = np.zeros((7, 24), dtype=int)
    for minute_ts, count in _conn.execute(
        "SELECT minute_ts, count FROM agg_minute WHERE minute_ts >= ?",
        (since,),
    ):
        dt = datetime.fromtimestamp(minute_ts / 1000)
        grid[dt.weekday(), dt.hour] += count
    return grid


def backup(manual: bool = False) -> Optional[Path]:
    """创建一致性快照,返回备份文件路径"""
    if _conn is None:
        return None
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = BACKUP_DIR / f"keynote-{ts}.db"
        bck = sqlite3.connect(dest)
        try:
            _conn.backup(bck)
        finally:
            bck.close()
        _prune_old_backups()
        return dest
    except Exception as e:
        print(f"Backup error: {e}")
        return None


def _auto_backup_if_needed(interval_days: int) -> None:
    if interval_days <= 0:
        return
    if not BACKUP_DIR.exists():
        backup(manual=False)
        return
    files = sorted(
        BACKUP_DIR.glob("keynote-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files or (time.time() - files[0].stat().st_mtime) > interval_days * 86400:
        backup(manual=False)


def _prune_old_backups() -> None:
    if not BACKUP_DIR.exists():
        return
    files = sorted(
        BACKUP_DIR.glob("keynote-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    keep = set()
    for f in files[:7]:
        keep.add(f)
    weekly = []
    last_week = -1
    for f in files:
        week = int(f.stat().st_mtime // (7 * 86400))
        if week != last_week:
            weekly.append(f)
            last_week = week
        if len(weekly) >= 4:
            break
    keep.update(weekly)
    for f in files:
        if f not in keep:
            try:
                f.unlink()
            except Exception:
                pass


def vacuum() -> bool:
    """重建数据库回收空间,执行前确保无活跃读取"""
    if _conn is None:
        return False
    try:
        _conn.execute("VACUUM")
        return True
    except sqlite3.Error as e:
        print(f"VACUUM error: {e}")
        return False


def health() -> dict:
    """返回 DB 健康状态字典"""
    if _conn is None:
        return {}
    out: dict = {}
    try:
        size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
        wal = DB_PATH.parent / (DB_PATH.name + "-wal")
        shm = DB_PATH.parent / (DB_PATH.name + "-shm")
        out["size_bytes"] = size
        out["wal_bytes"] = wal.stat().st_size if wal.exists() else 0
        out["shm_bytes"] = shm.stat().st_size if shm.exists() else 0
        out["raw_count"] = _conn.execute(
            "SELECT COUNT(*) FROM keypresses"
        ).fetchone()[0]
        out["minute_buckets"] = _conn.execute(
            "SELECT COUNT(*) FROM agg_minute"
        ).fetchone()[0]
        out["unique_keys"] = _conn.execute(
            "SELECT COUNT(*) FROM agg_key_total"
        ).fetchone()[0]
        if BACKUP_DIR.exists():
            files = sorted(
                BACKUP_DIR.glob("keynote-*.db"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if files:
                out["last_backup_ts"] = int(files[0].stat().st_mtime)
            else:
                out["last_backup_ts"] = 0
        else:
            out["last_backup_ts"] = 0
        out["retention_days"] = _retention_days
    except Exception as e:
        print(f"health error: {e}")
    return out