"""GitHub 风格年度贡献热力图 Canvas 组件,支持多行拆分布局、基于分位数的四色阶、鼠标悬停日期/数量提示"""
from __future__ import annotations

# ──── 布局常量 ────

import tkinter as tk
from datetime import timedelta

import customtkinter as ctk

import db
import theme


_TOTAL_COLS = 53
_ROWS = 7
_FIRST_DOW = 0

_CELL_MIN = 6
_CELL_MAX = 17
_CELL_SPACING = 2
_WEEKDAY_LABEL_W = 30
_MONTH_LABEL_H = 16
_LEGEND_H = 16
_MARGIN = 6
_MONTH_MIN_GAP = 6
_INTER_ROW_GAP = 18

_CN_WEEKDAYS = ["一", "三", "五"]
_CN_MONTHS = [
    "", "1月", "2月", "3月", "4月", "5月", "6月",
    "7月", "8月", "9月", "10月", "11月", "12月",
]

_FONT_FAMILY = "Microsoft YaHei UI"


class GhHeatmapWidget(ctk.CTkFrame):
    def __init__(self, master, days: int = 365, rows: int = 2):
        super().__init__(master, fg_color="transparent")
        self._days = days
        self._rows_count = max(1, int(rows))
        self._grid = None
        self._daily_values: list[int] = [0] * days
        self._sub_cols: list[int] = [_TOTAL_COLS]
        self._sub_start_col: list[int] = [0]
        self._start_dt = None
        self._end_dt = None
        self._grid_start = None
        self._percentiles = (1, 1, 1)
        self._hovered = (-1, -1, -1)
        self._resize_after_id = None
        self._tooltip = None
        self._hover_rect = None
        self._build()

    def _build(self) -> None:
        c = theme.current().colors

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=2, pady=(0, 4))
        self._title_lbl = ctk.CTkLabel(
            header,
            text=f"过去 {self._days} 天 · 每日按键贡献",
            font=("", 11, "bold"),
            text_color=c.fg_primary,
            anchor="w",
        )
        self._title_lbl.pack(side="left")
        self._summary_lbl = ctk.CTkLabel(
            header,
            text="",
            font=("", 10),
            text_color=c.fg_muted,
            anchor="e",
        )
        self._summary_lbl.pack(side="right")

        self._canvas = tk.Canvas(
            self, bg=c.bg_primary, highlightthickness=0, bd=0
        )
        self._canvas.pack(fill="both", expand=True, padx=2, pady=2)
        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", self._on_leave)

        self.refresh()
        self.after(50, self._render)

    # ──── 数据刷新 ────
    def refresh(self) -> None:
        grid, start_dt, end_dt = db.heatmap_yearly(self._days)
        self._grid = grid
        self._start_dt = start_dt
        self._end_dt = end_dt

        self._daily_values = [0] * self._days
        max_week = min(_TOTAL_COLS, grid.shape[0])
        for week_idx in range(max_week):
            for dow in range(_ROWS):
                v = int(grid[week_idx, dow])
                if v <= 0:
                    continue
                offset = week_idx * 7 + (dow - start_dt.weekday() + 7) % 7
                if 0 <= offset < self._days:
                    self._daily_values[offset] = v

        start_dow = start_dt.weekday()
        days_back = (start_dow - _FIRST_DOW + 7) % 7
        self._grid_start = start_dt - timedelta(days=days_back)

        self._split_into_rows()

        non_zero = sorted(v for v in self._daily_values if v > 0)
        self._percentiles = self._calc_percentiles(non_zero)

        total = sum(self._daily_values)
        active = sum(1 for v in self._daily_values if v > 0)
        max_val = max(self._daily_values) if self._daily_values else 0
        self._summary_lbl.configure(
            text=f"活跃 {active}/{self._days} 天 · 最高 {max_val:,} · 合计 {total:,}"
        )

        import sys as _sys, os as _os
        if _os.environ.get("KEYNOTE_HEATMAP_DIAG") and not getattr(self, "_diag_done", False):
            _diag = [
                f"[HEATMAP-DIAG] start_dt={start_dt} weekday={start_dt.weekday()}",
                f"[HEATMAP-DIAG] end_dt={end_dt}",
                f"[HEATMAP-DIAG] grid_start={self._grid_start} weekday={self._grid_start.weekday()}",
                f"[HEATMAP-DIAG] _daily_values nonzero: {[(i, self._daily_values[i]) for i in range(self._days) if self._daily_values[i] > 0]}",
                f"[HEATMAP-DIAG] sub_cols={self._sub_cols} sub_start_col={self._sub_start_col}",
            ]
            for w in range(53):
                for d in range(7):
                    if grid[w, d] > 0:
                        _diag.append(f"[HEATMAP-DIAG] grid[{w},{d}]={grid[w, d]}")
            print("\n".join(_diag), file=_sys.stderr, flush=True)
            self._diag_done = True

        self._render()

    def _split_into_rows(self) -> None:
        r = self._rows_count
        base = _TOTAL_COLS // r
        rem = _TOTAL_COLS - base * r
        self._sub_cols = []
        self._sub_start_col = []
        cursor = 0
        for i in range(r):
            cols_in_row = base + (1 if i < rem else 0)
            self._sub_cols.append(cols_in_row)
            self._sub_start_col.append(cursor)
            cursor += cols_in_row

    def apply_theme(self) -> None:
        c = theme.current().colors
        try:
            self._title_lbl.configure(text_color=c.fg_primary)
            self._summary_lbl.configure(text_color=c.fg_muted)
            self._canvas.configure(bg=c.bg_primary)
        except Exception:
            pass
        if self._tooltip is not None:
            try:
                self._tooltip._frame.configure(bg=c.bg_tertiary, highlightbackground=c.border)
                self._tooltip._date_lbl.configure(bg=c.bg_tertiary, fg=c.fg_primary)
                self._tooltip._count_lbl.configure(bg=c.bg_tertiary, fg=c.fg_secondary)
            except Exception:
                pass
        try:
            self.refresh()
        except Exception:
            try:
                self._render()
            except Exception:
                pass
        try:
            self._canvas.update_idletasks()
            self._canvas.update()
        except Exception:
            pass

    @staticmethod
    def _calc_percentiles(non_zero_sorted):
        n = len(non_zero_sorted)
        if n == 0:
            return (1, 1, 1)
        if n == 1:
            v = non_zero_sorted[0]
            return (v, v, v)
        if n == 2:
            return (non_zero_sorted[0], non_zero_sorted[0], non_zero_sorted[1])
        if n == 3:
            return (non_zero_sorted[0], non_zero_sorted[1], non_zero_sorted[2])
        return (
            non_zero_sorted[n // 4],
            non_zero_sorted[n // 2],
            non_zero_sorted[n * 3 // 4],
        )

    def _bucket_color(self, value):
        c = theme.current().colors
        if value <= 0:
            return c.heatmap_empty
        p25, p50, p75 = self._percentiles
        if value <= p25:
            return c.heatmap_l1
        if value <= p50:
            return c.heatmap_l2
        if value <= p75:
            return c.heatmap_l3
        return c.heatmap_l4

    # ──── 布局计算 ────
    def _compute_layout(self, w: int, h: int):
        if w < 100 or h < 60:
            return None
        avail_w = w - _WEEKDAY_LABEL_W - 2 * _MARGIN
        rows = self._rows_count
        inter = (rows - 1) * _INTER_ROW_GAP
        total_h_needed = rows * _MONTH_LABEL_H + rows * _ROWS * _CELL_MIN \
                         + (rows * (_ROWS - 1)) * _CELL_SPACING + inter \
                         + _LEGEND_H + 2 * _MARGIN
        if avail_w < 50 or h < total_h_needed / 2:
            return None

        max_cols = max(self._sub_cols) if self._sub_cols else _TOTAL_COLS
        spacing = _CELL_SPACING
        cell = (avail_w - (max_cols - 1) * spacing) / max_cols
        cell = max(_CELL_MIN, min(_CELL_MAX, cell))
        grid_w = max_cols * cell + (max_cols - 1) * spacing
        if grid_w > avail_w:
            spacing = max(1, (avail_w - max_cols * cell) / (max_cols - 1))
            grid_w = max_cols * cell + (max_cols - 1) * spacing
        grid_h_per_row = _ROWS * cell + (_ROWS - 1) * spacing
        ox = _MARGIN + _WEEKDAY_LABEL_W + max(0.0, (avail_w - grid_w) / 2.0)

        sub_origins = []
        cur_y = _MARGIN
        for r in range(rows):
            sub_origins.append(cur_y + _MONTH_LABEL_H)
            cur_y += _MONTH_LABEL_H + grid_h_per_row
            if r < rows - 1:
                cur_y += _INTER_ROW_GAP

        total_used = cur_y + _LEGEND_H + _MARGIN
        return {
            "ox": ox,
            "cell": cell,
            "spacing": spacing,
            "grid_w": grid_w,
            "grid_h_per_row": grid_h_per_row,
            "sub_origins": sub_origins,
            "total_used": total_used,
            "rows": rows,
        }

    def _sub_layout(self, layout, sub_idx):
        return layout["ox"], layout["sub_origins"][sub_idx], layout["cell"], layout["spacing"]

    # ──── 渲染与标签 ────
    def _render(self) -> None:
        if self._canvas is None:
            return
        self._canvas.delete("all")
        if self._grid is None or self._start_dt is None or self._grid_start is None:
            return
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        layout = self._compute_layout(w, h)
        if not layout:
            return
        ox = layout["ox"]
        cell = layout["cell"]
        spacing = layout["spacing"]
        grid_w = layout["grid_w"]
        sub_origins = layout["sub_origins"]
        rows = layout["rows"]
        c = theme.current().colors

        for sub_idx in range(rows):
            sub_ox = ox
            sub_oy = sub_origins[sub_idx]
            sub_cols = self._sub_cols[sub_idx]
            sub_start_col = self._sub_start_col[sub_idx]

            for local_col in range(sub_cols):
                global_col = sub_start_col + local_col
                for row in range(_ROWS):
                    cell_date = self._grid_start + timedelta(days=global_col * 7 + row)
                    delta = (cell_date - self._start_dt).days
                    if 0 <= delta < self._days:
                        value = self._daily_values[delta]
                    else:
                        value = 0
                    color = self._bucket_color(value)
                    x1 = sub_ox + local_col * (cell + spacing)
                    y1 = sub_oy + row * (cell + spacing)
                    x2 = x1 + cell
                    y2 = y1 + cell
                    self._canvas.create_rectangle(
                        x1, y1, x2, y2,
                        fill=color, outline="", width=0,
                    )

            for idx, row in enumerate([0, 2, 4]):
                label = _CN_WEEKDAYS[idx]
                tx = _MARGIN
                ty = sub_oy + row * (cell + spacing) + cell / 2
                self._canvas.create_text(
                    tx, ty, text=label, anchor="w",
                    fill=c.fg_muted, font=(_FONT_FAMILY, 10),
                )

            self._draw_month_labels(
                sub_ox, sub_oy, cell, spacing, sub_start_col, sub_cols
            )

        legend_y = layout["total_used"] - _LEGEND_H
        self._draw_legend(ox, grid_w, legend_y, cell, spacing)

        self._hover_rect = self._canvas.create_rectangle(
            0, 0, 0, 0,
            outline=c.accent, width=2,
            state="hidden",
        )
        self._canvas.tag_raise(self._hover_rect)
        col, row, sub_idx = self._hovered
        if 0 <= col < _TOTAL_COLS and 0 <= row < _ROWS and 0 <= sub_idx < rows:
            self._update_hover_rect(col, row, sub_idx)

        h = int(layout["total_used"])
        self._canvas.configure(height=h)

    def _draw_month_labels(
        self, ox: float, oy: float, cell: float, spacing: float,
        start_col: int, cols_in_row: int,
    ) -> None:
        c = theme.current().colors
        last_month = -1
        last_label_max_x = -1e9
        text_y = oy - 4

        for local_col in range(cols_in_row):
            global_col = start_col + local_col
            week_start = self._grid_start + timedelta(days=global_col * 7)
            if week_start.month != last_month:
                label = _CN_MONTHS[week_start.month]
                label_x = ox + local_col * (cell + spacing)
                if label_x - last_label_max_x >= _MONTH_MIN_GAP:
                    rid = self._canvas.create_text(
                        label_x, text_y, text=label, anchor="sw",
                        fill=c.fg_muted, font=(_FONT_FAMILY, 10),
                    )
                    bbox = self._canvas.bbox(rid)
                    if bbox:
                        last_label_max_x = bbox[2]
                    last_month = week_start.month

    def _draw_legend(self, grid_x: float, grid_w: float, y: float, cell: float, spacing: float) -> None:
        c = theme.current().colors
        less_text = "少"
        more_text = "多"
        box_size = max(8, min(int(cell), 10))
        box_spacing = 3

        less_w = 11
        more_w = 11
        legend_w = less_w + 8 + 5 * box_size + 4 * box_spacing + 8 + more_w
        right_edge = grid_x + grid_w
        x = right_edge - legend_w

        self._canvas.create_text(
            x, y + box_size / 2, text=less_text, anchor="w",
            fill=c.fg_muted, font=(_FONT_FAMILY, 10),
        )
        x += less_w + 8

        colors = [c.heatmap_empty, c.heatmap_l1, c.heatmap_l2, c.heatmap_l3, c.heatmap_l4]
        for level in range(5):
            self._canvas.create_rectangle(
                x, y, x + box_size, y + box_size,
                fill=colors[level], outline="",
            )
            x += box_size + box_spacing

        x += 8 - box_spacing
        self._canvas.create_text(
            x, y + box_size / 2, text=more_text, anchor="w",
            fill=c.fg_muted, font=(_FONT_FAMILY, 10),
        )

    def _on_resize(self, _event) -> None:
        if self._resize_after_id:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self.after(80, self._render)

    # ──── 交互(hover/tooltip) ────
    def _on_motion(self, event) -> None:
        if self._grid is None or self._grid_start is None:
            return
        col, row, sub_idx = self._hit_test(event.x, event.y)
        if (col, row, sub_idx) != self._hovered:
            self._hovered = (col, row, sub_idx)
            if col >= 0 and row >= 0 and sub_idx >= 0:
                self._update_hover_rect(col, row, sub_idx)
                self._show_tooltip(col, row)
            else:
                self._canvas.itemconfigure(self._hover_rect, state="hidden")
                self._hide_tooltip()

    def _on_leave(self, _event) -> None:
        self._hovered = (-1, -1, -1)
        if self._hover_rect is not None:
            self._canvas.itemconfigure(self._hover_rect, state="hidden")
        self._hide_tooltip()

    def _hit_test(self, x: float, y: float):
        if self._grid_start is None:
            return (-1, -1, -1)
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        layout = self._compute_layout(w, h)
        if not layout:
            return (-1, -1, -1)
        sub_origins = layout["sub_origins"]
        sub_heights = []
        for i, oy in enumerate(sub_origins):
            top = oy
            bottom = oy + layout["grid_h_per_row"]
            sub_heights.append((top, bottom))

        sub_idx = -1
        for i, (top, bottom) in enumerate(sub_heights):
            if top <= y < bottom:
                sub_idx = i
                break
        if sub_idx < 0:
            return (-1, -1, -1)

        ox = layout["ox"]
        cell = layout["cell"]
        spacing = layout["spacing"]
        if x < ox:
            return (-1, -1, -1)

        local_x = x - ox
        local_col_f = local_x / (cell + spacing)
        local_col = int(local_col_f)
        row_f = (y - sub_origins[sub_idx]) / (cell + spacing)
        row = int(row_f)

        cols_in_row = self._sub_cols[sub_idx]
        if local_col < 0 or local_col >= cols_in_row or row < 0 or row >= _ROWS:
            return (-1, -1, -1)
        cell_x = ox + local_col * (cell + spacing)
        cell_y = sub_origins[sub_idx] + row * (cell + spacing)
        if x >= cell_x + cell or y >= cell_y + cell:
            return (-1, -1, -1)

        global_col = self._sub_start_col[sub_idx] + local_col
        return (global_col, row, sub_idx)

    def _update_hover_rect(self, col: int, row: int, sub_idx: int) -> None:
        if col < 0 or row < 0 or sub_idx < 0 or self._hover_rect is None:
            return
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        layout = self._compute_layout(w, h)
        if not layout:
            return
        ox = layout["ox"]
        cell = layout["cell"]
        spacing = layout["spacing"]
        sub_oy = layout["sub_origins"][sub_idx]
        local_col = col - self._sub_start_col[sub_idx]
        x1 = ox + local_col * (cell + spacing)
        y1 = sub_oy + row * (cell + spacing)
        x2 = x1 + cell
        y2 = y1 + cell
        self._canvas.coords(self._hover_rect, x1, y1, x2, y2)
        self._canvas.itemconfigure(self._hover_rect, state="normal")

    def _show_tooltip(self, col: int, row: int) -> None:
        if self._start_dt is None or self._grid_start is None:
            return
        cell_date = self._grid_start + timedelta(days=col * 7 + row)
        delta = (cell_date - self._start_dt).days
        if 0 <= delta < self._days:
            value = self._daily_values[delta]
        else:
            value = 0

        date_str = cell_date.strftime("%Y-%m-%d")
        count_str = f"{value:,}"

        if self._tooltip is None:
            self._tooltip = _HeatmapTooltip(self)
        try:
            px = self._canvas.winfo_pointerx()
            py = self._canvas.winfo_pointery()
        except Exception:
            px, py = 0, 0
        self._tooltip.show(date_str, count_str, px, py)

    def _hide_tooltip(self) -> None:
        if self._tooltip is not None:
            self._tooltip.hide()

    def destroy(self):
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        super().destroy()


# ──── 悬停提示 ────
class _HeatmapTooltip:
    def __init__(self, parent):
        self._parent = parent
        self._win = tk.Toplevel(parent.winfo_toplevel())
        self._win.withdraw()
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)

        c = theme.current().colors
        self._frame = tk.Frame(
            self._win, bg=c.bg_tertiary, bd=0,
            highlightthickness=1, highlightbackground=c.border,
        )
        self._frame.pack()
        self._date_lbl = tk.Label(
            self._frame, text="", bg=c.bg_tertiary, fg=c.fg_primary,
            font=(_FONT_FAMILY, 10, "bold"),
        )
        self._date_lbl.pack(padx=8, pady=(4, 0))
        self._count_lbl = tk.Label(
            self._frame, text="", bg=c.bg_tertiary, fg=c.fg_secondary,
            font=(_FONT_FAMILY, 10),
        )
        self._count_lbl.pack(padx=8, pady=(0, 4))

    def show(self, date_str: str, count_str: str, x: int, y: int) -> None:
        c = theme.current().colors
        try:
            self._frame.configure(bg=c.bg_tertiary, highlightbackground=c.border)
            self._date_lbl.configure(text=date_str, bg=c.bg_tertiary, fg=c.fg_primary)
            self._count_lbl.configure(
                text=f"{count_str} 按键",
                bg=c.bg_tertiary, fg=c.fg_secondary,
            )
            self._win.update_idletasks()
            w = self._win.winfo_reqwidth()
            h = self._win.winfo_reqheight()
            sw = self._win.winfo_screenwidth()
            sh = self._win.winfo_screenheight()
            px = x + 14
            py = y + 14
            if px + w > sw:
                px = x - w - 14
            if py + h > sh:
                py = y - h - 14
            self._win.geometry(f"+{px}+{py}")
            self._win.deiconify()
        except Exception:
            pass

    def hide(self) -> None:
        try:
            self._win.withdraw()
        except Exception:
            pass

    def destroy(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass