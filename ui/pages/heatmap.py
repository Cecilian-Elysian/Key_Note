"""GitHub 风格年度贡献热力图页面(占位,Step 4 实现)。"""
from __future__ import annotations

import customtkinter as ctk
import theme
from ui.pages.base import BasePage


class HeatmapPage(BasePage):
    name = "heatmap"

    def _build(self) -> None:
        from ui.widgets.gh_heatmap import GhHeatmapWidget

        self._widget = GhHeatmapWidget(self, days=365)
        self._widget.pack(fill="both", expand=True, padx=16, pady=16)

    def _do_refresh(self) -> None:
        if hasattr(self, "_widget"):
            self._widget.refresh()

    def _do_apply_theme(self) -> None:
        if hasattr(self, "_widget"):
            self._widget.apply_theme()