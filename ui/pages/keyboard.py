"""键盘页(Page 2):3 张紧凑副卡 + 7×24 小时活跃度热力图 + QWERTY 键盘热力图"""
from __future__ import annotations

import math
import tkinter as tk
from datetime import datetime, timedelta

import customtkinter as ctk

import db
import theme
from ui.pages.base import BasePage


# ──── 页面专属调色板(与 dashboard.py 解耦,跟主题走) ────
_PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "bg":          "#0B1120",
        "card_bg":     "#1A1F2C",
        "accent":      "#FF5722",
        "fg_primary":  "#E2E8F0",
        "fg_muted":    "#64748B",
        "key_border":  "#2D3748",
        "key_empty":   "#1E293B",
        "grid_line":   "#2D3748",
        "h_empty":     "#2b2b2b",
        "h_l1":        "#0e4429",
        "h_l2":        "#006d32",
        "h_l3":        "#26a641",
        "h_l4":        "#39d353",
    },
    "light": {
        "bg":          "#F8FAFC",
        "card_bg":     "#FFFFFF",
        "accent":      "#E65100",
        "fg_primary":  "#1E293B",
        "fg_muted":    "#94A3B8",
        "key_border":  "#CBD5E1",
        "key_empty":   "#E2E8F0",
        "grid_line":   "#CBD5E1",
        "h_empty":     "#ebedf0",
        "h_l1":        "#9be9a8",
        "h_l2":        "#40c463",
        "h_l3":        "#30a14e",
        "h_l4":        "#216e39",
    },
}


def _palette() -> dict[str, str]:
    name = theme.current().name
    return _PALETTES.get(name, _PALETTES["dark"])


# ──── QWERTY 键盘布局 ────
_KEY_ROWS = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
    ["z", "x", "c", "v", "b", "n", "m"],
]
_ROW_OFFSETS = [0.0, 0.5, 0.75, 1.25]
_KEY_SPACER_W = 6


# ──── 颜色工具 ────
def _hex_to_rgb(hx: str) -> tuple:
    hx = hx.lstrip("#")
    return (int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16))


