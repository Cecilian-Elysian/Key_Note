"""主窗口模块,800×600 固定尺寸,左侧边栏导航(Fluent 药丸 + accent 竖条)+ 页面容器 + 通栏标题栏 + Mica 材质 + 自动刷新 + 闲置检测 + 设置回调"""
from __future__ import annotations

# ──── 字体适配 ────

from datetime import datetime
import sys
import tkinter as tk
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

# ──── 窗口尺寸(逻辑 px,DPI 缩放后为物理像素) ────
WIN_W = 800
WIN_H = 600
NAV_W = 160

# ──── Mica 材质(Win11 best-effort,异常/旧系统自动回退纯色;置 False 一键关闭) ────
MICA = True
MICA_MAGIC = "#1D1D1D"  # 透明键控色,与 bg_primary 仅差一档,文字抗锯齿边缘无色差


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
def _draw_pin_icon(colors, active: bool = False) -> Image.Image:
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fg = theme.hex_to_rgb(colors.accent if active else colors.fg_muted)
    d.ellipse([(9, 5), (17, 13)], fill=fg)
    d.line([(13, 13), (23, 23)], fill=fg, width=2)
    d.polygon([(21, 22), (26, 19), (25, 26)], fill=fg)
    return img


def _draw_gear_icon(colors) -> Image.Image:
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fg = theme.hex_to_rgb(colors.fg_muted)
    d.ellipse([(8, 8), (24, 24)], outline=fg, width=2)
    for x, y in [(16, 5), (16, 27), (5, 16), (27, 16)]:
        d.rectangle([(x-2, y-2), (x+2, y+2)], fill=fg)
    d.ellipse([(14, 14), (18, 18)], fill=fg)
    return img


def _draw_refresh_icon(colors) -> Image.Image:
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fg = theme.hex_to_rgb(colors.fg_muted)
    d.arc([(9, 9), (23, 23)], start=35, end=300, fill=fg, width=2)
    d.polygon([(22, 5), (25, 13), (16, 12)], fill=fg)
    return img


def _draw_nav_glyph(colors, char: str, tint: str = "") -> Image.Image:
    """Segoe Fluent/MDL2 字形渲染成 32×32 图标,tint 指定颜色,字体缺失时画圆点占位。"""
    from PIL import ImageFont

    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fg = theme.hex_to_rgb(tint or colors.fg_secondary)
    font = None
    for name in ("segfluent.ttf", "segmdl2.ttf"):
        try:
            font = ImageFont.truetype(name, 20)
            break
        except Exception:
            continue
    if font is not None:
        d.text((16, 17), char, font=font, fill=fg, anchor="mm")
    else:
        d.ellipse([(11, 11), (21, 21)], outline=fg, width=2)
    return img


def _draw_mouse_glyph(colors, tint: str) -> Image.Image:
    """手绘鼠标线稿(32×32):椭圆机身 + 中线 + 按键分割,PIL 兜底无对应 MDL2 字形。"""
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fg = theme.hex_to_rgb(tint)
    d.rounded_rectangle([(10, 4), (22, 28)], radius=6, outline=fg, width=2)
    d.line([(16, 8), (16, 15)], fill=fg, width=2)
    d.line([(10, 15), (22, 15)], fill=fg, width=2)
    return img


