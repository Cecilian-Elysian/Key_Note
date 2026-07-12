"""KeyNote 程序入口,按序启动数据库 → 主窗口 → 键盘监听 → 系统托盘 → 全局热键 → mainloop 事件循环"""
import sys
import threading

import config
import db
import listener
import tray
import window


_hotkey_listener = None


# ──── 热键解析 ────
def _parse_hotkey(spec: str):
    """将 'ctrl+shift+k' 解析为 pynput Key/KeyCode 集合。"""
    from pynput import keyboard

    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        return None
    modifiers = {
        "ctrl": keyboard.Key.ctrl,
        "shift": keyboard.Key.shift,
        "alt": keyboard.Key.alt,
    }
    pressed_modifiers: list = []
    trigger_char = None
    for p in parts:
        if p in modifiers:
            pressed_modifiers.append(modifiers[p])
        else:
            trigger_char = p
    if trigger_char is None:
        return None
    return pressed_modifiers, trigger_char


# ──── 全局热键监听 ────
def _start_global_hotkey(app, spec: str) -> None:
    global _hotkey_listener
    if _hotkey_listener is not None:
        try:
            _hotkey_listener.stop()
        except Exception:
            pass
        _hotkey_listener = None

    parsed = _parse_hotkey(spec)
    if parsed is None:
        return
    mods, target_char = parsed
    target_char_lower = target_char.lower()

    from pynput import keyboard

    state = {"pressed_mods": set()}

    def _char_to_lower(key) -> str:
        try:
            if hasattr(key, "char") and key.char:
                return key.char.lower()
        except Exception:
            return ""
        return ""

    def on_press(key):
        from pynput.keyboard import Key
        if key in (Key.ctrl, Key.ctrl_l, Key.ctrl_r):
            state["pressed_mods"].add("ctrl")
            return
        if key in (Key.shift, Key.shift_l, Key.shift_r):
            state["pressed_mods"].add("shift")
            return
        if key in (Key.alt, Key.alt_l, Key.alt_r):
            state["pressed_mods"].add("alt")
            return
        ch = _char_to_lower(key)
        if not ch:
            return
        needed = set()
        for m, name in [(Key.ctrl, "ctrl"), (Key.shift, "shift"), (Key.alt, "alt")]:
            if m in mods or getattr(m, "_name", "") in [mm.__class__.__name__ for mm in mods]:
                needed.add(name)
        for m in mods:
            for v in (m,):
                if v in (Key.ctrl, Key.ctrl_l, Key.ctrl_r):
                    needed.add("ctrl")
                elif v in (Key.shift, Key.shift_l, Key.shift_r):
                    needed.add("shift")
                elif v in (Key.alt, Key.alt_l, Key.alt_r):
                    needed.add("alt")
        if state["pressed_mods"] >= needed and ch == target_char_lower:
            try:
                app.after(0, lambda: _toggle_window_visibility(app))
            except Exception:
                pass

    def on_release(key):
        from pynput.keyboard import Key
        if key in (Key.ctrl, Key.ctrl_l, Key.ctrl_r):
            state["pressed_mods"].discard("ctrl")
        elif key in (Key.shift, Key.shift_l, Key.shift_r):
            state["pressed_mods"].discard("shift")
        elif key in (Key.alt, Key.alt_l, Key.alt_r):
            state["pressed_mods"].discard("alt")

    _hotkey_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    _hotkey_listener.daemon = True
    _hotkey_listener.start()


# ──── 窗口显隐切换 ────
def _toggle_window_visibility(app) -> None:
    try:
        if app.state() == "withdrawn":
            app.show()
        else:
            app.withdraw()
    except Exception:
        try:
            app.show()
        except Exception:
            pass


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

    if cfg.get("enable_global_hotkey", False):
        _start_global_hotkey(app, str(cfg.get("global_hotkey", "ctrl+shift+k")))

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
        global _hotkey_listener
        if _hotkey_listener is not None:
            try:
                _hotkey_listener.stop()
            except Exception:
                pass
            _hotkey_listener = None
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