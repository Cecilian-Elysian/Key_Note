"""pynput 全局键盘监听模块,后台守护线程常驻,捕获所有按键并异步入队,支持暂停/恢复和活动状态回调"""
from pynput import keyboard

import db

RECORDING = True
_activity_callbacks: list = []


# ──── 回调注册 ────
def register_activity_callback(fn) -> None:
    """注册按键活动回调。用于窗口/设置面板追踪闲置时间。"""
    if fn not in _activity_callbacks:
        _activity_callbacks.append(fn)


# ──── 按键处理 ────
def _on_press(key) -> None:
    if not RECORDING:
        return
    try:
        if hasattr(key, "char") and key.char:
            name = key.char
        else:
            name = str(key).replace("Key.", "")
        db.enqueue(name)
        for fn in _activity_callbacks:
            try:
                fn()
            except Exception:
                pass
    except Exception:
        pass


# ──── 启动/暂停/恢复 ────
def start() -> None:
    with keyboard.Listener(on_press=_on_press) as listener:
        listener.join()


def pause() -> None:
    global RECORDING
    RECORDING = False


def resume() -> None:
    global RECORDING
    RECORDING = True


def is_paused() -> bool:
    return not RECORDING