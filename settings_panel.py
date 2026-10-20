"""声明式设置面板,由托盘菜单或主窗口 ⚙ 打开独立 Toplevel。

FieldSpec schema + GROUPS 描述所有控件,每项自带 build/read/write 三接口,
支持开关/滑块/下拉/路径/按钮等表单类型;行式布局(左标题+说明 / 右控件)+
搜索过滤 + 固定底栏保存,路径实时校验,悬停帮助提示。
"""
from __future__ import annotations

# ──── 常量与辅助函数 ────

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import customtkinter as ctk
import tkinter as tk

import config
import theme


# ──── 主题颜色(页内专属色,不进 theme) ────
_HELP_ICON = "#FAA817"

# 行右侧控件列宽(逻辑 px)
_CTRL_COL_W = 200
# 左栏说明文字换行宽度
_DESC_WRAP = 236


def _card_bg() -> str:
    return theme.current().colors.bg_secondary


def _panel_bg() -> str:
    return theme.current().colors.bg_primary


def _tip_bg() -> str:
    return theme.current().colors.bg_tertiary


def _tip_fg() -> str:
    return theme.current().colors.fg_primary


_REQUIRES_RESTART_KEYS = {
    "start_minimized", "listener_enabled", "silent_start",
    "mouse_listener_enabled",
    "backup_dir",
}

_REQUIRES_RESTART_HINT = "重启后生效"


_HINTS_BY_KEY: dict[str, str] = {
    "auto_start": "系统登录时自动启动 KeyNote,持续后台记录按键。",
    "silent_start": "完全静默启动,无窗口、无托盘通知(适合后台常驻)。",
    "hide_tray_icon": "隐藏系统托盘图标(极致隐身),仅靠热键/重启恢复。",
    "mouse_listener_enabled": "后台记录鼠标左/右/中键与侧键(X1/X2)点击次数,供键盘页副卡展示。",
    "backup_dir": "备份 .db 文件的目标目录,空=使用数据目录下的 backups/。",
}

_UNIT_BY_KEY: dict[str, str] = {
    "window_alpha": "",
}


def label_unit(key: str) -> str:
    return _UNIT_BY_KEY.get(key, "")


class _HoverTip:
    def __init__(self, anchor: ctk.CTkBaseClass, text: str) -> None:
        self._anchor = anchor
        self._text = text
        self._win: Any = None
        self._label: Any = None

    def show(self) -> None:
        if self._win is not None:
            try:
                self._label.configure(fg_color=_tip_bg(), text_color=_tip_fg())
            except Exception:
                pass
            return
        try:
            x = self._anchor.winfo_rootx() + 20
            y = self._anchor.winfo_rooty() + 24
        except Exception:
            return
        win = ctk.CTkToplevel(self._anchor)
        win.overrideredirect(True)
        win.geometry(f"+{x}+{y}")
        self._label = ctk.CTkLabel(
            win, text=self._text, fg_color=_tip_bg(), text_color=_tip_fg(),
            corner_radius=6, padx=10, pady=6, font=theme.FONTS["body"],
        )
        self._label.pack()
        self._win = win

    def hide(self) -> None:
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None
            self._label = None


