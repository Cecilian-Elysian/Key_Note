"""KeyNote - 键盘记录器 入口"""
import sys
import threading

import config
import db
import listener
import tray
import window


def main() -> int:
    cfg = config.load()
    db.init(cfg)

    app = window.App()

    if cfg.get("start_minimized", False):
        app.withdraw()

    if cfg.get("listener_enabled", True):
        threading.Thread(target=listener.start, daemon=True).start()

    tray_icon = tray.start(app)
    app._tray_icon = tray_icon

    if cfg.get("start_minimized", False):
        if cfg.get("auto_start", False):
            pass
        else:
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