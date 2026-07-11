"""pynput 全局键盘监听,后台线程"""
from pynput import keyboard

import db

RECORDING = True


def _on_press(key) -> None:
    if not RECORDING:
        return
    try:
        if hasattr(key, "char") and key.char:
            name = key.char
        else:
            name = str(key).replace("Key.", "")
        db.enqueue(name)
    except Exception:
        pass


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