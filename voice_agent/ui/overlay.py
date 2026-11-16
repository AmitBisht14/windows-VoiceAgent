"""Small always-on-top pill showing dictation state at the bottom of the screen."""

import random

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from voice_agent.states import State

WIDTH = 100
HEIGHT = 18
BOTTOM_MARGIN = 55

BG_COLOR = "#1e1e1e"
ACCENT_IDLE = "#969696"
ACCENT_LISTENING = "#e64646"
ACCENT_PROCESSING = "#5a8ce6"

__all__ = ["OverlayPill", "State"]


class OverlayPill(QWidget):
    clicked = Signal()
    quit_requested = Signal()

    def __init__(self):
        super().__init__()
        # WindowDoesNotAcceptFocus keeps keyboard focus in the app being dictated into.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setToolTip("Voice Agent: hold Ctrl+Win to dictate")

        self._state = State.IDLE
        self._tick = 0
        self._level = 0.0
        self._bar_heights = [4] * 5

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(80)
        self._anim_timer.timeout.connect(self._on_tick)
        self._anim_timer.start()

        self._position_bottom_center()

    @property
    def state(self) -> State:
        return self._state

    def _position_bottom_center(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - WIDTH) // 2
        y = screen.y() + screen.height() - HEIGHT - BOTTOM_MARGIN // 2
        self.move(x, y)

    def set_state(self, state: State):
        self._state = state
        if state != State.LISTENING:
            self._level = 0.0
        self.update()

    def set_level(self, level: float):
        # Speech RMS is usually < 0.2; scale so normal speech fills the pill.
        self._level = max(0.0, min(1.0, level * 6))

    def _on_tick(self):
        self._tick += 1
        if self._state == State.LISTENING:
            min_h = 3
            max_h = HEIGHT - 6
            peak = min_h + (max_h - min_h) * self._level
            self._bar_heights = [max(min_h, peak * random.uniform(0.5, 1.0))
                                 for _ in self._bar_heights]
        if self._state in (State.LISTENING, State.PROCESSING):
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def _show_context_menu(self, global_pos):
        menu = QMenu(self)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.exec(global_pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(0, 0, WIDTH, HEIGHT)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(BG_COLOR)))
        painter.drawRoundedRect(rect, HEIGHT / 2, HEIGHT / 2)

        if self._state == State.IDLE:
            self._paint_idle(painter)
        elif self._state == State.LISTENING:
            self._paint_listening(painter)
        else:
            self._paint_processing(painter)

        painter.end()

    def _paint_idle(self, painter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(ACCENT_IDLE)))
        r = 3
        painter.drawEllipse(QRectF(WIDTH / 2 - r, HEIGHT / 2 - r, r * 2, r * 2))

    def _paint_listening(self, painter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(ACCENT_LISTENING)))
        n = len(self._bar_heights)
        bar_width = 4
        gap = 6
        total_width = n * bar_width + (n - 1) * gap
        start_x = (WIDTH - total_width) / 2
        for i, h in enumerate(self._bar_heights):
            x = start_x + i * (bar_width + gap)
            y = (HEIGHT - h) / 2
            painter.drawRoundedRect(QRectF(x, y, bar_width, h), 2, 2)

    def _paint_processing(self, painter):
        pen = QPen(QColor(ACCENT_PROCESSING))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        angle = (self._tick * 24) % 360
        r = HEIGHT / 2 - 4
        cx, cy = WIDTH / 2, HEIGHT / 2
        painter.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), -angle * 16, 270 * 16)
