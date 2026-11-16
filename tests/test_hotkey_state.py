from types import SimpleNamespace

import pytest

from voice_agent.hotkey.listener import key_to_token
from voice_agent.hotkey.state import HotkeyStateMachine, parse_hotkey


def make(mode="hold", spec="ctrl+win"):
    events = []
    sm = HotkeyStateMachine(parse_hotkey(spec), mode,
                            on_start=lambda: events.append("start"),
                            on_stop=lambda: events.append("stop"),
                            on_cancel=lambda: events.append("cancel"))
    return sm, events


def test_parse():
    assert parse_hotkey("Ctrl+Win") == {"ctrl", "win"}
    assert parse_hotkey("control + windows + a") == {"ctrl", "win", "a"}
    assert parse_hotkey("alt+f9") == {"alt", "f9"}
    with pytest.raises(ValueError):
        parse_hotkey("")
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+banana")


def test_hold_start_and_stop():
    sm, ev = make()
    sm.press("ctrl")
    assert ev == []
    sm.press("win")
    sm.press("win")  # auto-repeat
    assert ev == ["start"]
    sm.release("win")
    assert ev == ["start", "stop"]
    sm.release("ctrl")
    assert ev == ["start", "stop"]


def test_hold_order_independent():
    sm, ev = make()
    sm.press("win")
    sm.press("ctrl")
    sm.release("ctrl")
    assert ev == ["start", "stop"]


def test_hold_cancel_on_other_key():
    sm, ev = make()
    sm.press("ctrl")
    sm.press("win")
    sm.press("right")
    assert ev == ["start", "cancel"]
    sm.release("right")
    sm.release("win")
    sm.release("ctrl")
    assert ev == ["start", "cancel"]


def test_hold_requires_fresh_press_after_cancel():
    sm, ev = make()
    sm.press("ctrl"); sm.press("win"); sm.press("d"); sm.release("d")
    assert ev == ["start", "cancel"]
    sm.release("win"); sm.press("win")
    assert ev == ["start", "cancel", "start"]


def test_toggle_mode():
    sm, ev = make("toggle")
    sm.press("ctrl"); sm.press("win"); sm.release("win"); sm.release("ctrl")
    assert ev == ["start"]
    sm.press("a"); sm.release("a")  # typing while recording does not stop it
    sm.press("ctrl"); sm.press("win")
    assert ev == ["start", "stop"]


def test_none_tokens_ignored():
    sm, ev = make()
    sm.press(None); sm.release(None)
    assert ev == []


def test_key_to_token():
    assert key_to_token(SimpleNamespace(name="ctrl_l")) == "ctrl"
    assert key_to_token(SimpleNamespace(name="cmd")) == "win"
    assert key_to_token(SimpleNamespace(name="alt_gr")) == "alt"
    assert key_to_token(SimpleNamespace(name="f9")) == "f9"
    assert key_to_token(SimpleNamespace(name=None, char="A")) == "a"
    assert key_to_token(SimpleNamespace(name=None, char="\x01")) == "a"
    assert key_to_token(SimpleNamespace(name=None, char=None, vk=0x44)) == "d"
    assert key_to_token(SimpleNamespace(name=None, char=None, vk=None)) is None
