"""年度热力图页面:4 张 KPI 统计卡(今日/7 日均/30 日均/累计)+ GitHub 风格年度热力图。
原为未挂载死代码,2026-10 随侧边栏改版挂载为第 3 页并 Fluent 化。"""
from __future__ import annotations

import customtkinter as ctk

import db
import theme
from ui.pages.base import BasePage


class HeatmapPage(BasePage):
    name = "heatmap"

    def _build(self) -> None:
        c = theme.current().colors
        self.configure(fg_color=c.bg_primary)

        # ──── 页头(固定):标题 + 副标题 / 刷新按钮 ────
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 0))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            titles, text="热力图", font=theme.FONTS["page_title"],
            text_color=c.fg_primary,
        ).pack(anchor="w")
        self._sub = ctk.CTkLabel(
            titles, text="", font=theme.FONTS["label"],
            text_color=c.fg_secondary, anchor="w",
        )
        self._sub.pack(anchor="w", pady=(2, 0))
        self._refresh_btn = ctk.CTkButton(
            head, text="刷新", image=self.app.refresh_icon(), compound="left",
            width=64, height=28, corner_radius=theme.RADIUS["md"],
            fg_color="transparent", border_width=0,
            hover_color=c.bg_tertiary, command=self._do_refresh,
        )
        self._refresh_btn.pack(side="right", pady=(2, 0))

        # ──── 4 张 KPI 统计卡(标签 / 数值 / 脚注三层) ────
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 8))
        row.columnconfigure((0, 1, 2, 3), weight=1, uniform="kpi")
        items = (
            ("today", "今日按键", "实时统计"),
            ("avg7", "7 日均", "近 7 天平均"),
            ("avg30", "30 日均", "近 30 天平均"),
            ("total", "累计按键", "全部历史"),
        )
        self._cards: dict = {}
        for idx, (key, label, foot) in enumerate(items):
            card = ctk.CTkFrame(
                row, fg_color=c.bg_secondary,
                corner_radius=theme.RADIUS["md"],
                border_width=1, border_color=c.border,
            )
            card.grid(row=0, column=idx, sticky="nsew", padx=(0, 8) if idx < 3 else 0)
            ctk.CTkLabel(
                card, text=label, font=theme.FONTS["label"],
                text_color=c.fg_secondary,
            ).pack(anchor="w", padx=12, pady=(10, 0))
            val = ctk.CTkLabel(
                card, text="—", font=theme.FONTS["kpi_value"],
                text_color=c.fg_primary,
            )
            val.pack(anchor="w", padx=12, pady=(2, 0))
            ctk.CTkLabel(
                card, text=foot, font=theme.FONTS["caption"],
                text_color=c.fg_muted,
            ).pack(anchor="w", padx=12, pady=(2, 10))
            self._cards[key] = val

        # ──── 年度热力图卡 ────
        from ui.widgets.gh_heatmap import GhHeatmapWidget

        card = ctk.CTkFrame(
            self, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        card.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._heatmap = GhHeatmapWidget(
            card, days=int(self.app.cfg.get("heatmap_days", 365))
        )
        self._heatmap.configure(fg_color="transparent")
        self._heatmap.pack(fill="both", expand=True, padx=10, pady=8)

    def _do_refresh(self) -> None:
        days = int(self.app.cfg.get("heatmap_days", 365))
        self._sub.configure(text=f"最近 {days} 天的按键分布")
        self._cards["today"].configure(text=f"{db.count_today():,}")
        self._cards["avg7"].configure(text=f"{db.daily_average(7):,}")
        self._cards["avg30"].configure(text=f"{db.daily_average(30):,}")
        self._cards["total"].configure(text=f"{db.count_total():,}")
        if hasattr(self, "_heatmap"):
            self._heatmap.refresh()

    def _do_apply_theme(self) -> None:
        c = theme.current().colors
        try:
            self.configure(fg_color=c.bg_primary)
        except Exception:
            pass
        if hasattr(self, "_heatmap"):
            self._heatmap.apply_theme()
