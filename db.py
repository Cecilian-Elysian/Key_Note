"""SQLite 异步写入 + 聚合表 + 备份 + 保留策略 + 查询"""
from __future__ import annotations

import csv
import logging
import queue
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

import config

DB_PATH = Path(__file__).parent / "keynote.db"
BACKUP_DIR = Path(__file__).parent / "backups"
LOG_PATH = Path(__file__).parent / "keynote.log"

LOGGER = logging.getLogger("keynote")

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
_AGG_DAY_SQL = (
    "INSERT INTO agg_day(day_ts, count) VALUES (?, ?) "
    "ON CONFLICT(day_ts) DO UPDATE SET count = count + excluded.count"
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

    _setup_logger(bool(cfg.get("log_to_file", False)))

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
    if current < 3:
        _migrate_to_v3()
    _conn.commit()


def _table_cols(name: str) -> set:
    try:
        return {r[1] for r in _conn.execute(f"PRAGMA table_info({name})").fetchall()}
    except sqlite3.Error:
        return set()


def _migrate_to_v1() -> None:
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "started_at INTEGER NOT NULL, "
        "ended_at INTEGER"
        ")"
    )
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS keypresses ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "ts INTEGER NOT NULL, "
        "key TEXT NOT NULL"
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


def _migrate_to_v3() -> None:
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS agg_day ("
        "day_ts INTEGER PRIMARY KEY, "
        "count INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    _conn.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (3, ?)",
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
        day_buckets: dict = {}
        for ts_sec, _ in batch:
            ts_ms = int(ts_sec * 1000)
            day_ts = (ts_ms // 86400000) * 86400000
            day_buckets[day_ts] = day_buckets.get(day_ts, 0) + 1
        if day_buckets:
            _conn.executemany(_AGG_DAY_SQL, list(day_buckets.items()))
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


def _setup_logger(to_file: bool) -> None:
    """根据配置启用/关闭文件日志(运行时切换)。"""
    for h in list(LOGGER.handlers):
        LOGGER.removeHandler(h)
    LOGGER.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    LOGGER.addHandler(sh)
    if to_file:
        try:
            fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
            fh.setFormatter(fmt)
            LOGGER.addHandler(fh)
        except Exception as e:
            print(f"log file init failed: {e}")


def apply_log_to_file(enabled: bool) -> None:
    """运行时切换日志。调用 _setup_logger 重建 handler 列表。"""
    _setup_logger(bool(enabled))


def export_csv(path: str, days: int = 30) -> int:
    """导出过去 N 天的原始按键记录到 CSV,返回导出行数。"""
    if _conn is None:
        return 0
    cutoff_ms = int(time.time() * 1000) - max(1, days) * 86400000
    rows = _conn.execute(
        "SELECT ts, key, session_id FROM keypresses WHERE ts >= ? ORDER BY ts",
        (cutoff_ms,),
    ).fetchall()
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts_iso", "key", "session_id"])
        for ts, key, sid in rows:
            iso = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
            w.writerow([iso, key, sid])
    try:
        LOGGER.info("exported %d rows to %s", len(rows), path)
    except Exception:
        pass
    return len(rows)


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


def heatmap_yearly(days: int = 365) -> tuple[np.ndarray, datetime, datetime]:
    """返回 GitHub 风格年度热力图数据: (grid[weeks, 7], start_date, end_date)。

    grid[i, j] 表示第 i 周、第 j 天的按键总数。
    """
    if _conn is None:
        grid = np.zeros((53, 7), dtype=int)
        end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return grid, end, end
    end_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_dt = end_dt - __import__("datetime").timedelta(days=days - 1)
    since_ms = int(start_dt.timestamp() * 1000)
    grid = np.zeros((53, 7), dtype=int)
    for day_ts, count in _conn.execute(
        "SELECT day_ts, count FROM agg_day WHERE day_ts >= ?",
        (since_ms,),
    ):
        dt = datetime.fromtimestamp(day_ts / 1000)
        delta_days = (dt - start_dt).days
        if delta_days < 0 or delta_days >= days:
            continue
        week_idx = delta_days // 7
        dow_idx = dt.weekday()
        if 0 <= week_idx < 53:
            grid[week_idx, dow_idx] += count
    return grid, start_dt, end_dt


def daily_counts(days: int = 30) -> list[tuple[int, int]]:
    """返回过去 N 天每日 (day_ts_ms, count),按时间升序。"""
    if _conn is None:
        return []
    end_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_dt = end_dt - __import__("datetime").timedelta(days=days - 1)
    since_ms = int(start_dt.timestamp() * 1000)
    rows = _conn.execute(
        "SELECT day_ts, count FROM agg_day WHERE day_ts >= ? ORDER BY day_ts",
        (since_ms,),
    ).fetchall()
    return rows


def streak_days(days: int = 365) -> int:
    """返回连续按键天数(每日按键数 > 0 算活跃)。"""
    rows = daily_counts(days)
    if not rows:
        return 0
    counts_by_day = {day_ts // 86400000: c for day_ts, c in rows}
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_key = int(today.timestamp() // 86400)
    streak = 0
    cursor = today_key
    while counts_by_day.get(cursor, 0) > 0:
        streak += 1
        cursor -= 1
    return streak


def daily_average(days: int = 7) -> int:
    """返回过去 N 天平均每日按键数(无数据的天按 0 计入分母)。"""
    if days <= 0:
        return 0
    rows = daily_counts(days)
    counts_by_day = {day_ts // 86400000: c for day_ts, c in rows}
    end_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_dt = end_dt - __import__("datetime").timedelta(days=days - 1)
    start_key = int(start_dt.timestamp() // 86400)
    end_key = int(end_dt.timestamp() // 86400)
    total = 0
    for k in range(start_key, end_key + 1):
        total += counts_by_day.get(k, 0)
    return total // days


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
        cfg = config.load()
        keep_daily = int(cfg.get("backup_keep_daily", 7))
        keep_weekly = int(cfg.get("backup_keep_weekly", 4))
        _prune_old_backups(keep_daily, keep_weekly)
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


def _prune_old_backups(keep_daily: int = 7, keep_weekly: int = 4) -> None:
    if not BACKUP_DIR.exists():
        return
    files = sorted(
        BACKUP_DIR.glob("keynote-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    keep = set()
    for f in files[: max(0, keep_daily)]:
        keep.add(f)
    weekly = []
    last_week = -1
    for f in files:
        week = int(f.stat().st_mtime // (7 * 86400))
        if week != last_week:
            weekly.append(f)
            last_week = week
        if len(weekly) >= max(0, keep_weekly):
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