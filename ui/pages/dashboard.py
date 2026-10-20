"""统计页(Page 1):页头 + 时间范围筛选 + KPI 主卡 + 按键趋势折线 + 年度 GH 热力图"""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk
import numpy as np

import db
import theme
from ui.pages.base import BasePage
from ui.widgets.chart_utils import create_resizable_canvas, _sync_canvas_bg


class OverviewPage(BasePage):
    name = "overview"

    _STAT_OPTIONS = ["今日", "近 7 天", "近 30 天"]
    _STAT_KEYS = ["today", "week", "month"]

    # ──── 构建 ────
    def _build(self) -> None:
        c = theme.current().colors
        self.configure(fg_color=c.bg_primary)

        # ──── 页头(固定):标题 + 副标题 / 刷新按钮 ────
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 0))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        self._page_title = ctk.CTkLabel(
            titles, text="统计", font=theme.FONTS["page_title"], text_color=c.fg_primary
        )
        self._page_title.pack(anchor="w")
        self._page_sub = ctk.CTkLabel(
            titles, text="", font=theme.FONTS["label"],
            text_color=c.fg_secondary, anchor="w",
        )
        self._page_sub.pack(anchor="w", pady=(2, 0))
        self._refresh_btn = ctk.CTkButton(
            head, text="", image=self.app.refresh_icon(),
            width=28, height=28, corner_radius=theme.RADIUS["md"],
            fg_color="transparent", border_width=0,
            hover_color=c.bg_tertiary, command=self._on_refresh_click,
        )
        self._refresh_btn.pack(side="right", pady=(2, 0))

        # ──── 时间范围筛选(固定) ────
        seg = ctk.CTkSegmentedButton(
            self, values=self._STAT_OPTIONS,
            command=self._on_segment_change,
            font=theme.FONTS["label"],
            fg_color=c.bg_tertiary,
            selected_color=c.accent, selected_hover_color=c.accent_hover,
            unselected_color=c.bg_tertiary, unselected_hover_color=c.bg_tertiary,
            text_color=c.fg_primary,
        )
        seg.pack(fill="x", padx=16, pady=(10, 8))
        self._seg = seg
        self._stat_idx = 2
        self._trend_fp: tuple | None = None
        self._last_main_val = 0
        seg.set(self._STAT_OPTIONS[self._stat_idx])

        # ──── 滚动内容 ────
        scroll = ctk.CTkScrollableFrame(self, fg_color=c.bg_primary)
        scroll.pack(fill="both", expand=True)
        self._scroll = scroll
        self._scroll._parent_canvas.bind(
            "<MouseWheel>", self._on_mousewheel, add="+"
        )

        # ──── KPI 主卡:标签 / 数值 / 脚注 ────
        main_card = ctk.CTkFrame(
            scroll, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        main_card.pack(fill="x", padx=16, pady=(0, 10))
        self._main_card = main_card
        self._main_label = ctk.CTkLabel(
            main_card, text="今日按键", font=theme.FONTS["label"],
            text_color=c.fg_secondary, anchor="w",
        )
        self._main_label.pack(anchor="w", padx=16, pady=(12, 0))
        self._main_val = ctk.CTkLabel(
            main_card, text="—", font=theme.FONTS["hero_value"],
            text_color=c.fg_primary, anchor="w",
        )
        self._main_val.pack(anchor="w", padx=16, pady=(2, 0))
        self._main_sub = ctk.CTkLabel(
            main_card, text="", font=theme.FONTS["footnote"],
            text_color=c.fg_muted, anchor="w",
        )
        self._main_sub.pack(anchor="w", padx=16, pady=(2, 12))

        # ──── 趋势图卡 ────
        trend_card = ctk.CTkFrame(
            scroll, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        self._trend_card = trend_card
        trend_card.pack(fill="x", padx=16, pady=(0, 10))
        self._trend_title_lbl = ctk.CTkLabel(
            trend_card, text="近 30 天按键趋势",
            font=theme.FONTS["card_title"], text_color=c.fg_primary, anchor="w",
        )
        self._trend_title_lbl.pack(anchor="w", padx=16, pady=(12, 0))

        self._trend_fig, self._trend_canvas = create_resizable_canvas(
            trend_card, initial_size=(6.0, 1.8), dpi=72,
            fg_color=c.chart_face, padx=10, pady=(4, 12),
        )
        self._trend_fig.patch.set_facecolor(c.chart_face)
        self._trend_ax = self._trend_fig.add_subplot(111)
        self._trend_ax.set_facecolor(c.chart_face)

        # ──── GH 年度热力图卡 ────
        from ui.widgets.gh_heatmap import GhHeatmapWidget

        heat_card = ctk.CTkFrame(
            scroll, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        heat_card.pack(fill="x", padx=16, pady=(0, 16))
        self._heat_card = heat_card
        self._heatmap = GhHeatmapWidget(
            heat_card, days=int(self.app.cfg.get("heatmap_days", 365))
        )
        self._heatmap.configure(fg_color="transparent")
        self._heatmap.pack(fill="x", padx=10, pady=8)

        self._refresh_from_idx()

    # ──── 交互 ────
    def _on_refresh_click(self) -> None:
        try:
            self.app.refresh()
        except Exception:
            pass

    def _on_segment_change(self, value: str) -> None:
        try:
            self._stat_idx = self._STAT_OPTIONS.index(value)
        except ValueError:
            self._stat_idx = 2
        self._refresh_from_idx()

    def _yesterday_compare(self) -> tuple[str, str]:
        """今日 vs 昨日按键对比 → (脚注文本, 颜色);昨日无数据则回退空脚注。"""
        c = theme.current().colors
        try:
            t0 = int(
                datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                ).timestamp() * 1000
            )
            by_day = dict(db.daily_counts(2))
            y_cnt = int(by_day.get(t0 - 86_400_000, 0))
            t_cnt = int(by_day.get(t0, 0))
        except Exception:
            return "", c.fg_muted
        if y_cnt <= 0:
            return "", c.fg_muted
        pct = (t_cnt - y_cnt) / y_cnt * 100
        if pct > 0.5:
            return f"较昨日 +{pct:.0f}%", c.success
        if pct < -0.5:
            return f"较昨日 −{abs(pct):.0f}%", c.danger
        return "与昨日持平", c.fg_muted

    # ──── 数据刷新 ────
    def _refresh_from_idx(self) -> None:
        if not self._built:
            return
        idx = self._stat_idx
        key = self._STAT_KEYS[idx]
        label = self._STAT_OPTIONS[idx]

        if key == "today":
            val = db.count_today()
            data = db.hourly_today()
            title = "今日按键趋势(逐时)"
        elif key == "week":
            rows = db.daily_counts(7)
            val = sum(cnt for _, cnt in rows)
            data = rows
            title = "近 7 天按键趋势"
        else:
            rows = db.daily_counts(30)
            val = sum(cnt for _, cnt in rows)
            data = rows
            title = "近 30 天按键趋势"

        fp = (key, val, tuple(data))
        if fp != self._trend_fp:
            self._trend_fp = fp

            prev = self._last_main_val
            self._last_main_val = val
            try:
                if prev == val:
                    self._main_val.configure(text=f"{val:,}" if val else "—")
                else:
                    self.animate_number(self._main_val, prev, val, zero_text="—")
            except Exception:
                pass

            try:
                self._main_label.configure(text=f"{label}按键")
                if key == "today":
                    sub_text, sub_color = self._yesterday_compare()
                else:
                    sub_text = f"日均 {db.daily_average(7 if key == 'week' else 30):,} 次"
                    sub_color = theme.current().colors.fg_muted
                self._main_sub.configure(text=sub_text, text_color=sub_color)
            except Exception:
                pass

            try:
                self._trend_title_lbl.configure(text=title)
                self._draw_trend(data, key)
            except Exception:
                pass

        try:
            self._update_page_sub()
        except Exception:
            pass

        try:
            self._heatmap.refresh()
        except Exception:
            pass

    def _update_page_sub(self) -> None:
        """页头副标题:连续记录天数。"""
        try:
            streak = int(db.streak_days(365))
        except Exception:
            streak = 0
        text = f"已连续记录 {streak} 天" if streak > 0 else "暂无历史记录"
        try:
            self._page_sub.configure(text=text)
        except Exception:
            pass

    def _do_refresh(self) -> None:
        self._refresh_from_idx()

    def _on_mousewheel(self, event) -> str:
        delta = int(-1 * (event.delta / 120) * 3)
        try:
            self._scroll._parent_canvas.yview_scroll(delta, "units")
        except Exception:
            pass
        return "break"

    # ──── 趋势图 ────
    def _draw_trend(self, data: list, mode: str) -> None:
        c = theme.current().colors
        ax = self._trend_ax
        try:
            ax.clear()
            x = np.arange(len(data))
            y = np.array([v for _, v in data], dtype=float) if data else np.array([0.0])
            total = float(y.sum()) if len(y) else 0.0
            ax.set_facecolor(c.chart_face)
            for spine in ax.spines.values():
                spine.set_visible(False)

            if total <= 0:
                ax.set_xticks([])
                ax.set_yticks([])
                ax.text(
                    0.5, 0.5, "还没有记录",
                    transform=ax.transAxes, ha="center", va="center",
                    color=c.fg_muted, fontsize=9,
                )
            else:
                ax.fill_between(x, 0, y, alpha=0.25, color=c.chart_line, linewidth=0)
                ax.plot(x, y, color=c.chart_line, linewidth=2)
                if y.max() > 0:
                    pm = int(np.argmax(y))
                    ax.scatter(pm, y[pm], s=50, color=c.accent_hover,
                               edgecolors=c.chart_line, linewidth=1.5, zorder=5)
                ax.tick_params(colors=c.fg_muted, labelsize=7)
                ax.grid(axis="y", color=c.divider, linewidth=0.5)
                ax.set_xlim(-0.5, max(1, len(x)) - 0.5)
                ax.set_ylim(0, y.max() * 1.15)
                labels = [""] * len(x)
                if len(x) > 1:
                    if mode == "today" and data:
                        labels[0] = datetime.fromtimestamp(
                            data[0][0] / 1000).strftime("%H")
                        labels[-1] = datetime.fromtimestamp(
                            data[-1][0] / 1000).strftime("%H")
                    elif data:
                        labels[0] = datetime.fromtimestamp(
                            data[0][0] / 1000).strftime("%m/%d")
                        labels[-1] = datetime.fromtimestamp(
                            data[-1][0] / 1000).strftime("%m/%d")
                ax.set_xticks(x)
                ax.set_xticklabels(labels, ha="center")

            self._trend_fig.patch.set_facecolor(c.chart_face)
            self._trend_canvas.draw_idle()
        except Exception:
            pass

    def _do_apply_theme(self) -> None:
        c = theme.current().colors
        try:
            self.configure(fg_color=c.bg_primary)
            if hasattr(self, "_scroll"):
                self._scroll.configure(fg_color=c.bg_primary)
            if hasattr(self, "_main_card"):
                self._main_card.configure(
                    fg_color=c.bg_secondary, border_color=c.border
                )
                self._main_label.configure(text_color=c.fg_secondary)
                self._main_val.configure(text_color=c.fg_primary)
                self._main_sub.configure(text_color=c.fg_muted)
            if hasattr(self, "_trend_card"):
                self._trend_card.configure(
                    fg_color=c.bg_secondary, border_color=c.border
                )
                self._trend_title_lbl.configure(text_color=c.fg_primary)
            if hasattr(self, "_heat_card"):
                self._heat_card.configure(
                    fg_color=c.bg_secondary, border_color=c.border
                )
        except Exception:
            pass
        try:
            self._trend_fig.clear()
            self._trend_ax = self._trend_fig.add_subplot(111)
            self._trend_fig.patch.set_facecolor(c.chart_face)
            self._trend_fig.patch.set_alpha(1.0)
            self._trend_ax.set_facecolor(c.chart_face)
            _sync_canvas_bg(
                self._trend_fig, self._trend_canvas, fg_color=c.chart_face
            )
            if self._stat_idx == 2:
                self._draw_trend(db.daily_counts(30), self._STAT_KEYS[self._stat_idx])
            elif self._stat_idx == 1:
                self._draw_trend(db.daily_counts(7), self._STAT_KEYS[self._stat_idx])
            else:
                self._draw_trend(db.hourly_today(), self._STAT_KEYS[self._stat_idx])
            self._trend_canvas.draw()
            try:
                self._trend_canvas.flush_events()
            except Exception:
                pass
            try:
                self._trend_canvas.get_tk_widget().update_idletasks()
            except Exception:
                pass
            try:
                self._trend_canvas.get_tk_widget().update()
            except Exception:
                pass
        except Exception:
            pass
        try:
            self._heatmap.apply_theme()
        except Exception:
            pass
