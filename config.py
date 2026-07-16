"""用户配置持久化模块,从 config.json 加载/保存配置,定义所有配置项的默认值字典"""
import json
import os

# ──── 配置路径与默认值 ────
import sys
from pathlib import Path


_APP_SUBDIR = "KeyNote"


def _appdata_dir() -> Path:
    """返回 %LOCALAPPDATA%/KeyNote/(与安装器默认目录一致),目录不存在时惰性创建。"""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Local")
    p = Path(base) / _APP_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def exe_dir() -> Path:
    """返回数据目录。默认 %LOCALAPPDATA%/KeyNote/(与安装器默认目录一致),打包后回退到 exe 同目录(便携)。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Local")
    p = Path(base) / _APP_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def icon_path() -> Path:
    """返回 icon.ico 的运行时路径。开发模式 = 项目根目录,打包后 = sys._MEIPASS/。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "icon.ico"
    return Path(__file__).parent / "icon.ico"


CONFIG_PATH = exe_dir() / "config.json"

DEFAULTS = {
    "auto_start": False,
    "close_to_tray": True,
    "start_minimized": False,
    "listener_enabled": True,
    "idle_pause_min": 0,
    "theme": "dark",
    "font_family": "Microsoft YaHei UI",
    "window_alpha": 1.0,
    "remember_window_pos": True,
    "_window_geometry": "",
    "chart_auto_refresh": True,
    "refresh_interval_sec": 5,
    "heatmap_days": 365,
    "rate_chart_hours": 24,
    "db_retention_days": 365,
    "db_auto_backup_days": 7,
    "backup_keep_daily": 7,
    "backup_keep_weekly": 4,
    "db_flush_batch_size": 200,
    "db_flush_interval_sec": 1.0,
    "log_to_file": False,
    "silent_start": False,
    "hide_tray_icon": False,
    "window_topmost": False,
    "data_dir": "",
    "mouse_listener_enabled": True,
    "backup_dir": "",
}


# ──── 加载/保存 ────
def load() -> dict:
    if not CONFIG_PATH.exists():
        save(dict(DEFAULTS))
        return dict(DEFAULTS)
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = {**DEFAULTS, **cfg}
        for k in DEFAULTS:
            merged.setdefault(k, DEFAULTS[k])
        return merged
    except Exception:
        return dict(DEFAULTS)


def save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