# ──── 控件构建器 ────
@dataclass
class FieldSpec:
    """声明式控件描述:自带 build/read/write,行内含标题 + 常驻说明 + 控件。"""

    kind: str
    key: str
    label: str
    desc: str = ""
    hint: str = ""
    choices: Optional[list] = None
    lo: float = 0
    hi: float = 100
    step: float = 1
    requires_restart: bool = field(init=False)

    def __post_init__(self) -> None:
        self.requires_restart = self.key in _REQUIRES_RESTART_KEYS

    def build(self, parent: ctk.CTkBaseClass, panel: "SettingsPanel") -> ctk.CTkBaseClass:
        if self.kind == "switch":
            return self._build_switch(parent)
        if self.kind == "slider_int":
            return self._build_slider(parent, is_float=False)
        if self.kind == "slider_float":
            return self._build_slider(parent, is_float=True)
        if self.kind == "combo":
            return self._build_combo(parent)
        if self.kind == "combo_choices":
            return self._build_combo(parent, choices=self.choices or [])
        if self.kind == "path":
            return self._build_path(parent, panel)
        if self.kind == "text":
            return self._build_text(parent)
        if self.kind == "button":
            return self._build_button(parent, panel)
        raise ValueError(f"unknown field kind: {self.kind}")

    def read(self, ctrl: ctk.CTkBaseClass) -> Any:
        name = type(ctrl).__name__
        if name == "CTkSwitch":
            return bool(ctrl.get())
        if name == "CTkSlider":
            raw = float(ctrl.get())
            return round(raw, 2) if self.kind == "slider_float" else int(round(raw))
        if name == "CTkComboBox":
            return ctrl.get()
        if name == "CTkEntry":
            return ctrl.get().strip()
        return ctrl.get()

    def write(self, ctrl: ctk.CTkBaseClass, value: Any, panel: "SettingsPanel") -> None:
        name = type(ctrl).__name__
        if name == "CTkSwitch":
            ctrl.deselect()
            if value:
                ctrl.select()
            try:
                ctrl.configure(text="开" if value else "关")
            except Exception:
                pass
        elif name == "CTkSlider":
            try:
                ctrl.set(float(value))
            except Exception:
                ctrl.set(0)
            lbl = panel._value_labels.get(self.key)
            if lbl is not None:
                lbl.configure(text=self._format_slider_value(value))
        elif name == "CTkComboBox":
            ctrl.set(str(value))
        elif name == "CTkEntry":
            ctrl.delete(0, "end")
            if value:
                ctrl.insert(0, str(value))

    def _format_slider_value(self, value: Any) -> str:
        if self.kind == "slider_float":
            return f"{float(value):.2f}"
        return f"{int(round(float(value)))} {label_unit(self.key)}"

    def _build_switch(self, parent: ctk.CTkBaseClass) -> ctk.CTkSwitch:
        sw = ctk.CTkSwitch(
            parent, text="开", onvalue="开", offvalue="关",
            progress_color=theme.current().colors.accent,
            font=theme.FONTS["body"],
        )
        sw.pack(side="right")
        sw.configure(
            command=lambda s=sw: s.configure(text="开" if s.get() == "开" else "关")
        )
        return sw

    def _build_button(self, parent: ctk.CTkBaseClass, panel: "SettingsPanel") -> ctk.CTkButton:
        btn = ctk.CTkButton(
            parent, text="重启", width=80, height=28,
            corner_radius=theme.RADIUS["sm"],
            fg_color=theme.current().colors.bg_tertiary,
            hover_color=theme.current().colors.accent_hover,
            text_color=theme.current().colors.fg_primary,
            command=getattr(panel, f"_on_{self.key}", None),
        )
        btn.pack(side="right")
        return btn

    def _build_slider(self, parent: ctk.CTkBaseClass, is_float: bool) -> ctk.CTkSlider:
        steps = max(1, int(round((self.hi - self.lo) / max(self.step, 0.0001))))
        slider = ctk.CTkSlider(parent, from_=self.lo, to=self.hi, number_of_steps=steps)
        slider.pack(side="left", fill="x", expand=True)
        return slider

    def _build_combo(
        self, parent: ctk.CTkBaseClass, choices: Optional[list] = None
    ) -> ctk.CTkComboBox:
        values = choices if choices is not None else (self.choices or [])
        combo = ctk.CTkComboBox(parent, values=values, state="readonly", width=180)
        combo.pack(side="right")
        return combo

    def _build_text(self, parent: ctk.CTkBaseClass) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(parent, width=180)
        entry.pack(side="right")
        return entry

    def _build_path(self, parent: ctk.CTkBaseClass, panel: "SettingsPanel") -> ctk.CTkEntry:
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(side="right", fill="both", expand=True)

        row1 = ctk.CTkFrame(container, fg_color="transparent")
        row1.pack(fill="x")
        entry = ctk.CTkEntry(row1, placeholder_text="(默认 exe 同目录)", width=136)
        entry.pack(side="left", fill="x", expand=True)

        def _browse() -> None:
            from tkinter import filedialog

            initial = entry.get().strip() or str(config.exe_dir())
            initialdir = initial if Path(initial).is_dir() else str(config.exe_dir())
            chosen = filedialog.askdirectory(
                title=f"选择 {self.label}", initialdir=initialdir, mustexist=False
            )
            if chosen:
                entry.delete(0, "end")
                entry.insert(0, chosen)
                _validate()

        ctk.CTkButton(
            row1, text="浏览", width=52, height=28,
            corner_radius=theme.RADIUS["sm"],
            fg_color=theme.current().colors.bg_tertiary,
            hover_color=theme.current().colors.accent_hover,
            text_color=theme.current().colors.fg_primary,
            command=_browse,
        ).pack(side="right", padx=(6, 0))

        status_lbl = ctk.CTkLabel(
            container, text="", text_color=theme.current().colors.fg_muted,
            font=theme.FONTS["caption"], anchor="w",
        )
        status_lbl.pack(fill="x", pady=(2, 0))

        def _validate(_event: Any = None) -> None:
            v = entry.get().strip()
            if not v:
                entry.configure(border_color=ctk.ThemeManager.theme["CTkEntry"]["border_color"])
                status_lbl.configure(text="", text_color=theme.current().colors.fg_muted)
                return
            if Path(v).is_dir():
                entry.configure(border_color=theme.current().colors.success)
                status_lbl.configure(
                    text="✓ 路径有效", text_color=theme.current().colors.success
                )
            else:
                entry.configure(border_color=theme.current().colors.danger)
                status_lbl.configure(
                    text="⚠ 路径不存在,保存后重启会自动创建",
                    text_color=theme.current().colors.danger,
                )

        entry.bind("<FocusOut>", _validate)
        entry.bind("<KeyRelease>", _validate)
        panel._path_validators[self.key] = _validate
        return entry


