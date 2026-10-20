"""按键排行页面:Top 10 按键次数横向条形图(matplotlib,accent 配色 + 值标签 + 空状态)。
原为未挂载死代码,2026-10 随侧边栏改版挂载为第 4 页并 Fluent 化。"""
from __future__ import annotations

import customtkinter as ctk
import matplotlib.pyplot as plt

import db
import theme
from ui.pages.base import BasePage
from ui.widgets.chart_utils import create_resizable_canvas, fit_canvas


class TopKeysPage(BasePage):
    name = "top_keys"

    def _build(self) -> None:
        c = theme.current().colors
        self.configure(fg_color=c.bg_primary)

        # ──── 页头(固定):标题 + 副标题 / 刷新按钮 ────
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 0))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            titles, text="常用按键", font=theme.FONTS["page_title"],
            text_color=c.fg_primary,
        ).pack(anchor="w")
        self._sub = ctk.CTkLabel(
            titles, text="按键次数排行 · Top 10", font=theme.FONTS["label"],
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

        # ──── 排行卡 ────
        card = ctk.CTkFrame(
            self, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        card.pack(fill="both", expand=True, padx=16, pady=(10, 16))

        card_head = ctk.CTkFrame(card, fg_color="transparent")
        card_head.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(
            card_head, text="Top 10 按键", font=theme.FONTS["card_title"],
            text_color=c.fg_primary,
        ).pack(side="left")
        self._summary = ctk.CTkLabel(
            card_head, text="", font=theme.FONTS["caption"], text_color=c.fg_muted
        )
        self._summary.pack(side="right")

        self._fig, self._mpl_canvas = create_resizable_canvas(
            card, initial_size=(6.4, 4.0), dpi=72,
            fg_color=c.chart_face, padx=12, pady=(4, 12),
        )
        self._fig.patch.set_facecolor(c.chart_face)

    def _do_refresh(self) -> None:
        c = theme.current().colors
        self._fig.set_facecolor(c.chart_face)
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        data = db.top_keys(10)
        if data:
            top_key, top_cnt = data[0]
            self._summary.configure(text=f"最高 {top_key} × {top_cnt:,}")
            keys = [k for k, _ in data][::-1]
            counts = [cnt for _, cnt in data][::-1]
            bars = ax.barh(keys, counts, color=c.accent, height=0.62)
            mx = max(counts)
            for b, cnt in zip(bars, counts):
                ax.text(
                    b.get_width() + mx * 0.015,
                    b.get_y() + b.get_height() / 2,
                    f"{cnt:,}",
                    va="center",
                    color=c.fg_secondary,
                    fontsize=8,
                )
            ax.set_xlim(0, mx * 1.14)
        else:
            # ──── 空态三段式:图标 + 主文案 + 说明(vigil-watt 空态同构) ────
            self._summary.configure(text="")
            ax.text(
                0.5, 0.62, "\uE787",
                transform=ax.transAxes, ha="center", va="center",
                color=c.fg_muted, fontsize=22, fontfamily="Segoe MDL2 Assets",
            )
            ax.text(
                0.5, 0.42, "还没有记录",
                transform=ax.transAxes, ha="center", va="center",
                color=c.fg_secondary, fontsize=12,
            )
            ax.text(
                0.5, 0.28, "开始打字后,这里会按次数排出 Top 10",
                transform=ax.transAxes, ha="center", va="center",
                color=c.fg_muted, fontsize=10,
            )
            ax.set_axis_off()
        ax.set_facecolor(c.chart_face)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=c.fg_muted, labelsize=8, length=0)
        for lbl in ax.get_yticklabels():
            lbl.set_color(c.fg_secondary)
        self._fig.tight_layout()
        fit_canvas(self._fig, self._mpl_canvas)
        self._mpl_canvas.draw()

    def _do_apply_theme(self) -> None:
        c = theme.current().colors
        self._fig.patch.set_facecolor(c.chart_face)
        self._do_refresh()
