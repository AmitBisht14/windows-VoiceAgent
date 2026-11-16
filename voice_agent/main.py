"""Voice Agent entry point."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from voice_agent.audio.recorder import AudioRecorder
from voice_agent.config import config_dir, load_config
from voice_agent.controller import Controller
from voice_agent.hotkey.listener import HotkeyListener
from voice_agent.inject.text_injector import PynputKeyboard, QtClipboard, TextInjector
from voice_agent.stt import create_client
from voice_agent.ui.overlay import OverlayPill
from voice_agent.ui.tray import TrayIcon

log = logging.getLogger("voice_agent")


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_dir = config_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            log_dir / "voice_agent.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    # Transcript text is never logged, only lengths and errors.
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class HealthChecker(QObject):
    finished = Signal(bool, str, bool)

    def __init__(self, stt):
        super().__init__()
        self._stt = stt

    def run(self, notify_ok: bool = False) -> None:
        def work():
            status = self._stt.health_check()
            log.info("Health check: %s", status.message)
            self.finished.emit(status.ok, status.message, notify_ok)
        threading.Thread(target=work, daemon=True, name="health").start()


def main() -> int:
    setup_logging()
    cfg = load_config()
    app = QApplication(sys.argv)
    app.setApplicationName("Voice Agent")
    app.setQuitOnLastWindowClosed(False)

    recorder = AudioRecorder(cfg.sample_rate, cfg.min_duration, cfg.max_duration)
    stt = create_client(cfg)

    listener = None
    injector = TextInjector(
        QtClipboard(), PynputKeyboard(),
        schedule=QTimer.singleShot,
        keys_held=lambda: bool(listener and listener.state.pressed & listener.state.combo),
        restore_clipboard=cfg.restore_clipboard, append_space=cfg.append_space)
    controller = Controller(recorder, stt, injector, tail_ms=cfg.tail_ms)

    overlay = OverlayPill()
    hotkey_label = "+".join(p.capitalize() for p in cfg.hotkey.split("+"))
    overlay.setToolTip(f"Voice Agent: hold {hotkey_label} to dictate, or click")
    tray = TrayIcon(hotkey_label, str(config_dir()))

    controller.state_changed.connect(overlay.set_state)
    controller.state_changed.connect(tray.set_state)
    controller.level_changed.connect(overlay.set_level)
    controller.error.connect(tray.notify)
    overlay.clicked.connect(controller.toggle_recording)

    health = HealthChecker(stt)
    health.finished.connect(tray.set_health)
    tray.check_requested.connect(lambda: health.run(notify_ok=True))

    def quit_app():
        if listener:
            listener.stop()
        controller.shutdown()
        tray.hide()
        app.quit()

    overlay.quit_requested.connect(quit_app)
    tray.quit_requested.connect(quit_app)

    try:
        listener = HotkeyListener(cfg.hotkey, cfg.hotkey_mode,
                                  on_start=controller.start_requested.emit,
                                  on_stop=controller.stop_requested.emit,
                                  on_cancel=controller.cancel_requested.emit)
        listener.start()
        log.info("Listening for %s (%s mode)", cfg.hotkey, cfg.hotkey_mode)
    except Exception as exc:
        log.exception("Could not start hotkey listener")
        listener = None
        controller.error.emit(f"Hotkey unavailable ({exc}). Click the overlay to dictate.")

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
    overlay.show()
    health.run()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
