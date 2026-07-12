"""BasePage 页面基类,定义 build/refresh/apply_theme 三接口生命周期,build 在 ensure_built 时首次调用,refresh 在数据更新时触发"""
from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from window import App


class BasePage(ctk.CTkFrame):
    name: str = ""

    def __init__(self, master, app: "App"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._built = False

    def ensure_built(self) -> None:
        if not self._built:
            self._build()
            self._built = True

    def _build(self) -> None: ...

    def refresh(self) -> None:
        if self._built:
            self._do_refresh()

    def _do_refresh(self) -> None: ...

    def apply_theme(self) -> None:
        if self._built:
            self._do_apply_theme()

    def _do_apply_theme(self) -> None: ...