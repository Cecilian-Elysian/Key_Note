"""设置页面:包装现有 settings_panel,作为侧边栏中的一页。"""
from __future__ import annotations

import customtkinter as ctk

import theme
from ui.pages.base import BasePage


class SettingsPage(BasePage):
    name = "settings"

    def _build(self) -> None:
        from settings_panel import SettingsPanel

        self._panel = SettingsPanel(
            self,
            on_save_callback=self.app._on_settings_changed,
        )
        self._panel.pack(fill="both", expand=True, padx=8, pady=8)

    def _do_refresh(self) -> None:
        if hasattr(self, "_panel"):
            self._panel.load_values(self.app.cfg)