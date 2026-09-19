"""声明式设置面板,由托盘菜单或页面打开独立 Toplevel。FieldSpec schema + GROUPS 描述所有控件,每项自带 build/read/write 三接口,支持开关/滑块/下拉/路径/按钮等表单类型,路径实时校验,悬停帮助提示,CSV 导出"""
from __future__ import annotations

# ──── 常量与辅助函数 ────

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import customtkinter as ctk

import config
import theme


# ──── 主题颜色(从 theme 取,不写死) ────
_TOGGLE_ACTIVE = "#2196F3"
_HELP_ICON = "#FFB300"


def _card_bg() -> str:
    return theme.current().colors.bg_secondary


def _panel_bg() -> str:
    return theme.current().colors.bg_primary


def _tip_bg() -> str:
    return theme.current().colors.bg_secondary


def _tip_fg() -> str:
    return theme.current().colors.fg_primary


_REQUIRES_RESTART_KEYS = {
    "start_minimized", "listener_enabled", "silent_start",
    "mouse_listener_enabled",
    "backup_dir",
}

_REQUIRES_RESTART_HINT = "(重启后生效)"


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
            corner_radius=6, padx=10, pady=6, font=("", 10),
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
    """声明式控件描述:自带 build/read/write,标签自动加 🔄 重启标记。"""

    kind: str
    key: str
    label: str
    hint: str = ""
    choices: Optional[list] = None
    lo: float = 0
    hi: float = 100
    step: float = 1
    requires_restart: bool = field(init=False)

    def __post_init__(self) -> None:
        self.requires_restart = self.key in _REQUIRES_RESTART_KEYS

    def display_label(self) -> str:
        suffix = f" 🔄 {_REQUIRES_RESTART_HINT}" if self.requires_restart else ""
        return f"{self.label}{suffix}"

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
        right = parent
        sw = ctk.CTkSwitch(right, text="", progress_color=_TOGGLE_ACTIVE)
        sw.pack(side="right", padx=8)
        return sw

    def _build_button(self, parent: ctk.CTkBaseClass, panel: "SettingsPanel") -> ctk.CTkButton:
        right = parent
        btn = ctk.CTkButton(right, text="重启", width=80, command=getattr(panel, f"_on_{self.key}", None))
        btn.pack(side="right", padx=8)
        return btn

    def _build_slider(self, parent: ctk.CTkBaseClass, is_float: bool) -> ctk.CTkSlider:
        right = parent
        steps = max(1, int(round((self.hi - self.lo) / max(self.step, 0.0001))))
        slider = ctk.CTkSlider(right, from_=self.lo, to=self.hi, number_of_steps=steps)
        slider.pack(side="left", fill="x", expand=True, padx=8)
        return slider

    def _build_combo(
        self, parent: ctk.CTkBaseClass, choices: Optional[list] = None
    ) -> ctk.CTkComboBox:
        right = parent
        values = choices if choices is not None else (self.choices or [])
        combo = ctk.CTkComboBox(right, values=values, state="readonly", width=150)
        combo.pack(side="right", padx=8)
        return combo

    def _build_text(self, parent: ctk.CTkBaseClass) -> ctk.CTkEntry:
        right = parent
        entry = ctk.CTkEntry(right, width=200)
        entry.pack(side="right", padx=8, fill="x", expand=True)
        return entry

    def _build_path(self, parent: ctk.CTkBaseClass, panel: "SettingsPanel") -> ctk.CTkEntry:
        right = parent

        container = ctk.CTkFrame(right, fg_color="transparent")
        container.pack(side="left", fill="both", expand=True, padx=(8, 4))

        row1 = ctk.CTkFrame(container, fg_color="transparent")
        row1.pack(fill="x")
        entry = ctk.CTkEntry(row1, placeholder_text="(默认 exe 同目录)", width=260)
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

        ctk.CTkButton(row1, text="📂 浏览", width=70, command=_browse).pack(
            side="right", padx=(6, 0)
        )

        status_lbl = ctk.CTkLabel(
            container, text="", text_color="gray", font=("", 10), anchor="w"
        )
        status_lbl.pack(fill="x", pady=(2, 0))

        def _validate(_event: Any = None) -> None:
            v = entry.get().strip()
            if not v:
                entry.configure(border_color=ctk.ThemeManager.theme["CTkEntry"]["border_color"])
                status_lbl.configure(text="", text_color="gray")
                return
            if Path(v).is_dir():
                entry.configure(border_color="#2ecc71")
                status_lbl.configure(text="✓ 路径有效", text_color="#2ecc71")
            else:
                entry.configure(border_color="#e74c3c")
                status_lbl.configure(text="⚠ 路径不存在,保存后重启 KeyNote 会自动创建", text_color="#e74c3c")

        entry.bind("<FocusOut>", _validate)
        entry.bind("<KeyRelease>", _validate)
        panel._path_validators[self.key] = _validate
        return entry


