"""SQLite 数据持久化层:异步批量写入按键记录与鼠标点击、聚合表更新(分钟/小时/天/周、按键类型、鼠标按钮)、数据库迁移(v1~v6)、自动备份与保留策略清理、CSV 导出、健康状态检查"""
from __future__ import annotations

# ──── 数据目录与迁移 ────

import csv
import logging
import os
import queue
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

import config


def _get_data_dir(cfg: dict) -> Path:
    """根据配置返回数据目录。空字符串=exe 同目录,非空=自定义路径。"""
    custom = cfg.get("data_dir", "")
    return Path(custom) if custom else config.exe_dir()


def _get_backup_dir(cfg: dict) -> Path:
    """返回备份目录。空 = data_dir/backups,非空 = 自定义路径(自动追加 /backups)。"""
    custom = cfg.get("backup_dir", "")
    if custom:
        return Path(custom)
    return _get_data_dir(cfg) / "backups"


def _migrate_from_appdata(target_dir: Path) -> None:
    """把 %APPDATA%/KeyNote/ 下的旧数据(来自上一版 AppData 方案)搬回 target_dir。"""
    appdata_dir = Path(os.environ.get("APPDATA", "")) / "KeyNote"
    if not appdata_dir.exists() or target_dir == appdata_dir:
        return
    for fname in ("keynote.db", "keynote.db-wal", "keynote.db-shm"):
        src = appdata_dir / fname
        dst = target_dir / fname
        if src.exists() and not dst.exists():
            try:
                shutil.move(str(src), str(dst))
            except Exception:
                try:
                    shutil.copy2(str(src), str(dst))
                    src.unlink()
                except Exception:
                    pass
    for name, is_dir in [("config.json", False), ("backups", True), ("keynote.log", False)]:
        src = appdata_dir / name
        dst = target_dir / name
        if not src.exists() or dst.exists():
            continue
        try:
            shutil.move(str(src), str(dst))
        except Exception:
            try:
                if is_dir:
                    shutil.copytree(str(src), str(dst))
                    shutil.rmtree(str(src), ignore_errors=True)
                else:
                    shutil.copy2(str(src), str(dst))
                    src.unlink()
            except Exception:
                pass
    try:
        remaining = list(appdata_dir.iterdir())
        if not remaining:
            appdata_dir.rmdir()
    except Exception:
        pass


# 初始占位,init() 时会根据 cfg["data_dir"] 重新赋值
DB_PATH = config.exe_dir() / "keynote.db"
BACKUP_DIR = config.exe_dir() / "backups"
LOG_PATH = config.exe_dir() / "keynote.log"

LOGGER = logging.getLogger("keynote")

_conn: Optional[sqlite3.Connection] = None
_writer_thread: Optional[threading.Thread] = None
_write_queue: Optional["queue.Queue"] = None
_shutdown_event = threading.Event()
_session_id: Optional[int] = None
_retention_days: int = 7

_MIN_MS = 10_000_000_000  # 1970-04-26;低于此视为非毫秒脏数据
_MAX_MS = 4_102_444_800_000  # 2100-01-01

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
_INSERT_MOUSE_SQL = (
    "INSERT INTO mouse_clicks (ts, button, session_id) VALUES (?, ?, ?)"
)
_AGG_MOUSE_BUTTON_SQL = (
    "INSERT INTO agg_mouse_button_total(button, count) VALUES (?, ?) "
    "ON CONFLICT(button) DO UPDATE SET count = count + excluded.count"
)
_AGG_KEY_TYPE_SQL = (
    "INSERT INTO agg_key_type_total(type, count) VALUES (?, ?) "
    "ON CONFLICT(type) DO UPDATE SET count = count + excluded.count"
)

_LAST_CLEANUP_MONO = 0.0
_CLEANUP_INTERVAL_SEC = 24 * 3600


def _local_midnight_ms(ts_sec: float) -> int:
    """返回本地当天 00:00 对应的 Unix 毫秒时间戳。"""
    dt = datetime.fromtimestamp(ts_sec)
    local_midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(local_midnight.timestamp() * 1000)


def _local_hour_ms(ts_sec: float) -> int:
    """返回本地整点对应的 Unix 毫秒时间戳。"""
    dt = datetime.fromtimestamp(ts_sec)
    local_hour = dt.replace(minute=0, second=0, microsecond=0)
    return int(local_hour.timestamp() * 1000)


def _local_minute_ms(ts_sec: float) -> int:
    """返回本地整分对应的 Unix 毫秒时间戳。"""
    dt = datetime.fromtimestamp(ts_sec)
    local_minute = dt.replace(second=0, microsecond=0)
    return int(local_minute.timestamp() * 1000)


