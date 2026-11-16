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
    def release_keys(self, tokens: set[str]) -> None: ...


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
        self._kb = None
        self._key = None

    def _ensure(self):
        if self._kb is None:  # lazy: pynput needs a desktop session
            from pynput.keyboard import Controller, Key
            self._kb, self._key = Controller(), Key

    def release_keys(self, tokens: set[str]) -> None:
        self._ensure()
        names = {"ctrl": ("ctrl", "ctrl_l", "ctrl_r"), "win": ("cmd", "cmd_l", "cmd_r"),
                 "alt": ("alt", "alt_l", "alt_r"), "shift": ("shift", "shift_l", "shift_r")}
        for token in tokens:
            for name in names.get(token, ()):
                key = getattr(self._key, name, None)
                if key is not None:
                    self._kb.release(key)

    def paste(self) -> None:
        self._ensure()
        with self._kb.pressed(self._key.ctrl):
            self._kb.press("v")
            self._kb.release("v")


class TextInjector:
    """Pastes text into the focused window and restores the clipboard afterwards.

    ``held_keys`` reports hotkey keys the user is still physically holding.
    Pasting while Win is down would turn Ctrl+V into Win+V (clipboard history),
    so we wait briefly for release and then release them synthetically.
    """

    def __init__(self, clipboard: Clipboard, keyboard: Keyboard,
                 schedule: Callable[[int, Callable[[], None]], None] | None = None,
                 held_keys: Callable[[], set[str]] = set,
                 restore_clipboard: bool = True, append_space: bool = True,
                 restore_delay_ms: int = 400, release_wait: float = 0.5,
                 settle_seconds: float = 0.01, sleep=time.sleep):
        self.clipboard = clipboard
        self.keyboard = keyboard
        self.schedule = schedule or (lambda ms, fn: (sleep(ms / 1000), fn()))
        self.held_keys = held_keys
        self.restore_clipboard = restore_clipboard
        self.append_space = append_space
        self.restore_delay_ms = restore_delay_ms
        self.release_wait = release_wait
        self.settle_seconds = settle_seconds
        self._sleep = sleep

    def _clear_modifiers(self) -> None:
        deadline = time.monotonic() + self.release_wait
        held = self.held_keys()
        while held and time.monotonic() < deadline:
            self._sleep(0.01)
            held = self.held_keys()
        if held:
            self.keyboard.release_keys(set(held))

    def inject(self, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        if self.append_space:
            text += " "
        previous = self.clipboard.get_text() if self.restore_clipboard else None
        self.clipboard.set_text(text)
        self._clear_modifiers()
        if self.settle_seconds:
            self._sleep(self.settle_seconds)
        self.keyboard.paste()
        if self.restore_clipboard and previous is not None:
            def restore():
                if self.clipboard.get_text() == text:  # don't clobber a newer user copy
                    self.clipboard.set_text(previous)
            self.schedule(self.restore_delay_ms, restore)
        return True
