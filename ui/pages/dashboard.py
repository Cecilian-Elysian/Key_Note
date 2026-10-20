"""统计页(Page 1):页头 + 时间范围筛选 + 设备行式主卡(图标/进度条/对比胶囊) + 趋势图
(vigil-watt BatteryChart 复刻:2px 圆角线 + 15% 面积填充 + 线端值标签 + 悬停十字线气泡)+ 年度 GH 热力图"""
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
        self._trend_fp: tuple | None = None
        self._trend_pts = None
        self._hover_art = None
        self._hover_i = -1
        self._last_main_val = 0
        self._stat_idx = 2

        # ──── 页头(固定):标题 + 副标题 / 刷新按钮 ────
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 0))
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
            head, text="刷新", image=self.app.refresh_icon(), compound="left",
            width=68, height=28, corner_radius=theme.RADIUS["md"],
            fg_color="transparent", border_width=0,
            hover_color=c.bg_tertiary, text_color=c.fg_secondary,
            font=theme.FONTS["label"], command=self._on_refresh_click,
        )
        self._refresh_btn.pack(side="right", pady=(2, 0))

        # ──── 时间范围筛选(固定,vigil-watt 蓝色实心选中态) ────
        seg = ctk.CTkSegmentedButton(
            self, values=self._STAT_OPTIONS,
            command=self._on_segment_change,
            font=theme.FONTS["label"],
            fg_color=c.bg_tertiary,
            selected_color=c.accent, selected_hover_color=c.accent_hover,
            unselected_color=c.bg_tertiary, unselected_hover_color=c.bg_tertiary,
            text_color=c.fg_primary,
        )
        seg.pack(anchor="w", padx=20, pady=(12, 12))
        self._seg = seg
        self._stat_idx = 2
        seg.set(self._STAT_OPTIONS[self._stat_idx])

        # ──── 滚动内容 ────
        scroll = ctk.CTkScrollableFrame(self, fg_color=c.bg_primary)
        scroll.pack(fill="both", expand=True)
        self._scroll = scroll
        self._scroll._parent_canvas.bind(
            "<MouseWheel>", self._on_mousewheel, add="+"
        )

        # ──── 主卡(设备行式:图标 + 标签 / 右侧大数 + 6px 进度条 + 对比胶囊) ────
        main_card = ctk.CTkFrame(
            scroll, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        main_card.pack(fill="x", padx=20, pady=(0, 12))
        self._main_card = main_card

        top = ctk.CTkFrame(main_card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 0))
        self._main_icon = ctk.CTkLabel(
            top, text="", image=self.app.glyph_icon("\uE9D2", c.accent)
        )
        self._main_icon.pack(side="left")
        self._main_label = ctk.CTkLabel(
            top, text="今日按键", font=theme.FONTS["label"],
            text_color=c.fg_secondary, anchor="w",
        )
        self._main_label.pack(side="left", padx=(8, 0))
        self._main_val = ctk.CTkLabel(
            top, text="—", font=theme.FONTS["hero_value"],
            text_color=c.fg_primary, anchor="e",
        )
        self._main_val.pack(side="right")

        bar_track = theme.mix_hex(c.accent, c.bg_secondary, 0.16)
        self._bar = ctk.CTkProgressBar(
            main_card, height=6, corner_radius=3,
            fg_color=bar_track, progress_color=c.accent,
        )
        self._bar.pack(fill="x", padx=14, pady=(10, 0))
        self._bar.set(0)

        foot = ctk.CTkFrame(main_card, fg_color="transparent")
        foot.pack(fill="x", padx=14, pady=(8, 12))
        self._main_foot = foot
        self._main_pill = ctk.CTkLabel(
            foot, text="", corner_radius=4, height=18,
            font=("", 10, "bold"), fg_color="transparent",
        )
        self._main_pill.pack(side="left")
        self._main_sub = ctk.CTkLabel(
            foot, text="", font=theme.FONTS["footnote"],
            text_color=c.fg_muted, anchor="w",
        )
        self._main_sub.pack(side="left", padx=(8, 0))

        # ──── 趋势图卡 ────
        trend_card = ctk.CTkFrame(
            scroll, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        self._trend_card = trend_card
        trend_card.pack(fill="x", padx=20, pady=(0, 12))
        self._trend_title_lbl = ctk.CTkLabel(
            trend_card, text="近 30 天按键趋势",
            font=theme.FONTS["card_title"], text_color=c.fg_primary, anchor="w",
        )
        self._trend_title_lbl.pack(anchor="w", padx=14, pady=(12, 0))

        self._trend_fig, self._trend_canvas = create_resizable_canvas(
            trend_card, initial_size=(6.0, 1.8), dpi=72,
            fg_color=c.chart_face, padx=10, pady=(4, 12),
        )
        self._trend_fig.patch.set_facecolor(c.chart_face)
        self._trend_ax = self._trend_fig.add_subplot(111)
        self._trend_ax.set_facecolor(c.chart_face)
        self._trend_canvas.mpl_connect(
            "motion_notify_event", self._on_trend_motion
        )
        self._trend_canvas.mpl_connect("axes_leave_event", self._on_trend_leave)

        # ──── GH 年度热力图卡 ────
        from ui.widgets.gh_heatmap import GhHeatmapWidget

        heat_card = ctk.CTkFrame(
            scroll, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        heat_card.pack(fill="x", padx=20, pady=(0, 16))
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
        """今日 vs 昨日按键对比 → (胶囊文本, 语义色);昨日无数据则回退空。"""
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
            return "", ""
        if y_cnt <= 0:
            return "", ""
        pct = (t_cnt - y_cnt) / y_cnt * 100
        if pct > 0.5:
            return f"较昨日 +{pct:.0f}%", c.success
        if pct < -0.5:
            return f"较昨日 −{abs(pct):.0f}%", c.danger
        return "与昨日持平", c.fg_muted

    def _set_pill(self, text: str, color: str) -> None:
        """对比胶囊:语义色文字 + 同色 16% tint 底(vigil-watt 徽标同款)。"""
        if not text or not color:
            self._main_pill.configure(text="", fg_color="transparent")
            return
        self._main_pill.configure(
            text=f" {text} ",
            text_color=color,
            fg_color=theme.mix_hex(color, theme.current().colors.bg_secondary, 0.16),
        )

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
                c = theme.current().colors
                self._main_label.configure(text=f"{label}按键")
                if key == "today":
                    # 进度条:今日 vs 近 30 日日均,达标转绿(电量条语义同款)
                    avg30 = max(int(db.daily_average(30)), 1)
                    ratio = min(val / avg30, 1.0)
                    bar_color = c.success if ratio >= 1.0 else c.accent
                    self._bar.configure(progress_color=bar_color)
                    self._bar.set(ratio)
                    self._bar.pack(
                        fill="x", padx=14, pady=(10, 0), before=self._main_foot
                    )
                    pill_text, pill_color = self._yesterday_compare()
                    self._set_pill(pill_text, pill_color)
                    self._main_sub.configure(
                        text=f"日均 {db.daily_average(30):,} 次"
                    )
                else:
                    days = 7 if key == "week" else 30
                    self._bar.pack_forget()
                    self._set_pill("", "")
                    self._main_sub.configure(
                        text=f"日均 {db.daily_average(days):,} 次"
                    )
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

    # ──── 趋势图(vigil-watt BatteryChart 复刻) ────
    def _draw_trend(self, data: list, mode: str) -> None:
        c = theme.current().colors
        ax = self._trend_ax
        self._trend_pts = None
        self._hover_i = -1
        self._hover_art = None
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
                    0.5, 0.60, "还没有记录",
                    transform=ax.transAxes, ha="center", va="center",
                    color=c.fg_secondary, fontsize=11,
                )
                ax.text(
                    0.5, 0.36, "开始打字后,这里会出现每小时 / 每天的按键曲线",
                    transform=ax.transAxes, ha="center", va="center",
                    color=c.fg_muted, fontsize=8,
                )
            else:
                ax.fill_between(x, 0, y, color=c.chart_line, alpha=0.15, linewidth=0)
                ax.plot(
                    x, y, color=c.chart_line, linewidth=2,
                    solid_capstyle="round", solid_joinstyle="round",
                )
                if len(x) <= 40:
                    ax.plot(x, y, "o", ms=4.5, color=c.chart_line)
                # 线端值标签(vigil-watt "94%" 同款)
                ax.annotate(
                    f"{y[-1]:,.0f}", (x[-1], y[-1]),
                    textcoords="offset points", xytext=(8, 0),
                    va="center", color=c.chart_line,
                    fontsize=10, fontweight="bold",
                )
                ax.tick_params(colors=c.fg_muted, labelsize=8, length=0)
                ax.grid(
                    axis="y", color=c.divider,
                    ls=(0, (3, 3)), alpha=0.55, linewidth=0.8,
                )
                ax.set_xlim(-0.5, max(1, len(x)) - 0.5)
                ax.set_ylim(0, y.max() * 1.18)
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
                self._trend_pts = (x, y, data, mode)

            self._trend_fig.patch.set_facecolor(c.chart_face)
            self._trend_canvas.draw_idle()
        except Exception:
            pass

    # ──── 悬停十字线 + 气泡(vigil-watt 同款交互) ────
    def _clear_trend_hover(self, draw: bool = True) -> None:
        for a in self._hover_art or []:
            try:
                a.remove()
            except Exception:
                pass
        self._hover_art = None
        if draw:
            try:
                self._trend_canvas.draw_idle()
            except Exception:
                pass

    def _on_trend_motion(self, event) -> None:
        pts = self._trend_pts
        if pts is None or event.inaxes is not self._trend_ax:
            return
        if event.xdata is None:
            return
        x, y, data, mode = pts
        i = int(np.clip(round(float(event.xdata)), 0, len(x) - 1))
        if i == self._hover_i:
            return
        self._hover_i = i
        self._clear_trend_hover(draw=False)
        try:
            c = theme.current().colors
            ax = self._trend_ax
            art = [
                ax.axvline(
                    x[i], color=c.fg_muted,
                    ls=(0, (3, 3)), alpha=0.55, linewidth=0.9,
                ),
                ax.scatter(
                    [x[i]], [y[i]], s=42, color=c.chart_line,
                    edgecolors="#FFFFFF", linewidths=1.4, zorder=6,
                ),
            ]
            if mode == "today" and data:
                lbl = datetime.fromtimestamp(data[i][0] / 1000).strftime("%H 时")
            elif data:
                lbl = datetime.fromtimestamp(data[i][0] / 1000).strftime("%m/%d")
            else:
                lbl = ""
            art.append(ax.annotate(
                f"{y[i]:,.0f}   {lbl}", (x[i], y[i]),
                textcoords="offset points", xytext=(0, 12),
                ha="center", fontsize=9, color=c.fg_primary,
                bbox=dict(
                    boxstyle="round,pad=0.45",
                    fc=c.bg_tertiary, ec=c.border, linewidth=1,
                ),
                zorder=7,
            ))
            self._hover_art = art
            self._trend_canvas.draw_idle()
        except Exception:
            self._hover_art = None

    def _on_trend_leave(self, _event) -> None:
        self._hover_i = -1
        self._clear_trend_hover()

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
                self._main_icon.configure(
                    image=self.app.glyph_icon("\uE9D2", c.accent)
                )
                self._main_label.configure(text_color=c.fg_secondary)
                self._main_val.configure(text_color=c.fg_primary)
                self._bar.configure(fg_color=theme.mix_hex(c.accent, c.bg_secondary, 0.16))
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
            self._hover_art = None
            self._hover_i = -1
            self._trend_pts = None
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