# ──── 声明式字段列表 ────
GROUPS: list[tuple[str, list[FieldSpec]]] = [
    ("启动与常规", [
        FieldSpec(
            "switch", "auto_start", "开机自启动",
            desc="系统登录时自动启动 KeyNote,持续后台记录按键。",
        ),
        FieldSpec(
            "switch", "silent_start", "静默启动",
            desc="完全静默启动,无窗口、无托盘通知(适合后台常驻)。",
        ),
        FieldSpec(
            "switch", "hide_tray_icon", "隐藏托盘图标",
            desc="隐藏系统托盘图标(极致隐身),仅靠热键/重启恢复。",
        ),
        FieldSpec(
            "switch", "start_minimized", "启动时最小化",
            desc="开机后直接驻留托盘,不弹出主窗口。",
        ),
        FieldSpec(
            "switch", "close_to_tray", "关闭窗口到托盘",
            desc="点关闭按钮时最小化到托盘而不是退出程序。",
        ),
        FieldSpec(
            "switch", "listener_enabled", "启动时启动监听",
            desc="启动时开启全局键盘监听,关闭后不再记录按键。",
        ),
        FieldSpec(
            "switch", "mouse_listener_enabled", "记录鼠标点击",
            desc="后台记录鼠标左/右/中键与侧键(X1/X2)点击次数。",
        ),
    ]),
    ("界面", [
        FieldSpec(
            "slider_float", "window_alpha", "窗口透明度",
            desc="主窗口整体不透明度,0.6(全透) ~ 1.0(不透明)。",
            lo=0.6, hi=1.0, step=0.05,
        ),
        FieldSpec(
            "switch", "remember_window_pos", "记住窗口位置",
            desc="记住主窗口位置,下次启动恢复。",
        ),
    ]),
    ("数据", [
        FieldSpec(
            "path", "backup_dir", "备份目录",
            desc="备份 .db 文件的目标目录,空=使用数据目录下的 backups/。",
        ),
    ]),
]


