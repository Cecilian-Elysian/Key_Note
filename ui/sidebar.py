"""侧边栏导航。

固定宽度,纵向排列 5 个导航项。当前激活项高亮。
回调函数由 App 注入,接收 page_name。
"""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

import theme


NAV_ITEMS = [
    ("dashboard", "📊", "仪表盘"),
    ("rate", "📈", "速率"),
    ("heatmap", "🟩", "贡献图"),
    ("top_keys", "⌨", "按键排行"),
    ("settings", "⚙", "设置"),
]


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, on_select: Callable[[str], None]):
        super().__init__(master, width=180, corner_radius=0)
        self._on_select = on_select
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._active: Optional[str] = None
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(
            self,
            text="KeyNote",
            font=("", 18, "bold"),
            text_color=theme.current().colors.accent,
        ).pack(pady=(20, 6), padx=12, anchor="w")

        ctk.CTkLabel(
            self,
            text="键盘活动记录",
            font=("", 11),
            text_color=theme.current().colors.fg_muted,
        ).pack(pady=(0, 16), padx=14, anchor="w")

        for name, icon, label in NAV_ITEMS:
            btn = ctk.CTkButton(
                self,
                text=f"  {icon}  {label}",
                anchor="w",
                height=40,
                corner_radius=8,
                fg_color="transparent",
                text_color=theme.current().colors.fg_primary,
                hover_color=theme.current().colors.bg_tertiary,
                command=lambda n=name: self._on_select(n),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._buttons[name] = btn

    def set_active(self, name: str) -> None:
        if name == self._active:
            return
        colors = theme.current().colors
        for key, btn in self._buttons.items():
            if key == name:
                btn.configure(fg_color=colors.accent, text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color=colors.fg_primary)
        self._active = name

    def apply_theme(self) -> None:
        colors = theme.current().colors
        for key, btn in self._buttons.items():
            if key == self._active:
                btn.configure(fg_color=colors.accent, text_color="#ffffff")
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=colors.fg_primary,
                    hover_color=colors.bg_tertiary,
                )