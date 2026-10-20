"""pystray 系统托盘模块,提供动态菜单(实时统计/暂停继续/数据管理/设置/退出)、开机自启注册、托盘图标显隐控制"""
import sys

# ──── 托盘图标 ────
import threading
import time
import traceback
import winreg
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from pystray import Icon, Menu, MenuItem

import config
import db
import listener

if TYPE_CHECKING:
    from window import App

APP_NAME = "KeyNote"
KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

_RETENTION_OPTIONS = [("永久", 0), ("7 天", 7), ("180 天", 180), ("365 天", 365), ("730 天", 730)]

_icon: "Icon | None" = None
_window: "App | None" = None

_TINT_ACTIVE = (30, 144, 255)
_TINT_ALPHA = 0.3
_TRAY_SIZE = 64
_base_icon_cache: "Image.Image | None" = None


def _log_failure(prefix: str, e: BaseException) -> None:
    """stderr + crash.log 双通道记录异常,tray 子线程 / 自启失败统一走这里。"""
    try:
        sys.stderr.write(f"[{prefix}] {e}\n")
        sys.stderr.flush()
        log_path = Path(config.exe_dir()) / "keynote.crash.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{prefix}] {ts}\n")
            f.write("".join(traceback.format_exception(type(e), e, e.__traceback__)))
            f.write("\n")
    except Exception:
        pass


def _load_base_icon() -> Image.Image:
    """加载并缓存 icon.ico 为 64×64 RGBA 底图,供托盘 tint 叠加使用。"""
    global _base_icon_cache
    if _base_icon_cache is not None:
        return _base_icon_cache
    img = Image.open(str(config.icon_path())).convert("RGBA")
    img = img.resize((_TRAY_SIZE, _TRAY_SIZE), Image.LANCZOS)
    _base_icon_cache = img
    return img


def _icon_image() -> Image.Image:
    base = _load_base_icon()
    overlay = Image.new("RGBA", base.size, (*_TINT_ACTIVE, 0))
    overlay.putalpha(base.split()[3])
    return Image.blend(base, overlay, _TINT_ALPHA)


def notify(message: str, title: str = APP_NAME) -> None:
    """托盘气泡通知,图标未启动时静默忽略。"""
    if _icon is None:
        return
    try:
        _icon.notify(message, title)
    except Exception:
        pass


# ──── 开机自启 ────
def _set_autostart(enable: bool) -> None:
    if not sys.platform.startswith("win"):
        return
    if getattr(sys, "frozen", False):
        exe = f'"{sys.executable}"'
    else:
        exe = f'"{sys.executable}" "{__file__}"'
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as k:
            if enable:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, exe)
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
    except Exception as e:
        _log_failure("autostart", e)


# ──── 设置入口 ────
def _open_settings_toplevel(master):
    """打开设置:2026-10 侧边栏改版后设置为主窗口第 5 页,统一走页面导航。"""
    master._open_settings()


