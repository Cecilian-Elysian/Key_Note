"""设置页面:整页嵌入 SettingsPanel(搜索 + 分组行式布局 + 固定底栏),保存走 app._on_settings_changed。
原为未挂载死代码,2026-10 随侧边栏改版挂载为第 5 页,⚙ 入口(托盘/标题栏/Alt+,)统一改走页面导航。"""
from __future__ import annotations

from ui.pages.base import BasePage


class SettingsPage(BasePage):
    name = "settings"

    def _build(self) -> None:
        from settings_panel import SettingsPanel

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._panel = SettingsPanel(
            self, on_save_callback=self.app._on_settings_changed,
        )
        self._panel.grid(row=0, column=0, sticky="nsew")
        self._panel.build_footer(self)

    def _do_refresh(self) -> None:
        # auto-refresh 已被 window.refresh 跳过(避免覆盖编辑中的表单);
        # 这里只在切页/保存后显式刷新时重载
        if hasattr(self, "_panel"):
            self._panel.load_values(self.app.cfg)
