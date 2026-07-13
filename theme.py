"""统一主题令牌系统,集中管理 dark/light 两套预设的颜色/间距/圆角,UI 模块通过 current().colors 取色,支持应用主题与递归重绘"""
from __future__ import annotations

# ──── 令牌定义 ────
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from customtkinter import CTk


@dataclass(frozen=True)
class ColorTokens:
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    fg_primary: str
    fg_secondary: str
    fg_muted: str
    accent: str
    accent_hover: str
    success: str
    warning: str
    danger: str
    border: str
    chart_face: str
    chart_line: str
    heatmap_empty: str
    heatmap_l1: str
    heatmap_l2: str
    heatmap_l3: str
    heatmap_l4: str


@dataclass(frozen=True)
class SpacingTokens:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24


@dataclass(frozen=True)
class RadiusTokens:
    sm: int = 6
    md: int = 10
    lg: int = 14


@dataclass(frozen=True)
class Theme:
    name: str
    appearance: str
    plt_style: str
    colors: ColorTokens
    spacing: SpacingTokens = field(default_factory=SpacingTokens)
    radius: RadiusTokens = field(default_factory=RadiusTokens)


# ──── 预设主题 ────
DARK = Theme(
    name="dark",
    appearance="dark",
    plt_style="dark_background",
    colors=ColorTokens(
        bg_primary="#1a1a1a",
        bg_secondary="#2b2b2b",
        bg_tertiary="#3a3a3a",
        fg_primary="#e8e8e8",
        fg_secondary="#c8c8c8",
        fg_muted="#8a8a8a",
        accent="#4dabf7",
        accent_hover="#74c0fc",
        success="#51cf66",
        warning="#fcc419",
        danger="#ff6b6b",
        border="#3a3a3a",
        chart_face="#1a1a1a",
        chart_line="#39d353",
        heatmap_empty="#2b2b2b",
        heatmap_l1="#0e4429",
        heatmap_l2="#006d32",
        heatmap_l3="#26a641",
        heatmap_l4="#39d353",
    ),
)


LIGHT = Theme(
    name="light",
    appearance="light",
    plt_style="default",
    colors=ColorTokens(
        bg_primary="#f5f5f5",
        bg_secondary="#ffffff",
        bg_tertiary="#ebebeb",
        fg_primary="#1a1a1a",
        fg_secondary="#3a3a3a",
        fg_muted="#6a6a6a",
        accent="#1971c2",
        accent_hover="#1c7ed6",
        success="#2f9e44",
        warning="#f08c00",
        danger="#e03131",
        border="#d0d0d0",
        chart_face="#ffffff",
        chart_line="#2f9e44",
        heatmap_empty="#ebedf0",
        heatmap_l1="#9be9a8",
        heatmap_l2="#40c463",
        heatmap_l3="#30a14e",
        heatmap_l4="#216e39",
    ),
)


THEMES: dict[str, Theme] = {
    "dark": DARK,
    "light": LIGHT,
}


_current: Theme = DARK


def current() -> Theme:
    return _current


def get(name: str) -> Theme:
    return THEMES.get(name, DARK)


# ──── 切换与应用 ────
def apply_theme(name: str, root: "CTk | None" = None) -> Theme:
    """切换主题并应用到 customtkinter 根窗口。

    若 root 给出,会触发重绘;调用方负责刷新图表。
    """
    global _current
    theme = get(name)
    _current = theme
    ctk.set_appearance_mode(theme.appearance)
    if root is not None:
        try:
            for w in root.winfo_children():
                _recolor(w, theme)
        except Exception:
            pass
    return theme


def _recolor(widget, theme: Theme) -> None:
    """递归根据 widget 类型映射主题色。

    仅覆盖明确支持的 CTk 控件类;其余保留默认。页面专属 widget 由页面
    _do_apply_theme() 后置覆盖(优先级:页面 > 全局)。
    """
    cls_name = type(widget).__name__
    try:
        if cls_name == "CTkFrame":
            widget.configure(fg_color=theme.colors.bg_secondary)
        elif cls_name == "CTkLabel":
            widget.configure(text_color=theme.colors.fg_primary)
        elif cls_name == "CTkButton":
            try:
                widget.configure(
                    border_color=theme.colors.border,
                    hover_color=theme.colors.bg_tertiary,
                )
            except Exception:
                pass
    except Exception:
        pass
    try:
        for child in widget.winfo_children():
            _recolor(child, theme)
    except Exception:
        pass