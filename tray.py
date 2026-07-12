"""pystray 系统托盘模块,提供动态菜单(实时统计/暂停继续/数据管理/设置/退出)、开机自启注册、托盘图标显隐控制"""
import sys

# ──── 托盘图标 ────
import threading
import time
import winreg
from datetime import datetime
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw
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


def _icon_image(state: str = "active") -> Image.Image:
    palette = {
        "active": ((30, 144, 255), (255, 255, 255)),
        "paused": ((120, 120, 120), (200, 200, 200)),
        "idle":   ((255, 193, 7),   (255, 255, 255)),
    }
    bg, fg = palette.get(state, palette["active"])
    img = Image.new("RGB", (64, 64), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([12, 20, 52, 44], fill=fg)
    return img


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
        print(f"autostart err: {e}")


# ──── 设置窗口 ────
def _open_settings_toplevel(master):
    import customtkinter as ctk
    from settings_panel import SettingsPanel

    top = ctk.CTkToplevel(master)
    top.title("KeyNote 设置")
    top.geometry("400x480")
    top.resizable(False, False)
    panel = SettingsPanel(top, on_save_callback=master._on_settings_changed)
    panel.pack(fill="both", expand=True)
    panel.load_values(master.cfg)


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
        current_retention = int(c.get("db_retention_days", 7))

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
    threading.Thread(target=icon.run, daemon=True).start()
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