def _lerp_color(c0: tuple, c1: tuple, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r = round(c0[0] + (c1[0] - c0[0]) * t)
    g = round(c0[1] + (c1[1] - c0[1]) * t)
    b = round(c0[2] + (c1[2] - c0[2]) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


class KeyboardPage(BasePage):
    name = "keyboard"

    def _build(self) -> None:
        p = _palette()
        self.configure(fg_color=p["bg"])

        # ──── 顶紧凑副卡(3 张) ────
        self._sub: dict[str, ctk.CTkLabel] = {}
        sub_frame = ctk.CTkFrame(self, fg_color="transparent")
        sub_frame.pack(fill="x", padx=6, pady=(8, 4))
        sub_frame.columnconfigure((0, 1, 2), weight=1, uniform="sub")
        for idx, (key, title) in enumerate([
            ("total", "累计按键"),
            ("mouse", "鼠标点击"),
            ("active", "活跃天数"),
        ]):
            card = ctk.CTkFrame(sub_frame, fg_color=p["card_bg"], corner_radius=8)
            card.grid(row=0, column=idx, padx=3, pady=2, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=("", 9), text_color=p["fg_muted"]
                         ).pack(anchor="w", padx=8, pady=(4, 0))
            val = ctk.CTkLabel(card, text="—", font=("", 13, "bold"), text_color=p["fg_primary"])
            val.pack(anchor="w", padx=8, pady=(0, 4))
            self._sub[key] = val

        # ──── 7×24 小时热力图 ────
        h_card = ctk.CTkFrame(self, fg_color=p["card_bg"], corner_radius=10)
        h_card.pack(fill="x", padx=6, pady=4)
        self._h_title_lbl = ctk.CTkLabel(
            h_card, text="7×24 小时活跃度", font=("", 11), text_color=p["fg_primary"]
        )
        self._h_title_lbl.pack(anchor="w", padx=10, pady=(6, 0))
        self._h_summary_lbl = ctk.CTkLabel(
            h_card, text="", font=("", 9), text_color=p["fg_muted"]
        )
        self._h_summary_lbl.pack(anchor="e", padx=10)
        self._h_canvas = tk.Canvas(
            h_card, bg=p["card_bg"], highlightthickness=0, height=130
        )
        self._h_canvas.pack(fill="x", padx=10, pady=(2, 8))
        self._h_canvas.bind("<Configure>", lambda _e: self._draw_hourly())

        # ──── 键盘热力图 ────
        kb_card = ctk.CTkFrame(self, fg_color=p["card_bg"], corner_radius=10)
        kb_card.pack(fill="x", padx=6, pady=(4, 8))
        self._kb_card = kb_card
        kb_head = ctk.CTkFrame(kb_card, fg_color="transparent")
        kb_head.pack(fill="x", padx=10, pady=(6, 2))
        self._kb_title_lbl = ctk.CTkLabel(
            kb_head, text="按键分布热力图", font=("", 11), text_color=p["fg_primary"]
        )
        self._kb_title_lbl.pack(side="left")
        self._kb_legend = ctk.CTkLabel(
            kb_head, text="", font=("", 9), text_color=p["fg_muted"]
        )
        self._kb_legend.pack(side="right")

        self._kb_canvas = tk.Canvas(
            kb_card, bg=p["card_bg"], highlightthickness=0, height=160
        )
        self._kb_canvas.pack(fill="x", padx=10, pady=(0, 10))
        self._kb_canvas.bind("<Configure>", lambda _e: self._draw_keyboard())
        self._kb_counts: dict[str, int] = {}
        self._kb_max = 0

    # ──── 副卡数据 ────
    def _refresh_sub(self) -> None:
        try:
            self._sub["total"].configure(text=f"{db.count_total():,}")
        except Exception:
            pass
        try:
            self._sub["mouse"].configure(text=f"{db.mouse_total():,}")
        except Exception:
            pass
        try:
            self._sub["active"].configure(text=f"{db.daily_active_days(30)} 天")
        except Exception:
            pass

    # ──── 7×24 渲染 ────
    def _draw_hourly(self) -> None:
        p = _palette()
        c = self._h_canvas
        c.delete("all")
        w = c.winfo_width()
        if w < 60:
            return
        h = int(c.winfo_height() or 130)

        try:
            grid = db.heatmap_data(7)
        except Exception:
            return
        if grid is None or grid.size == 0:
            return

        peak = int(grid.max()) if grid.size else 0

        margin_x = 28
        margin_top = 14
        margin_bottom = 16
        usable_w = max(40, w - margin_x - 6)
        usable_h = max(40, h - margin_top - margin_bottom)
        cols = 24
        rows = 7
        gap = 2
        cell_w = max(6, min(20, (usable_w - (cols - 1) * gap) / cols))
        cell_h = max(8, min(16, (usable_h - (rows - 1) * gap) / rows))
        grid_w = cols * cell_w + (cols - 1) * gap
        ox = margin_x + max(0, (usable_w - grid_w) / 2)
        oy = margin_top

        def _bucket(val: int) -> str:
            if val <= 0 or peak <= 0:
                return p["h_empty"]
            r = val / peak
            if r <= 0.25: return p["h_l1"]
            if r <= 0.50: return p["h_l2"]
            if r <= 0.75: return p["h_l3"]
            return p["h_l4"]

        _CN_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]
        for dow in range(rows):
            ty = oy + dow * (cell_h + gap) + cell_h / 2
            c.create_text(6, ty, text=_CN_WEEKDAYS[dow], anchor="w",
                          fill=p["fg_muted"], font=("", 9))
            for hour in range(cols):
                x1 = ox + hour * (cell_w + gap)
                y1 = oy + dow * (cell_h + gap)
                val = int(grid[dow, hour])
                c.create_rectangle(
                    x1, y1, x1 + cell_w, y1 + cell_h,
                    fill=_bucket(val), outline="", width=0,
                )

        for hr in (0, 6, 12, 18, 23):
            tx = ox + hr * (cell_w + gap) + cell_w / 2
            c.create_text(tx, oy + rows * (cell_h + gap) + 2, text=str(hr), anchor="n",
                          fill=p["fg_muted"], font=("", 8))

        try:
            total = int(grid.sum())
            active = int((grid > 0).sum())
            self._h_summary_lbl.configure(
                text=f"近 7 天 · 合计 {total:,} · 活跃 {active}/168 桶 · 峰值 {peak:,}"
            )
        except Exception:
            pass

    # ──── QWERTY 渲染 ────
    def _draw_keyboard(self) -> None:
        p = _palette()
        c = self._kb_canvas
        c.delete("all")
        c.configure(bg=p["card_bg"])
        w = c.winfo_width()
        if w < 50:
            return

        gap = 4
        max_cols = max(len(r) for r in _KEY_ROWS)
        cell_w = max(24, (w - (max_cols - 1) * gap - 8) // max_cols)
        cell_h = 28
        grid_w = max_cols * cell_w + (max_cols - 1) * gap
        start_x = (w - grid_w) // 2

        base_rgb = _hex_to_rgb(p["key_empty"])
        peak_rgb = _hex_to_rgb(p["accent"])

        def color_for(key: str) -> str:
            count = self._kb_counts.get(key, 0)
            if self._kb_max <= 0 or count == 0:
                return p["key_empty"]
            t = math.pow(count / self._kb_max, 0.5)
            return _lerp_color(base_rgb, peak_rgb, t)

        y = 8
        for row_idx, row in enumerate(_KEY_ROWS):
            ox = start_x + _ROW_OFFSETS[row_idx] * (cell_w + gap) / 2
            for k_idx, key in enumerate(row):
                x0 = ox + k_idx * (cell_w + gap)
                y0 = y
                x1 = x0 + cell_w
                y1 = y0 + cell_h
                fill = color_for(key)
                c.create_rectangle(
                    x0, y0, x1, y1,
                    fill=fill, outline=p["key_border"], width=1,
                )
                c.create_text(
                    (x0 + x1) // 2, (y0 + y1) // 2,
                    text=key.upper(), fill=p["fg_primary"], font=("", 10, "bold"),
                )
            y += cell_h + gap

        space_count = self._kb_counts.get("space", 0)
        space_w = cell_w * _KEY_SPACER_W + (_KEY_SPACER_W - 1) * gap
        sx0 = (w - space_w) // 2
        sx1 = sx0 + space_w
        sy0 = y
        sy1 = sy0 + cell_h
        if self._kb_max > 0 and space_count > 0:
            t = math.pow(space_count / self._kb_max, 0.5)
            spc_fill = _lerp_color(base_rgb, peak_rgb, t)
        else:
            spc_fill = p["key_empty"]
        c.create_rectangle(
            sx0, sy0, sx1, sy1,
            fill=spc_fill, outline=p["key_border"], width=1,
        )
        c.create_text(
            (sx0 + sx1) // 2, (sy0 + sy1) // 2,
            text="SPACE", fill=p["fg_primary"], font=("", 9, "bold"),
        )

    def _do_refresh(self) -> None:
        self._refresh_sub()
        self._draw_hourly()
        try:
            rows = db.top_keys(5000)
            self._kb_counts = {k.lower(): c for k, c in rows}
            self._kb_max = max(self._kb_counts.values(), default=0)
            if self._kb_max > 0:
                top_key = max(self._kb_counts.items(), key=lambda kv: kv[1])
                self._kb_legend.configure(
                    text=f"最高: {top_key[0].upper()} × {top_key[1]:,}"
                )
            else:
                self._kb_legend.configure(text="")
        except Exception:
            pass
        self._draw_keyboard()

    def _do_apply_theme(self) -> None:
        p = _palette()
        try:
            self.configure(fg_color=p["bg"])
            if hasattr(self, "_h_canvas"):
                self._h_canvas.configure(bg=p["card_bg"])
            if hasattr(self, "_kb_canvas"):
                self._kb_canvas.configure(bg=p["card_bg"])
            if hasattr(self, "_kb_card"):
                self._kb_card.configure(fg_color=p["card_bg"])
            self._kb_title_lbl.configure(text_color=p["fg_primary"])
            self._kb_legend.configure(text_color=p["fg_muted"])
            self._h_title_lbl.configure(text_color=p["fg_primary"])
            self._h_summary_lbl.configure(text_color=p["fg_muted"])
        except Exception:
            pass
        self._draw_hourly()
        self._draw_keyboard()
