"""matplotlib 可缩放画布工厂,创建自适应容器尺寸的 FigureCanvas,统一背景色同步,提供给 dashboard 折线图和各死代码页面复用"""
from __future__ import annotations

from typing import Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


def fit_canvas(fig: Figure, canvas: FigureCanvasTkAgg, margin: float = 0.2) -> bool:
    """将 figure 尺寸调整为 canvas 控件的实际像素尺寸，返回 True 表示尺寸有变化。"""
    widget = canvas.get_tk_widget()
    w_px = widget.winfo_width()
    h_px = widget.winfo_height()
    if w_px <= 50 or h_px <= 50:
        return False
    new_w = max(1.0, w_px / fig.dpi - margin)
    new_h = max(1.0, h_px / fig.dpi - margin)
    cur_w, cur_h = fig.get_size_inches()
    if abs(cur_w - new_w) < 0.05 and abs(cur_h - new_h) < 0.05:
        return False
    fig.set_size_inches(new_w, new_h, forward=True)
    return True


def _to_hex(color) -> str:
    """matplotlib 颜色 (r,g,b,a) 或字符串 → hex 字符串。"""
    try:
        if isinstance(color, str):
            return color
        if len(color) >= 3:
            r, g, b = color[0], color[1], color[2]
            return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'
    except Exception:
        pass
    return '#2b2b2b'


def _sync_canvas_bg(fig: Figure, canvas: FigureCanvasTkAgg, fg_color=None) -> None:
    """将 figure.patch / axes / tk Canvas 控件的背景色统一为 fg_color。"""
    color = fg_color if fg_color is not None else fig.get_facecolor()
    hex_color = _to_hex(color)
    try:
        fig.patch.set_facecolor(color)
    except Exception:
        pass
    try:
        for ax in fig.get_axes():
            ax.set_facecolor(color)
    except Exception:
        pass
    try:
        canvas.get_tk_widget().configure(bg=hex_color)
    except Exception:
        pass


def create_resizable_canvas(
    master,
    initial_size: Tuple[float, float] = (8, 5),
    dpi: int = 72,
    margin: float = 0.08,
    fg_color: Optional[str] = None,
    **pack_kwargs,
) -> Tuple[Figure, FigureCanvasTkAgg]:
    """创建随容器尺寸变化的 matplotlib 画布。"""
    bg = fg_color or '#2b2b2b'
    fig = Figure(figsize=initial_size, dpi=dpi, facecolor=bg)
    fig.patch.set_facecolor(bg)
    canvas = FigureCanvasTkAgg(fig, master=master)
    widget = canvas.get_tk_widget()
    widget.configure(bg=bg)
    widget.pack(fill="both", expand=True, **pack_kwargs)

    _sync_canvas_bg(fig, canvas, fg_color=bg)

    def _on_resize(event, fig=fig, canvas=canvas, margin=margin):
        if fit_canvas(fig, canvas, margin):
            canvas.draw_idle()

    widget.bind("<Configure>", _on_resize)

    def _schedule_fit(fig=fig, canvas=canvas, margin=margin):
        if fit_canvas(fig, canvas, margin):
            canvas.draw_idle()

    for ms in (100, 400, 1000):
        widget.after(ms, _schedule_fit)

    return fig, canvas