# ──── 菜单构建与启动 ────
def start(window: "App") -> Icon:
    global _icon, _window
    _window = window
    cfg = config.load()
    icon_ref: dict = {"icon": None}

    def _toggle_pause(_icon, _item):
        if listener.is_paused():
            listener.resume()
        else:
            listener.pause()
        try:
            window.after(0, window.refresh_status)
        except Exception:
            pass
        if icon_ref["icon"]:
            icon_ref["icon"].update_menu()

    def _show_window(_icon, _item):
        try:
            window.after(0, window.show)
        except Exception:
            pass

    def _open_settings(_icon, _item):
        try:
            window.after(0, lambda: _open_settings_toplevel(window))
        except Exception:
            pass

    def _quit(_icon, _item):
        try:
            window.after(0, window.quit_app)
        except Exception:
            pass
        if icon_ref["icon"]:
            icon_ref["icon"].stop()

    def _make_menu():
        c = config.load()
        h = db.health()
        size_mb = h.get("size_bytes", 0) / (1024 * 1024)
        last_backup_ts = h.get("last_backup_ts", 0)
        if last_backup_ts:
            last_bk = datetime.fromtimestamp(last_backup_ts).strftime("%m-%d %H:%M")
        else:
            last_bk = "从未"
        current_retention = int(c.get("db_retention_days", 365))

        def _retention_label(days: int) -> str:
            mark = "✓ " if current_retention == days else "  "
            label = next((n for n, d in _RETENTION_OPTIONS if d == days), str(days))
            return mark + label

        def _do_backup(_icon=None, _item=None):
            path = db.backup(manual=True)
            if icon_ref["icon"]:
                msg = f"已备份: {path.name}" if path else "备份失败"
                try:
                    icon_ref["icon"].notify(msg)
                except Exception:
                    pass

        def _do_vacuum(_icon=None, _item=None):
            ok = db.vacuum()
            if icon_ref["icon"]:
                try:
                    icon_ref["icon"].notify("VACUUM 完成" if ok else "VACUUM 失败")
                except Exception:
                    pass
                icon_ref["icon"].update_menu()

        def _set_retention(days: int):
            cc = config.load()
            cc["db_retention_days"] = days
            config.save(cc)
            db.set_retention_days(days)
            if icon_ref["icon"]:
                icon_ref["icon"].update_menu()

        def _make_retention_handler(days: int):
            def _h(_icon, _item):
                _set_retention(days)

            return _h

        def _streak_label(_text):
            return f"连续打卡: {db.streak_days(365)} 天"

        def _rate_1h_label(_text):
            rows = db.rate_series(1)
            total = sum(c for _, c in rows)
            avg = total / max(1, len(rows))
            return f"近 1h 平均: {avg:.1f}/分钟"

        realtime_submenu = Menu(
            MenuItem(
                lambda text: f"总按键: {db.count_total():,}",
                None,
                enabled=False,
            ),
            MenuItem(
                lambda text: f"今日: {db.count_today():,}",
                None,
                enabled=False,
            ),
            MenuItem(_streak_label, None, enabled=False),
            MenuItem(_rate_1h_label, None, enabled=False),
        )

        def _recent_bars():
            rows = db.rate_series(1)
            bucket = [0] * 5
            now_ms = int(time.time() * 1000)
            cutoff = now_ms - 5 * 60 * 1000
            for ts, c in rows:
                if ts < cutoff:
                    continue
                idx = min(4, max(0, (ts - cutoff) // 60000))
                bucket[4 - idx] += c
            peak = max(bucket) or 1
            glyphs = " ▁▂▃▄▅▆▇█"
            return "".join(glyphs[min(8, int((v / peak) * 8))] for v in bucket)

        recent_submenu = Menu(
            MenuItem(
                lambda text: f"最近 5 分钟: {_recent_bars()}",
                None,
                enabled=False,
            ),
            MenuItem(
                lambda text: f"当前状态: {'⏸ 暂停' if listener.is_paused() else '● 记录中'}",
                None,
                enabled=False,
            ),
        )

        data_submenu = Menu(
            MenuItem(
                lambda text: f"总按键: {db.count_total():,}",
                None,
                enabled=False,
            ),
            MenuItem(
                lambda text: f"原始记录: {h.get('raw_count', 0):,}",
                None,
                enabled=False,
            ),
            MenuItem(
                lambda text: f"数据库: {size_mb:.1f} MB",
                None,
                enabled=False,
            ),
            MenuItem(
                lambda text: f"上次备份: {last_bk}",
                None,
                enabled=False,
            ),
            Menu.SEPARATOR,
            MenuItem("💾 立即备份", _do_backup),
            MenuItem("🗜 立即 VACUUM", _do_vacuum),
            Menu.SEPARATOR,
            MenuItem(
                "保留 raw 数据",
                Menu(
                    *[
                        MenuItem(
                            lambda text, d=d: _retention_label(d),
                            _make_retention_handler(d),
                        )
                        for _, d in _RETENTION_OPTIONS
                    ],
                ),
            ),
        )

        return Menu(
            MenuItem("显示主窗口", _show_window, default=True),
            MenuItem(
                lambda text: "▶ 继续" if listener.is_paused() else "⏸ 暂停",
                _toggle_pause,
            ),
            MenuItem("⚙ 设置...", _open_settings),
            Menu.SEPARATOR,
            MenuItem("📈 实时统计", realtime_submenu),
            MenuItem("🕐 最近活动", recent_submenu),
            MenuItem("📊 数据管理", data_submenu),
            Menu.SEPARATOR,
            MenuItem("退出", _quit),
        )

    icon = Icon(APP_NAME, _icon_image(), "KeyNote 键盘记录", _make_menu())
    icon_ref["icon"] = icon
    _icon = icon

    def _icon_run_with_log():
        try:
            icon.run()
        except Exception as e:
            _log_failure("tray.icon.run", e)

    threading.Thread(target=_icon_run_with_log, daemon=True).start()
    return icon


# ──── 托盘显隐 ────
def set_visible(show: bool) -> None:
    """动态显示/隐藏托盘图标。"""
    global _icon
    if show:
        if _icon is None and _window is not None:
            start(_window)
    else:
        if _icon is not None:
            try:
                _icon.stop()
            except Exception:
                pass
            _icon = None
