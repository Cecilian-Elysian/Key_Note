"""[死代码] 速率图页面,每分钟按键数随时间变化的折线图,使用 matplotlib 渲染"""
from __future__ import annotations

from datetime import datetime

import matplotlib.pyplot as plt

import db
import theme
from ui.pages.base import BasePage
from ui.widgets.chart_utils import create_resizable_canvas, fit_canvas


class RatePage(BasePage):
    name = "rate"

    def _build(self) -> None:
        c = theme.current().colors
        self._fig, self._mpl_canvas = create_resizable_canvas(
            self,
            initial_size=(8, 4.5),
            dpi=72,
            margin=0.08,
            padx=4,
            pady=4,
        )
        self._fig.set_facecolor(c.chart_face)

    def _do_refresh(self) -> None:
        fit_canvas(self._fig, self._mpl_canvas)
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
            fontsize=10,
        )
        ax.set_xlabel("时间", color=c.fg_secondary, fontsize=8)
        ax.set_ylabel("按键/分钟", color=c.fg_secondary, fontsize=8)
        ax.tick_params(colors=c.fg_muted, labelsize=7)
        ax.grid(True, alpha=0.2)
        ax.set_facecolor(c.chart_face)
        self._fig.autofmt_xdate()
        self._fig.tight_layout(pad=0.3)
        self._mpl_canvas.draw()

    def _do_apply_theme(self) -> None:
        c = theme.current().colors
        self._fig.set_facecolor(c.chart_face)
        self._do_refresh()