# ──── 声明式字段列表 ────
GROUPS: list[tuple[str, list[FieldSpec]]] = [
    ("常规设置", [
        FieldSpec("switch", "auto_start", "开机自启动"),
        FieldSpec("switch", "silent_start", "静默启动"),
        FieldSpec("switch", "hide_tray_icon", "隐藏托盘图标"),
        FieldSpec("switch", "start_minimized", "启动时最小化"),
        FieldSpec("switch", "close_to_tray", "关闭窗口到托盘"),
        FieldSpec("switch", "listener_enabled", "启动时启动监听"),
        FieldSpec("switch", "mouse_listener_enabled", "记录鼠标点击"),
    ]),
    ("界面", [
        FieldSpec("slider_float", "window_alpha", "窗口透明度 (0.6 ~ 1.0)", lo=0.6, hi=1.0, step=0.05),
        FieldSpec("switch", "remember_window_pos", "记住窗口位置"),
    ]),
    ("数据", [
        FieldSpec("path", "backup_dir", "备份目录"),
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
    top.geometry("400x480")
    top.resizable(False, False)
    panel = SettingsPanel(top, on_save_callback=on_save_callback)
    panel.pack(fill="both", expand=True)
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
        self._group_frames: list[ctk.CTkFrame] = []
        self._build()
        self.load_values(config.load())

    def _build(self) -> None:
        for group_title, fields in GROUPS:
            self._build_group(group_title, fields)
        self._build_footer()

    def _build_group(self, title: str, fields: list[FieldSpec]) -> None:
        frame = ctk.CTkFrame(self, fg_color=_card_bg(), corner_radius=12)
        self._group_frames.append(frame)
        frame.pack(fill="x", padx=5, pady=(8, 4))
        ctk.CTkLabel(
            frame, text=title, font=("", 14, "bold"), anchor="w"
        ).pack(fill="x", padx=12, pady=(8, 4))

        for field_spec in fields:
            self._render_field(frame, field_spec)

    def apply_theme(self) -> None:
        """重染面板所有 widget 颜色(保留接口,当前无主题切换,启动时调用一次)。"""
        c = theme.current().colors
        try:
            self.configure(fg_color=_panel_bg())
        except Exception:
            pass
        for f in self._group_frames:
            try:
                f.configure(fg_color=_card_bg())
            except Exception:
                pass
        for ctrl in self._controls.values():
            try:
                cls = type(ctrl).__name__
                if cls == "CTkSwitch":
                    ctrl.configure(progress_color=_TOGGLE_ACTIVE)
                elif cls == "CTkButton":
                    ctrl.configure(
                        fg_color=c.bg_secondary,
                        text_color=c.fg_primary,
                        hover_color=c.bg_tertiary,
                        border_color=c.border,
                    )
            except Exception:
                pass
        for btn in (getattr(self, "_save_btn", None), getattr(self, "_restore_btn", None)):
            if btn is None:
                continue
            try:
                btn.configure(
                    fg_color=c.bg_secondary,
                    text_color=c.fg_primary,
                    hover_color=c.bg_tertiary,
                    border_color=c.border,
                )
            except Exception:
                pass
        try:
            if hasattr(self, "_save_status") and self._save_status is not None:
                self._save_status.configure(text_color=c.fg_muted)
        except Exception:
            pass

    def _render_field(self, group_frame: ctk.CTkBaseClass, field_spec: FieldSpec) -> None:
        row = ctk.CTkFrame(group_frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=3)

        label_text = field_spec.display_label()
        lbl = ctk.CTkLabel(row, text=label_text, anchor="w", width=240)
        lbl.pack(side="left", padx=(4, 4))

        tooltip_text = field_spec.hint or _HINTS_BY_KEY.get(field_spec.key, "")
        if tooltip_text:
            help_lbl = ctk.CTkLabel(
                row, text="?", text_color=_HELP_ICON, width=18,
                font=("", 11, "bold"), cursor="question_arrow"
            )
            help_lbl.pack(side="left", padx=(0, 8))

            tip = _HoverTip(row, tooltip_text)

            def _on_enter(_e, t=tip):
                t.show()

            def _on_leave(_e, t=tip):
                t.hide()

            help_lbl.bind("<Enter>", _on_enter)
            help_lbl.bind("<Leave>", _on_leave)

        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True)

        ctrl = field_spec.build(right, self)
        self._fields[field_spec.key] = field_spec
        self._controls[field_spec.key] = ctrl

        if field_spec.kind in ("slider_int", "slider_float"):
            val_lbl = ctk.CTkLabel(right, text="", width=72, anchor="e")
            val_lbl.pack(side="right", padx=8)

            def _on_change(_v: Any, fs: FieldSpec = field_spec, vl: ctk.CTkLabel = val_lbl) -> None:
                vl.configure(text=fs._format_slider_value(float(ctrl.get())))

            ctrl.configure(command=_on_change)
            self._value_labels[field_spec.key] = val_lbl

    def _make_row(self, parent, label_text: str) -> tuple:
        row = ctk.CTkFrame(parent)
        row.pack(fill="x", padx=12, pady=3)
        lbl = ctk.CTkLabel(row, text=label_text, anchor="w", width=260)
        lbl.pack(side="left", padx=(4, 8))
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True)
        return row, right

    def _build_footer(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=5, pady=(12, 8))
        bar = ctk.CTkFrame(frame)
        bar.pack(fill="x", padx=12, pady=8)

        self._save_btn = ctk.CTkButton(
            bar, text="💾 保存并应用", command=self._on_save, width=140
        )
        self._save_btn.pack(side="left", padx=6)
        self._restore_btn = ctk.CTkButton(
            bar, text="🔄 恢复默认", command=self._on_restore_defaults, width=120
        )
        self._restore_btn.pack(side="left", padx=6)
        c = theme.current().colors
        self._save_status = ctk.CTkLabel(bar, text="", text_color=c.fg_muted)
        self._save_status.pack(side="right", padx=12)

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

    def _on_save(self) -> None:
        new_cfg = self._read_controls()
        old = config.load()
        merged = {**old, **new_cfg}
        try:
            config.save(merged)
        except Exception as e:
            self._save_status.configure(text=f"保存失败: {e}", text_color="red")
            return
        if self._on_save_callback:
            try:
                self._on_save_callback(merged)
            except Exception as e:
                self._save_status.configure(text=f"应用异常: {e}", text_color="orange")
                return
        self._save_status.configure(text="✓ 已保存并应用", text_color="green")
        self.after(2500, lambda: self._save_status.configure(text=""))

    def _on_restore_defaults(self) -> None:
        self.load_values(config.DEFAULTS)
        new_cfg = dict(config.DEFAULTS)
        old = config.load()
        merged = {**old, **new_cfg}
        config.save(merged)
        if self._on_save_callback:
            self._on_save_callback(merged)
        self._save_status.configure(text="✓ 已恢复默认", text_color="green")
        self.after(2500, lambda: self._save_status.configure(text=""))