# ──── 面板主体 ────
def open_or_focus(master, cfg: dict, on_save_callback) -> None:
    """创建或聚焦设置面板。重复调用不会重复创建,自动聚焦已有窗口。"""
    existing = getattr(master, "_settings_win", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass
        try:
            master._settings_win = None
        except Exception:
            pass
        try:
            master._settings_panel = None
        except Exception:
            pass

    top = ctk.CTkToplevel(master)
    top.title("KeyNote 设置")
    top.geometry("520x660")
    top.minsize(460, 480)
    top.resizable(True, True)
    top.grid_rowconfigure(0, weight=1)
    top.grid_columnconfigure(0, weight=1)

    panel = SettingsPanel(top, on_save_callback=on_save_callback)
    panel.grid(row=0, column=0, sticky="nsew")
    panel.build_footer(top)
    panel.load_values(cfg)

    def _on_close_settings():
        try:
            panel._on_save()
        except Exception:
            pass
        try:
            master._settings_win = None
        except Exception:
            pass
        try:
            master._settings_panel = None
        except Exception:
            pass
        try:
            top.destroy()
        except Exception:
            pass

    top.protocol("WM_DELETE_WINDOW", _on_close_settings)
    top.bind("<Escape>", lambda _e: _on_close_settings())
    master._settings_win = top
    master._settings_panel = panel


class SettingsPanel(ctk.CTkScrollableFrame):
    def __init__(self, master, on_save_callback: Optional[Callable[[dict], None]] = None):
        super().__init__(master, label_text="", fg_color=_panel_bg())
        self._on_save_callback = on_save_callback
        self._fields: dict[str, FieldSpec] = {}
        self._controls: dict[str, ctk.CTkBaseClass] = {}
        self._value_labels: dict[str, ctk.CTkLabel] = {}
        self._path_validators: dict[str, Callable[[], None]] = {}
        self._group_cards: list[ctk.CTkFrame] = []
        self._group_headers: list[ctk.CTkFrame] = []
        self._group_bars: list[ctk.CTkFrame] = []
        self._rows: dict[str, ctk.CTkFrame] = {}
        self._dividers: dict[str, ctk.CTkFrame] = {}
        self._groups: dict[str, dict] = {}
        self._desc_labels: list[tk.Label] = []
        self._empty_lbl: Optional[ctk.CTkLabel] = None
        self._footer: Optional[ctk.CTkFrame] = None
        self._save_status: Optional[ctk.CTkLabel] = None
        self._build()
        self.load_values(config.load())

    # ──── 构建 ────
    def _build(self) -> None:
        c = theme.current().colors
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 0))
        ctk.CTkLabel(
            header, text="设置", font=theme.FONTS["page_title"], text_color=c.fg_primary
        ).pack(anchor="w")
        ctk.CTkLabel(
            header, text="启动方式、界面与数据备份",
            font=theme.FONTS["label"], text_color=c.fg_secondary, anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        self._search = ctk.CTkEntry(
            self, placeholder_text="搜索设置项",
            font=theme.FONTS["body"], height=32,
        )
        self._search.grid(row=1, column=0, sticky="ew", padx=16, pady=(12, 0))
        self._search.bind("<KeyRelease>", self._on_search)

        row = 2
        for group_title, fields in GROUPS:
            header_frame = ctk.CTkFrame(self, fg_color="transparent")
            header_frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(14, 6))
            bar = ctk.CTkFrame(
                header_frame, width=3, height=14,
                corner_radius=2, fg_color=c.accent,
            )
            bar.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                header_frame, text=group_title,
                font=theme.FONTS["section_title"], text_color=c.fg_primary,
            ).pack(side="left")
            self._group_headers.append(header_frame)
            self._group_bars.append(bar)
            row += 1

            card = ctk.CTkFrame(
                self, fg_color=c.bg_secondary,
                corner_radius=theme.RADIUS["md"],
                border_width=1, border_color=c.border,
            )
            card.grid(row=row, column=0, sticky="ew", padx=16)
            card.grid_columnconfigure(0, weight=1)
            self._group_cards.append(card)
            row += 1

            prev_key = ""
            for idx, field_spec in enumerate(fields):
                if idx > 0:
                    divider = ctk.CTkFrame(card, height=1, fg_color=c.border)
                    divider.grid(row=idx * 2 - 1, column=0, sticky="ew", padx=14)
                    self._dividers[prev_key] = divider
                self._render_field(card, field_spec, row=idx * 2)
                prev_key = field_spec.key
            self._groups[group_title] = {"header": header_frame, "card": card}

        self._empty_lbl = ctk.CTkLabel(
            self, text="没有匹配的设置项",
            font=theme.FONTS["body"], text_color=c.fg_muted,
        )
        self._empty_lbl.grid(row=row, column=0, sticky="ew", padx=16, pady=(20, 0))
        self._empty_lbl.grid_remove()

    def _render_field(
        self, card: ctk.CTkFrame, field_spec: FieldSpec, row: int
    ) -> None:
        c = theme.current().colors
        line = ctk.CTkFrame(card, fg_color="transparent")
        line.grid(row=row, column=0, sticky="ew", padx=14, pady=10)
        line.grid_columnconfigure(0, weight=1)
        line.grid_columnconfigure(1, minsize=_CTRL_COL_W)

        left = ctk.CTkFrame(line, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")

        title_row = ctk.CTkFrame(left, fg_color="transparent")
        title_row.pack(anchor="w", fill="x")
        ctk.CTkLabel(
            title_row, text=field_spec.label,
            font=theme.FONTS["row_title"], text_color=c.fg_primary, anchor="w",
        ).pack(side="left")
        if field_spec.requires_restart:
            ctk.CTkLabel(
                title_row, text=_REQUIRES_RESTART_HINT,
                font=theme.FONTS["caption"], text_color=c.warning,
            ).pack(side="left", padx=(8, 0))
        tooltip_text = field_spec.hint or _HINTS_BY_KEY.get(field_spec.key, "")
        if tooltip_text:
            help_lbl = ctk.CTkLabel(
                title_row, text="?", text_color=_HELP_ICON,
                font=("", 11, "bold"), cursor="question_arrow",
            )
            help_lbl.pack(side="left", padx=(6, 0))
            tip = _HoverTip(title_row, tooltip_text)

            def _on_enter(_e, t=tip):
                t.show()

            def _on_leave(_e, t=tip):
                t.hide()

            help_lbl.bind("<Enter>", _on_enter)
            help_lbl.bind("<Leave>", _on_leave)

        if field_spec.desc:
            # 说明文字用原生 tk.Label:CTkLabel 不会按 wraplength 自增高度,换行会叠字
            desc_lbl = tk.Label(
                left, text=field_spec.desc, font=("", 12),
                bg=c.bg_secondary, fg=c.fg_secondary,
                anchor="w", justify="left", wraplength=_DESC_WRAP,
            )
            desc_lbl.pack(anchor="w", pady=(3, 0))
            self._desc_labels.append(desc_lbl)

        right = ctk.CTkFrame(line, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=(12, 0))

        ctrl = field_spec.build(right, self)
        self._fields[field_spec.key] = field_spec
        self._controls[field_spec.key] = ctrl
        self._rows[field_spec.key] = line

        if field_spec.kind in ("slider_int", "slider_float"):
            val_lbl = ctk.CTkLabel(
                right, text="", width=64, anchor="e",
                font=theme.FONTS["label"], text_color=c.fg_secondary,
            )
            val_lbl.pack(side="right", padx=(6, 0))

            def _on_change(_v: Any, fs: FieldSpec = field_spec, vl: ctk.CTkLabel = val_lbl) -> None:
                vl.configure(text=fs._format_slider_value(float(ctrl.get())))

            ctrl.configure(command=_on_change)
            self._value_labels[field_spec.key] = val_lbl

    # ──── 底栏(固定在 Toplevel 底部,不随内容滚动) ────
    def build_footer(self, host) -> None:
        c = theme.current().colors
        footer = ctk.CTkFrame(host, fg_color=c.bg_secondary, corner_radius=0)
        footer.grid(row=1, column=0, sticky="ew")
        self._footer = footer
        ctk.CTkFrame(footer, height=1, fg_color=c.border).pack(side="top", fill="x")

        self._save_status = ctk.CTkLabel(
            footer, text="", text_color=c.fg_muted, font=theme.FONTS["body"],
        )
        self._save_status.pack(side="left", padx=20)

        self._restore_btn = ctk.CTkButton(
            footer, text="恢复默认", width=96, height=30,
            corner_radius=theme.RADIUS["sm"],
            fg_color="transparent", border_width=1, border_color=c.border,
            text_color=c.fg_secondary, hover_color=c.bg_tertiary,
            font=theme.FONTS["body"], command=self._on_restore_defaults,
        )
        self._restore_btn.pack(side="right", padx=(0, 8), pady=10)

        self._save_btn = ctk.CTkButton(
            footer, text="保存设置", width=104, height=30,
            corner_radius=theme.RADIUS["sm"],
            fg_color=c.accent, hover_color=c.accent_hover,
            text_color="#FFFFFF", font=theme.FONTS["body"], command=self._on_save,
        )
        self._save_btn.pack(side="right", padx=(0, 16), pady=10)

    # ──── 搜索过滤 ────
    def _on_search(self, _event: Any = None) -> None:
        keyword = self._search.get().strip().lower()
        any_hit = False
        for group_title, fields in GROUPS:
            group_hit = keyword in group_title.lower()
            group = self._groups.get(group_title)
            if group is None:
                continue
            visible = 0
            for field_spec in fields:
                key = field_spec.key
                haystack = f"{field_spec.label} {field_spec.desc} {field_spec.hint}".lower()
                hit = group_hit or (keyword in haystack)
                row = self._rows.get(key)
                if row is None:
                    continue
                divider = self._dividers.get(key)
                if hit:
                    row.grid()
                    if divider is not None:
                        divider.grid()
                    visible += 1
                else:
                    row.grid_remove()
                    if divider is not None:
                        divider.grid_remove()
            if visible:
                group["header"].grid()
                group["card"].grid()
                any_hit = True
            else:
                group["header"].grid_remove()
                group["card"].grid_remove()
        if self._empty_lbl is not None:
            if any_hit:
                self._empty_lbl.grid_remove()
            else:
                self._empty_lbl.grid()

    # ──── 主题 ────
    def apply_theme(self) -> None:
        """重染面板所有 widget 颜色(保留接口,当前无主题切换,启动时调用一次)。"""
        c = theme.current().colors
        try:
            self.configure(fg_color=_panel_bg())
        except Exception:
            pass
        for card in self._group_cards:
            try:
                card.configure(fg_color=c.bg_secondary, border_color=c.border)
            except Exception:
                pass
        for lbl in self._desc_labels:
            try:
                lbl.configure(bg=c.bg_secondary, fg=c.fg_secondary)
            except Exception:
                pass
        for bar in self._group_bars:
            try:
                bar.configure(fg_color=c.accent)
            except Exception:
                pass
        for ctrl in self._controls.values():
            try:
                cls = type(ctrl).__name__
                if cls == "CTkSwitch":
                    ctrl.configure(progress_color=c.accent)
                elif cls == "CTkButton":
                    ctrl.configure(
                        fg_color=c.bg_tertiary,
                        text_color=c.fg_primary,
                        hover_color=c.accent_hover,
                        border_color=c.border,
                    )
            except Exception:
                pass
        for btn in (getattr(self, "_save_btn", None), getattr(self, "_restore_btn", None)):
            if btn is None:
                continue
            try:
                if btn is self._save_btn:
                    btn.configure(
                        fg_color=c.accent, hover_color=c.accent_hover, text_color="#FFFFFF"
                    )
                else:
                    btn.configure(
                        fg_color="transparent", border_color=c.border,
                        text_color=c.fg_secondary, hover_color=c.bg_tertiary,
                    )
            except Exception:
                pass
        try:
            if hasattr(self, "_save_status") and self._save_status is not None:
                self._save_status.configure(text_color=c.fg_muted)
        except Exception:
            pass
        if self._footer is not None:
            try:
                self._footer.configure(fg_color=c.bg_secondary)
            except Exception:
                pass

    # ──── 取值 / 保存 ────
    def _read_controls(self) -> dict:
        out: dict = {}
        for key, ctrl in self._controls.items():
            field_spec = self._fields[key]
            out[key] = field_spec.read(ctrl)
        return out

    def load_values(self, cfg: dict) -> None:
        for key, ctrl in self._controls.items():
            field_spec = self._fields[key]
            value = cfg.get(key, config.DEFAULTS.get(key))
            field_spec.write(ctrl, value, self)

        for validator in self._path_validators.values():
            try:
                validator()
            except Exception:
                pass

    def _set_status(self, text: str, color: str) -> None:
        """底栏状态提示(底栏未构建时静默忽略)。"""
        if self._save_status is None:
            return
        try:
            self._save_status.configure(text=text, text_color=color)
        except Exception:
            pass

    def _on_save(self) -> None:
        new_cfg = self._read_controls()
        old = config.load()
        merged = {**old, **new_cfg}
        c = theme.current().colors
        try:
            config.save(merged)
        except Exception as e:
            self._set_status(f"保存失败: {e}", c.danger)
            return
        if self._on_save_callback:
            try:
                self._on_save_callback(merged)
            except Exception as e:
                self._set_status(f"应用异常: {e}", c.warning)
                return
        self._set_status("✓ 已保存并应用", c.success)
        self.after(2500, lambda: self._set_status("", c.fg_muted))

    def _on_restore_defaults(self) -> None:
        self.load_values(config.DEFAULTS)
        new_cfg = dict(config.DEFAULTS)
        old = config.load()
        merged = {**old, **new_cfg}
        config.save(merged)
        if self._on_save_callback:
            self._on_save_callback(merged)
        c = theme.current().colors
        self._set_status("✓ 已恢复默认", c.success)
        self.after(2500, lambda: self._set_status("", c.fg_muted))
