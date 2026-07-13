"""统计页(Page 1):segmented 选项切换主卡(今日 / 近 7 天 / 近 30 天)+ 30 天按键趋势折线 + WPM 卡 + 年度 GH 热力图"""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk
import numpy as np

import db
import theme
from ui.pages.base import BasePage
from ui.widgets.chart_utils import create_resizable_canvas, _sync_canvas_bg


# ──── 页面专属调色板(与 keyboard.py 解耦,跟主题走) ────
_PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "bg":          "#0B1120",
        "card_bg":     "#1A1F2C",
        "card_bg2":    "#131A26",
        "accent":      "#FF5722",
        "accent_glow": "#FF7043",
        "fg_primary":  "#E2E8F0",
        "fg_muted":    "#64748B",
        "grid_line":   "#2D3748",
        "border":      "#2D3748",
    },
    "light": {
        "bg":          "#F8FAFC",
        "card_bg":     "#FFFFFF",
        "card_bg2":    "#F1F5F9",
        "accent":      "#E65100",
        "accent_glow": "#FF8A65",
        "fg_primary":  "#1E293B",
        "fg_muted":    "#94A3B8",
        "grid_line":   "#CBD5E1",
        "border":      "#CBD5E1",
    },
}


def _palette() -> dict[str, str]:
    name = theme.current().name
    return _PALETTES.get(name, _PALETTES["dark"])


