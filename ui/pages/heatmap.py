"""年度热力图页面(完整实现,未挂载到 App):顶部 4 张统计卡(今日/7日均/30日均/累计) + GhHeatmapWidget 年度热力图,右上角设置按钮打开 SettingsPanel。后续可作第 3 页候选恢复。"""
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

        header = ctk.CTkFrame(self, fg_color=c.bg_primary)
        header.pack(fill="x", padx=8, pady=(8, 2))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)

        title = ctk.CTkLabel(
            header,
            text="年度热力图",
            font=("", 12, "bold"),
            text_color=c.fg_primary,
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="w")

        self._settings_btn = ctk.CTkButton(
            header,
            text="⚙ 设置",
            width=70,
            height=24,
            font=("", 10),
            fg_color=c.bg_secondary,
            hover_color=c.bg_tertiary,
            text_color=c.fg_primary,
            border_width=0,
            command=self._open_settings,
        )
        self._settings_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))

        cards = ctk.CTkFrame(self, fg_color=c.bg_primary)
        cards.pack(fill="x", padx=8, pady=(4, 4))
        cards.columnconfigure((0, 1, 2, 3), weight=1, uniform="stat")

        items = [
            ("today", "今日按键"),
            ("avg7", "7 日均"),
            ("avg30", "30 日均"),
            ("total", "累计按键"),
        ]
        self._cards: dict[str, tuple[ctk.CTkFrame, ctk.CTkLabel, ctk.CTkLabel]] = {}
        for idx, (key, title) in enumerate(items):
            card = ctk.CTkFrame(cards, fg_color=c.bg_secondary)
            card.grid(row=0, column=idx, padx=4, pady=4, sticky="nsew")
            title_lbl = ctk.CTkLabel(
                card, text=title, font=("", 10), text_color=c.fg_muted
            )
            title_lbl.pack(anchor="w", padx=10, pady=(8, 0))
            value_lbl = ctk.CTkLabel(
                card, text="—", font=("", 16, "bold"), text_color=c.fg_primary
            )
            value_lbl.pack(anchor="w", padx=10, pady=(2, 8))
            self._cards[key] = (card, title_lbl, value_lbl)

        from ui.widgets.gh_heatmap import GhHeatmapWidget

        self._heatmap = GhHeatmapWidget(self, days=365, rows=2)
        self._heatmap.configure(fg_color=c.bg_primary)
        self._heatmap.pack(fill="both", expand=True, padx=8, pady=(2, 8))

        self._settings_window = None

    def _open_settings(self) -> None:
        if self._settings_window is not None:
            try:
                if self._settings_window.winfo_exists():
                    self._settings_window.focus_force()
                    return
            except Exception:
                pass
        self._settings_window = self._build_settings_window()

    def _build_settings_window(self):
        from settings_panel import SettingsPanel

        top = ctk.CTkToplevel(self)
        top.title("KeyNote 设置")
        top.geometry("400x480")
        top.resizable(False, False)

        app = getattr(self, "app", None)
        on_save = getattr(app, "_on_settings_changed", None) if app else None

        def _on_save(new_cfg):
            try:
                if on_save is not None:
                    on_save(new_cfg)
            except Exception:
                pass
            try:
                top.destroy()
            except Exception:
                pass
            self._settings_window = None

        panel = SettingsPanel(top, on_save_callback=_on_save)
        panel.pack(fill="both", expand=True)
        cfg = getattr(app, "cfg", {}) if app else {}
        try:
            panel.load_values(cfg)
        except Exception:
            pass
        return top

    def _do_refresh(self) -> None:
        today = db.count_today()
        avg7 = db.daily_average(7)
        avg30 = db.daily_average(30)
        total = db.count_total()
        self._cards["today"][2].configure(text=f"{today:,}")
        self._cards["avg7"][2].configure(text=f"{avg7:,}")
        self._cards["avg30"][2].configure(text=f"{avg30:,}")
        self._cards["total"][2].configure(text=f"{total:,}")
        if hasattr(self, "_heatmap"):
            self._heatmap.refresh()

    def _do_apply_theme(self) -> None:
        c = theme.current().colors
        try:
            self.configure(fg_color=c.bg_primary)
        except Exception:
            pass
        try:
            self._settings_btn.configure(
                fg_color=c.bg_secondary,
                hover_color=c.bg_tertiary,
                text_color=c.fg_primary,
            )
        except Exception:
            pass
        for _card, title_lbl, value_lbl in self._cards.values():
            try:
                title_lbl.configure(text_color=c.fg_muted)
                value_lbl.configure(text_color=c.fg_primary)
            except Exception:
                pass
        if hasattr(self, "_heatmap"):
            self._heatmap.apply_theme()