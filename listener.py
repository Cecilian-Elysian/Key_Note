"""pynput 全局键盘+鼠标监听模块,后台守护线程常驻,异步分类入队,支持暂停/恢复和活动状态回调"""
import time

from pynput import keyboard, mouse

import db

# 录音标志
RECORDING = True
MOUSE_RECORDING = True

_activity_callbacks: list = []


# ──── 回调注册 ────
def register_activity_callback(fn) -> None:
    """注册按键活动回调。用于窗口/设置面板追踪闲置时间。"""
    if fn not in _activity_callbacks:
        _activity_callbacks.append(fn)


def _fire_activity() -> None:
    for fn in _activity_callbacks:
        try:
            fn()
        except Exception:
            pass


# ──── 按键过滤 ────
_MODIFIER_KEYS = frozenset({
    keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
    keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
    keyboard.Key.caps_lock, keyboard.Key.num_lock, keyboard.Key.scroll_lock,
})

_FUNCTION_KEYS = frozenset({
    keyboard.Key.enter, keyboard.Key.space, keyboard.Key.tab, keyboard.Key.backspace,
    keyboard.Key.delete, keyboard.Key.esc,
    keyboard.Key.up, keyboard.Key.down, keyboard.Key.left, keyboard.Key.right,
    keyboard.Key.home, keyboard.Key.end,
    keyboard.Key.page_up, keyboard.Key.page_down, keyboard.Key.insert,
    keyboard.Key.f1, keyboard.Key.f2, keyboard.Key.f3, keyboard.Key.f4,
    keyboard.Key.f5, keyboard.Key.f6, keyboard.Key.f7, keyboard.Key.f8,
    keyboard.Key.f9, keyboard.Key.f10, keyboard.Key.f11, keyboard.Key.f12,
    keyboard.Key.f13, keyboard.Key.f14, keyboard.Key.f15, keyboard.Key.f16,
    keyboard.Key.f17, keyboard.Key.f18, keyboard.Key.f19, keyboard.Key.f20,
    keyboard.Key.print_screen, keyboard.Key.scroll_lock, keyboard.Key.pause,
    keyboard.Key.menu,
})

_LETTER_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_DIGIT_CHARS = frozenset("0123456789")
_SYMBOL_CHARS = frozenset("!@#$%^&*()_+-=[]{}|;:'\\\",.<>?/`~ ")


def _classify_key(name: str) -> str:
    """按键名 → 类型 letter / digit / symbol / modifier / function"""
    if not name:
        return "symbol"
    if name in _LETTER_CHARS:
        return "letter"
    if name in _DIGIT_CHARS:
        return "digit"
    if name in _SYMBOL_CHARS:
        return "symbol"
    return "function"


_DEDUP_WINDOW_SEC = 0.08
_last_key_name: object = None
_last_key_mono: float = 0.0


# ──── 键盘处理 ────
def _on_press(key) -> None:
    global _last_key_name, _last_key_mono

    if key in _MODIFIER_KEYS:
        _fire_activity()
        return

    if hasattr(key, "char") and key.char:
        name = key.char
    else:
        name = str(key).replace("Key.", "")

    try:
        now_mono = time.monotonic()
        if name == _last_key_name and (now_mono - _last_key_mono) < _DEDUP_WINDOW_SEC:
            return
        _last_key_name = name
        _last_key_mono = now_mono
    except Exception:
        pass

    _fire_activity()

    if not RECORDING:
        return

    try:
        if key in _FUNCTION_KEYS:
            ktype = "function"
        else:
            ktype = _classify_key(name)
        db.enqueue(name, ktype)
    except Exception:
        pass


# ──── 鼠标处理 ────
_MOUSE_BUTTON_NAMES = {
    mouse.Button.left: "left",
    mouse.Button.right: "right",
    mouse.Button.middle: "middle",
    mouse.Button.x1: "x1",
    mouse.Button.x2: "x2",
}


def _on_click(x, y, button, pressed) -> None:
    """按下时记录一次;mouse.Listener 的 on_click 默认 pressed=True 时调用。"""
    if not pressed:
        return
    _fire_activity()
    if not MOUSE_RECORDING:
        return
    name = _MOUSE_BUTTON_NAMES.get(button, str(button).replace("Button.", ""))
    try:
        db.enqueue_mouse(name)
    except Exception:
        pass


# ──── 启动 ────
def start() -> None:
    """并行启动 keyboard + mouse 监听,各自守护线程,阻塞直到被外部 stop"""
    with keyboard.Listener(on_press=_on_press) as kb, \
         mouse.Listener(on_click=_on_click) as ms:
        kb.join()


# ──── 暂停 / 恢复 ────
def pause() -> None:
    global RECORDING
    RECORDING = False


def resume() -> None:
    global RECORDING
    RECORDING = True


def pause_mouse() -> None:
    global MOUSE_RECORDING
    MOUSE_RECORDING = False


def resume_mouse() -> None:
    global MOUSE_RECORDING
    MOUSE_RECORDING = True


def is_paused() -> bool:
    return not RECORDING


def is_mouse_paused() -> bool:
    return not MOUSE_RECORDING


def apply_mouse_listener_enabled(enabled: bool) -> None:
    """运行时切换鼠标监听。"""
    if enabled:
        resume_mouse()
    else:
        pause_mouse()
