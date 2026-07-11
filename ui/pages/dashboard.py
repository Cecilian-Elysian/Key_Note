"""仪表盘页面:统计卡片 + GitHub 年历热力图。"""
from __future__ import annotations

import customtkinter as ctk

import db
import theme
from ui.pages.base import BasePage


class DashboardPage(BasePage):
    name = "dashboard"

    def _build(self) -> None:
        c = theme.current().colors

        self.configure(fg_color=c.bg_primary)

        grid = ctk.CTkFrame(self, fg_color=c.bg_primary)
        grid.pack(fill="x", padx=6, pady=(6, 4))
        grid.columnconfigure((0, 1), weight=1, uniform="col")
        grid.rowconfigure((0, 1), weight=1)

        self._cards: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel]] = {}
        items = [
            ("today", "今日按键"),
            ("total", "累计按键"),
            ("streak", "连续天数"),
            ("db", "数据库"),
        ]
        for idx, (key, title) in enumerate(items):
            row, col = divmod(idx, 2)
            card = ctk.CTkFrame(grid)
            card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            ctk.CTkLabel(
                card, text=title, font=("", 9), text_color=c.fg_muted
            ).pack(anchor="w", padx=8, pady=(6, 0))
            value = ctk.CTkLabel(
                card, text="—", font=("", 15, "bold"), text_color=c.fg_primary
            )
            value.pack(anchor="w", padx=8, pady=(2, 6))
            self._cards[key] = (card, value)

        from ui.widgets.gh_heatmap import GhHeatmapWidget

        self._heatmap = GhHeatmapWidget(self, days=365)
        self._heatmap.configure(fg_color=c.bg_primary)
        self._heatmap.pack(fill="both", expand=True, padx=4, pady=(2, 4))

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

        self._heatmap.refresh()

    def _do_apply_theme(self) -> None:
        self._heatmap.apply_theme()