class _TopTip:
    """顶栏按钮悬停提示:隐藏式 Toplevel 单例 + 300ms 显示延迟防闪。"""

    def __init__(self, anchor, get_text) -> None:
        self._anchor = anchor
        self._get_text = get_text
        self._win = None
        self._lbl = None
        self._after_id: Optional[str] = None

    def schedule_show(self) -> None:
        self.hide()
        self._after_id = self._anchor.after(300, self._show)

    def hide(self) -> None:
        if self._after_id is not None:
            try:
                self._anchor.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._win is not None:
            try:
                self._win.withdraw()
            except Exception:
                pass

    def _show(self) -> None:
        self._after_id = None
        try:
            text = self._get_text()
            bx = self._anchor.winfo_rootx() + self._anchor.winfo_width() // 2
            by = self._anchor.winfo_rooty() + self._anchor.winfo_height() + 6
        except Exception:
            return
        try:
            if self._win is None:
                self._win = tk.Toplevel(self._anchor.winfo_toplevel())
                self._win.withdraw()
                self._win.overrideredirect(True)
                self._win.attributes("-topmost", True)
                c = theme.current().colors
                self._lbl = tk.Label(
                    self._win, bg=c.bg_tertiary, fg=c.fg_primary,
                    font=("", 10), padx=8, pady=3,
                    highlightthickness=1, highlightbackground=c.border,
                )
                self._lbl.pack()
            c = theme.current().colors
            self._lbl.configure(
                text=text, bg=c.bg_tertiary, fg=c.fg_primary,
                highlightbackground=c.border,
            )
            self._win.update_idletasks()
            w = self._win.winfo_reqwidth()
            sw = self._win.winfo_screenwidth()
            x = max(4, min(bx - w // 2, sw - w - 4))
            self._win.geometry(f"+{x}+{by}")
            self._win.deiconify()
        except Exception:
            pass


# ──── 主窗口 ────
class App(ctk.CTk):
    PAGE_OVERVIEW = "overview"
    PAGE_KEYBOARD = "keyboard"
    PAGE_HEATMAP = "heatmap"
    PAGE_TOP_KEYS = "top_keys"
    PAGE_SETTINGS = "settings"

    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        theme.apply_theme()

        # ──── DPI 缩放系数(逻辑 800×600 不变,物理像素按屏放大) ────
        self._ui_scale = 1.0
        try:
            self._ui_scale = max(
                1.0, float(ctk.ScalingTracker.get_window_scaling(self))
            )
        except Exception:
            pass

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
        self._enable_drag()
        self._bind_shortcuts()
        self._apply_mouse_listener_setting()
        self._set_window_icon()
        self._apply_backdrop()

    @property
    def ui_scale(self) -> float:
        """DPI 缩放系数,页面/组件的像素常量用它做屏幕适配。"""
        return self._ui_scale

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
        w = round(WIN_W * self._ui_scale)
        h = round(WIN_H * self._ui_scale)
        if cfg.get("remember_window_pos", True):
            geo = str(cfg.get("_window_geometry", "") or "")
            if geo:
                try:
                    self.geometry(geo)
                    self._clamp_window_size()
                    return
                except Exception:
                    pass
        self.geometry(f"{w}x{h}")
        self.minsize(w, h)
        self.maxsize(w, h)

    def _clamp_window_size(self) -> None:
        """将窗口尺寸锁定到逻辑 800×600(按 DPI 换算物理像素),保留原位置。"""
        w = round(WIN_W * self._ui_scale)
        h = round(WIN_H * self._ui_scale)
        try:
            self.maxsize(w, h)
            self.minsize(w, h)
            cur = self.geometry()
            plus_idx = cur.find("+")
            if plus_idx < 0:
                self.geometry(f"{w}x{h}")
                return
            rest = cur[plus_idx:]
            self.geometry(f"{w}x{h}{rest}")
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

    def _set_window_icon(self) -> None:
        try:
            self.iconbitmap(str(config.icon_path()))
        except Exception:
            pass

    # ──── Mica 材质(侧边栏/页面壳层键控透明,标题栏保不透明可拖拽) ────
    def _apply_backdrop(self) -> None:
        if not MICA:
            return
        try:
            import ctypes
            if sys.getwindowsversion().build < 22621:
                return
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            mica = ctypes.c_int(2)  # DWMSBT_MAINWINDOW
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 38, ctypes.byref(mica), 4
            ) != 0:
                return
            self.configure(fg_color=MICA_MAGIC)
            self.attributes("-transparentcolor", MICA_MAGIC)
            self._mica_on = True
            # 仅侧边栏窗格键控(NavigationView 观感):内容区保持实底,
            # 避免透明底按钮在 Mica 上留下实色块
            self._mica_tint(self._sidebar)
        except Exception:
            self._mica_on = False

    def _mica_tint(self, pane) -> None:
        """把侧边栏窗格染成键控色;窗格上的按钮一律实底近色,防按钮体点击穿透。"""
        solid = theme.current().colors.bg_primary

        def walk(w) -> None:
            for ch in w.winfo_children():
                cls = type(ch).__name__
                if "ScrollableFrame" in cls or isinstance(
                    ch, (tk.Canvas, ctk.CTkCanvas)
                ):
                    continue
                try:
                    fg = ch.cget("fg_color")
                    if isinstance(ch, ctk.CTkButton):
                        if fg == "transparent" or fg == solid:
                            ch.configure(fg_color=solid)
                    elif fg == solid:
                        ch.configure(fg_color=MICA_MAGIC)
                except Exception:
                    pass
                walk(ch)

        walk(pane)
        try:
            pane.configure(fg_color=MICA_MAGIC)
        except Exception:
            pass

    # ──── 窗口拖动(WS_EX_TOOLWINDOW 无标题栏,客户区整体拖) ────
    def _enable_drag(self) -> None:
        self._drag_offset = None
        self.bind("<Button-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_motion)
        self.bind("<ButtonRelease-1>", self._on_drag_end)

    def _on_drag_start(self, event) -> None:
        try:
            self._drag_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())
        except Exception:
            self._drag_offset = None

    def _on_drag_motion(self, event) -> None:
        if self._drag_offset is None:
            return
        try:
            self.geometry(f"+{event.x_root - self._drag_offset[0]}+{event.y_root - self._drag_offset[1]}")
        except Exception:
            pass

    def _on_drag_end(self, _event) -> None:
        self._drag_offset = None

    # ──── 窗口级快捷键 ────
    def _bind_shortcuts(self) -> None:
        """Alt+1~5 切页,Alt+P 切换置顶。"""
        self.bind("<Alt-Key-1>", lambda _e: self._switch_page(self.PAGE_OVERVIEW))
        self.bind("<Alt-Key-2>", lambda _e: self._switch_page(self.PAGE_KEYBOARD))
        self.bind("<Alt-Key-3>", lambda _e: self._switch_page(self.PAGE_HEATMAP))
        self.bind("<Alt-Key-4>", lambda _e: self._switch_page(self.PAGE_TOP_KEYS))
        self.bind("<Alt-Key-5>", lambda _e: self._switch_page(self.PAGE_SETTINGS))
        self.bind("<Alt-Key-p>", lambda _e: self._toggle_topmost())

    # ──── UI 构建(grid:标题栏通栏 / 左侧边栏 + 竖分隔线 + 内容区) ────
    def _build_ui(self) -> None:
        c = theme.current().colors
        s = self._ui_scale
        self.configure(fg_color=c.bg_primary)

        self.grid_rowconfigure(0, minsize=round(48 * s))
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, minsize=round(NAV_W * s))
        self.grid_columnconfigure(1, minsize=1)
        self.grid_columnconfigure(2, weight=1)

        # row 0: 通栏标题栏(Fluent 风格:标题 + 状态胶囊 / 右侧图标按钮)
        top = ctk.CTkFrame(self, height=round(48 * s), fg_color=c.bg_primary)
        self._top = top
        top.grid(row=0, column=0, columnspan=3, sticky="ew")
        top.pack_propagate(False)

        ctk.CTkFrame(top, height=1, fg_color=c.divider).pack(side="bottom", fill="x")

        ctk.CTkLabel(
            top, text="KeyNote", text_color=c.fg_primary, font=("", 13, "bold")
        ).pack(side="left", padx=(16, 10), pady=6)

        self._status_pill = ctk.CTkFrame(
            top, fg_color=c.bg_tertiary, corner_radius=theme.RADIUS["md"]
        )
        self._status_pill.pack(side="left", pady=6)
        self.status_lbl = ctk.CTkLabel(
            self._status_pill, text="● 记录中", text_color=c.success, font=("", 11)
        )
        self.status_lbl.pack(padx=8, pady=3)

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="right", padx=10, pady=6)

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
            width=28, height=26, corner_radius=theme.RADIUS["sm"],
            fg_color="transparent", border_width=0,
            hover_color=c.bg_tertiary, command=self._open_settings,
        )
        self._settings_btn.pack(side="right", padx=(0, 2))

        self._pin_btn = ctk.CTkButton(
            right, text="", image=self._pin_icon_normal,
            width=28, height=26, corner_radius=theme.RADIUS["sm"],
            fg_color="transparent", border_width=0,
            hover_color=c.bg_tertiary, command=self._toggle_topmost,
        )
        self._pin_btn.pack(side="right", padx=(0, 2))

        self.today_lbl = ctk.CTkLabel(
            right, text="今日 0", text_color=c.fg_secondary, font=("", 11)
        )
        self.today_lbl.pack(side="right", padx=(0, 10))

        self._update_pin_btn()

        self._gear_tip = _TopTip(self._settings_btn, lambda: "设置 (Alt+5)")
        self._pin_tip = _TopTip(
            self._pin_btn,
            lambda: ("已置顶 (Alt+P 取消)" if self.cfg.get("window_topmost", False)
                     else "窗口置顶 (Alt+P)"),
        )
        self._settings_btn.bind("<Enter>", lambda _e: self._gear_tip.schedule_show())
        self._settings_btn.bind("<Leave>", lambda _e: self._gear_tip.hide())
        self._pin_btn.bind("<Enter>", lambda _e: self._pin_tip.schedule_show())
        self._pin_btn.bind("<Leave>", lambda _e: self._pin_tip.hide())

        # col 0 row 1: 侧边栏导航
        sidebar = ctk.CTkFrame(self, fg_color=c.bg_primary)
        self._sidebar = sidebar
        sidebar.grid(row=1, column=0, sticky="nsew")

        # col 1 row 1: 侧边栏与内容区之间的竖分隔线
        ctk.CTkFrame(self, width=1, fg_color=c.divider).grid(
            row=1, column=1, sticky="ns"
        )

        # col 2 row 1: 内容区(当前页面)
        self._body = ctk.CTkFrame(self, fg_color=c.bg_primary)
        self._body.grid(row=1, column=2, sticky="nsew")

        from ui.pages.dashboard import OverviewPage
        from ui.pages.keyboard import KeyboardPage
        from ui.pages.heatmap import HeatmapPage
        from ui.pages.top_keys import TopKeysPage
        from ui.pages.settings import SettingsPage

        self._pages[self.PAGE_OVERVIEW] = OverviewPage(self._body, self)
        self._pages[self.PAGE_KEYBOARD] = KeyboardPage(self._body, self)
        self._pages[self.PAGE_HEATMAP] = HeatmapPage(self._body, self)
        self._pages[self.PAGE_TOP_KEYS] = TopKeysPage(self._body, self)
        self._pages[self.PAGE_SETTINGS] = SettingsPage(self._body, self)

        self._build_nav(sidebar)

    # ──── 侧边栏导航(药丸选中态 + 左缘 accent 竖条) ────
    def _build_nav(self, sidebar) -> None:
        c = theme.current().colors
        self._nav_icons: dict = {}
        items = (
            (self.PAGE_OVERVIEW, "统计", "\uE9D2"),
            (self.PAGE_KEYBOARD, "后台", "\uE765"),
            (self.PAGE_HEATMAP, "热力图", "\uE787"),
            (self.PAGE_TOP_KEYS, "常用按键", "\uE734"),
            (self.PAGE_SETTINGS, "设置", "\uE713"),
        )
        for name, label, char in items:
            icon = ctk.CTkImage(
                light_image=_draw_nav_glyph(c, char),
                dark_image=_draw_nav_glyph(c, char),
                size=(16, 16),
            )
            self._nav_icons[name] = icon
            btn = ctk.CTkButton(
                sidebar, text=label, image=icon, compound="left",
                anchor="w", border_spacing=10,
                height=36, corner_radius=theme.RADIUS["md"],
                fg_color=c.bg_primary, hover_color=c.bg_tertiary,
                text_color=c.fg_secondary, border_width=0,
                font=("", 13),
                command=lambda n=name: self._switch_page(n),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_buttons[name] = btn

        # 左缘 accent 竖条(选中项指示,首次布局完成后放置)
        self._nav_bar = ctk.CTkFrame(
            sidebar, width=3, height=20, corner_radius=2, fg_color=c.accent
        )

    def _move_nav_bar(self) -> None:
        btn = self._nav_buttons.get(self._current_page_name)
        bar = getattr(self, "_nav_bar", None)
        if btn is None or bar is None:
            return
        try:
            if btn.winfo_height() < 10:
                # 冷启动尚未完成布局:放置成功前每 50ms 重试
                self.after(50, self._move_nav_bar)
                return
            y = btn.winfo_y() + max(0, (btn.winfo_height() - 20) // 2)
            bar.place(in_=self._sidebar, x=0, y=y)
            bar.lift()
        except Exception:
            pass

    # ──── 页头刷新按钮图标(供各页面复用) ────
    def refresh_icon(self) -> ctk.CTkImage:
        """返回刷新图标(缓存),页面标题栏的刷新按钮直接引用。"""
        img = getattr(self, "_refresh_icon_img", None)
        if img is None:
            c = theme.current().colors
            img = ctk.CTkImage(
                light_image=_draw_refresh_icon(c),
                dark_image=_draw_refresh_icon(c),
                size=(14, 14),
            )
            self._refresh_icon_img = img
        return img

    def glyph_icon(self, char: str, tint: str, size: int = 22) -> ctk.CTkImage:
        """按颜色/尺寸渲染 MDL2 字形图标(KPI 卡/徽章用,带缓存);鼠标用手绘。"""
        cache = getattr(self, "_glyph_icon_cache", None)
        if cache is None:
            self._glyph_icon_cache = cache = {}
        key = (char, tint, size)
        if key not in cache:
            c = theme.current().colors
            if char == "mouse":
                pil = _draw_mouse_glyph(c, tint)
            else:
                pil = _draw_nav_glyph(c, char, tint=tint)
            img = ctk.CTkImage(
                light_image=pil, dark_image=pil, size=(size, size)
            )
            cache[key] = img
        return cache[key]

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
                    text_color=(c.fg_primary if is_active else c.fg_secondary),
                    # 未选中用实底近色而非 transparent:侧边栏在 Mica 下被键控,
                    # transparent 会让按钮体随底色一起点击穿透
                    fg_color=(c.bg_tertiary if is_active else c.bg_primary),
                )
            except Exception:
                pass
        self._move_nav_bar()

    def current_page_name(self) -> str:
        return self._current_page_name

    # ──── 状态栏 ────
    def refresh_status(self) -> None:
        c = theme.current().colors
        if listener.is_paused():
            self.status_lbl.configure(text="⏸ 已暂停", text_color=c.warning)
        else:
            self.status_lbl.configure(text="● 记录中", text_color=c.success)
        self.today_lbl.configure(
            text=f"今日 {db.count_today():,}", text_color=c.fg_secondary
        )

    # ──── 刷新 / 自动刷新 ────
    def refresh(self) -> None:
        self.refresh_status()
        # 设置页表单不参与 auto-refresh,避免覆盖用户正在编辑的值
        if (
            self._current_page is not None
            and self._current_page_name != self.PAGE_SETTINGS
        ):
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
            self._notify_close_hint_once()
            self.withdraw()
        else:
            self.quit_app()

    def _notify_close_hint_once(self) -> None:
        """首次关闭到托盘时弹气泡,避免用户以为程序退出。"""
        if getattr(self, "_close_hinted", False):
            return
        self._close_hinted = True
        try:
            if _tray is not None:
                _tray.notify("KeyNote 已最小化到托盘,点击托盘图标可重新打开")
        except Exception:
            pass

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
            self._pin_btn.configure(
                image=self._pin_icon_active, fg_color=c.bg_tertiary
            )
        else:
            self._pin_btn.configure(
                image=self._pin_icon_normal, fg_color="transparent"
            )

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
        self._refresh_icon_img = None
        self._settings_btn.configure(image=self._gear_icon)
        self._update_pin_btn()

    def _open_settings(self) -> None:
        """打开设置页:窗口隐藏时先唤起,再切到设置页(托盘/标题栏 ⚙ 共用)。"""
        try:
            if not self.winfo_viewable():
                self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass
        self._switch_page(self.PAGE_SETTINGS)

    # ──── 设置变更处理 ────
    def _on_settings_changed(self, new_cfg: dict) -> None:
        old = self.cfg
        self.cfg = dict(new_cfg)
        try:
            self.attributes("-alpha", float(self.cfg.get("window_alpha", 1.0)))
        except Exception:
            pass
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
