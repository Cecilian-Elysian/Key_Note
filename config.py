"""用户配置持久化,存到 config.json"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULTS = {
    "auto_start": False,
    "close_to_tray": True,
    "refresh_interval_sec": 5,
    "heatmap_days": 7,
    "rate_chart_hours": 24,
    "db_flush_batch_size": 200,
    "db_flush_interval_sec": 1.0,
    "db_retention_days": 7,
    "db_auto_backup_days": 7,
}


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
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )