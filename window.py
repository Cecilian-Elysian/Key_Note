"""主窗口:仪表盘单页布局。"""
from __future__ import annotations

from datetime import datetime
from tkinter import font as tkfont
from typing import Optional

import customtkinter as ctk
import matplotlib.pyplot as plt

import config
import db
import listener
import theme

try:
    import tray as _tray
except Exception:
    _tray = None

CJK_FONT = "Microsoft YaHei"
CTK_FONT_CANDIDATES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans SC",
    "Arial",
)


def _pick_font() -> Optional[str]:
    try:
        available = set(tkfont.families())
    except Exception:
        return None
    for f in CTK_FONT_CANDIDATES:
        if f in available:
            return f
    return None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        theme.apply_theme(self.cfg.get("theme", "dark"))

        font = self._pick_app_font()
        if font:
            try:
                for n in ("TkDefaultFont", "TkTextFont", "TkHeadingFont"):
                    tkfont.nametofont(n).configure(family=font)
            except Exception:
                pass

        self.title("KeyNote")
        self._apply_geometry(self.cfg)
        try:
            self.attributes("-alpha", float(self.cfg.get("window_alpha", 1.0)))
        except Exception:
            pass

        plt.rcParams["font.sans-serif"] = [font or CJK_FONT, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        self._refresh_after_id: Optional[str] = None
        self._last_keypress_mono: float = 0.0
        self._was_paused_by_idle: bool = False
        try:
            listener.register_activity_callback(self.on_keypress)
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self.refresh()
        self._schedule_auto_refresh()

    def _pick_app_font(self) -> Optional[str]:
        candidate = str(self.cfg.get("font_family", "Microsoft YaHei UI"))
        if candidate == "System Default":
            candidate = _pick_font() or "Microsoft YaHei UI"
        try:
            available = set(tkfont.families())
        except Exception:
            return None
        if candidate in available:
            return candidate
        return _pick_font()

    def _apply_geometry(self, cfg: dict) -> None:
        if cfg.get("remember_window_pos", True):
            geo = str(cfg.get("_window_geometry", "") or "")
            if geo:
                try:
                    self.geometry(geo)
                    return
                except Exception:
                    pass
        self.geometry("400x500")
        self.minsize(380, 450)

    def _build_ui(self) -> None:
        c = theme.current().colors
        self.configure(fg_color=c.bg_primary)

        top = ctk.CTkFrame(self, height=28, fg_color=c.bg_secondary)
        top.pack(fill="x")
        top.pack_propagate(False)

        self.status_lbl = ctk.CTkLabel(
            top, text="●记录中", text_color=c.success, font=("", 11, "bold")
        )
        self.status_lbl.pack(side="left", padx=8)
        self.today_lbl = ctk.CTkLabel(top, text="今日: 0", text_color=c.fg_primary, font=("", 10))
        self.today_lbl.pack(side="left", padx=6)

        body = ctk.CTkFrame(self, fg_color=c.bg_primary)
        body.pack(fill="both", expand=True)

        from ui.pages.dashboard import DashboardPage

        self._dashboard = DashboardPage(body, self)
        self._dashboard.pack(fill="both", expand=True)
        self._dashboard.ensure_built()

    def _toggle(self):
        if listener.is_paused():
            listener.resume()
        else:
            listener.pause()
        self.refresh_status()

    def refresh_status(self) -> None:
        c = theme.current().colors
        if listener.is_paused():
            self.status_lbl.configure(text="⏸ 已暂停", text_color=c.warning)
        else:
            self.status_lbl.configure(text="● 记录中", text_color=c.success)
        self.today_lbl.configure(text=f"今日: {db.count_today():,}")

    def refresh(self) -> None:
        self.refresh_status()
        try:
            self._dashboard.refresh()
        except Exception:
            pass

    def _auto_refresh(self) -> None:
        if not listener.is_paused():
            self.refresh()
        self._check_idle()
        self._schedule_auto_refresh()

    def _schedule_auto_refresh(self) -> None:
        if getattr(self, "_refresh_after_id", None) is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except Exception:
                pass
            self._refresh_after_id = None
        if not self.cfg.get("chart_auto_refresh", True):
            return
        interval_ms = max(500, int(self.cfg.get("refresh_interval_sec", 5) * 1000))
        self._refresh_after_id = self.after(interval_ms, self._auto_refresh)

    def _check_idle(self) -> None:
        minutes = int(self.cfg.get("idle_pause_min", 0) or 0)
        if minutes <= 0:
            return
        if not self._last_keypress_mono:
            return
        try:
            import time as _t
            elapsed_min = (_t.monotonic() - self._last_keypress_mono) / 60.0
        except Exception:
            return
        if elapsed_min >= minutes:
            if not listener.is_paused():
                listener.pause()
                self._was_paused_by_idle = True
                self.refresh_status()
        else:
            if self._was_paused_by_idle and listener.is_paused():
                listener.resume()
                self._was_paused_by_idle = False
                self.refresh_status()

    def on_keypress(self) -> None:
        import time as _t
        self._last_keypress_mono = _t.monotonic()

    def _on_close(self) -> None:
        self._save_geometry()
        if self.cfg.get("close_to_tray", True):
            self.withdraw()
        else:
            self.quit_app()

    def _save_geometry(self) -> None:
        if not self.cfg.get("remember_window_pos", True):
            return
        try:
            geo = self.geometry()
            cfg = config.load()
            cfg["_window_geometry"] = geo
            config.save(cfg)
            self.cfg["_window_geometry"] = geo
        except Exception:
            pass

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()
        self.refresh()

    def _on_settings_changed(self, new_cfg: dict) -> None:
        old = self.cfg
        self.cfg = dict(new_cfg)
        try:
            self.attributes("-alpha", float(self.cfg.get("window_alpha", 1.0)))
        except Exception:
            pass
        theme_name = str(self.cfg.get("theme", "dark"))
        if theme_name != str(old.get("theme", "dark")):
            self._apply_theme_change(theme_name)
        if str(self.cfg.get("font_family", "")) != str(old.get("font_family", "")):
            self._apply_font_change()
        try:
            self._apply_geometry(self.cfg)
        except Exception:
            pass
        try:
            db.set_retention_days(int(self.cfg.get("db_retention_days", 365)))
        except Exception:
            pass
        try:
            db.apply_log_to_file(bool(self.cfg.get("log_to_file", False)))
        except Exception:
            pass
        if bool(self.cfg.get("auto_start")) != bool(old.get("auto_start", False)):
            try:
                if _tray is not None and hasattr(_tray, "_set_autostart"):
                    _tray._set_autostart(bool(self.cfg["auto_start"]))
            except Exception:
                pass
        if int(self.cfg.get("refresh_interval_sec", 5)) != int(
            old.get("refresh_interval_sec", 5)
        ) or bool(self.cfg.get("chart_auto_refresh", True)) != bool(
            old.get("chart_auto_refresh", True)
        ):
            self._schedule_auto_refresh()
        if (
            int(self.cfg.get("idle_pause_min", 0)) > 0
            and self._last_keypress_mono == 0.0
        ):
            import time as _t
            self._last_keypress_mono = _t.monotonic()
        self.refresh()

    def _apply_theme_change(self, theme_name: str) -> None:
        theme.apply_theme(theme_name)
        try:
            self._dashboard.apply_theme()
        except Exception:
            pass
        self.refresh()

    def _apply_font_change(self) -> None:
        font = self._pick_app_font()
        if not font:
            return
        try:
            for n in ("TkDefaultFont", "TkTextFont", "TkHeadingFont"):
                try:
                    tkfont.nametofont(n).configure(family=font)
                except Exception:
                    pass
        except Exception:
            pass
        plt.rcParams["font.sans-serif"] = [font, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        self.refresh()

    def quit_app(self) -> None:
        try:
            db.close()
        except Exception:
            pass
        try:
            self.quit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