class OverviewPage(BasePage):
    name = "overview"

    _STAT_OPTIONS = ["今日", "近 7 天", "近 30 天"]
    _STAT_KEYS = ["today", "week", "month"]

    def _build(self) -> None:
        p = _palette()
        self.configure(fg_color=p["bg"])

        scroll = ctk.CTkScrollableFrame(self, fg_color=p["bg"])
        scroll.pack(fill="both", expand=True)
        self._scroll = scroll
        self._scroll._parent_canvas.bind(
            "<MouseWheel>", self._on_mousewheel, add="+"
        )

        # ──── segmented + 主卡 ────
        seg = ctk.CTkSegmentedButton(
            scroll, values=self._STAT_OPTIONS,
            command=self._on_segment_change,
            font=("", 12),
            selected_color=p["accent"],
            selected_hover_color=p["accent_glow"],
            unselected_color=p["card_bg2"],
            text_color=p["fg_primary"],
        )
        seg.pack(fill="x", padx=8, pady=(8, 4))
        self._seg = seg
        self._stat_idx = 2
        seg.set(self._STAT_OPTIONS[self._stat_idx])

        main_card = ctk.CTkFrame(scroll, fg_color=p["card_bg"], corner_radius=10)
        main_card.pack(fill="x", padx=6, pady=(0, 4))
        self._main_card = main_card
        self._main_val = ctk.CTkLabel(
            main_card, text="—", font=("", 36, "bold"), text_color=p["fg_primary"]
        )
        self._main_val.pack(anchor="w", padx=14, pady=(12, 0))
        self._main_sub = ctk.CTkLabel(
            main_card, text="按键", font=("", 11), text_color=p["fg_muted"]
        )
        self._main_sub.pack(anchor="w", padx=14, pady=(0, 12))

        # ──── 趋势图卡 ────
        trend_card = ctk.CTkFrame(scroll, fg_color=p["card_bg"], corner_radius=10)
        self._trend_card = trend_card
        trend_card.pack(fill="x", padx=6, pady=4)
        self._trend_title_lbl = ctk.CTkLabel(
            trend_card, text="近 30 天按键趋势", font=("", 11), text_color=p["fg_primary"]
        )
        self._trend_title_lbl.pack(anchor="w", padx=10, pady=(6, 0))

        self._trend_fig, self._trend_canvas = create_resizable_canvas(
            trend_card, initial_size=(6.0, 1.8), dpi=72, fg_color=p["card_bg"]
        )
        self._trend_fig.patch.set_facecolor(p["card_bg"])
        self._trend_ax = self._trend_fig.add_subplot(111)
        self._trend_ax.set_facecolor(p["card_bg"])

        # ──── WPM 卡 ────
        wpm_card = ctk.CTkFrame(scroll, fg_color=p["card_bg"], corner_radius=10)
        self._wpm_card = wpm_card
        wpm_card.pack(fill="x", padx=6, pady=4)
        wpm_title = ctk.CTkLabel(
            wpm_card, text="⌨ 打字速度", font=("", 11), text_color=p["fg_primary"]
        )
        wpm_title.pack(anchor="w", padx=10, pady=(8, 0))
        body = ctk.CTkFrame(wpm_card, fg_color="transparent")
        body.pack(fill="x", padx=10, pady=(0, 8))
        self._wpm_val = ctk.CTkLabel(
            body, text="—", font=("", 22, "bold"), text_color=p["accent"]
        )
        self._wpm_val.pack(side="left")
        self._wpm_unit = ctk.CTkLabel(
            body, text=" WPM", font=("", 12, "bold"), text_color=p["fg_muted"]
        )
        self._wpm_unit.pack(side="left")
        self._wpm_sub = ctk.CTkLabel(
            body, text="(5 分钟均值)", font=("", 10), text_color=p["fg_muted"]
        )
        self._wpm_sub.pack(side="right")

        # ──── GH 年度热力图 ────
        from ui.widgets.gh_heatmap import GhHeatmapWidget

        self._heatmap = GhHeatmapWidget(
            scroll, days=int(self.app.cfg.get("heatmap_days", 365))
        )
        self._heatmap.configure(fg_color=p["bg"])
        self._heatmap.pack(fill="x", padx=4, pady=(4, 8))

        self._refresh_from_idx()

    def _on_segment_change(self, value: str) -> None:
        try:
            self._stat_idx = self._STAT_OPTIONS.index(value)
        except ValueError:
            self._stat_idx = 2
        self._refresh_from_idx()

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
            val = sum(c for _, c in rows)
            data = rows
            title = "近 7 天按键趋势"
        else:
            rows = db.daily_counts(30)
            val = sum(c for _, c in rows)
            data = rows
            title = "近 30 天按键趋势"

        try:
            self._main_val.configure(text=f"{val:,}" if val else "—")
            self._main_sub.configure(text=f"{label}按键")
        except Exception:
            pass

        try:
            self._trend_title_lbl.configure(text=title)
            self._draw_trend(data, key)
        except Exception:
            pass

        try:
            cpm = db.cpm_recent(5)
            wpm = int(cpm / 5)
            self._wpm_val.configure(text=f"{wpm:,}" if wpm > 0 else "—")
        except Exception:
            pass

        try:
            self._heatmap.refresh()
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

    def _draw_trend(self, data: list, mode: str) -> None:
        p = _palette()
        ax = self._trend_ax
        try:
            ax.clear()
            x = np.arange(len(data))
            y = np.array([v for _, v in data], dtype=float) if data else np.array([0.0])
            if len(y) > 0:
                for a in (0.02, 0.04, 0.06, 0.08, 0.10, 0.12):
                    ax.fill_between(x, 0, y, alpha=a, color=p["accent"])
                ax.plot(x, y, color=p["accent"], linewidth=2)
                if y.max() > 0:
                    pm = int(np.argmax(y))
                    ax.scatter(pm, y[pm], s=50, color=p["accent_glow"],
                               edgecolors=p["accent"], linewidth=1.5, zorder=5)
            ax.set_facecolor(p["card_bg"])
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.tick_params(colors=p["fg_muted"], labelsize=7)
            ax.grid(axis="y", color=p["grid_line"], linewidth=0.3)
            ax.set_xlim(-0.5, max(1, len(x)) - 0.5)
            if len(y) > 0 and y.max() > 0:
                ax.set_ylim(0, y.max() * 1.15)
            labels = [""] * len(x)
            if len(x) > 0 and len(x) > 1:
                if mode == "today" and data:
                    labels[0] = datetime.fromtimestamp(data[0][0] / 1000).strftime("%H")
                    labels[-1] = datetime.fromtimestamp(data[-1][0] / 1000).strftime("%H")
                elif data:
                    labels[0] = datetime.fromtimestamp(data[0][0] / 1000).strftime("%m/%d")
                    labels[-1] = datetime.fromtimestamp(data[-1][0] / 1000).strftime("%m/%d")
            ax.set_xticks(x)
            ax.set_xticklabels(labels, ha="center")
            self._trend_fig.patch.set_facecolor(p["card_bg"])
            self._trend_canvas.draw_idle()
        except Exception:
            pass

    def _do_apply_theme(self) -> None:
        p = _palette()
        try:
            self.configure(fg_color=p["bg"])
            if hasattr(self, "_scroll"):
                self._scroll.configure(fg_color=p["bg"])
            if hasattr(self, "_main_card"):
                self._main_card.configure(fg_color=p["card_bg"])
                self._main_val.configure(text_color=p["fg_primary"])
                self._main_sub.configure(text_color=p["fg_muted"])
            if hasattr(self, "_trend_card"):
                self._trend_card.configure(fg_color=p["card_bg"])
                self._trend_title_lbl.configure(text_color=p["fg_primary"])
            if hasattr(self, "_wpm_card"):
                self._wpm_card.configure(fg_color=p["card_bg"])
            self._wpm_val.configure(text_color=p["accent"])
            self._wpm_unit.configure(text_color=p["fg_muted"])
            self._wpm_sub.configure(text_color=p["fg_muted"])
            if hasattr(self, "_heatmap"):
                self._heatmap.configure(fg_color=p["bg"])
        except Exception:
            pass
        try:
            _sync_canvas_bg(self._trend_fig, self._trend_canvas, fg_color=p["card_bg"])
            self._trend_ax.set_facecolor(p["card_bg"])
            self._trend_fig.patch.set_facecolor(p["card_bg"])
            self._trend_ax.set_facecolor(p["card_bg"])
            if self._stat_idx == 2:
                self._draw_trend(db.daily_counts(30), self._STAT_KEYS[self._stat_idx])
            elif self._stat_idx == 1:
                self._draw_trend(db.daily_counts(7), self._STAT_KEYS[self._stat_idx])
            else:
                self._draw_trend(db.hourly_today(), self._STAT_KEYS[self._stat_idx])
            self._trend_canvas.draw()
        except Exception:
            pass
        try:
            self._heatmap.apply_theme()
        except Exception:
            pass
