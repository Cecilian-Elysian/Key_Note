"""仪表盘页面,程序唯一激活页面:顶部三张统计卡(今日/周/月)、30 天按键趋势折线图、年度 GitHub 风格热力图、键盘分布热力图"""
from __future__ import annotations

import math
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

import db
import theme
from ui.pages.base import BasePage


_BG = "#0B1120"
_CARD_BG = "#1A1F2C"
_ACCENT = "#FF5722"
_ACCENT_GLOW = "#FF7043"
_FG_PRIMARY = "#E2E8F0"
_FG_MUTED = "#64748B"
_KEY_BORDER = "#2D3748"
_KEY_EMPTY = "#1E293B"


_KEY_ROWS = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
    ["z", "x", "c", "v", "b", "n", "m"],
]
_ROW_OFFSETS = [0.0, 0.5, 0.75, 1.25]  # left edge offset as fraction of (cell_w+gap)
_KEY_SPACER_W = 6  # 6 cells wide for the space bar


def _hex_to_rgb(hx: str) -> tuple:
    hx = hx.lstrip("#")
    return (int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16))


def _lerp_color(c0: tuple, c1: tuple, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r = round(c0[0] + (c1[0] - c0[0]) * t)
    g = round(c0[1] + (c1[1] - c0[1]) * t)
    b = round(c0[2] + (c1[2] - c0[2]) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


class DashboardPage(BasePage):
    name = "dashboard"

    def _build(self) -> None:
        self.configure(fg_color=_BG)

        scroll = ctk.CTkScrollableFrame(self, fg_color=_BG)
        scroll.pack(fill="both", expand=True)
        self._scroll = scroll
        self._scroll._parent_canvas.bind(
            "<MouseWheel>", self._on_mousewheel, add="+"
        )

        self._cards: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel]] = {}
        top = ctk.CTkFrame(scroll, fg_color="transparent")
        top.pack(fill="x", padx=6, pady=(8, 4))
        top.columnconfigure((0, 1, 2), weight=1, uniform="col")
        for idx, (key, title) in enumerate([
            ("today", "今日"),
            ("week", "近 7 天"),
            ("month", "近 30 天"),
        ]):
            card = ctk.CTkFrame(top, fg_color=_CARD_BG, corner_radius=10)
            card.grid(row=0, column=idx, padx=4, pady=4, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=("", 9), text_color=_FG_MUTED
            ).pack(anchor="w", padx=10, pady=(8, 0))
            val = ctk.CTkLabel(
                card, text="—", font=("", 18, "bold"), text_color=_FG_PRIMARY
            )
            val.pack(anchor="w", padx=10, pady=(0, 8))
            self._cards[key] = (card, val)

        trend_card = ctk.CTkFrame(scroll, fg_color=_CARD_BG, corner_radius=10)
        trend_card.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(
            trend_card, text="近 30 天按键趋势", font=("", 11), text_color=_FG_PRIMARY
        ).pack(anchor="w", padx=10, pady=(6, 0))

        from ui.widgets.chart_utils import create_resizable_canvas

        self._trend_fig, self._trend_canvas = create_resizable_canvas(
            trend_card, initial_size=(6.0, 1.8), dpi=72, fg_color=_CARD_BG
        )
        self._trend_ax = self._trend_fig.add_subplot(111)

        self._side_cards: dict[str, ctk.CTkLabel] = {}
        side = ctk.CTkFrame(scroll, fg_color="transparent")
        side.pack(fill="x", padx=6, pady=4)
        side.columnconfigure((0, 1, 2), weight=1, uniform="col")
        for idx, (key, title) in enumerate([
            ("total", "累计按键"),
            ("peak", "单日峰值"),
            ("active", "活跃天数"),
        ]):
            card = ctk.CTkFrame(side, fg_color=_CARD_BG, corner_radius=10)
            card.grid(row=0, column=idx, padx=4, pady=4, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=("", 9), text_color=_FG_MUTED
            ).pack(anchor="w", padx=10, pady=(8, 0))
            val = ctk.CTkLabel(
                card, text="—", font=("", 13, "bold"), text_color=_FG_PRIMARY
            )
            val.pack(anchor="w", padx=10, pady=(0, 8))
            self._side_cards[key] = val

        from ui.widgets.gh_heatmap import GhHeatmapWidget

        self._heatmap = GhHeatmapWidget(scroll, days=365)
        self._heatmap.configure(fg_color=_BG)
        self._heatmap.pack(fill="x", padx=4, pady=(4, 8))

        kb_card = ctk.CTkFrame(scroll, fg_color=_CARD_BG, corner_radius=10)
        kb_card.pack(fill="x", padx=6, pady=(4, 8))
        kb_head = ctk.CTkFrame(kb_card, fg_color="transparent")
        kb_head.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(
            kb_head, text="按键分布热力图", font=("", 11), text_color=_FG_PRIMARY
        ).pack(side="left")
        self._kb_legend = ctk.CTkLabel(
            kb_head, text="", font=("", 9), text_color=_FG_MUTED
        )
        self._kb_legend.pack(side="right")

        self._kb_canvas = tk.Canvas(
            kb_card, bg=_CARD_BG, highlightthickness=0, height=180,
        )
        self._kb_canvas.pack(fill="x", padx=10, pady=(0, 10))
        self._kb_canvas.bind("<Configure>", lambda _e: self._draw_keyboard())
        self._kb_counts: dict[str, int] = {}
        self._kb_max = 0

    def _on_mousewheel(self, event) -> str:
        delta = int(-1 * (event.delta / 120) * 3)
        self._scroll._parent_canvas.yview_scroll(delta, "units")
        return "break"

    def _do_refresh(self) -> None:
        today = db.count_today()
        wk = db.daily_counts(7)
        mo = db.daily_counts(30)
        week_sum = sum(v for _, v in wk)
        month_sum = sum(v for _, v in mo)
        total = db.count_total()
        peak = max((v for _, v in mo), default=0)
        active = sum(1 for _, v in mo if v > 0)

        self._cards["today"][1].configure(text=f"{today:,}")
        self._cards["week"][1].configure(text=f"{week_sum:,}")
        self._cards["month"][1].configure(text=f"{month_sum:,}")
        self._side_cards["total"].configure(text=f"{total:,}")
        self._side_cards["peak"].configure(text=f"{peak:,}")
        self._side_cards["active"].configure(text=f"{active} 天")

        if mo:
            self._draw_trend(mo)
        self._heatmap.refresh()

        rows = db.top_keys(5000)
        self._kb_counts = {k.lower(): c for k, c in rows}
        self._kb_max = max(self._kb_counts.values(), default=0)
        if self._kb_max > 0:
            top_key = max(self._kb_counts.items(), key=lambda kv: kv[1])
            self._kb_legend.configure(
                text=f"最高: {top_key[0].upper()} × {top_key[1]:,}",
            )
        else:
            self._kb_legend.configure(text="")
        self._draw_keyboard()

    def _draw_trend(self, data: list) -> None:
        import matplotlib.pyplot as plt
        import numpy as np

        ax = self._trend_ax
        ax.clear()

        x = np.arange(len(data))
        y = np.array([v for _, v in data])

        for a in (0.02, 0.04, 0.06, 0.08, 0.10, 0.12):
            ax.fill_between(x, 0, y, alpha=a, color=_ACCENT)
        ax.plot(x, y, color=_ACCENT, linewidth=2)

        if len(y) > 0:
            pm = np.argmax(y)
            ax.scatter(pm, y[pm], s=50, color=_ACCENT_GLOW,
                       edgecolors=_ACCENT, linewidth=1.5, zorder=5)

        ax.set_facecolor(_CARD_BG)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=_FG_MUTED, labelsize=7)
        ax.grid(axis="y", color="#2D3748", linewidth=0.3)
        ax.set_xlim(-0.5, len(x) - 0.5)
        if y.max() > 0:
            ax.set_ylim(0, y.max() * 1.15)

        labels = [""] * len(x)
        if len(x) > 1:
            labels[0] = datetime.fromtimestamp(data[0][0] / 1000).strftime("%m/%d")
            labels[-1] = datetime.fromtimestamp(data[-1][0] / 1000).strftime("%m/%d")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, ha="center")

        self._trend_canvas.draw_idle()

    def _draw_keyboard(self) -> None:
        c = self._kb_canvas
        c.delete("all")
        w = c.winfo_width()
        if w < 50:
            return

        gap = 4
        max_cols = max(len(r) for r in _KEY_ROWS)
        cell_w = max(28, (w - (max_cols - 1) * gap - 8) // max_cols)
        cell_h = 30
        grid_w = max_cols * cell_w + (max_cols - 1) * gap
        start_x = (w - grid_w) // 2

        base_rgb = _hex_to_rgb(_KEY_EMPTY)
        peak_rgb = _hex_to_rgb(_ACCENT)

        def color_for(key: str) -> str:
            count = self._kb_counts.get(key, 0)
            if self._kb_max <= 0 or count == 0:
                return _KEY_EMPTY
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
                    fill=fill, outline=_KEY_BORDER, width=1,
                )
                c.create_text(
                    (x0 + x1) // 2, (y0 + y1) // 2,
                    text=key.upper(), fill=_FG_PRIMARY, font=("", 10, "bold"),
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
            spc_fill = _KEY_EMPTY
        c.create_rectangle(
            sx0, sy0, sx1, sy1,
            fill=spc_fill, outline=_KEY_BORDER, width=1,
        )
        c.create_text(
            (sx0 + sx1) // 2, (sy0 + sy1) // 2,
            text="SPACE", fill=_FG_PRIMARY, font=("", 9, "bold"),
        )

    def _do_apply_theme(self) -> None:
        self._heatmap.apply_theme()
