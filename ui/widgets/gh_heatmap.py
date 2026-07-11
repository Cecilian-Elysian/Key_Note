"""GitHub 风格年度贡献热力图组件。

53 周 × 7 天网格,5 档颜色渐变,显示月份标签和星期标签。
"""
from __future__ import annotations

import calendar

import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import db
import theme


_CN_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]


class GhHeatmapWidget(ctk.CTkFrame):
    def __init__(self, master, days: int = 365):
        super().__init__(master)
        self._days = days
        self._build()

    def _build(self) -> None:
        c = theme.current().colors

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(0, 4))
        self._title = ctk.CTkLabel(
            header,
            text=f"过去 {self._days} 天 · 每日按键贡献",
            font=("", 13, "bold"),
            text_color=c.fg_primary,
            anchor="w",
        )
        self._title.pack(side="left")
        self._summary = ctk.CTkLabel(
            header,
            text="",
            font=("", 11),
            text_color=c.fg_muted,
        )
        self._summary.pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self._fig = Figure(figsize=(11, 3.2), dpi=80, facecolor=c.chart_face)
        self._mpl_canvas = FigureCanvasTkAgg(self._fig, master=body)
        widget = self._mpl_canvas.get_tk_widget()
        widget.pack(fill="both", expand=True)

        def _on_resize(event, fig=self._fig, canvas=self._mpl_canvas):
            if event.width > 100 and event.height > 100:
                fig.set_size_inches(
                    event.width / fig.dpi - 0.4,
                    event.height / fig.dpi - 0.4,
                )
                canvas.draw_idle()

        widget.bind("<Configure>", _on_resize)

        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(
            legend,
            text="少",
            font=("", 10),
            text_color=c.fg_muted,
        ).pack(side="right", padx=(0, 4))
        for lvl in ("heatmap_empty", "heatmap_l1", "heatmap_l2", "heatmap_l3", "heatmap_l4"):
            sw = ctk.CTkFrame(
                legend,
                width=12,
                height=12,
                fg_color=getattr(c, lvl),
                corner_radius=2,
            )
            sw.pack(side="right", padx=1)
        ctk.CTkLabel(
            legend,
            text="多",
            font=("", 10),
            text_color=c.fg_muted,
        ).pack(side="right", padx=(0, 6))

        self.refresh()

    def refresh(self) -> None:
        grid, start_dt, end_dt = db.heatmap_yearly(self._days)
        total = int(grid.sum())
        active_days = int((grid > 0).sum())
        max_val = int(grid.max()) if grid.size else 0
        self._summary.configure(
            text=f"活跃 {active_days}/{self._days} 天 · 最高 {max_val} · 合计 {total:,}"
        )
        self._max_value = max(1, max_val)
        self._render_heatmap(grid, start_dt, end_dt)

    def _bucket_color(self, value: int, c) -> str:
        if value <= 0:
            return c.heatmap_empty
        levels = [c.heatmap_l1, c.heatmap_l2, c.heatmap_l3, c.heatmap_l4]
        ratio = min(1.0, value / self._max_value)
        idx = min(len(levels) - 1, int(ratio * len(levels)))
        return levels[idx]

    def _render_heatmap(self, grid, start_dt, end_dt) -> None:
        c = theme.current().colors
        plt.style.use(theme.current().plt_style)
        self._fig.clear()
        ax = self._fig.add_subplot(111)

        weeks = grid.shape[0]
        face = c.chart_face

        for w in range(weeks):
            for d in range(7):
                v = int(grid[w, d])
                color = self._bucket_color(v, c)
                ax.add_patch(
                    plt.Rectangle(
                        (w, d),
                        0.92,
                        0.92,
                        facecolor=color,
                        edgecolor=face,
                        linewidth=1.5,
                    )
                )

        ax.set_xlim(-0.5, weeks + 0.5)
        ax.set_ylim(-0.5, 7.5)
        ax.invert_yaxis()
        ax.set_aspect("equal")
        ax.set_yticks(range(7))
        ax.set_yticklabels(_CN_WEEKDAYS, color=c.fg_muted, fontsize=8)
        ax.set_xticks([])
        ax.set_facecolor(face)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(left=False, bottom=False)

        from datetime import timedelta
        month_starts = []
        for w in range(weeks):
            day_offset = w * 7
            try:
                dt = start_dt + timedelta(days=day_offset)
                if dt.day <= 7 and (not month_starts or dt.month != month_starts[-1][1]):
                    month_starts.append((w, dt.month))
            except Exception:
                pass

        for w, m in month_starts:
            ax.text(
                w,
                7.6,
                calendar.month_abbr[m],
                color=c.fg_muted,
                fontsize=8,
                ha="left",
                va="bottom",
            )

        self._fig.tight_layout(pad=0.4)
        self._mpl_canvas.draw()

    def apply_theme(self) -> None:
        self.refresh()