"""后台页(Page 2):3 张紧凑副卡 + 7×24 小时活跃度热力图 + QWERTY 键盘热力图"""
from __future__ import annotations

import math
import tkinter as tk

import customtkinter as ctk

import db
import theme
from ui.pages.base import BasePage
from ui.widgets.chart_utils import CanvasTip


# ──── 页面专属调色板(与 dashboard.py 解耦) ────
_PALETTE: dict[str, str] = {
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
}


def _palette() -> dict[str, str]:
    return _PALETTE


# ──── QWERTY 键盘布局 ────
_KEY_ROWS = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
    ["z", "x", "c", "v", "b", "n", "m"],
]
_ROW_OFFSETS = [0.0, 0.5, 0.75, 1.25]
_KEY_SPACER_W = 5
_CN_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]


# ──── 颜色工具 ────
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
        s = getattr(self.app, "ui_scale", 1.0)
        self.configure(fg_color=p["bg"])
        self._tip = None
        self._h_layout = None
        self._h_grid = None
        self._kb_rects: list[tuple[str, int, int, int, int]] = []
        self._h_fp: bytes | None = None
        self._h_grid_data = None
        self._kb_fp: tuple | None = None
        self._sub_fp: tuple | None = None
        self._sub_last: tuple = (0, 0, 0)

        # ──── 顶紧凑副卡(3 张) ────
        self._sub: dict[str, ctk.CTkLabel] = {}
        sub_frame = ctk.CTkFrame(self, fg_color="transparent")
        sub_frame.pack(fill="x", padx=6, pady=(4, 2))
        sub_frame.columnconfigure((0, 1, 2), weight=1, uniform="sub")
        for idx, (key, title) in enumerate([
            ("total", "累计按键"),
            ("mouse", "鼠标点击"),
            ("active", "活跃天数"),
        ]):
            card = ctk.CTkFrame(sub_frame, fg_color=p["card_bg"], corner_radius=8)
            card.grid(row=0, column=idx, padx=3, pady=1, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=("", 9), text_color=p["fg_muted"]
                         ).pack(anchor="w", padx=8, pady=(3, 0))
            val = ctk.CTkLabel(card, text="—", font=("", 13, "bold"), text_color=p["fg_primary"])
            val.pack(anchor="w", padx=8, pady=(0, 3))
            self._sub[key] = val

        # ──── 7×24 小时热力图 ────
        h_card = ctk.CTkFrame(self, fg_color=p["card_bg"], corner_radius=10)
        h_card.pack(fill="x", padx=6, pady=(2, 2))
        h_head = ctk.CTkFrame(h_card, fg_color="transparent")
        h_head.pack(fill="x", padx=10, pady=(4, 0))
        self._h_title_lbl = ctk.CTkLabel(
            h_head, text="7×24 小时活跃度", font=("", 11), text_color=p["fg_primary"]
        )
        self._h_title_lbl.pack(side="left")
        self._h_summary_lbl = ctk.CTkLabel(
            h_head, text="", font=("", 9), text_color=p["fg_muted"]
        )
        self._h_summary_lbl.pack(side="right")
        self._h_canvas = tk.Canvas(
            h_card, bg=p["card_bg"], highlightthickness=0, height=round(127 * s)
        )
        self._h_canvas.pack(fill="x", padx=10, pady=(2, 6))
        self._h_canvas.bind("<Configure>", lambda _e: self._draw_hourly())
        self._h_canvas.bind("<Motion>", self._on_h_motion)
        self._h_canvas.bind("<Leave>", lambda _e: self._hide_tip())

        # ──── 键盘热力图 ────
        kb_card = ctk.CTkFrame(self, fg_color=p["card_bg"], corner_radius=10)
        kb_card.pack(fill="x", padx=6, pady=(2, 6))
        self._kb_card = kb_card
        kb_head = ctk.CTkFrame(kb_card, fg_color="transparent")
        kb_head.pack(fill="x", padx=10, pady=(4, 2))
        self._kb_title_lbl = ctk.CTkLabel(
            kb_head, text="按键分布热力图", font=("", 11), text_color=p["fg_primary"]
        )
        self._kb_title_lbl.pack(side="left")
        self._kb_legend = ctk.CTkLabel(
            kb_head, text="", font=("", 9), text_color=p["fg_muted"]
        )
        self._kb_legend.pack(side="right")

        self._kb_canvas = tk.Canvas(
            kb_card, bg=p["card_bg"], highlightthickness=0, height=round(184 * s)
        )
        self._kb_canvas.pack(fill="x", padx=10, pady=(0, 8))
        self._kb_canvas.bind("<Configure>", lambda _e: self._draw_keyboard())
        self._kb_canvas.bind("<Motion>", self._on_kb_motion)
        self._kb_canvas.bind("<Leave>", lambda _e: self._hide_tip())
        self._kb_counts: dict[str, int] = {}
        self._kb_max = 0

    # ──── 刷新(带数据指纹,无变化跳过重绘) ────
    def _do_refresh(self) -> None:
        try:
            sub = (db.count_total(), db.mouse_total(), db.daily_active_days(30))
            if sub != self._sub_fp:
                self._sub_fp = sub
                prev = self._sub_last
                self._sub_last = sub
                self.animate_number(self._sub["total"], prev[0], sub[0])
                self.animate_number(self._sub["mouse"], prev[1], sub[1])
                self.animate_number(self._sub["active"], prev[2], sub[2], suffix=" 天")
        except Exception:
            pass

        try:
            grid = db.heatmap_data(7)
            if grid is not None and grid.size > 0:
                fp = grid.tobytes()
                if fp != self._h_fp:
                    self._h_fp = fp
                    self._draw_hourly(grid)
        except Exception:
            pass

        try:
            rows = db.top_keys(5000)
            fp = tuple(rows)
            if fp != self._kb_fp:
                self._kb_fp = fp
                self._kb_counts = {k.lower(): c for k, c in rows}
                self._kb_max = max(self._kb_counts.values(), default=0)
                if self._kb_max > 0:
                    top_key = max(self._kb_counts.items(), key=lambda kv: kv[1])
                    self._kb_legend.configure(
                        text=f"最高: {top_key[0].upper()} × {top_key[1]:,}"
                    )
                else:
                    self._kb_legend.configure(text="")
                self._draw_keyboard()
        except Exception:
            pass

    # ──── 7×24 渲染 ────
    def _draw_hourly(self, grid=None) -> None:
        p = _palette()
        s = getattr(self.app, "ui_scale", 1.0)
        c = self._h_canvas
        self._h_layout = None
        self._h_grid = None
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 60 or h < 40:
            return
        c.delete("all")

        if grid is None:
            grid = self._h_grid_data
        if grid is None:
            try:
                grid = db.heatmap_data(7)
            except Exception:
                return
        self._h_grid_data = grid
        if grid is None or grid.size == 0:
            return

        peak = int(grid.max()) if grid.size else 0

        margin_x = round(24 * s)
        cols = 24
        rows = 7
        gap = 1
        pad_y = round(8 * s)
        label_h = round(12 * s)
        usable_w = max(round(40 * s), w - margin_x - 4)
        cell = max(round(10 * s), min(round(22 * s), (usable_w - (cols - 1) * gap) / cols))
        grid_w = cols * cell + (cols - 1) * gap
        grid_h = rows * cell + (rows - 1) * gap
        content_h = grid_h + 2 + label_h
        needed = int(content_h + pad_y * 2)
        if abs(h - needed) > 2:
            c.configure(height=needed)
        ox = margin_x + max(0, (usable_w - grid_w) / 2)
        oy = max(pad_y, (h - content_h) / 2)
        self._h_layout = (ox, oy, cell, cell, gap)
        self._h_grid = grid

        def _bucket(val: int) -> str:
            if val <= 0 or peak <= 0:
                return p["h_empty"]
            r = val / peak
            if r <= 0.25: return p["h_l1"]
            if r <= 0.50: return p["h_l2"]
            if r <= 0.75: return p["h_l3"]
            return p["h_l4"]

        for dow in range(rows):
            ty = oy + dow * (cell + gap) + cell / 2
            c.create_text(6, ty, text=_CN_WEEKDAYS[dow], anchor="w",
                          fill=p["fg_muted"], font=("", 9))
            for hour in range(cols):
                x1 = ox + hour * (cell + gap)
                y1 = oy + dow * (cell + gap)
                val = int(grid[dow, hour])
                c.create_rectangle(
                    x1, y1, x1 + cell, y1 + cell,
                    fill=_bucket(val), outline="", width=0,
                )

        for hr in (0, 6, 12, 18, 23):
            tx = ox + hr * (cell + gap) + cell / 2
            c.create_text(tx, oy + grid_h + 2, text=str(hr), anchor="n",
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
        s = getattr(self.app, "ui_scale", 1.0)
        c = self._kb_canvas
        c.delete("all")
        c.configure(bg=p["card_bg"])
        self._kb_rects = []
        w = c.winfo_width()
        if w < 50 or c.winfo_height() < 100:
            return

        gap = round(5 * s)
        max_cols = max(len(r) for r in _KEY_ROWS)
        cell_w = max(
            round(20 * s),
            min(round(30 * s), (w - round(8 * s) - (max_cols - 1) * gap) // max_cols),
        )
        cell_h = round(30 * s)
        grid_w = max_cols * cell_w + (max_cols - 1) * gap
        start_x = (w - grid_w) // 2

        base_rgb = theme.hex_to_rgb(p["key_empty"])
        peak_rgb = theme.hex_to_rgb(p["accent"])

        def color_for(key: str) -> str:
            count = self._kb_counts.get(key, 0)
            if self._kb_max <= 0 or count == 0:
                return p["key_empty"]
            t = math.pow(count / self._kb_max, 0.5)
            return _lerp_color(base_rgb, peak_rgb, t)

        y = round(8 * s)
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
                self._kb_rects.append((key, int(x0), int(y0), int(x1), int(y1)))
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
        self._kb_rects.append(("space", int(sx0), int(sy0), int(sx1), int(sy1)))

    # ──── canvas 悬停提示 ────
    def _show_tip(self, text: str, x: int, y: int) -> None:
        if self._tip is None:
            p = _palette()
            self._tip = CanvasTip(
                self, bg=p["card_bg"], fg=p["fg_primary"],
                border=p["key_border"], bold=False,
            )
        self._tip.show(text, x, y)

    def _hide_tip(self) -> None:
        if self._tip is not None:
            self._tip.hide()

    def _on_h_motion(self, event) -> None:
        layout = self._h_layout
        grid = self._h_grid
        if layout is None or grid is None:
            return
        ox, oy, cell_w, cell_h, gap = layout
        col = int((event.x - ox) // (cell_w + gap))
        row = int((event.y - oy) // (cell_h + gap))
        if not (0 <= col < 24 and 0 <= row < 7):
            self._hide_tip()
            return
        cell_x = ox + col * (cell_w + gap)
        cell_y = oy + row * (cell_h + gap)
        if event.x > cell_x + cell_w or event.y > cell_y + cell_h:
            self._hide_tip()
            return
        val = int(grid[row, col])
        self._show_tip(
            f"周{_CN_WEEKDAYS[row]} {col}:00 · {val:,} 按键",
            self._h_canvas.winfo_pointerx(), self._h_canvas.winfo_pointery(),
        )

    def _on_kb_motion(self, event) -> None:
        for key, x0, y0, x1, y1 in self._kb_rects:
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                count = int(self._kb_counts.get(key, 0))
                label = "Space" if key == "space" else key.upper()
                if self._kb_max > 0 and count > 0:
                    pct = round(count / self._kb_max * 100)
                    text = f"{label} · {count:,} 次 · 占峰值 {pct}%"
                else:
                    text = f"{label} · 0 次"
                self._show_tip(
                    text,
                    self._kb_canvas.winfo_pointerx(), self._kb_canvas.winfo_pointery(),
                )
                return
        self._hide_tip()

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
