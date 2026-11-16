"""System tray icon with status, Ollama health check and quit."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from voice_agent.states import State

_COLORS = {State.IDLE: "#969696", State.LISTENING: "#e64646", State.PROCESSING: "#5a8ce6"}
_LABELS = {State.IDLE: "Idle", State.LISTENING: "Listening…", State.PROCESSING: "Transcribing…"}


def make_icon(color: str) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1e1e1e"))
    p.drawRoundedRect(4, 4, 56, 56, 16, 16)
    p.setBrush(QColor(color))
    p.drawRoundedRect(24, 12, 16, 28, 8, 8)  # microphone capsule
    p.drawRect(30, 42, 4, 8)
    p.drawRect(22, 50, 20, 4)
    p.end()
    return QIcon(pm)


class TrayIcon(QSystemTrayIcon):
    check_requested = Signal()
    quit_requested = Signal()

    def __init__(self, hotkey_label: str, config_folder: str, parent=None):
        super().__init__(parent)
        self._hotkey_label = hotkey_label
        self._config_folder = config_folder
        self._icons = {s: make_icon(c) for s, c in _COLORS.items()}

        menu = QMenu()
        self._status_action = QAction(menu)
        self._status_action.setEnabled(False)
        self._health_action = QAction("Ollama: checking…", menu)
        self._health_action.setEnabled(False)
        check = QAction("Check Ollama", menu)
        check.triggered.connect(self.check_requested.emit)
        open_cfg = QAction("Open config folder", menu)
        open_cfg.triggered.connect(self._open_config)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        for a in (self._status_action, self._health_action):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(check)
        menu.addAction(open_cfg)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._menu = menu
        self.setContextMenu(menu)
        self.set_state(State.IDLE)

    def set_state(self, state: State) -> None:
        self.setIcon(self._icons[state])
        label = f"{_LABELS[state]} (hold {self._hotkey_label} to dictate)"
        self._status_action.setText(label)
        self.setToolTip(f"Voice Agent: {label}")

    def set_health(self, ok: bool, message: str, notify: bool = False) -> None:
        self._health_action.setText(("✓ " if ok else "⚠ ") + message)
        if notify or not ok:
            self.notify(message, error=not ok)

    def notify(self, message: str, error: bool = True) -> None:
        icon = QSystemTrayIcon.Warning if error else QSystemTrayIcon.Information
        self.showMessage("Voice Agent", message, icon, 5000)

    def _open_config(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._config_folder))
