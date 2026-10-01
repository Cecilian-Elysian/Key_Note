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

    # ──── 数值 count-up 动画 ────
    def animate_number(
        self, label, old: int, new: int,
        suffix: str = "", zero_text: "str | None" = None,
    ) -> None:
        """~260ms 缓出插值滚动到目标值,重入自动取消旧动画。"""
        aid = getattr(label, "_anim_id", None)
        if aid is not None:
            try:
                self.after_cancel(aid)
            except Exception:
                pass
            label._anim_id = None
        if new <= 0:
            label.configure(text=zero_text if zero_text is not None else f"0{suffix}")
            return
        steps = 8

        def _step(i: int = 0) -> None:
            t = (i + 1) / steps
            v = round(old + (new - old) * (t * (2 - t)))
            label.configure(text=f"{v:,}{suffix}")
            if i + 1 < steps:
                label._anim_id = self.after(32, lambda: _step(i + 1))
            else:
                label._anim_id = None

        _step()