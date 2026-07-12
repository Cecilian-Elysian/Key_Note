"""声明式设置面板,由托盘菜单或页面打开独立 Toplevel。FieldSpec schema + GROUPS 描述所有控件,每项自带 build/read/write 三接口,支持开关/滑块/下拉/路径/按钮等表单类型,路径实时校验,悬停帮助提示,CSV 导出"""
from __future__ import annotations

# ──── 常量与辅助函数 ────

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import customtkinter as ctk

import config


_CARD_BG = "#2A2A2A"
_TOGGLE_ACTIVE = "#2196F3"
_HELP_ICON = "#FFB300"


_REQUIRES_RESTART_KEYS = {
    "theme", "font_family", "data_dir", "log_to_file",
    "start_minimized", "listener_enabled", "silent_start",
}

_REQUIRES_RESTART_HINT = "(重启后生效)"


_HINTS_BY_KEY: dict[str, str] = {
    "auto_start": "系统登录时自动启动 KeyNote,持续后台记录按键。",
    "silent_start": "完全静默启动,无窗口、无托盘通知(适合后台常驻)。",
    "hide_tray_icon": "隐藏系统托盘图标(极致隐身),仅靠热键/重启恢复。",
    "edge_snap": "窗口拖到屏幕边缘时自动贴边收纳。",
    "admin_restart": "键盘钩子通常需要管理员权限,点击以重启 KeyNote。",
}

_RETENTION_CHOICES = [
    ("永久", 0),
    ("7 天", 7),
    ("180 天", 180),
    ("365 天", 365),
    ("730 天", 730),
]
_FONT_CHOICES = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans SC",
    "PingFang SC",
    "Arial",
    "System Default",
]
_HOTKEY_CHOICES = [
    "ctrl+shift+k",
    "ctrl+alt+k",
    "alt+shift+k",
    "ctrl+shift+s",
    "ctrl+alt+s",
]


_UNIT_BY_KEY: dict[str, str] = {
    "refresh_interval_sec": "秒",
    "heatmap_days": "天",
    "rate_chart_hours": "小时",
    "idle_pause_min": "分钟",
    "db_auto_backup_days": "天",
    "backup_keep_daily": "份",
    "backup_keep_weekly": "份",
    "db_flush_batch_size": "条",
    "db_flush_interval_sec": "秒",
    "window_alpha": "",
}


def label_unit(key: str) -> str:
    return _UNIT_BY_KEY.get(key, "")


def _retention_label_to_int(label: str) -> int:
    for n, d in _RETENTION_CHOICES:
        if n == label:
            return d
    return 7


def _retention_int_to_label(v: int) -> str:
    for n, d in _RETENTION_CHOICES:
        if d == v:
            return n
    return "7 天"


class _HoverTip:
    def __init__(self, anchor: ctk.CTkBaseClass, text: str) -> None:
        self._anchor = anchor
        self._text = text
        self._win: Any = None

    def show(self) -> None:
        if self._win is not None:
            return
        try:
            x = self._anchor.winfo_rootx() + 20
            y = self._anchor.winfo_rooty() + 24
        except Exception:
            return
        win = ctk.CTkToplevel(self._anchor)
        win.overrideredirect(True)
        win.geometry(f"+{x}+{y}")
        ctk.CTkLabel(
            win, text=self._text, fg_color="#222222", text_color="#F5F5F5",
            corner_radius=6, padx=10, pady=6, font=("", 10),
        ).pack()
        self._win = win

    def hide(self) -> None:
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None


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
            v = ctrl.get()
            if self.key == "db_retention_days":
                return _retention_label_to_int(v)
            return v
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
            if self.key == "db_retention_days":
                ctrl.set(_retention_int_to_label(int(value)))
            else:
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
        if self.key == "db_retention_days":
            values = [n for n, _ in _RETENTION_CHOICES]
        combo = ctk.CTkComboBox(right, values=values, state="readonly")
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
        FieldSpec("switch", "edge_snap", "贴边自动收纳"),
        FieldSpec("switch", "start_minimized", "启动时最小化"),
        FieldSpec("switch", "close_to_tray", "关闭窗口到托盘"),
        FieldSpec("switch", "listener_enabled", "启动时启动监听"),
        FieldSpec("slider_int", "idle_pause_min", "闲置 N 分钟自动暂停 (0=禁用)", lo=0, hi=60),
        FieldSpec("button", "admin_restart", "以管理员身份重启"),
    ]),
    ("全局热键", [
        FieldSpec("switch", "enable_global_hotkey", "启用全局热键切换主窗口"),
        FieldSpec("combo_choices", "global_hotkey", "热键组合", choices=_HOTKEY_CHOICES),
    ]),
    ("界面", [
        FieldSpec("combo", "theme", "主题", choices=["dark", "light"]),
        FieldSpec("combo_choices", "font_family", "字体", choices=_FONT_CHOICES),
        FieldSpec("slider_float", "window_alpha", "窗口透明度 (0.6 ~ 1.0)", lo=0.6, hi=1.0, step=0.05),
        FieldSpec("switch", "remember_window_pos", "记住窗口位置"),
    ]),
    ("高级功能", [
        FieldSpec("switch", "chart_auto_refresh", "图表自动刷新"),
        FieldSpec("slider_int", "refresh_interval_sec", "刷新间隔", lo=1, hi=60),
        FieldSpec("slider_int", "heatmap_days", "热力图统计天数", lo=1, hi=365),
        FieldSpec("slider_int", "rate_chart_hours", "速率图小时数", lo=1, hi=168),
    ]),
    ("数据库与备份", [
        FieldSpec("combo", "db_retention_days", "原始数据保留"),
        FieldSpec("path", "data_dir", "数据存储目录",
                  hint="留空=默认 exe 同目录。点击 📂 浏览选择文件夹"),
        FieldSpec("slider_int", "db_auto_backup_days", "自动备份间隔", lo=1, hi=30),
        FieldSpec("slider_int", "backup_keep_daily", "日备份保留份数", lo=1, hi=30),
        FieldSpec("slider_int", "backup_keep_weekly", "周备份保留份数", lo=0, hi=12),
        FieldSpec("slider_int", "db_flush_batch_size", "批量写入大小", lo=50, hi=2000),
        FieldSpec("slider_float", "db_flush_interval_sec", "写入间隔", lo=0.1, hi=10.0, step=0.1),
    ]),
    ("数据导出 / 日志", [
        FieldSpec("switch", "log_to_file", "启用日志写入 keynote.log"),
    ]),
]


