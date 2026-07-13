"""KeyNote 程序入口,按序启动数据库 → 主窗口 → 键盘+鼠标监听 → 系统托盘 → mainloop 事件循环"""
import sys
import threading

import config
import db
import listener
import tray
import window


# ──── 主启动流程 ────
def main() -> int:
    cfg = config.load()
    db.init(cfg)

    app = window.App()

    silent = cfg.get("silent_start", False)
    if silent or cfg.get("start_minimized", False):
        app.withdraw()

    if cfg.get("listener_enabled", True):
        threading.Thread(target=listener.start, daemon=True).start()

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
