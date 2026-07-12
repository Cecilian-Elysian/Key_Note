"""[死代码] 设置页面,包装 SettingsPanel 作为页面,通过 app._on_settings_changed 回调应用配置"""
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
        self._panel.pack(fill="both", expand=True, padx=4, pady=4)

    def _do_refresh(self) -> None:
        if hasattr(self, "_panel"):
            self._panel.load_values(self.app.cfg)