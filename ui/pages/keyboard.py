"""后台页(Page 2):3 张 KPI 副卡 + 7×24 小时活跃度热力图 + QWERTY 键盘热力图"""
from __future__ import annotations

import math
import tkinter as tk

import customtkinter as ctk

import db
import theme
from ui.pages.base import BasePage
from ui.widgets.chart_utils import CanvasTip


# ──── QWERTY 键盘布局 ────
_KEY_ROWS = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
    ["z", "x", "c", "v", "b", "n", "m"],
]
_ROW_OFFSETS = [0.0, 0.5, 0.75, 1.25]
_KEY_SPACER_W = 5
_CN_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]
_MOUSE_BTN_CN = {
    "left": "左键",
    "right": "右键",
    "middle": "中键",
    "x1": "侧键 1",
    "x2": "侧键 2",
}

# ──── 键型分布胶囊(页内专属色,vigil-watt 徽标同款语义色) ────
_TYPE_META = {
    "letter": ("字母", "#0A84FF"),
    "digit": ("数字", "#34C759"),
    "symbol": ("符号", "#FAAA17"),
    "modifier": ("修饰键", "#BF5AF2"),
    "function": ("功能键", "#8E8E93"),
}


# ──── 颜色工具 ────
def _lerp_color(c0: tuple, c1: tuple, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r = round(c0[0] + (c1[0] - c0[0]) * t)
    g = round(c0[1] + (c1[1] - c0[1]) * t)
    b = round(c0[2] + (c1[2] - c0[2]) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


def _draw_scale_legend(
    cv: tk.Canvas, right_x: float, y: float, colors: list[str], s: float
) -> None:
    """色阶图例:少 → 多,靠右对齐。"""
    c = theme.current().colors
    box = max(6, min(10, round(9 * s)))
    gap = max(2, round(3 * s))
    text_w = round(11 * s)
    total = text_w + round(8 * s) + len(colors) * box + (len(colors) - 1) * gap + \
        round(8 * s) + text_w
    x = right_x - total
    cv.create_text(
        x, y + box / 2, text="少", anchor="w",
        fill=c.fg_muted, font=("", 9),
    )
    x += text_w + round(8 * s)
    for col in colors:
        cv.create_rectangle(x, y, x + box, y + box, fill=col, outline="")
        x += box + gap
    x += round(8 * s) - gap
    cv.create_text(
        x, y + box / 2, text="多", anchor="w",
        fill=c.fg_muted, font=("", 9),
    )


class KeyboardPage(BasePage):
    name = "keyboard"

    # ──── 构建 ────
    def _build(self) -> None:
        c = theme.current().colors
        s = getattr(self.app, "ui_scale", 1.0)
        self.configure(fg_color=c.bg_primary)
        self._tip = None
        self._h_layout = None
        self._h_grid = None
        self._kb_rects: list[tuple[str, int, int, int, int]] = []
        self._h_fp: bytes | None = None
        self._h_grid_data = None
        self._kb_fp: tuple | None = None
        self._sub_fp: tuple | None = None
        self._sub_last: tuple = (0, 0, 0)

        # ──── 页头(固定):标题 + 副标题 / 刷新按钮 ────
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 10))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        self._page_title = ctk.CTkLabel(
            titles, text="后台", font=theme.FONTS["page_title"], text_color=c.fg_primary
        )
        self._page_title.pack(anchor="w")
        self._page_sub = ctk.CTkLabel(
            titles, text="键盘与鼠标活动分布", font=theme.FONTS["label"],
            text_color=c.fg_secondary, anchor="w",
        )
        self._page_sub.pack(anchor="w", pady=(2, 0))
        self._refresh_btn = ctk.CTkButton(
            head, text="刷新", image=self.app.refresh_icon(), compound="left",
            width=64, height=28, corner_radius=theme.RADIUS["md"],
            fg_color="transparent", border_width=0,
            hover_color=c.bg_tertiary, command=self._on_refresh_click,
        )
        self._refresh_btn.pack(side="right", pady=(2, 0))

        # ──── 滚动内容 ────
        scroll = ctk.CTkScrollableFrame(self, fg_color=c.bg_primary)
        scroll.pack(fill="both", expand=True)
        self._scroll = scroll
        self._scroll._parent_canvas.bind(
            "<MouseWheel>", self._on_mousewheel, add="+"
        )

        # ──── 3 张 KPI 副卡 ────
        kpi_row = ctk.CTkFrame(scroll, fg_color="transparent")
        kpi_row.pack(fill="x", padx=16, pady=(0, 10))
        kpi_row.columnconfigure((0, 1, 2), weight=1, uniform="kpi")
        self._sub: dict[str, ctk.CTkLabel] = {}
        self._sub_foot: dict[str, ctk.CTkLabel] = {}
        for idx, (key, title) in enumerate([
            ("total", "累计按键"),
            ("mouse", "鼠标点击"),
            ("active", "活跃天数"),
        ]):
            card = ctk.CTkFrame(
                kpi_row, fg_color=c.bg_secondary,
                corner_radius=theme.RADIUS["md"],
                border_width=1, border_color=c.border,
            )
            card.grid(row=0, column=idx, padx=4, sticky="nsew")
            ctk.CTkLabel(
                card, text=title, font=theme.FONTS["label"],
                text_color=c.fg_secondary, anchor="w",
            ).pack(anchor="w", padx=10, pady=(8, 0))
            val = ctk.CTkLabel(
                card, text="—", font=theme.FONTS["kpi_value"],
                text_color=c.fg_primary, anchor="w",
            )
            val.pack(anchor="w", padx=10, pady=(1, 0))
            foot = ctk.CTkLabel(
                card, text="", font=theme.FONTS["caption"],
                text_color=c.fg_muted, anchor="w",
            )
            foot.pack(anchor="w", padx=10, pady=(1, 8))
            self._sub[key] = val
            self._sub_foot[key] = foot

        # ──── 键型分布胶囊行(vigil-watt 徽标同款;初始不打包,有数据才上屏) ────
        self._type_pill_row = ctk.CTkFrame(scroll, fg_color="transparent")
        self._type_pills: dict[str, ctk.CTkLabel] = {}
        for t_key in _TYPE_META:
            pill = ctk.CTkLabel(
                self._type_pill_row, text="", corner_radius=4,
                font=theme.FONTS["caption"], height=22,
            )
            pill.pack(side="left", padx=(0, 6), pady=1)
            self._type_pills[t_key] = pill
        self._type_fp: tuple | None = None

        # ──── 7×24 小时热力图卡 ────
        h_card = ctk.CTkFrame(
            scroll, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        h_card.pack(fill="x", padx=16, pady=(0, 10))
        self._h_card = h_card
        h_head = ctk.CTkFrame(h_card, fg_color="transparent")
        h_head.pack(fill="x", padx=14, pady=(10, 0))
        self._h_title_lbl = ctk.CTkLabel(
            h_head, text="7×24 小时活跃度", font=theme.FONTS["card_title"],
            text_color=c.fg_primary,
        )
        self._h_title_lbl.pack(side="left")
        self._h_summary_lbl = ctk.CTkLabel(
            h_head, text="", font=theme.FONTS["caption"], text_color=c.fg_muted
        )
        self._h_summary_lbl.pack(side="right")
        self._h_canvas = tk.Canvas(
            h_card, bg=c.bg_secondary, highlightthickness=0, height=round(140 * s)
        )
        self._h_canvas.pack(fill="x", padx=14, pady=(4, 12))
        self._h_canvas.bind("<Configure>", lambda _e: self._draw_hourly())
        self._h_canvas.bind("<Motion>", self._on_h_motion)
        self._h_canvas.bind("<Leave>", lambda _e: self._hide_tip())

        # ──── 键盘热力图卡 ────
        kb_card = ctk.CTkFrame(
            scroll, fg_color=c.bg_secondary,
            corner_radius=theme.RADIUS["md"],
            border_width=1, border_color=c.border,
        )
        kb_card.pack(fill="x", padx=16, pady=(0, 16))
        self._kb_card = kb_card
        kb_head = ctk.CTkFrame(kb_card, fg_color="transparent")
        kb_head.pack(fill="x", padx=14, pady=(10, 2))
        self._kb_title_lbl = ctk.CTkLabel(
            kb_head, text="按键分布热力图", font=theme.FONTS["card_title"],
            text_color=c.fg_primary,
        )
        self._kb_title_lbl.pack(side="left")
        self._kb_legend = ctk.CTkLabel(
            kb_head, text="", font=theme.FONTS["caption"], text_color=c.fg_muted
        )
        self._kb_legend.pack(side="right")
        self._kb_canvas = tk.Canvas(
            kb_card, bg=c.bg_secondary, highlightthickness=0, height=round(200 * s)
        )
        self._kb_canvas.pack(fill="x", padx=14, pady=(0, 12))
        self._kb_canvas.bind("<Configure>", lambda _e: self._draw_keyboard())
        self._kb_canvas.bind("<Motion>", self._on_kb_motion)
        self._kb_canvas.bind("<Leave>", lambda _e: self._hide_tip())
        self._kb_counts: dict[str, int] = {}
        self._kb_max = 0

    # ──── 交互 ────
    def _on_refresh_click(self) -> None:
        try:
            self.app.refresh()
        except Exception:
            pass

    def _on_mousewheel(self, event) -> str:
        delta = int(-1 * (event.delta / 120) * 3)
        try:
            self._scroll._parent_canvas.yview_scroll(delta, "units")
        except Exception:
            pass
        return "break"

    # ──── 刷新(带数据指纹,无变化跳过重绘) ────
    def _do_refresh(self) -> None:
        try:
            sub = (db.count_total(), db.mouse_total(), db.daily_active_days(30))
            if sub != self._sub_fp:
                self._sub_fp = sub
                prev = self._sub_last
                self._sub_last = sub
                self.animate_number(self._sub["total"], prev[0], sub[0])
                self.animate_number(self._sub["mouse"], prev[1], sub[1])
                self.animate_number(
                    self._sub["active"], prev[2], sub[2], suffix=" 天"
                )
                self._update_sub_foots()
        except Exception:
            pass

        try:
            self._update_type_pills()
        except Exception:
            pass

        try:
            grid = db.heatmap_data(7)
            if grid is not None and grid.size > 0:
                fp = grid.tobytes()
                if fp != self._h_fp:
                    self._h_fp = fp
                    self._draw_hourly(grid)
        except Exception:
            pass

        try:
            rows = db.top_keys(5000)
            fp = tuple(rows)
            if fp != self._kb_fp:
                self._kb_fp = fp
                self._kb_counts = {k.lower(): c for k, c in rows}
                self._kb_max = max(self._kb_counts.values(), default=0)
                if self._kb_max > 0:
                    top_key = max(self._kb_counts.items(), key=lambda kv: kv[1])
                    self._kb_legend.configure(
                        text=f"最高 {top_key[0].upper()} × {top_key[1]:,}"
                    )
                else:
                    self._kb_legend.configure(text="")
                self._draw_keyboard()
        except Exception:
            pass

    def _update_type_pills(self) -> None:
        """键型分布胶囊:彩字 + 16% tint 底(vigil-watt 徽标同款);无数据整行隐藏。"""
        rows = {str(t): int(n) for t, n in db.key_type_distribution()}
        total = sum(rows.values())
        fp = tuple(sorted(rows.items()))
        if fp == self._type_fp:
            return
        self._type_fp = fp
        if total <= 0:
            self._type_pill_row.pack_forget()
            return
        c = theme.current().colors
        self._type_pill_row.pack(
            fill="x", padx=16, pady=(0, 10), before=self._h_card
        )
        for t_key, (name, color) in _TYPE_META.items():
            pct = round(rows.get(t_key, 0) / total * 100)
            self._type_pills[t_key].configure(
                text=f" {name} {pct}% ",
                text_color=color,
                fg_color=theme.mix_hex(color, c.bg_primary, 0.16),
            )

    def _update_sub_foots(self) -> None:
        """副卡脚注:今日新增 / 鼠标主键占比 / 统计窗口。"""
        try:
            today = db.count_today()
            self._sub_foot["total"].configure(text=f"今日 +{today:,}")
        except Exception:
            pass
        try:
            rows = db.mouse_by_button()
            total = db.mouse_total()
            if rows and total > 0:
                button, cnt = rows[0]
                name = _MOUSE_BTN_CN.get(str(button).lower(), str(button))
                pct = round(int(cnt) / total * 100)
                self._sub_foot["mouse"].configure(text=f"{name} {pct}%")
            else:
                self._sub_foot["mouse"].configure(text="暂无数据")
        except Exception:
            pass
        try:
            self._sub_foot["active"].configure(text="近 30 天")
        except Exception:
            pass

    # ──── 7×24 渲染 ────
    def _draw_hourly(self, grid=None) -> None:
        c = theme.current().colors
        s = getattr(self.app, "ui_scale", 1.0)
        cv = self._h_canvas
        self._h_layout = None
        self._h_grid = None
        w = cv.winfo_width()
        h = cv.winfo_height()
        if w < 60 or h < 40:
            return
        cv.delete("all")

        if grid is None:
            grid = self._h_grid_data
        if grid is None:
            try:
                grid = db.heatmap_data(7)
            except Exception:
                return
        self._h_grid_data = grid
        if grid is None or grid.size == 0:
            return

        peak = int(grid.max()) if grid.size else 0
        total = int(grid.sum())

        # ──── 空态三段式:图标 + 主文案 + 说明(vigil-watt 空态同构) ────
        if total <= 0:
            self._h_layout = None
            self._h_grid = None
            needed = round(120 * s)
            if abs(h - needed) > 2:
                cv.configure(height=needed)
            cx, cy = w / 2, h / 2
            cv.create_text(
                cx, cy - round(30 * s), text="\uE787",
                fill=c.fg_muted, font=("Segoe MDL2 Assets", 22),
            )
            cv.create_text(
                cx, cy + round(6 * s), text="近 7 天还没有记录",
                fill=c.fg_secondary, font=("", 12),
            )
            cv.create_text(
                cx, cy + round(26 * s), text="开始打字后,这里会按小时点亮",
                fill=c.fg_muted, font=("", 10),
            )
            try:
                self._h_summary_lbl.configure(text="")
            except Exception:
                pass
            return

        margin_x = round(24 * s)
        cols = 24
        rows = 7
        gap = 1
        pad_y = round(8 * s)
        label_h = round(12 * s)
        legend_h = round(16 * s)
        usable_w = max(round(40 * s), w - margin_x - 4)
        cell = max(round(10 * s), min(round(22 * s), (usable_w - (cols - 1) * gap) / cols))
        grid_w = cols * cell + (cols - 1) * gap
        grid_h = rows * cell + (rows - 1) * gap
        content_h = grid_h + 2 + label_h + legend_h
        needed = int(content_h + pad_y * 2)
        if abs(h - needed) > 2:
            cv.configure(height=needed)
        ox = margin_x + max(0, (usable_w - grid_w) / 2)
        oy = max(pad_y, (h - content_h) / 2)
        self._h_layout = (ox, oy, cell, cell, gap)
        self._h_grid = grid

        def _bucket(val: int) -> str:
            if val <= 0 or peak <= 0:
                return c.heatmap_empty
            r = val / peak
            if r <= 0.25:
                return c.heatmap_l1
            if r <= 0.50:
                return c.heatmap_l2
            if r <= 0.75:
                return c.heatmap_l3
            return c.heatmap_l4

        for dow in range(rows):
            ty = oy + dow * (cell + gap) + cell / 2
            cv.create_text(6, ty, text=_CN_WEEKDAYS[dow], anchor="w",
                           fill=c.fg_muted, font=("", 9))
            for hour in range(cols):
                x1 = ox + hour * (cell + gap)
                y1 = oy + dow * (cell + gap)
                val = int(grid[dow, hour])
                cv.create_rectangle(
                    x1, y1, x1 + cell, y1 + cell,
                    fill=_bucket(val), outline="", width=0,
                )

        for hr in (0, 6, 12, 18, 23):
            tx = ox + hr * (cell + gap) + cell / 2
            cv.create_text(tx, oy + grid_h + 2, text=str(hr), anchor="n",
                           fill=c.fg_muted, font=("", 8))

        legend_y = oy + grid_h + 2 + label_h
        _draw_scale_legend(
            cv, ox + grid_w, legend_y,
            [c.heatmap_empty, c.heatmap_l1, c.heatmap_l2, c.heatmap_l3, c.heatmap_l4],
            s,
        )

        try:
            active = int((grid > 0).sum())
            self._h_summary_lbl.configure(
                text=f"活跃 {active}/168 桶 · 峰值 {peak:,}"
            )
        except Exception:
            pass

    # ──── QWERTY 渲染 ────
    def _draw_keyboard(self) -> None:
        c = theme.current().colors
        s = getattr(self.app, "ui_scale", 1.0)
        cv = self._kb_canvas
        cv.delete("all")
        cv.configure(bg=c.bg_secondary)
        self._kb_rects = []
        w = cv.winfo_width()
        if w < 50 or cv.winfo_height() < 100:
            return

        gap = round(5 * s)
        max_cols = max(len(r) for r in _KEY_ROWS)
        cell_w = max(
            round(20 * s),
            min(round(30 * s), (w - round(8 * s) - (max_cols - 1) * gap) // max_cols),
        )
        cell_h = round(30 * s)
        grid_w = max_cols * cell_w + (max_cols - 1) * gap
        start_x = (w - grid_w) // 2

        base_rgb = theme.hex_to_rgb(c.bg_tertiary)
        peak_rgb = theme.hex_to_rgb(c.accent)

        def color_for(key: str) -> str:
            count = self._kb_counts.get(key, 0)
            if self._kb_max <= 0 or count == 0:
                return c.bg_tertiary
            t = math.pow(count / self._kb_max, 0.5)
            return _lerp_color(base_rgb, peak_rgb, t)

        y = round(8 * s)
        for row_idx, row in enumerate(_KEY_ROWS):
            ox = start_x + _ROW_OFFSETS[row_idx] * (cell_w + gap) / 2
            for k_idx, key in enumerate(row):
                x0 = ox + k_idx * (cell_w + gap)
                y0 = y
                x1 = x0 + cell_w
                y1 = y0 + cell_h
                fill = color_for(key)
                cv.create_rectangle(
                    x0, y0, x1, y1,
                    fill=fill, outline=c.border, width=1,
                )
                cv.create_text(
                    (x0 + x1) // 2, (y0 + y1) // 2,
                    text=key.upper(), fill=c.fg_primary, font=("", 10, "bold"),
                )
                self._kb_rects.append((key, int(x0), int(y0), int(x1), int(y1)))
            y += cell_h + gap

        space_count = self._kb_counts.get("space", 0)
        space_w = cell_w * _KEY_SPACER_W + (_KEY_SPACER_W - 1) * gap
        sx0 = (w - space_w) // 2
        sx1 = sx0 + space_w
        sy0 = y
        sy1 = sy0 + cell_h
        if self._kb_max > 0 and space_count > 0:
            t = math.pow(space_count / self._kb_max, 0.5)
            spc_fill = _lerp_color(base_rgb, peak_rgb, t)
        else:
            spc_fill = c.bg_tertiary
        cv.create_rectangle(
            sx0, sy0, sx1, sy1,
            fill=spc_fill, outline=c.border, width=1,
        )
        cv.create_text(
            (sx0 + sx1) // 2, (sy0 + sy1) // 2,
            text="SPACE", fill=c.fg_primary, font=("", 9, "bold"),
        )
        self._kb_rects.append(("space", int(sx0), int(sy0), int(sx1), int(sy1)))

        legend_y = sy1 + round(4 * s)
        legend_colors = [
            _lerp_color(base_rgb, peak_rgb, t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]
        _draw_scale_legend(cv, sx1, legend_y, legend_colors, s)
        cv.configure(height=int(legend_y + round(14 * s)))

        if self._kb_max <= 0:
            cv.create_text(
                w / 2, (sy0 - round(8 * s)) / 2, text="还没有按键记录",
                fill=c.fg_muted, font=("", 10),
            )

    # ──── canvas 悬停提示 ────
    def _show_tip(self, text: str, x: int, y: int) -> None:
        if self._tip is None:
            c = theme.current().colors
            self._tip = CanvasTip(
                self, bg=c.bg_tertiary, fg=c.fg_primary,
                border=c.border, bold=False,
            )
        self._tip.show(text, x, y)

    def _hide_tip(self) -> None:
        if self._tip is not None:
            self._tip.hide()

    def _on_h_motion(self, event) -> None:
        layout = self._h_layout
        grid = self._h_grid
        if layout is None or grid is None:
            return
        ox, oy, cell_w, cell_h, gap = layout
        col = int((event.x - ox) // (cell_w + gap))
        row = int((event.y - oy) // (cell_h + gap))
        if not (0 <= col < 24 and 0 <= row < 7):
            self._hide_tip()
            return
        cell_x = ox + col * (cell_w + gap)
        cell_y = oy + row * (cell_h + gap)
        if event.x > cell_x + cell_w or event.y > cell_y + cell_h:
            self._hide_tip()
            return
        val = int(grid[row, col])
        self._show_tip(
            f"周{_CN_WEEKDAYS[row]} {col}:00 · {val:,} 按键",
            self._h_canvas.winfo_pointerx(), self._h_canvas.winfo_pointery(),
        )

    def _on_kb_motion(self, event) -> None:
        for key, x0, y0, x1, y1 in self._kb_rects:
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                count = int(self._kb_counts.get(key, 0))
                label = "Space" if key == "space" else key.upper()
                if self._kb_max > 0 and count > 0:
                    pct = round(count / self._kb_max * 100)
                    text = f"{label} · {count:,} 次 · 占峰值 {pct}%"
                else:
                    text = f"{label} · 0 次"
                self._show_tip(
                    text,
                    self._kb_canvas.winfo_pointerx(), self._kb_canvas.winfo_pointery(),
                )
                return
        self._hide_tip()

    def _do_apply_theme(self) -> None:
        c = theme.current().colors
        try:
            self.configure(fg_color=c.bg_primary)
            if hasattr(self, "_scroll"):
                self._scroll.configure(fg_color=c.bg_primary)
            if hasattr(self, "_h_canvas"):
                self._h_canvas.configure(bg=c.bg_secondary)
            if hasattr(self, "_kb_canvas"):
                self._kb_canvas.configure(bg=c.bg_secondary)
            if hasattr(self, "_kb_card"):
                self._kb_card.configure(
                    fg_color=c.bg_secondary, border_color=c.border
                )
            if hasattr(self, "_h_card"):
                self._h_card.configure(
                    fg_color=c.bg_secondary, border_color=c.border
                )
            try:
                self._type_fp = None
                self._update_type_pills()
            except Exception:
                pass
            self._kb_title_lbl.configure(text_color=c.fg_primary)
            self._kb_legend.configure(text_color=c.fg_muted)
            self._h_title_lbl.configure(text_color=c.fg_primary)
            self._h_summary_lbl.configure(text_color=c.fg_muted)
        except Exception:
            pass
        self._draw_hourly()
        self._draw_keyboard()
