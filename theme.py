"""统一主题令牌系统,dark 主题颜色集中管理,UI 模块通过 current().colors 取色

色板对齐 WinUI 暗色 Fluent:#1C1C1C 底 / #272727 卡 / #0A84FF 强调,
状态色取自同一套语义(绿/琥珀/红/灰),页面不再各自维护调色板。
"""
from __future__ import annotations

# ──── 令牌定义 ────
from dataclasses import dataclass
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
    offline: str
    border: str
    divider: str
    chart_face: str
    chart_line: str
    heatmap_empty: str
    heatmap_l1: str
    heatmap_l2: str
    heatmap_l3: str
    heatmap_l4: str


@dataclass(frozen=True)
class Theme:
    name: str
    appearance: str
    plt_style: str
    colors: ColorTokens


# ──── 唯一主题(dark) ────
DARK = Theme(
    name="dark",
    appearance="dark",
    plt_style="dark_background",
    colors=ColorTokens(
        bg_primary="#1C1C1C",
        bg_secondary="#272727",
        bg_tertiary="#333333",
        fg_primary="#FFFFFF",
        fg_secondary="#C5C5C5",
        fg_muted="#8D8D8D",
        accent="#0A84FF",
        accent_hover="#3A96FF",
        success="#34C759",
        warning="#FAA817",
        danger="#E2445C",
        offline="#8E8E93",
        border="#3D3D3D",
        divider="#2F2F2F",
        chart_face="#272727",
        chart_line="#0A84FF",
        heatmap_empty="#2A2A2A",
        heatmap_l1="#0E4429",
        heatmap_l2="#006D32",
        heatmap_l3="#26A641",
        heatmap_l4="#39D353",
    ),
)


_current: Theme = DARK


def current() -> Theme:
    return _current


# ──── 间距 / 圆角(逻辑 px,页面内按 DPI 缩放) ────
SPACE = {
    "xs": 4,
    "s": 8,
    "m": 12,
    "l": 16,
    "xl": 20,
}

RADIUS = {
    "sm": 4,
    "md": 8,
    "lg": 12,
}


# ──── 字号(字体族留空,跟随应用默认字体) ────
FONTS = {
    "page_title": ("", 18, "bold"),
    "card_title": ("", 15, "bold"),
    "row_title": ("", 14),
    "body": ("", 13),
    "label": ("", 12),
    "footnote": ("", 11),
    "caption": ("", 10),
    "hero_value": ("", 32, "bold"),
    "kpi_value": ("", 22, "bold"),
}


# ──── 颜色工具 ────
def hex_to_rgb(hx: str) -> tuple[int, int, int]:
    """`#RRGGBB` / `RRGGBB` → `(r, g, b)` 元组,供 Pillow RGBA / 托盘图标 tint 用。"""
    h = hx.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ──── 应用 ────
def apply_theme(root: "CTk | None" = None) -> Theme:
    """应用 dark 主题到 customtkinter 根窗口,启动时调用一次即可。"""
    ctk.set_appearance_mode(DARK.appearance)
    return DARK
