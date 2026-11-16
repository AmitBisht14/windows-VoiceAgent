"""Global keyboard listener (pynput) feeding the hotkey state machine."""

from __future__ import annotations

import logging
import sys
from typing import Callable

from .state import HotkeyStateMachine, parse_hotkey

log = logging.getLogger(__name__)

_VK_UNASSIGNED = 0xE8  # unassigned virtual key, used to swallow the Start menu
_KEYEVENTF_KEYUP = 0x0002


def key_to_token(key) -> str | None:
    """Normalize a pynput key object to a token used by :func:`parse_hotkey`."""
    name = getattr(key, "name", None)
    if name:
        for prefix, token in (("ctrl", "ctrl"), ("cmd", "win"), ("alt", "alt"),
                              ("shift", "shift")):
            if name.startswith(prefix):
                return token
        return name
    char = getattr(key, "char", None)
    if char:
        if len(char) == 1 and ord(char) < 32:  # Ctrl+letter arrives as a control char
            return chr(ord(char) + 96)
        return char.lower()
    vk = getattr(key, "vk", None)
    if vk is not None:
        if 0x41 <= vk <= 0x5A:
            return chr(vk).lower()
        if 0x30 <= vk <= 0x39:
            return chr(vk)
        return f"vk{vk}"
    return None


def suppress_start_menu() -> None:
    """Tap an unassigned key so releasing Win does not open the Start menu."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.keybd_event(_VK_UNASSIGNED, 0, 0, 0)
        user32.keybd_event(_VK_UNASSIGNED, 0, _KEYEVENTF_KEYUP, 0)
    except Exception:  # pragma: no cover - best effort
        log.debug("Could not suppress Start menu", exc_info=True)


class HotkeyListener:
    """Listens for the configured combo system-wide.

    Callbacks run on pynput's hook thread; keep them short (e.g. emit a Qt signal).
    """

    def __init__(self, hotkey: str, mode: str, on_start: Callable[[], None],
                 on_stop: Callable[[], None], on_cancel: Callable[[], None]):
        combo = parse_hotkey(hotkey)

        def start():
            if "win" in combo:
                suppress_start_menu()
            on_start()

        self.state = HotkeyStateMachine(combo, mode, start, on_stop, on_cancel)
        self._listener = None

    def _on_press(self, key):
        token = key_to_token(key)
        if token != f"vk{_VK_UNASSIGNED}":
            self.state.press(token)

    def _on_release(self, key):
        self.state.release(key_to_token(key))

    def start(self) -> None:
        from pynput import keyboard  # lazy: needs a desktop session

        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
