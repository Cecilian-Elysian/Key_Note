"""设置面板 (customtkinter),作为 window.py 主窗口内嵌 Tab

设计要点:
- 嵌入到 ctk.CTkScrollableFrame,小屏自然可滚动
- 所有控件按 GROUPS 规则顺序生成
- 滑块旁显示当前值
- 应用变更通过 on_save_callback(由 App 注入)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

import config


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


class SettingsPanel(ctk.CTkScrollableFrame):
    def __init__(self, master, on_save_callback: Optional[Callable[[dict], None]] = None):
        super().__init__(master, label_text="")
        self._on_save_callback = on_save_callback
        self._controls: dict[str, Any] = {}
        self._value_labels: dict[str, ctk.CTkLabel] = {}
        self._export_btn: Optional[ctk.CTkButton] = None
        self._build()
        self.load_values(config.load())

    def _build(self) -> None:
        self._build_group("常规", [
            ("switch", "auto_start", "开机自启"),
            ("switch", "close_to_tray", "关闭窗口到托盘"),
            ("switch", "start_minimized", "启动时最小化到托盘"),
            ("switch", "listener_enabled", "启动时启动键盘监听"),
            ("slider_int", "idle_pause_min", "闲置 N 分钟后自动暂停记录 (0=禁用)", 0, 60),
        ])

        self._build_group("界面", [
            ("combo", "theme", "主题", ["dark", "light"], None),
            ("combo_font", "font_family", "字体"),
            ("slider_float", "window_alpha", "窗口透明度 (0.6 ~ 1.0)", 0.6, 1.0, 0.05),
            ("switch", "remember_window_pos", "记住窗口位置"),
        ])

        self._build_group("刷新与图表", [
            ("switch", "chart_auto_refresh", "图表自动刷新"),
            ("slider_int", "refresh_interval_sec", "刷新间隔 (秒)", 1, 60),
            ("slider_int", "heatmap_days", "热力图统计天数", 1, 365),
            ("slider_int", "rate_chart_hours", "速率图小时数", 1, 168),
        ])

        self._build_group("数据库与备份", [
            ("combo_retention", "db_retention_days", "原始数据保留"),
            ("slider_int", "db_auto_backup_days", "自动备份间隔 (天)", 1, 30),
            ("slider_int", "backup_keep_daily", "日备份保留份数", 1, 30),
            ("slider_int", "backup_keep_weekly", "周备份保留份数", 0, 12),
            ("slider_int", "db_flush_batch_size", "批量写入大小", 50, 2000),
            ("slider_float", "db_flush_interval_sec", "写入间隔 (秒)", 0.1, 10.0, 0.1),
        ])

        self._build_group("数据导出 / 日志", [
            ("switch", "log_to_file", "启用日志写入 keynote.log (重启后生效)"),
        ])
        self._build_export_section()
        self._build_footer()

    def _build_group(self, title: str, rows: list) -> None:
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=5, pady=(8, 4))
        ctk.CTkLabel(
            frame, text=title, font=("", 14, "bold"), anchor="w"
        ).pack(fill="x", padx=12, pady=(8, 4))
        for r in rows:
            kind = r[0]
            if kind == "switch":
                _, key, label = r
                self._build_switch_row(frame, key, label)
            elif kind == "slider_int":
                _, key, label, lo, hi = r
                self._build_slider_int_row(frame, key, label, lo, hi)
            elif kind == "slider_float":
                _, key, label, lo, hi, step = r
                self._build_slider_float_row(frame, key, label, lo, hi, step)
            elif kind == "combo":
                _, key, label, values, _ = r
                self._build_combo_row(frame, key, label, values)
            elif kind == "combo_retention":
                _, key, label = r
                self._build_combo_row(
                    frame, key, label, [n for n, _ in _RETENTION_CHOICES]
                )
            elif kind == "combo_font":
                _, key, label = r
                self._build_combo_row(frame, key, label, _FONT_CHOICES)

    def _make_row(self, parent, label_text: str) -> tuple:
        row = ctk.CTkFrame(parent)
        row.pack(fill="x", padx=12, pady=3)
        lbl = ctk.CTkLabel(row, text=label_text, anchor="w", width=260)
        lbl.pack(side="left", padx=(4, 8))
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True)
        return row, right

    def _build_switch_row(self, parent, key: str, label: str) -> None:
        row, right = self._make_row(parent, label)
        sw = ctk.CTkSwitch(right, text="")
        sw.pack(side="right", padx=8)
        self._controls[key] = sw
        self._value_labels[key] = None

    def _build_slider_int_row(self, parent, key: str, label: str, lo: int, hi: int) -> None:
        row, right = self._make_row(parent, label)
        slider = ctk.CTkSlider(right, from_=lo, to=hi, number_of_steps=hi - lo)
        slider.pack(side="left", fill="x", expand=True, padx=8)
        val_lbl = ctk.CTkLabel(right, text=str(lo), width=72, anchor="e")
        val_lbl.pack(side="right", padx=8)

        def _on_change(v):
            val_lbl.configure(text=f"{int(round(v))} {label_unit(label)}")

        slider.configure(command=_on_change)
        self._controls[key] = slider
        self._value_labels[key] = val_lbl

    def _build_slider_float_row(
        self, parent, key: str, label: str, lo: float, hi: float, step: float
    ) -> None:
        row, right = self._make_row(parent, label)
        steps = max(1, int(round((hi - lo) / step)))
        slider = ctk.CTkSlider(right, from_=lo, to=hi, number_of_steps=steps)
        slider.pack(side="left", fill="x", expand=True, padx=8)
        val_lbl = ctk.CTkLabel(right, text=f"{lo:.2f}", width=72, anchor="e")
        val_lbl.pack(side="right", padx=8)

        def _on_change(v):
            val_lbl.configure(text=f"{v:.2f}")

        slider.configure(command=_on_change)
        self._controls[key] = slider
        self._value_labels[key] = val_lbl

    def _build_combo_row(self, parent, key: str, label: str, values: list) -> None:
        row, right = self._make_row(parent, label)
        combo = ctk.CTkComboBox(right, values=values, state="readonly")
        combo.pack(side="right", padx=8)
        self._controls[key] = combo
        self._value_labels[key] = None

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
            kind = type(ctrl).__name__
            if kind == "CTkSwitch":
                v = bool(ctrl.get())
            elif kind == "CTkSlider":
                raw = float(ctrl.get())
                if key in (
                    "window_alpha",
                    "db_flush_interval_sec",
                ):
                    v = round(raw, 2)
                else:
                    v = int(round(raw))
            elif kind == "CTkComboBox":
                v = ctrl.get()
                if key == "db_retention_days":
                    v = _retention_label_to_int(v)
            else:
                v = ctrl.get()
            out[key] = v
        return out

    def load_values(self, cfg: dict) -> None:
        for key, ctrl in self._controls.items():
            v = cfg.get(key, config.DEFAULTS.get(key))
            kind = type(ctrl).__name__
            if kind == "CTkSwitch":
                ctrl.deselect()
                if v:
                    ctrl.select()
            elif kind == "CTkSlider":
                ctrl.set(v)
                if self._value_labels.get(key) is not None:
                    lbl_text = (
                        f"{v:.2f}"
                        if key in ("window_alpha", "db_flush_interval_sec")
                        else f"{int(round(v))} {label_unit_safe(key)}"
                    )
                    self._value_labels[key].configure(text=lbl_text)
            elif kind == "CTkComboBox":
                if key == "db_retention_days":
                    ctrl.set(_retention_int_to_label(int(v)))
                else:
                    ctrl.set(str(v))

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


def label_unit(label: str) -> str:
    """提取滑块 value label 的辅助单位"""
    if "天" in label:
        return "天"
    if "小时" in label:
        return "小时"
    if "秒" in label:
        return "秒"
    if "份" in label:
        return "份"
    if "条" in label or "大小" in label:
        return "条"
    return ""


def label_unit_safe(key: str) -> str:
    if key == "refresh_interval_sec":
        return "秒"
    if key == "heatmap_days":
        return "天"
    if key == "rate_chart_hours":
        return "小时"
    if key == "db_auto_backup_days":
        return "天"
    if key == "backup_keep_daily":
        return "份"
    if key == "backup_keep_weekly":
        return "份"
    if key == "db_flush_batch_size":
        return "条"
    return ""