# ──── 数据库初始化 ────
def init(cfg: Optional[dict] = None) -> sqlite3.Connection:
    """初始化 DB: PRAGMA + 迁移 + writer 线程 + 新 session + 自动备份"""
    global _conn, _writer_thread, _write_queue, _retention_days, DB_PATH, BACKUP_DIR, LOG_PATH
    cfg = cfg or {}
    data_dir = _get_data_dir(cfg)
    data_dir.mkdir(parents=True, exist_ok=True)
    DB_PATH = data_dir / "keynote.db"
    BACKUP_DIR = _get_backup_dir(cfg)
    LOG_PATH = data_dir / "keynote.log"
    _migrate_from_appdata(data_dir)
    batch_size = int(cfg.get("db_flush_batch_size", 200))
    interval = float(cfg.get("db_flush_interval_sec", 1.0))
    _retention_days = int(cfg.get("db_retention_days", 365))
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


# ──── 迁移版本 ────
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
    if current < 4:
        _migrate_to_v4()
    if current < 5:
        _migrate_to_v5()
    if current < 6:
        _migrate_to_v6()
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


def _migrate_to_v4() -> None:
    """把 agg_day / agg_hour / agg_minute 中所有时间戳从 UTC 基准回填为本地基准。

    旧数据生成时按 (ts_ms // 86400000) * 86400000 等 UTC 整除方式分桶;
    新数据按本地整点/整分/整日分桶。本迁移读取旧值 → 反算 dt_local → 重写为本地整点 Unix ms。
    agg_dow_hour 不含时间戳,无需迁移。

    使用 with _conn: 上下文管理器自动处理事务:
      - 若已有隐式事务 → 复用并在退出时 COMMIT
      - 若无事务 → 自动 BEGIN, 退出时 COMMIT
      - 异常 → 自动 ROLLBACK
    """
    with _conn:
        rows = _conn.execute("SELECT day_ts, count FROM agg_day").fetchall()
        new_buckets: dict = {}
        for day_ts, count in rows:
            dt_local = datetime.fromtimestamp(day_ts / 1000)
            new_ts = _local_midnight_ms(dt_local.timestamp())
            new_buckets[new_ts] = new_buckets.get(new_ts, 0) + count
        _conn.execute("DELETE FROM agg_day")
        if new_buckets:
            _conn.executemany(_AGG_DAY_SQL, list(new_buckets.items()))

        rows = _conn.execute("SELECT hour_ts, count FROM agg_hour").fetchall()
        new_buckets = {}
        for hour_ts, count in rows:
            dt_local = datetime.fromtimestamp(hour_ts / 1000)
            new_ts = _local_hour_ms(dt_local.timestamp())
            new_buckets[new_ts] = new_buckets.get(new_ts, 0) + count
        _conn.execute("DELETE FROM agg_hour")
        if new_buckets:
            _conn.executemany(_AGG_HOUR_SQL, list(new_buckets.items()))

        rows = _conn.execute("SELECT minute_ts, count FROM agg_minute").fetchall()
        new_buckets = {}
        for minute_ts, count in rows:
            dt_local = datetime.fromtimestamp(minute_ts / 1000)
            new_ts = _local_minute_ms(dt_local.timestamp())
            new_buckets[new_ts] = new_buckets.get(new_ts, 0) + count
        _conn.execute("DELETE FROM agg_minute")
        if new_buckets:
            _conn.executemany(_AGG_MINUTE_SQL, list(new_buckets.items()))

        _conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES (4, ?)",
            (int(time.time() * 1000),),
        )


def _migrate_to_v5() -> None:
    """新增鼠标点击事件 + 按键类型聚合。mouse_clicks(原表,受保留策略影响) + agg_mouse_button_total(永久)。"""
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS mouse_clicks ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "ts INTEGER NOT NULL, "
        "button TEXT NOT NULL, "
        "session_id INTEGER REFERENCES sessions(id)"
        ")"
    )
    _conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mc_ts ON mouse_clicks(ts)"
    )
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS agg_mouse_button_total ("
        "button TEXT PRIMARY KEY, "
        "count INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    _conn.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (5, ?)",
        (int(time.time() * 1000),),
    )


def _migrate_to_v6() -> None:
    """新增按键类型聚合(letter/digit/symbol/modifier/function)。"""
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS agg_key_type_total ("
        "type TEXT PRIMARY KEY, "
        "count INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    _conn.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (6, ?)",
        (int(time.time() * 1000),),
    )


# ──── 会话管理 ────
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


# ──── 写入队列 ────
def _enqueue_event(kind: str, payload: str, ktype: str = "") -> None:
    """非阻塞入队。事件格式:(ts_sec, kind, payload, ktype)"""
    if _write_queue is None or _shutdown_event.is_set():
        return
    try:
        _write_queue.put_nowait((time.time(), kind, payload, ktype))
    except queue.Full:
        pass


