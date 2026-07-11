"""按键排行页面:Top N 按键次数横向条形图。"""
from __future__ import annotations

import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import db
import theme
from ui.pages.base import BasePage


class TopKeysPage(BasePage):
    name = "top_keys"

    def _build(self) -> None:
        c = theme.current().colors
        self._fig = Figure(figsize=(9, 5), dpi=80, facecolor=c.chart_face)
        self._mpl_canvas = FigureCanvasTkAgg(self._fig, master=self)
        widget = self._mpl_canvas.get_tk_widget()
        widget.pack(fill="both", expand=True, padx=16, pady=16)

        def _on_resize(event, fig=self._fig, canvas=self._mpl_canvas):
            if event.width > 100 and event.height > 100:
                fig.set_size_inches(
                    event.width / fig.dpi - 0.4,
                    event.height / fig.dpi - 0.4,
                )
                canvas.draw_idle()

        widget.bind("<Configure>", _on_resize)

    def _do_refresh(self) -> None:
        c = theme.current().colors
        plt.style.use(theme.current().plt_style)
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        data = db.top_keys(20)
        if data:
            keys = [k for k, _ in data][::-1]
            counts = [cnt for _, cnt in data][::-1]
            bars = ax.barh(keys, counts, color=c.accent)
            for b, cnt in zip(bars, counts):
                ax.text(
                    b.get_width() + max(counts) * 0.01,
                    b.get_y() + b.get_height() / 2,
                    str(cnt),
                    va="center",
                    color=c.fg_primary,
                    fontsize=9,
                )
        ax.set_title("Top 20 按键排行", color=c.fg_primary, fontsize=12)
        ax.set_xlabel("次数", color=c.fg_secondary)
        ax.tick_params(colors=c.fg_muted)
        ax.set_facecolor(c.chart_face)
        for spine in ax.spines.values():
            spine.set_color(c.border)
        self._fig.tight_layout()
        self._mpl_canvas.draw()

    def _do_apply_theme(self) -> None:
        self._do_refresh()