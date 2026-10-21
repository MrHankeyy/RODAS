"""Qt adapters for the shared offline math renderer."""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QLabel, QComboBox, QStyledItemDelegate, QStyle, QStyleOptionViewItem, QTextEdit

from backend.reporting.math_format import Math, PATTERN, rich_text

MATH_ROLE = int(Qt.ItemDataRole.UserRole) + 21


class MathLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self.setText(text)

    def setText(self, text):
        mathematical = isinstance(text, Math) or PATTERN.search(str(text))
        self.setTextFormat(Qt.TextFormat.RichText if mathematical else Qt.TextFormat.PlainText)
        super().setText(rich_text(text) if mathematical else str(text))
        self.setToolTip(str(text) if mathematical else '')

    def setHtml(self, content):
        self.setTextFormat(Qt.TextFormat.RichText)
        super().setText(content)


def decorate_item(item, value):
    if isinstance(value, Math) or PATTERN.search(str(value)):
        item.setData(MATH_ROLE, rich_text(value))
    return item


def decorate_combo(combo):
    install_delegate(combo)
    combo.setLabelDrawingMode(QComboBox.LabelDrawingMode.UseDelegate)
    for index in range(combo.count()):
        value = combo.itemText(index)
        if PATTERN.search(value):
            combo.setItemData(index, rich_text(value), MATH_ROLE)


def install_delegate(widget):
    if not hasattr(widget, '_math_delegate'):
        widget._math_delegate = MathDelegate(widget)
        widget.setItemDelegate(widget._math_delegate)


class MathDelegate(QStyledItemDelegate):
    """Render formulas while preserving the item's plain data for copy/export."""
    def document(self, option, index):
        document = QTextDocument()
        document.setDocumentMargin(2)
        document.setDefaultFont(option.font)
        document.setHtml(index.data(MATH_ROLE))
        return document

    def paint(self, painter, option, index):
        if not index.data(MATH_ROLE):
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ''
        opt.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        document = self.document(option, index)
        painter.save()
        painter.setClipRect(option.rect)
        painter.translate(option.rect.x() + 4, option.rect.y() + max(0, (option.rect.height() - document.size().height()) / 2))
        document.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        if not index.data(MATH_ROLE):
            return super().sizeHint(option, index)
        size = self.document(option, index).size()
        return QSize(int(size.width()) + 10, int(size.height()) + 8)


class MathTextEdit(QTextEdit):
    def setPlainText(self, text):
        self.setHtml(rich_text(text))

    def setText(self, text):
        self.setPlainText(text)