def enqueue(key: str, key_type: str = "letter") -> None:
    """按键入队,key_type 由 listener 调用时分类(letter/digit/symbol/modifier/function)"""
    _enqueue_event("k", key, key_type)


def enqueue_mouse(button: str) -> None:
    """鼠标点击入队,button: left/right/middle/x1/x2"""
    _enqueue_event("m", button, "")


# ──── 批量写入与聚合 ────
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
        k_rows: list = []
        m_rows: list = []
        minute_buckets: dict = {}
        hour_buckets: dict = {}
        dow_hour_buckets: dict = {}
        key_buckets: dict = {}
        key_type_buckets: dict = {}
        day_buckets: dict = {}
        mouse_buckets: dict = {}

        for item in batch:
            ts_sec, kind, payload, ktype = item
            ts_ms = int(ts_sec * 1000)
            if kind == "k":
                k_rows.append((ts_ms, payload, _session_id))
                m_ms = _local_minute_ms(ts_sec)
                h_ms = _local_hour_ms(ts_sec)
                d_ms = _local_midnight_ms(ts_sec)
                minute_buckets[m_ms] = minute_buckets.get(m_ms, 0) + 1
                hour_buckets[h_ms] = hour_buckets.get(h_ms, 0) + 1
                dt = datetime.fromtimestamp(ts_sec)
                dh = (dt.weekday(), dt.hour)
                dow_hour_buckets[dh] = dow_hour_buckets.get(dh, 0) + 1
                key_buckets[payload] = key_buckets.get(payload, 0) + 1
                if ktype:
                    key_type_buckets[ktype] = key_type_buckets.get(ktype, 0) + 1
                day_buckets[d_ms] = day_buckets.get(d_ms, 0) + 1
            elif kind == "m":
                m_rows.append((ts_ms, payload, _session_id))
                mouse_buckets[payload] = mouse_buckets.get(payload, 0) + 1

        with _conn:
            if k_rows:
                _conn.executemany(_INSERT_SQL, k_rows)
                _conn.executemany(_AGG_MINUTE_SQL, list(minute_buckets.items()))
                _conn.executemany(_AGG_HOUR_SQL, list(hour_buckets.items()))
                _conn.executemany(
                    _AGG_DOW_HOUR_SQL,
                    [(d, h, c) for (d, h), c in dow_hour_buckets.items()],
                )
                _conn.executemany(_AGG_KEY_SQL, list(key_buckets.items()))
                if key_type_buckets:
                    _conn.executemany(_AGG_KEY_TYPE_SQL, list(key_type_buckets.items()))
                if day_buckets:
                    _conn.executemany(_AGG_DAY_SQL, list(day_buckets.items()))
            if m_rows:
                _conn.executemany(_INSERT_MOUSE_SQL, m_rows)
                _conn.executemany(_AGG_MOUSE_BUTTON_SQL, list(mouse_buckets.items()))
    except sqlite3.Error as e:
        LOGGER.warning("DB write error: %s", e)


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
        _conn.execute("DELETE FROM mouse_clicks WHERE ts < ?", (cutoff_ms,))
        _conn.execute(
            "DELETE FROM sessions WHERE ended_at IS NOT NULL AND ended_at < ?",
            (cutoff_ms,),
        )
        _conn.commit()
    except sqlite3.Error as e:
        LOGGER.warning("DB cleanup error: %s", e)


# ──── 清理与保留 ────
def set_retention_days(days: int) -> None:
    """运行时更新保留天数,0 = 永久"""
    global _retention_days
    _retention_days = max(0, int(days))


# ──── 日志 ────
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
            LOGGER.warning("log file init failed: %s", e)


def apply_log_to_file(enabled: bool) -> None:
    """运行时切换日志。调用 _setup_logger 重建 handler 列表。"""
    _setup_logger(bool(enabled))


# ──── 查询接口 ────
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
    cur = _conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM agg_minute "
        "WHERE minute_ts BETWEEN ? AND ?",
        (_MIN_MS, _MAX_MS),
    )
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
        "WHERE minute_ts BETWEEN ? AND ? ORDER BY minute_ts",
        (max(_MIN_MS, since), _MAX_MS),
    ).fetchall()


def heatmap_data(days: int = 7) -> np.ndarray:
    if _conn is None:
        return np.zeros((7, 24), dtype=int)
    since = int((time.time() - days * 86400) * 1000)
    grid = np.zeros((7, 24), dtype=int)
    for minute_ts, count in _conn.execute(
        "SELECT minute_ts, count FROM agg_minute WHERE minute_ts BETWEEN ? AND ?",
        (max(_MIN_MS, since), _MAX_MS),
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
        "SELECT day_ts, count FROM agg_day WHERE day_ts BETWEEN ? AND ?",
        (max(_MIN_MS, since_ms), _MAX_MS),
    ):
        dt = datetime.fromtimestamp(day_ts / 1000).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        delta_days = (dt - start_dt).days
        if delta_days < 0 or delta_days >= days:
            continue
        week_idx = delta_days // 7
        dow_idx = dt.weekday()
        if 0 <= week_idx < 53:
            grid[week_idx, dow_idx] += count
    return grid, start_dt, end_dt


