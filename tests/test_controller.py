import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402

from voice_agent.audio.recorder import RecorderError  # noqa: E402
from voice_agent.controller import Controller  # noqa: E402
from voice_agent.states import State  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeRecorder:
    def __init__(self, wav=b"wav", fail=False):
        self.wav, self.fail = wav, fail
        self.is_recording = False
        self.level = 0.1

    def start(self):
        if self.fail:
            raise RecorderError("no mic")
        self.is_recording = True

    def stop(self):
        self.is_recording = False
        return self.wav


class FakeSTT:
    def __init__(self, text="Hello.", exc=None):
        self.text, self.exc = text, exc

    def transcribe(self, wav):
        if self.exc:
            raise self.exc
        return self.text


class FakeInjector:
    def __init__(self):
        self.texts = []

    def inject(self, text):
        self.texts.append(text)


class DeferredExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, fn, *args):
        self.jobs.append((fn, args))

    def run_all(self):
        while self.jobs:
            fn, args = self.jobs.pop(0)
            fn(*args)

    def shutdown(self, **kw):
        pass


def make(recorder=None, stt=None):
    ex = DeferredExecutor()
    inj = FakeInjector()
    c = Controller(recorder or FakeRecorder(), stt or FakeSTT(), inj, executor=ex)
    states, errors = [], []
    c.state_changed.connect(states.append)
    c.error.connect(errors.append)
    return c, ex, inj, states, errors


def test_full_flow(app):
    c, ex, inj, states, errors = make()
    c.start_requested.emit()
    assert c.state == State.LISTENING
    c.stop_requested.emit()
    assert c.state == State.PROCESSING
    ex.run_all()
    assert inj.texts == ["Hello."]
    assert states == [State.LISTENING, State.PROCESSING, State.IDLE]
    assert errors == []


def test_cancel_discards(app):
    c, ex, inj, states, _ = make()
    c.start_recording()
    c.cancel_recording()
    assert ex.jobs == [] and c.state == State.IDLE


def test_short_recording_goes_idle(app):
    c, ex, inj, states, _ = make(recorder=FakeRecorder(wav=None))
    c.toggle_recording()
    c.toggle_recording()
    assert ex.jobs == [] and c.state == State.IDLE


def test_mic_error(app):
    c, ex, inj, states, errors = make(recorder=FakeRecorder(fail=True))
    c.start_recording()
    assert errors == ["no mic"] and c.state == State.IDLE


def test_stt_error(app):
    c, ex, inj, states, errors = make(stt=FakeSTT(exc=RuntimeError("Is Ollama running?")))
    c.start_recording()
    c.stop_recording()
    ex.run_all()
    assert errors == ["Is Ollama running?"] and inj.texts == [] and c.state == State.IDLE


def test_record_again_while_processing(app):
    c, ex, inj, states, _ = make()
    c.start_recording(); c.stop_recording()
    c.start_recording()
    assert c.state == State.LISTENING
    ex.run_all()
    assert c.state == State.LISTENING
    c.stop_recording(); ex.run_all()
    assert inj.texts == ["Hello.", "Hello."] and c.state == State.IDLE


def test_overlay_states(app):
    from voice_agent.ui.overlay import OverlayPill
    pill = OverlayPill()
    for s in State:
        pill.set_state(s)
        pill.set_level(0.05)
        pill._on_tick()
        pill.repaint()
    assert pill.state == State.PROCESSING


def test_tray(app):
    from voice_agent.ui.tray import TrayIcon
    tray = TrayIcon("Ctrl+Win", ".")
    for s in State:
        tray.set_state(s)
    assert "Ctrl+Win" in tray.toolTip()
    tray.set_health(True, "Ollama ready")
    assert tray._health_action.text().endswith("Ollama ready")


def test_main_module_imports(app):
    import voice_agent.main as m
    assert callable(m.main)


def test_tail_keeps_recording_after_release(app):
    from PySide6.QtTest import QTest
    ex = DeferredExecutor()
    rec = FakeRecorder()
    c = Controller(rec, FakeSTT(), FakeInjector(), executor=ex, tail_ms=100)
    c.start_recording()
    c.stop_recording()
    assert rec.is_recording and ex.jobs == []  # still capturing the tail
    QTest.qWait(250)
    assert not rec.is_recording and len(ex.jobs) == 1


def test_press_again_during_tail_continues(app):
    from PySide6.QtTest import QTest
    ex = DeferredExecutor()
    rec = FakeRecorder()
    c = Controller(rec, FakeSTT(), FakeInjector(), executor=ex, tail_ms=100)
    c.start_recording(); c.stop_recording(); c.start_recording()
    QTest.qWait(250)
    assert rec.is_recording and ex.jobs == []
    c.cancel_recording()
    assert not rec.is_recording


def test_timings_logged_without_text(app, caplog):
    import logging
    c, ex, inj, states, _ = make(stt=FakeSTT(text="secret words"))
    with caplog.at_level(logging.INFO, logger="voice_agent.controller"):
        c.start_recording(); c.stop_recording(); ex.run_all()
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "speech-to-text" in msgs and "secret" not in msgs
    assert inj.texts == ["secret words"]
