"""Qt adapters for running long calculations off the UI thread."""
from PyQt6.QtCore import pyqtSignal, QThread

import optimizer_engine as optimizer


class OptimizationWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, context, settings, parent=None):
        super().__init__(parent)
        self.context = context
        self.settings = settings

    def run(self):
        try:
            result = optimizer.robust_optimize(
                self.context, **self.settings, progress=self.progress.emit)
            self.result_ready.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
