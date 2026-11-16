
from PyQt6.QtCore import QObject, pyqtSignal

from backend.services.project_service import set_operation_sink


class MessageBus(QObject):
    posted = pyqtSignal(str, str, str)

    def post(self, level, title, message):
        self.posted.emit(level, str(title), str(message))


bus = MessageBus()

set_operation_sink(bus.post)


class Notice:
    @staticmethod
    def information(parent, title, message, *args, **kwargs):
        bus.post("成功", title, message)

    @staticmethod
    def warning(parent, title, message, *args, **kwargs):
        bus.post("提醒", title, message)

    @staticmethod
    def critical(parent, title, message, *args, **kwargs):
        bus.post("错误", title, message)
