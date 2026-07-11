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
    threading.Thread(target=listener.start, daemon=True).start()

    app = window.App()
    tray_icon = tray.start(app)
    app._tray_icon = tray_icon

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