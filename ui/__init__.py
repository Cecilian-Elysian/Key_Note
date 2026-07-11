"""UI 子包入口。

提供侧边栏 + 多页布局所需组件。所有页面采用懒加载策略
(切换时才构建),降低内存占用。
"""
from ui.sidebar import Sidebar, NAV_ITEMS

__all__ = ["Sidebar", "NAV_ITEMS"]