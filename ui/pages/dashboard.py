"""仪表盘页面:4 个统计卡片 + 30 天迷你折线。"""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import db
import theme
from ui.pages.base import BasePage


class DashboardPage(BasePage):
    name = "dashboard"

    def _build(self) -> None:
        c = theme.current().colors

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(16, 8))
        grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="col")

        self._cards: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel]] = {}
        for col, (key, title) in enumerate(
            [
                ("today", "今日按键"),
                ("total", "累计按键"),
                ("streak", "连续天数"),
                ("db", "数据库"),
            ]
        ):
            card = ctk.CTkFrame(grid)
            card.grid(row=0, column=col, padx=6, pady=6, sticky="nsew")
            ctk.CTkLabel(
                card, text=title, font=("", 11), text_color=c.fg_muted
            ).pack(anchor="w", padx=14, pady=(12, 0))
            value = ctk.CTkLabel(
                card, text="—", font=("", 22, "bold"), text_color=c.fg_primary
            )
            value.pack(anchor="w", padx=14, pady=(2, 12))
            self._cards[key] = (card, value)

        spark_frame = ctk.CTkFrame(self)
        spark_frame.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        ctk.CTkLabel(
            spark_frame,
            text="过去 30 天每日按键",
            font=("", 12, "bold"),
            text_color=c.fg_primary,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 4))

        self._spark_fig = Figure(figsize=(9, 2.4), dpi=80, facecolor=c.chart_face)
        self._spark_canvas = FigureCanvasTkAgg(self._spark_fig, master=spark_frame)
        spark_widget = self._spark_canvas.get_tk_widget()
        spark_widget.pack(fill="both", expand=True, padx=8, pady=8)

        def _on_spark_resize(event, fig=self._spark_fig, canvas=self._spark_canvas):
            if event.width > 100 and event.height > 100:
                fig.set_size_inches(
                    event.width / fig.dpi - 0.2,
                    event.height / fig.dpi - 0.2,
                )
                canvas.draw_idle()

        spark_widget.bind("<Configure>", _on_spark_resize)

    def _do_refresh(self) -> None:
        today = db.count_today()
        total = db.count_total()
        streak = db.streak_days(365)
        h = db.health()
        size_mb = h.get("size_bytes", 0) / (1024 * 1024)

        self._cards["today"][1].configure(text=f"{today:,}")
        self._cards["total"][1].configure(text=f"{total:,}")
        self._cards["streak"][1].configure(text=f"{streak} 天")
        self._cards["db"][1].configure(text=f"{size_mb:.1f} MB")

        self._draw_spark()

    def _draw_spark(self) -> None:
        c = theme.current().colors
        self._spark_fig.clear()
        ax = self._spark_fig.add_subplot(111)
        rows = db.daily_counts(30)
        if rows:
            xs = [datetime.fromtimestamp(t / 1000) for t, _ in rows]
            ys = [cnt for _, cnt in rows]
            ax.fill_between(xs, ys, alpha=0.25, color=c.chart_line)
            ax.plot(xs, ys, color=c.chart_line, linewidth=1.5)
            ax.set_ylim(bottom=0)
        ax.set_facecolor(c.chart_face)
        ax.tick_params(colors=c.fg_muted, labelsize=8)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(True, alpha=0.15, color=c.fg_muted)
        self._spark_fig.tight_layout()
        self._spark_canvas.draw()

    def _do_apply_theme(self) -> None:
        c = theme.current().colors
        self._spark_fig.clear()
        self._draw_spark()