"""主窗口模块,400×550 固定尺寸 2 页布局(统计 / 键盘)+ 底部 tab bar 切换 + 顶部状态栏 + 自动刷新 + 闲置检测 + 设置回调"""
from __future__ import annotations

# ──── 字体适配 ────

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

from PIL import Image, ImageDraw

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


# ──── 顶部栏图标自绘 ────
def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _draw_pin_icon(colors, active: bool = False) -> Image.Image:
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fg = _hex_to_rgb(colors.accent if active else colors.fg_muted)
    d.ellipse([(9, 5), (17, 13)], fill=fg)
    d.line([(13, 13), (23, 23)], fill=fg, width=2)
    d.polygon([(21, 22), (26, 19), (25, 26)], fill=fg)
    return img


def _draw_gear_icon(colors) -> Image.Image:
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fg = _hex_to_rgb(colors.fg_muted)
    d.ellipse([(8, 8), (24, 24)], outline=fg, width=2)
    for x, y in [(16, 5), (16, 27), (5, 16), (27, 16)]:
        d.rectangle([(x-2, y-2), (x+2, y+2)], fill=fg)
    d.ellipse([(14, 14), (18, 18)], fill=fg)
    return img


# ──── 主窗口 ────
class App(ctk.CTk):
    PAGE_OVERVIEW = "overview"
    PAGE_KEYBOARD = "keyboard"

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
        try:
            self.attributes("-topmost", bool(self.cfg.get("window_topmost", False)))
        except Exception:
            pass

        plt.rcParams["font.sans-serif"] = [font or CJK_FONT, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        self._refresh_after_id: Optional[str] = None
        self._last_keypress_mono: float = 0.0
        self._was_paused_by_idle: bool = False

        self._pages: dict = {}
        self._current_page_name: str = ""
        self._current_page = None
        self._nav_buttons: dict = {}

        try:
            listener.register_activity_callback(self.on_keypress)
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self._switch_page(self.PAGE_OVERVIEW)
        self.refresh()
        self._schedule_auto_refresh()
        self.update_idletasks()
        self._hide_from_taskbar()
        self._apply_mouse_listener_setting()

    def _apply_mouse_listener_setting(self) -> None:
        """启动时按 config 应用鼠标监听状态。"""
        try:
            listener.apply_mouse_listener_enabled(
                bool(self.cfg.get("mouse_listener_enabled", True))
            )
        except Exception:
            pass

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
                    self._clamp_window_size()
                    return
                except Exception:
                    pass
        self.geometry("400x550")
        self.minsize(400, 550)
        self.maxsize(400, 550)

    def _clamp_window_size(self) -> None:
        """将窗口尺寸锁定到 400×550,保留原位置。"""
        try:
            self.maxsize(400, 550)
            self.minsize(400, 550)
            cur = self.geometry()
            plus_idx = cur.find("+")
            if plus_idx < 0:
                self.geometry("400x550")
                return
            rest = cur[plus_idx:]
            self.geometry(f"400x550{rest}")
        except Exception:
            pass

    def _hide_from_taskbar(self) -> None:
        try:
            import ctypes
            hwnd = self.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
            )
        except Exception:
            pass

    # ──── UI 构建(grid 三段) ────
    def _build_ui(self) -> None:
        c = theme.current().colors
        self.configure(fg_color=c.bg_primary)

        self.grid_rowconfigure(0, minsize=28)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, minsize=46)
        self.grid_columnconfigure(0, weight=1)

        # row 0: 顶栏
        top = ctk.CTkFrame(self, height=28, fg_color=c.bg_secondary)
        self._top = top
        top.grid(row=0, column=0, sticky="ew")
        top.pack_propagate(False)

        self.status_lbl = ctk.CTkLabel(
            top, text="●记录中", text_color=c.success, font=("", 11, "bold")
        )
        self.status_lbl.pack(side="left", padx=8)
        self.today_lbl = ctk.CTkLabel(
            top, text="今日: 0", text_color=c.fg_primary, font=("", 10)
        )
        self.today_lbl.pack(side="left", padx=6)

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="right", padx=4)

        self._pin_icon_normal = ctk.CTkImage(
            light_image=_draw_pin_icon(c, active=False),
            dark_image=_draw_pin_icon(c, active=False),
            size=(14, 14),
        )
        self._pin_icon_active = ctk.CTkImage(
            light_image=_draw_pin_icon(c, active=True),
            dark_image=_draw_pin_icon(c, active=True),
            size=(14, 14),
        )
        self._gear_icon = ctk.CTkImage(
            light_image=_draw_gear_icon(c),
            dark_image=_draw_gear_icon(c),
            size=(14, 14),
        )

        self._settings_btn = ctk.CTkButton(
            right, text="", image=self._gear_icon,
            width=26, height=22, corner_radius=6,
            fg_color="transparent", border_width=1, border_color=c.border,
            hover_color=c.bg_tertiary, command=self._open_settings,
        )
        self._settings_btn.pack(side="right", padx=(0, 4))

        self._pin_btn = ctk.CTkButton(
            right, text="", image=self._pin_icon_normal,
            width=26, height=22, corner_radius=6,
            fg_color="transparent", border_width=1, border_color=c.border,
            hover_color=c.bg_tertiary, command=self._toggle_topmost,
        )
        self._pin_btn.pack(side="right", padx=(0, 4))

        self._update_pin_btn()

        # row 1: body(当前页面)
        self._body = ctk.CTkFrame(self, fg_color=c.bg_primary)
        self._body.grid(row=1, column=0, sticky="nsew")

        from ui.pages.dashboard import OverviewPage
        from ui.pages.keyboard import KeyboardPage

        self._pages[self.PAGE_OVERVIEW] = OverviewPage(self._body, self)
        self._pages[self.PAGE_KEYBOARD] = KeyboardPage(self._body, self)

        # row 2: nav bar
        nav = ctk.CTkFrame(self, height=46, fg_color=c.bg_secondary)
        self._nav = nav
        nav.grid(row=2, column=0, sticky="ew")
        nav.grid_columnconfigure((0, 1), weight=1, uniform="nav")

        tabs = [(self.PAGE_OVERVIEW, "统计"), (self.PAGE_KEYBOARD, "键盘")]
        for col, (name, label) in enumerate(tabs):
            btn = ctk.CTkButton(
                nav, text=label,
                fg_color="transparent",
                text_color=c.fg_muted,
                hover_color=c.bg_tertiary,
                font=("", 12, "bold"),
                corner_radius=0,
                border_width=0,
                border_color=c.border,
                command=lambda n=name: self._switch_page(n),
            )
            btn.grid(row=0, column=col, padx=0, pady=0, sticky="nsew")
            self._nav_buttons[name] = btn

    # ──── 页面切换 ────
    def _switch_page(self, name: str) -> None:
        if not name or name not in self._pages:
            return
        if name == self._current_page_name and self._current_page is not None:
            return
        if self._current_page is not None:
            try:
                self._current_page.pack_forget()
            except Exception:
                pass
        page = self._pages[name]
        try:
            page.ensure_built()
            page.pack(in_=self._body, fill="both", expand=True)
            page.refresh()
        except Exception:
            pass
        self._current_page = page
        self._current_page_name = name
        self._update_nav_active(name)

    def _update_nav_active(self, name: str) -> None:
        c = theme.current().colors
        for n, btn in self._nav_buttons.items():
            is_active = (n == name)
            try:
                btn.configure(
                    text_color=(c.accent if is_active else c.fg_muted),
                    border_width=(2 if is_active else 0),
                    border_color=c.accent,
                )
            except Exception:
                pass

    def current_page_name(self) -> str:
        return self._current_page_name

    # ──── 状态栏 ────
    def refresh_status(self) -> None:
        c = theme.current().colors
        if listener.is_paused():
            self.status_lbl.configure(text="⏸ 已暂停", text_color=c.warning)
        else:
            self.status_lbl.configure(text="● 记录中", text_color=c.success)
        self.today_lbl.configure(text=f"今日: {db.count_today():,}", text_color=c.fg_primary)

    # ──── 刷新 / 自动刷新 ────
    def refresh(self) -> None:
        self.refresh_status()
        if self._current_page is not None:
            try:
                self._current_page.refresh()
            except Exception:
                pass

    def _auto_refresh(self) -> None:
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

    # ──── 顶部栏按钮动作 ────
    def _toggle_topmost(self) -> None:
        new_val = not bool(self.cfg.get("window_topmost", False))
        self.cfg["window_topmost"] = new_val
        try:
            self.attributes("-topmost", new_val)
        except Exception:
            pass
        self._update_pin_btn()
        try:
            cfg = config.load()
            cfg["window_topmost"] = new_val
            config.save(cfg)
        except Exception:
            pass

    def _update_pin_btn(self) -> None:
        c = theme.current().colors
        if self.cfg.get("window_topmost", False):
            self._pin_btn.configure(image=self._pin_icon_active, border_color=c.accent)
        else:
            self._pin_btn.configure(image=self._pin_icon_normal, border_color=c.border)

    def _redraw_icons(self) -> None:
        c = theme.current().colors
        self._pin_icon_normal = ctk.CTkImage(
            light_image=_draw_pin_icon(c, active=False),
            dark_image=_draw_pin_icon(c, active=False),
            size=(14, 14),
        )
        self._pin_icon_active = ctk.CTkImage(
            light_image=_draw_pin_icon(c, active=True),
            dark_image=_draw_pin_icon(c, active=True),
            size=(14, 14),
        )
        self._gear_icon = ctk.CTkImage(
            light_image=_draw_gear_icon(c),
            dark_image=_draw_gear_icon(c),
            size=(14, 14),
        )
        self._settings_btn.configure(image=self._gear_icon)
        self._update_pin_btn()

    def _open_settings(self) -> None:
        from settings_panel import open_or_focus

        open_or_focus(self, self.cfg, self._on_settings_changed)

    # ──── 设置变更处理 ────
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
        if bool(self.cfg.get("hide_tray_icon", False)) != bool(
            old.get("hide_tray_icon", False)
        ):
            try:
                if _tray is not None and hasattr(_tray, "set_visible"):
                    _tray.set_visible(not bool(self.cfg["hide_tray_icon"]))
            except Exception:
                pass
        if bool(self.cfg.get("mouse_listener_enabled", True)) != bool(
            old.get("mouse_listener_enabled", True)
        ):
            try:
                listener.apply_mouse_listener_enabled(
                    bool(self.cfg.get("mouse_listener_enabled", True))
                )
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
        if bool(self.cfg.get("window_topmost")) != bool(old.get("window_topmost", False)):
            try:
                self.attributes("-topmost", bool(self.cfg["window_topmost"]))
            except Exception:
                pass
            self._update_pin_btn()
        self.refresh()

    def _apply_theme_change(self, theme_name: str) -> None:
        theme.apply_theme(theme_name, root=self)
        c = theme.current().colors
        try:
            self.configure(fg_color=c.bg_primary)
            if hasattr(self, "_body") and self._body is not None:
                self._body.configure(fg_color=c.bg_primary)
            if hasattr(self, "_top") and self._top is not None:
                self._top.configure(fg_color=c.bg_secondary)
            if hasattr(self, "_nav") and self._nav is not None:
                self._nav.configure(fg_color=c.bg_secondary)
        except Exception:
            pass
        for page in self._pages.values():
            try:
                page.apply_theme()
            except Exception:
                pass
        try:
            self._redraw_icons()
        except Exception:
            pass
        try:
            self._update_pin_btn()
        except Exception:
            pass
        try:
            self._update_nav_active(self._current_page_name or self.PAGE_OVERVIEW)
        except Exception:
            pass
        try:
            panel = getattr(self, "_settings_panel", None)
            if panel is not None:
                try:
                    if panel.winfo_exists():
                        panel.apply_theme()
                except Exception:
                    pass
            else:
                win = getattr(self, "_settings_win", None)
                if win is not None:
                    try:
                        if win.winfo_exists():
                            for child in win.winfo_children():
                                if isinstance(child, ctk.CTkScrollableFrame) and hasattr(child, "apply_theme"):
                                    child.apply_theme()
                                    break
                    except Exception:
                        pass
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
