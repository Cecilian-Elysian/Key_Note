"""customtkinter 主窗口,含 3 个图表"""
from datetime import datetime
from tkinter import font as tkfont

import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import config
import db
import listener

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
plt.style.use("dark_background")

CJK_FONT = "Microsoft YaHei"
plt.rcParams["font.sans-serif"] = [CJK_FONT, "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

CTK_FONT_CANDIDATES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans SC",
    "Arial",
)


def _pick_font() -> str | None:
    """在 Tk 根窗口已建后调用,返回首个可用中文字体"""
    try:
        available = set(tkfont.families())
    except Exception:
        return None
    for f in CTK_FONT_CANDIDATES:
        if f in available:
            return f
    return None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        font = _pick_font()
        if font:
            try:
                default_font = tkfont.nametofont("TkDefaultFont")
                default_font.configure(family=font)
                tkfont.nametofont("TkTextFont").configure(family=font)
                tkfont.nametofont("TkHeadingFont").configure(family=font)
            except Exception:
                pass
        self.cfg = config.load()
        self.title("KeyNote - 键盘记录")
        self.geometry("1000x700")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self.refresh()
        self.after(self.cfg["refresh_interval_sec"] * 1000, self._auto_refresh)

    def _build_ui(self):
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=5)

        self.status_lbl = ctk.CTkLabel(
            top, text="●记录中", text_color="green", font=("", 14, "bold")
        )
        self.status_lbl.pack(side="left", padx=10)
        self.today_lbl = ctk.CTkLabel(top, text="今日: 0")
        self.today_lbl.pack(side="left", padx=20)
        self.total_lbl = ctk.CTkLabel(top, text="总计: 0")
        self.total_lbl.pack(side="left", padx=20)

        ctk.CTkButton(top, text="🔄 刷新", command=self.refresh, width=80).pack(
            side="right", padx=5
        )
        self.toggle_btn = ctk.CTkButton(
            top, text="⏸ 暂停", command=self._toggle, width=80
        )
        self.toggle_btn.pack(side="right", padx=5)

        self.db_lbl = ctk.CTkLabel(top, text="", text_color="gray")
        self.db_lbl.pack(side="right", padx=10)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=5)
        self.tabs.add("总量速率")
        self.tabs.add("热力图")
        self.tabs.add("按键排行")

        self.fig_rate = Figure(figsize=(9, 5), dpi=80, facecolor="#2b2b2b")
        self.fig_heat = Figure(figsize=(9, 5), dpi=80, facecolor="#2b2b2b")
        self.fig_top = Figure(figsize=(9, 5), dpi=80, facecolor="#2b2b2b")

        self.cv_rate = FigureCanvasTkAgg(self.fig_rate, master=self.tabs.tab("总量速率"))
        self.cv_heat = FigureCanvasTkAgg(self.fig_heat, master=self.tabs.tab("热力图"))
        self.cv_top = FigureCanvasTkAgg(self.fig_top, master=self.tabs.tab("按键排行"))
        for cv in (self.cv_rate, self.cv_heat, self.cv_top):
            cv.get_tk_widget().pack(fill="both", expand=True)

    def _toggle(self):
        if listener.is_paused():
            listener.resume()
        else:
            listener.pause()
        self.refresh_status()

    def refresh_status(self):
        if listener.is_paused():
            self.status_lbl.configure(text="⏸已暂停", text_color="orange")
            self.toggle_btn.configure(text="▶ 继续")
        else:
            self.status_lbl.configure(text="●记录中", text_color="green")
            self.toggle_btn.configure(text="⏸ 暂停")
        self.today_lbl.configure(text=f"今日: {db.count_today():,}")
        self.total_lbl.configure(text=f"总计: {db.count_total():,}")
        h = db.health()
        size_mb = h.get("size_bytes", 0) / (1024 * 1024)
        last_bk_ts = h.get("last_backup_ts", 0)
        if last_bk_ts:
            last_bk = datetime.fromtimestamp(last_bk_ts).strftime("%m-%d %H:%M")
        else:
            last_bk = "无"
        self.db_lbl.configure(text=f"DB: {size_mb:.1f}MB · 备份: {last_bk}")

    def refresh(self):
        self.refresh_status()
        self._draw_rate()
        self._draw_heat()
        self._draw_top()

    def _auto_refresh(self):
        if not listener.is_paused():
            self.refresh()
        self.after(self.cfg["refresh_interval_sec"] * 1000, self._auto_refresh)

    def _draw_rate(self):
        self.fig_rate.clear()
        ax = self.fig_rate.add_subplot(111)
        data = db.rate_series(self.cfg["rate_chart_hours"])
        if data:
            xs = [datetime.fromtimestamp(t / 1000) for t, _ in data]
            ys = [c for _, c in data]
            ax.plot(xs, ys, color="#4CAF50", linewidth=1)
            ax.fill_between(xs, ys, alpha=0.3, color="#4CAF50")
        ax.set_title(
            f"过去 {self.cfg['rate_chart_hours']}h - 每分钟按键数", color="white"
        )
        ax.set_xlabel("时间", color="white")
        ax.set_ylabel("按键/分钟", color="white")
        ax.tick_params(colors="white")
        ax.grid(True, alpha=0.3)
        self.fig_rate.autofmt_xdate()
        self.fig_rate.tight_layout()
        self.cv_rate.draw()

    def _draw_heat(self):
        self.fig_heat.clear()
        ax = self.fig_heat.add_subplot(111)
        grid = db.heatmap_data(self.cfg["heatmap_days"])
        im = ax.imshow(grid, cmap="YlOrRd", aspect="auto")
        ax.set_xticks(range(24))
        ax.set_xticklabels(range(24))
        ax.set_yticks(range(7))
        ax.set_yticklabels(["一", "二", "三", "四", "五", "六", "日"])
        ax.set_title(
            f"按键活跃度热力图 (过去 {self.cfg['heatmap_days']} 天)", color="white"
        )
        ax.set_xlabel("小时", color="white")
        ax.set_ylabel("星期", color="white")
        ax.tick_params(colors="white")
        self.fig_heat.colorbar(im, ax=ax, label="按键数")
        self.fig_heat.tight_layout()
        self.cv_heat.draw()

    def _draw_top(self):
        self.fig_top.clear()
        ax = self.fig_top.add_subplot(111)
        data = db.top_keys(20)
        if data:
            keys = [k for k, _ in data][::-1]
            counts = [c for _, c in data][::-1]
            bars = ax.barh(keys, counts, color="#2196F3")
            for b, c in zip(bars, counts):
                ax.text(
                    b.get_width() + 1,
                    b.get_y() + b.get_height() / 2,
                    str(c),
                    va="center",
                    color="white",
                    fontsize=9,
                )
        ax.set_title("Top 20 按键排行", color="white")
        ax.set_xlabel("次数", color="white")
        ax.tick_params(colors="white")
        self.fig_top.tight_layout()
        self.cv_top.draw()

    def _on_close(self):
        if self.cfg.get("close_to_tray", True):
            self.withdraw()
        else:
            self.quit_app()

    def show(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.refresh()

    def quit_app(self):
        try:
            db.close()
        except Exception:
            pass
        try:
            self.quit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass