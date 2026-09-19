"""按键排行页面(完整实现,未挂载到 App):Top N 按键次数横向条形图,使用 matplotlib 渲染。后续可作第 3 页候选恢复。"""
from __future__ import annotations

import matplotlib.pyplot as plt

import db
import theme
from ui.pages.base import BasePage
from ui.widgets.chart_utils import create_resizable_canvas, fit_canvas


class TopKeysPage(BasePage):
    name = "top_keys"

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
        plt.style.use(theme.current().plt_style)
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        data = db.top_keys(10)
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
                    fontsize=7,
                )
        ax.set_title("按键排行", color=c.fg_primary, fontsize=10)
        ax.set_xlabel("次数", color=c.fg_secondary, fontsize=8)
        ax.tick_params(colors=c.fg_muted, labelsize=7)
        ax.set_facecolor(c.chart_face)
        for spine in ax.spines.values():
            spine.set_color(c.border)
        self._fig.tight_layout()
        self._mpl_canvas.draw()

    def _do_apply_theme(self) -> None:
        c = theme.current().colors
        self._fig.set_facecolor(c.chart_face)
        self._do_refresh()
