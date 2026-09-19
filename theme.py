"""统一主题令牌系统,dark 主题颜色集中管理,UI 模块通过 current().colors 取色"""
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
    border: str
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


_current: Theme = DARK


def current() -> Theme:
    return _current


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
