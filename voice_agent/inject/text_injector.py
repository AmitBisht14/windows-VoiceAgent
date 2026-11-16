"""Insert text into the focused application via the clipboard and Ctrl+V."""

from __future__ import annotations

import logging
import time
from typing import Callable, Protocol

log = logging.getLogger(__name__)


class Clipboard(Protocol):
    def get_text(self) -> str | None: ...
    def set_text(self, text: str) -> None: ...


class Keyboard(Protocol):
    def paste(self) -> None: ...


class QtClipboard:
    """Clipboard backed by Qt. Must be used from the GUI thread."""

    def __init__(self):
        from PySide6.QtGui import QGuiApplication
        self._cb = QGuiApplication.clipboard()

    def get_text(self) -> str | None:
        mime = self._cb.mimeData()
        if mime is None or not mime.hasText():
            return None
        return mime.text()

    def set_text(self, text: str) -> None:
        self._cb.setText(text)


class PynputKeyboard:
    def __init__(self):
        from pynput.keyboard import Controller, Key
        self._kb = Controller()
        self._key = Key

    def paste(self) -> None:
        with self._kb.pressed(self._key.ctrl):
            self._kb.press("v")
            self._kb.release("v")


class TextInjector:
    def __init__(self, clipboard: Clipboard, keyboard: Keyboard,
                 schedule: Callable[[int, Callable[[], None]], None] | None = None,
                 keys_held: Callable[[], bool] = lambda: False,
                 restore_clipboard: bool = True, append_space: bool = True,
                 restore_delay_ms: int = 400, sleep=time.sleep):
        self.clipboard = clipboard
        self.keyboard = keyboard
        self.schedule = schedule or (lambda ms, fn: (sleep(ms / 1000), fn()))
        self.keys_held = keys_held
        self.restore_clipboard = restore_clipboard
        self.append_space = append_space
        self.restore_delay_ms = restore_delay_ms
        self._sleep = sleep

    def _wait_for_release(self, timeout: float = 2.0) -> None:
        # Pasting while Win is still physically held would trigger Win+V (clipboard history).
        deadline = time.monotonic() + timeout
        while self.keys_held() and time.monotonic() < deadline:
            self._sleep(0.02)

    def inject(self, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        if self.append_space:
            text += " "
        previous = self.clipboard.get_text() if self.restore_clipboard else None
        self.clipboard.set_text(text)
        self._wait_for_release()
        self._sleep(0.03)  # let the clipboard settle before the paste keystroke
        self.keyboard.paste()
        if self.restore_clipboard and previous is not None:
            def restore():
                if self.clipboard.get_text() == text:  # don't clobber a newer user copy
                    self.clipboard.set_text(previous)
            self.schedule(self.restore_delay_ms, restore)
        return True