# ──── 面板主体 ────
class SettingsPanel(ctk.CTkScrollableFrame):
    def __init__(self, master, on_save_callback: Optional[Callable[[dict], None]] = None):
        super().__init__(master, label_text="", fg_color="#1E1E1E")
        self._on_save_callback = on_save_callback
        self._fields: dict[str, FieldSpec] = {}
        self._controls: dict[str, ctk.CTkBaseClass] = {}
        self._value_labels: dict[str, ctk.CTkLabel] = {}
        self._path_validators: dict[str, Callable[[], None]] = {}
        self._export_btn: Optional[ctk.CTkButton] = None
        self._build()
        self.load_values(config.load())

    def _build(self) -> None:
        for group_title, fields in GROUPS:
            self._build_group(group_title, fields)
        self._build_export_section()
        self._build_footer()

    def _build_group(self, title: str, fields: list[FieldSpec]) -> None:
        frame = ctk.CTkFrame(self, fg_color=_CARD_BG, corner_radius=12)
        frame.pack(fill="x", padx=5, pady=(8, 4))
        ctk.CTkLabel(
            frame, text=title, font=("", 14, "bold"), anchor="w"
        ).pack(fill="x", padx=12, pady=(8, 4))

        for field_spec in fields:
            self._render_field(frame, field_spec)

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

    def _build_export_section(self) -> None:
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=5, pady=4)
        row, right = self._make_row(frame, "导出过去 30 天的按键记录到 CSV")
        btn = ctk.CTkButton(right, text="📤 导出 CSV", width=140)
        btn.pack(side="right", padx=8)
        btn.configure(command=self._on_export_csv)
        self._export_btn = btn
        self._export_status = ctk.CTkLabel(frame, text="", text_color="gray")
        self._export_status.pack(fill="x", padx=20, pady=(0, 6))

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

        ctk.CTkButton(bar, text="💾 保存并应用", command=self._on_save, width=140).pack(
            side="left", padx=6
        )
        ctk.CTkButton(
            bar, text="🔄 恢复默认", command=self._on_restore_defaults, width=120
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            bar, text="↩ 重载当前值", command=self._on_reload, width=120
        ).pack(side="left", padx=6)
        self._save_status = ctk.CTkLabel(bar, text="", text_color="gray")
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

    def _on_reload(self) -> None:
        self.load_values(config.load())
        self._save_status.configure(text="✓ 已从磁盘重载", text_color="gray")
        self.after(2500, lambda: self._save_status.configure(text=""))

    def _on_export_csv(self) -> None:
        try:
            from tkinter import filedialog

            path = filedialog.asksaveasfilename(
                title="导出 CSV",
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("All", "*.*")],
                initialfile=f"keynote-export-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')}.csv",
            )
            if not path:
                return
            import db

            count = db.export_csv(path, days=30)
            self._export_status.configure(
                text=f"✓ 导出 {count:,} 条记录到 {path}", text_color="green"
            )
        except Exception as e:
            self._export_status.configure(text=f"导出失败: {e}", text_color="red")

    def _on_admin_restart(self) -> None:
        import ctypes

        try:
            params = " ".join(f'"{a}"' for a in sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        except Exception:
            pass
        try:
            if hasattr(self, "_on_save_callback") and self._on_save_callback:
                self._on_save_callback(config.load())
        except Exception:
            pass
        try:
            self.winfo_toplevel().after(200, self.winfo_toplevel().destroy)
        except Exception:
            pass