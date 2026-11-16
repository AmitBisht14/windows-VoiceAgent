"""Wires hotkey -> recorder -> speech-to-text -> text injection."""

from __future__ import annotations

import logging
from concurrent.futures import Executor, ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .audio.recorder import RecorderError
from .states import State

log = logging.getLogger(__name__)


class Controller(QObject):
    state_changed = Signal(object)  # State
    level_changed = Signal(float)
    error = Signal(str)

    # Thread-safe entry points: emit from any thread (e.g. the keyboard hook).
    start_requested = Signal()
    stop_requested = Signal()
    cancel_requested = Signal()

    _transcribed = Signal(str)
    _failed = Signal(str)

    def __init__(self, recorder, stt, injector, executor: Executor | None = None,
                 tail_ms: int = 0, parent=None):
        super().__init__(parent)
        self.recorder = recorder
        self.stt = stt
        self.injector = injector
        self._executor = executor or ThreadPoolExecutor(max_workers=1,
                                                        thread_name_prefix="stt")
        self._pending = 0
        self._state = State.IDLE

        self.start_requested.connect(self.start_recording)
        self.stop_requested.connect(self.stop_recording)
        self.cancel_requested.connect(self.cancel_recording)
        self._transcribed.connect(self._on_transcribed)
        self._failed.connect(self._on_failed)

        # Keep capturing briefly after release so the last word is not clipped.
        self._tail_timer = QTimer(self)
        self._tail_timer.setSingleShot(True)
        self._tail_timer.setInterval(max(0, int(tail_ms)))
        self._tail_timer.timeout.connect(self._finish_recording)

        self._level_timer = QTimer(self)
        self._level_timer.setInterval(50)
        self._level_timer.timeout.connect(lambda: self.level_changed.emit(self.recorder.level))

    @property
    def state(self) -> State:
        return self._state

    def _set_state(self, state: State) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)

    def _settle_state(self) -> None:
        if self.recorder.is_recording:
            self._set_state(State.LISTENING)
        elif self._pending:
            self._set_state(State.PROCESSING)
        else:
            self._set_state(State.IDLE)

    @Slot()
    def start_recording(self) -> None:
        if self._tail_timer.isActive():  # pressed again during the tail: keep going
            self._tail_timer.stop()
            return
        if self.recorder.is_recording:
            return
        try:
            self.recorder.start()
        except RecorderError as exc:
            log.error("Microphone error: %s", exc)
            self.error.emit(str(exc))
            self._settle_state()
            return
        self._level_timer.start()
        self._settle_state()

    @Slot()
    def stop_recording(self) -> None:
        if not self.recorder.is_recording or self._tail_timer.isActive():
            return
        if self._tail_timer.interval() > 0:
            self._tail_timer.start()
        else:
            self._finish_recording()

    @Slot()
    def _finish_recording(self) -> None:
        if not self.recorder.is_recording:
            return
        self._level_timer.stop()
        wav = self.recorder.stop()
        if wav:
            self._pending += 1
            self._executor.submit(self._work, wav)
        self._settle_state()

    @Slot()
    def cancel_recording(self) -> None:
        if not self.recorder.is_recording:
            return
        self._tail_timer.stop()
        self._level_timer.stop()
        self.recorder.stop()
        log.info("Dictation cancelled")
        self._settle_state()

    @Slot()
    def toggle_recording(self) -> None:
        if self.recorder.is_recording and not self._tail_timer.isActive():
            self.stop_recording()
        else:
            self.start_recording()

    def _work(self, wav: bytes) -> None:  # worker thread
        try:
            self._transcribed.emit(self.stt.transcribe(wav))
        except Exception as exc:
            log.exception("Transcription failed")
            self._failed.emit(str(exc) or exc.__class__.__name__)

    @Slot(str)
    def _on_transcribed(self, text: str) -> None:
        self._pending -= 1
        log.info("Transcribed %d characters", len(text))
        try:
            self.injector.inject(text)
        except Exception as exc:
            log.exception("Text injection failed")
            self.error.emit(f"Could not insert text: {exc}")
        self._settle_state()

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._pending -= 1
        self.error.emit(message)
        self._settle_state()

    def shutdown(self) -> None:
        self._tail_timer.stop()
        self._level_timer.stop()
        if self.recorder.is_recording:
            self.recorder.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
