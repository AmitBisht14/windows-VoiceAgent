import random
from enum import Enum

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QMenu, QWidget

WIDTH = 100
HEIGHT = 18
BOTTOM_MARGIN = 55

BG_COLOR = "#1e1e1e"
ACCENT_IDLE = "#969696"
ACCENT_LISTENING = "#e64646"
ACCENT_PROCESSING = "#5a8ce6"


class State(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"


class OverlayPill(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)

        self._state = State.IDLE
        self._tick = 0
        self._bar_heights = [4] * 5

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(80)
        self._anim_timer.timeout.connect(self._on_tick)
        self._anim_timer.start()

        self._advance_timer = QTimer(self)
        self._advance_timer.setSingleShot(True)
        self._advance_timer.timeout.connect(self._advance_state)

        self._position_bottom_center()

    def _position_bottom_center(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.x() + (screen.width() - WIDTH) // 2
        y = screen.y() + screen.height() - HEIGHT - BOTTOM_MARGIN
        self.move(x, y)

    def _on_tick(self):
        self._tick += 1
        if self._state == State.LISTENING:
            min_h = 4
            max_h = max(min_h, HEIGHT - 6)
            self._bar_heights = [random.randint(min_h, max_h) for _ in self._bar_heights]
        if self._state in (State.LISTENING, State.PROCESSING):
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._advance_state()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def _show_context_menu(self, global_pos):
        menu = QMenu(self)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.exec(global_pos)

    def _advance_state(self):
        if self._state == State.IDLE:
            self._set_state(State.LISTENING)
            self._advance_timer.start(2000)
        elif self._state == State.LISTENING:
            self._set_state(State.PROCESSING)
            self._advance_timer.start(1000)
        else:
            self._set_state(State.IDLE)

    def _set_state(self, state):
        self._state = state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(0, 0, WIDTH, HEIGHT)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._qcolor(BG_COLOR)))
        painter.drawRoundedRect(rect, HEIGHT / 2, HEIGHT / 2)

        if self._state == State.IDLE:
            self._paint_idle(painter)
        elif self._state == State.LISTENING:
            self._paint_listening(painter)
        else:
            self._paint_processing(painter)

        painter.end()

    @staticmethod
    def _qcolor(hex_str):
        return QColor(hex_str)

    def _paint_idle(self, painter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._qcolor(ACCENT_IDLE)))
        r = 5
        painter.drawEllipse(QRectF(WIDTH / 2 - r, HEIGHT / 2 - r, r * 2, r * 2))

    def _paint_listening(self, painter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._qcolor(ACCENT_LISTENING)))
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
        pen = QPen(self._qcolor(ACCENT_PROCESSING))
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        angle = (self._tick * 12) % 360
        r = max(4, min(WIDTH, HEIGHT) / 2 - 3)
        cx, cy = WIDTH / 2, HEIGHT / 2
        arc_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        painter.drawArc(arc_rect, -angle * 16, 270 * 16)
