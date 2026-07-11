"""pystray 系统托盘"""
import sys
import threading
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


def _icon_image() -> Image.Image:
    img = Image.new("RGB", (64, 64), (30, 144, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([12, 20, 52, 44], fill="white")
    return img


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


def start(window: "App") -> Icon:
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

    def _toggle_close_to_tray(_icon=None, _item=None):
        c = config.load()
        c["close_to_tray"] = not c.get("close_to_tray", True)
        config.save(c)
        if icon_ref["icon"]:
            icon_ref["icon"].update_menu()

    def _toggle_autostart(_icon=None, _item=None):
        c = config.load()
        c["auto_start"] = not c.get("auto_start", False)
        config.save(c)
        _set_autostart(c["auto_start"])
        if icon_ref["icon"]:
            icon_ref["icon"].update_menu()

    def _show_window(_icon, _item):
        try:
            window.after(0, window.show)
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
                            lambda _i, _it, d=d: _set_retention(d),
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
            Menu.SEPARATOR,
            MenuItem(
                lambda text: ("✓" if c.get("close_to_tray") else " ")
                + " 关闭窗口到托盘",
                _toggle_close_to_tray,
            ),
            MenuItem(
                lambda text: ("✓" if c.get("auto_start") else " ")
                + " 开机自启",
                _toggle_autostart,
            ),
            Menu.SEPARATOR,
            MenuItem("📊 数据管理", data_submenu),
            Menu.SEPARATOR,
            MenuItem("退出", _quit),
        )

    icon = Icon(APP_NAME, _icon_image(), "KeyNote 键盘记录", _make_menu())
    icon_ref["icon"] = icon
    threading.Thread(target=icon.run, daemon=True).start()
    return icon