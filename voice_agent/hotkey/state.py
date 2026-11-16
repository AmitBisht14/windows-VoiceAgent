"""Pure hotkey state machine (no OS dependencies) for hold-to-talk and toggle modes."""

from __future__ import annotations

from typing import Callable

ALIASES = {
    "control": "ctrl", "ctl": "ctrl", "ctrl": "ctrl",
    "win": "win", "windows": "win", "cmd": "win", "super": "win", "meta": "win",
    "alt": "alt", "option": "alt",
    "shift": "shift",
    "space": "space",
}


def parse_hotkey(spec: str) -> frozenset[str]:
    """Parse ``"ctrl+win"`` style strings into a set of normalized key tokens."""
    tokens = []
    for raw in (spec or "").lower().replace(" ", "").split("+"):
        if not raw:
            continue
        token = ALIASES.get(raw, raw)
        if token not in ALIASES.values() and not (len(token) == 1 or
                                                   (token.startswith("f") and token[1:].isdigit())):
            raise ValueError(f"Unsupported key {raw!r} in hotkey {spec!r}")
        tokens.append(token)
    if not tokens:
        raise ValueError("Hotkey must contain at least one key")
    return frozenset(tokens)


class HotkeyStateMachine:
    """Turns a stream of key press/release tokens into start/stop/cancel events.

    hold mode:   combo fully pressed -> start; any combo key released -> stop.
                 Another key pressed while held (e.g. Ctrl+Win+Right to switch
                 desktops) -> cancel, so OS shortcuts don't produce dictation.
    toggle mode: each fresh press of the full combo alternates start / stop.
    """

    def __init__(self, combo: frozenset[str], mode: str = "hold",
                 on_start: Callable[[], None] = lambda: None,
                 on_stop: Callable[[], None] = lambda: None,
                 on_cancel: Callable[[], None] = lambda: None):
        if mode not in ("hold", "toggle"):
            raise ValueError(f"Unknown hotkey mode {mode!r}")
        self.combo = combo
        self.mode = mode
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_cancel = on_cancel
        self.pressed: set[str] = set()
        self.active = False
        self._combo_latched = False  # combo held since last activation edge

    def press(self, token: str | None) -> None:
        if token is None:
            return
        if token in self.pressed:  # key auto-repeat
            return
        self.pressed.add(token)
        if token not in self.combo:
            if self.mode == "hold" and self.active:
                self.active = False
                self.on_cancel()
            return
        if self.combo <= self.pressed and not self._combo_latched:
            self._combo_latched = True
            if self.mode == "hold":
                if not self.active:
                    self.active = True
                    self.on_start()
            else:
                self.active = not self.active
                (self.on_start if self.active else self.on_stop)()

    def release(self, token: str | None) -> None:
        if token is None:
            return
        self.pressed.discard(token)
        if token in self.combo:
            self._combo_latched = False
            if self.mode == "hold" and self.active:
                self.active = False
                self.on_stop()

    def reset(self) -> None:
        self.pressed.clear()
        self._combo_latched = False
        self.active = False
