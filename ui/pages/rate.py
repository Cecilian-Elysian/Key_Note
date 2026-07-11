"""速率图页面:每分钟按键数随时间变化。"""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import db
import theme
from ui.pages.base import BasePage


class RatePage(BasePage):
    name = "rate"

    def _build(self) -> None:
        c = theme.current().colors
        self._fig = Figure(figsize=(9, 5), dpi=80, facecolor=c.chart_face)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=16, pady=16)

    def _do_refresh(self) -> None:
        c = theme.current().colors
        cfg = self.app.cfg
        plt.style.use(theme.current().plt_style)
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        data = db.rate_series(cfg.get("rate_chart_hours", 24))
        if data:
            xs = [datetime.fromtimestamp(t / 1000) for t, _ in data]
            ys = [cnt for _, cnt in data]
            ax.plot(xs, ys, color=c.chart_line, linewidth=1.2)
            ax.fill_between(xs, ys, alpha=0.3, color=c.chart_line)
        ax.set_title(
            f"过去 {cfg.get('rate_chart_hours', 24)}h · 每分钟按键数",
            color=c.fg_primary,
            fontsize=12,
        )
        ax.set_xlabel("时间", color=c.fg_secondary)
        ax.set_ylabel("按键/分钟", color=c.fg_secondary)
        ax.tick_params(colors=c.fg_muted)
        ax.grid(True, alpha=0.2)
        ax.set_facecolor(c.chart_face)
        self._fig.autofmt_xdate()
        self._fig.tight_layout()
        self._canvas.draw()

    def _do_apply_theme(self) -> None:
        self._do_refresh()