"""One session-only working directory shared by every desktop page."""
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton


class Workspace(QObject):
    directory_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.directory = ''

    def set_directory(self, directory):
        if not str(directory).strip():
            raise ValueError('请选择一个存在的文件夹作为工作目录。')
        target = Path(directory).expanduser().resolve()
        if not target.is_dir():
            raise ValueError('请选择一个存在的文件夹作为工作目录。')
        self.directory = str(target)
        self.directory_changed.emit(self.directory)

    def file_path(self, filename=''):
        # Do not chdir: bundled resources and other windows keep their own paths.
        return str(Path(self.directory) / filename) if self.directory else filename


def dialog_path(widget, filename=''):
    """Resolve a dialog default at click time, including deeply nested panels."""
    workspace = getattr(widget.window(), 'workspace', None)
    return workspace.file_path(filename) if workspace is not None else filename


class DirectoryButton(QPushButton):
    """A global status-bar entry with an elided path and a full-path tooltip."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('workingDirectory')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName('工作目录，点击更改')
        self._directory = ''
        self.setMinimumWidth(120)
        self.update_directory('')

    def update_directory(self, directory):
        self._directory = directory
        self.setToolTip(directory or '点击设置工作目录')
        self._update_text()

    def _update_text(self):
        text = '工作目录：' + (self._directory or '未设置')
        self.setText(self.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideMiddle, max(100, self.width() - 24)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_text()
