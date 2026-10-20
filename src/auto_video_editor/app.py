from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def main(argv: Sequence[str] | None = None) -> int:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("自动视频剪辑")
    app.setOrganizationName("AutoVideoEditor")
    window = MainWindow()
    window.show()
    return app.exec()