def daily_counts(days: int = 30) -> list[tuple[int, int]]:
    """返回过去 N 天每日 (day_ts_ms, count),按时间升序,跳过非法时间戳。"""
    if _conn is None:
        return []
    end_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=days - 1)
    since_ms = int(start_dt.timestamp() * 1000)
    rows = []
    for day_ts, c in _conn.execute(
        "SELECT day_ts, count FROM agg_day WHERE day_ts BETWEEN ? AND ? ORDER BY day_ts",
        (max(_MIN_MS, since_ms), _MAX_MS),
    ):
        rows.append((day_ts, c))
    return rows


def streak_days(days: int = 365) -> int:
    """返回连续按键天数(每日按键数 > 0 算活跃)。"""
    rows = daily_counts(days)
    if not rows:
        return 0
    counts_by_day: dict = {}
    for day_ts, c in rows:
        dt = datetime.fromtimestamp(day_ts / 1000).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        counts_by_day[dt.date()] = counts_by_day.get(dt.date(), 0) + c
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    streak = 0
    cursor = today
    while counts_by_day.get(cursor.date(), 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def daily_average(days: int = 7) -> int:
    """返回过去 N 天平均每日按键数(无数据的天按 0 计入分母)。"""
    if days <= 0:
        return 0
    rows = daily_counts(days)
    counts_by_day: dict = {}
    for day_ts, c in rows:
        dt = datetime.fromtimestamp(day_ts / 1000).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        counts_by_day[dt.date()] = counts_by_day.get(dt.date(), 0) + c
    end_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=days - 1)
    total = 0
    cursor = start_dt
    while cursor <= end_dt:
        total += counts_by_day.get(cursor.date(), 0)
        cursor += timedelta(days=1)
    return total // days


def daily_active_days(days: int = 30) -> int:
    """过去 N 天中有按键记录的天数(0 即最近 N 天无活动)。"""
    if _conn is None:
        return 0
    end_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=days - 1)
    since_ms = int(start_dt.timestamp() * 1000)
    row = _conn.execute(
        "SELECT COUNT(*) FROM agg_day "
        "WHERE day_ts BETWEEN ? AND ? AND count > 0",
        (max(_MIN_MS, since_ms), _MAX_MS),
    ).fetchone()
    return int(row[0]) if row else 0


def hourly_today() -> list:
    """返回今日每小时 (hour_ts_ms, count) 按时间升序,不足 24 桶也按整小时排。"""
    if _conn is None:
        return []
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    since_ms = int(midnight.timestamp() * 1000)
    rows = _conn.execute(
        "SELECT hour_ts, count FROM agg_hour WHERE hour_ts BETWEEN ? AND ? ORDER BY hour_ts",
        (max(_MIN_MS, since_ms), _MAX_MS),
    ).fetchall()
    return rows


def cpm_recent(minutes: int = 5) -> float:
    """返回最近 minutes 分钟平均每分钟按键数(0 表示无数据)。"""
    if _conn is None or minutes <= 0:
        return 0.0
    since = int((time.time() - minutes * 60) * 1000)
    row = _conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM agg_minute "
        "WHERE minute_ts BETWEEN ? AND ?",
        (max(_MIN_MS, since), _MAX_MS),
    ).fetchone()
    total = float(row[0]) if row else 0.0
    return total / minutes


def mouse_total() -> int:
    """累计鼠标点击总数。"""
    if _conn is None:
        return 0
    row = _conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM agg_mouse_button_total"
    ).fetchone()
    return int(row[0]) if row else 0


def mouse_by_button() -> list:
    """鼠标各按钮点击数,返回 [(button, count), ...] 按 count 降序。"""
    if _conn is None:
        return []
    return _conn.execute(
        "SELECT button, count FROM agg_mouse_button_total ORDER BY count DESC"
    ).fetchall()


def key_type_distribution() -> list:
    """按键类型分布,返回 [(type, count), ...] 按 count 降序。type ∈ letter/digit/symbol/modifier/function。"""
    if _conn is None:
        return []
    return _conn.execute(
        "SELECT type, count FROM agg_key_type_total ORDER BY count DESC"
    ).fetchall()


# ──── 备份与维护 ────
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
        LOGGER.warning("Backup error: %s", e)
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
        LOGGER.warning("VACUUM error: %s", e)
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
        LOGGER.warning("health error: %s", e)
    return out
