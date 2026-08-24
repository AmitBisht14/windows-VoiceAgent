import sys

from PySide6.QtWidgets import QApplication

from voice_agent.ui.overlay import OverlayPill


def main():
    app = QApplication(sys.argv)

    overlay = OverlayPill()
    overlay.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
