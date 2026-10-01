"""KeyNote 程序入口,按序启动 DB→窗口→监听→托盘→热键→mainloop。
包含两道防线:Windows 命名互斥单实例 + sys/threading excepthook 落 keynote.crash.log。"""
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

import config
import db
import listener
import tray
import window


# ──── 单实例互斥(Windows 命名互斥) ────
_mutex_handle = None  # 进程生命周期内持有,Kernel 在进程退出时回收


def _acquire_single_instance() -> bool:
    """返回 True=本次为唯一实例,False=已有实例在跑(调用方应直接 return 0)。"""
    global _mutex_handle
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        CreateMutexW = kernel32.CreateMutexW
        CreateMutexW.restype = wintypes.HANDLE
        CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        GetLastError = kernel32.GetLastError
        GetLastError.restype = wintypes.DWORD
        h = CreateMutexW(None, False, r"Local\KeyNoteSingleInstance")
        _mutex_handle = h
        if not h:
            return True
        return GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def _bring_existing_to_front() -> None:
    """尝试把已有 KeyNote 主窗口从隐藏状态拉回。失败忽略(用户可手动开托盘)。"""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        SW_RESTORE = 9
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        found = []

        def _cb(h, _l):
            found.append(h)
            return True

        user32.EnumWindows(EnumWindowsProc(_cb), 0)
        for h in found:
            try:
                exstyle = user32.GetWindowLongW(h, GWL_EXSTYLE)
                if not (exstyle & WS_EX_TOOLWINDOW):
                    continue
                length = user32.GetWindowTextLengthW(h)
                if length <= 0:
                    continue
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                if buf.value == "KeyNote":
                    user32.ShowWindow(h, SW_RESTORE)
                    return
            except Exception:
                continue
    except Exception:
        pass


# ──── 崩溃日志(sys/threading excepthook → 永远落盘,不受 log_to_file 影响) ────
_crash_log_path: Optional[Path] = None


def _install_crash_log(log_dir: Path) -> None:
    """注册全局 excepthook,把未捕获异常写进 keynote.crash.log,与用户日志开关解耦。"""
    global _crash_log_path
    log_dir.mkdir(parents=True, exist_ok=True)
    _crash_log_path = log_dir / "keynote.crash.log"

    def _write(prefix: str, exc_type, value, tb) -> None:
        try:
            with open(_crash_log_path, "a", encoding="utf-8") as f:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{prefix}] {ts}\n")
                f.write("".join(traceback.format_exception(exc_type, value, tb)))
                f.write("\n")
        except Exception:
            pass

    def _excepthook(exc_type, value, tb):
        _write("main", exc_type, value, tb)
        sys.__excepthook__(exc_type, value, tb)

    def _thread_excepthook(args):
        name = getattr(args.thread, "name", "?") if args.thread else "?"
        _write(f"thread:{name}", args.exc_type, args.exc_value, args.exc_traceback)
        orig = getattr(threading, "__excepthook__", None)
        if orig is not None:
            try:
                orig(args)
            except Exception:
                pass

    sys.excepthook = _excepthook
    try:
        threading.excepthook = _thread_excepthook
    except AttributeError:
        pass


# ──── DPI 感知 ────
def _enable_dpi_awareness() -> None:
    """进程级 DPI 感知:高分屏(125%/150%)不再被系统位图拉伸发虚。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # SYSTEM_DPI_AWARE
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ──── 主启动流程 ────
def main() -> int:
    cfg = config.load()
    _install_crash_log(config.exe_dir())

    if not _acquire_single_instance():
        try:
            _bring_existing_to_front()
        except Exception:
            pass
        return 0

    _enable_dpi_awareness()

    db.init(cfg)

    app = window.App()

    silent = cfg.get("silent_start", False)
    if silent or cfg.get("start_minimized", False):
        app.withdraw()

    if cfg.get("listener_enabled", True):
        threading.Thread(target=listener.start, daemon=True, name="listener").start()

    tray_icon = tray.start(app)
    app._tray_icon = tray_icon

    if cfg.get("hide_tray_icon", False):
        try:
            tray.set_visible(False)
        except Exception:
            pass

    if not silent and cfg.get("start_minimized", False):
        if not cfg.get("auto_start", False):
            try:
                tray_icon.notify("KeyNote 已启动,窗口已最小化到托盘")
            except Exception:
                pass

    try:
        app.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass
        try:
            tray_icon.stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
