"""Reusable table widgets shared by workflow pages."""
from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QRect, QSize, QEvent
from PyQt6.QtGui import QPainter, QPen, QColor, QPalette
from PyQt6.QtWidgets import QApplication, QHeaderView, QTableWidget, QTableWidgetItem, QToolTip


class MultiLevelHeader(QHeaderView):
    """多级表头：支持「分组大栏 → 小栏 → 叶子列」的层级渲染。"""

    def __init__(self, levels, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._leaves = []
        self._group_bands = []
        self._leaf_count = 0
        self._section_tooltips = {}
        for node in levels:
            self._build(node, 0)
        self._band_height = 28
        self._header_height = self._band_height * (
            len(self._group_bands) + 1)
        self.setFixedHeight(self._header_height)
        self.setSectionsClickable(False)
        self.setHighlightSections(False)
        self.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sectionResized.connect(lambda *_: self.viewport().update())
        self.sectionMoved.connect(lambda *_: self.viewport().update())

    def sizeHint(self):
        return QSize(super().sizeHint().width(), self._header_height)

    def set_section_tooltip(self, section, text):
        """Set help text shown only while hovering a specific leaf section."""
        if text:
            self._section_tooltips[section] = text
        else:
            self._section_tooltips.pop(section, None)

    def section_tooltip(self, section):
        return self._section_tooltips.get(section, "")

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.ToolTip:
            text = self.section_tooltip(self.logicalIndexAt(event.pos()))
            if text:
                QToolTip.showText(event.globalPos(), text, self.viewport())
                return True
            QToolTip.hideText()
        return super().viewportEvent(event)

    def _build(self, node, depth):
        if isinstance(node, str):
            start = self._leaf_count
            self._leaf_count += 1
            self._leaves.append((start, start, node))
            return
        label, children = node
        start = self._leaf_count
        for child in children:
            self._build(child, depth + 1)
        end = self._leaf_count - 1
        while len(self._group_bands) <= depth:
            self._group_bands.append([])
        self._group_bands[depth].append((start, end, label))

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.fillRect(event.rect(), self.palette().window())
        self._draw_band(painter, 0, self._leaves, bold=False)
        for band_index, groups in enumerate(self._group_bands, start=1):
            self._draw_band(painter, band_index, groups, bold=True)

    def _draw_band(self, painter, band_index, items, bold):
        band_height = self._band_height
        y = (
            self.height() - band_height if band_index == 0
            else (band_index - 1) * band_height)
        font = self.font()
        font.setBold(bold)
        painter.setFont(font)
        for start, end, label in items:
            left = self.sectionViewportPosition(start)
            right = (
                self.sectionViewportPosition(end) + self.sectionSize(end))
            if right <= 0 or left >= self.viewport().width():
                continue
            rect = QRect(left, y, right - left, band_height)
            painter.fillRect(rect, QColor(237, 242, 247))
            painter.setPen(QPen(QColor(213, 222, 231)))
            painter.drawRect(rect)
            painter.setPen(
                self.palette().color(QPalette.ColorRole.Text))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)


class ExcelLikeTableWidget(QTableWidget):
    """支持从 Excel/CSV 范围复制、粘贴以及批量删除的增强表格。"""

    def keyPressEvent(self, event):
        if event.matches(QtGui.QKeySequence.StandardKey.Copy):
            self.copy_to_clipboard()
        elif event.matches(QtGui.QKeySequence.StandardKey.Paste):
            self.paste_from_clipboard()
        elif event.key() in (
                Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        else:
            super().keyPressEvent(event)

    def copy_to_clipboard(self):
        selected_ranges = self.selectedRanges()
        if not selected_ranges:
            return
        top = min(item.topRow() for item in selected_ranges)
        bottom = max(item.bottomRow() for item in selected_ranges)
        left = min(item.leftColumn() for item in selected_ranges)
        right = max(item.rightColumn() for item in selected_ranges)
        lines = []
        for row in range(top, bottom + 1):
            lines.append("\t".join(
                self.item(row, column).text()
                if self.item(row, column) else ""
                for column in range(left, right + 1)))
        QApplication.clipboard().setText("\n".join(lines) + "\n")

    def paste_from_clipboard(self):
        text = QApplication.clipboard().text()
        if not text:
            return
        selected_ranges = self.selectedRanges()
        if selected_ranges:
            start_row = selected_ranges[0].topRow()
            start_column = selected_ranges[0].leftColumn()
        else:
            start_row, start_column = 0, 0
        for row_offset, row in enumerate(text.rstrip("\n").split("\n")):
            for column_offset, value in enumerate(row.split("\t")):
                target_row = start_row + row_offset
                target_column = start_column + column_offset
                if (target_row < self.rowCount()
                        and target_column < self.columnCount()):
                    item = self.item(target_row, target_column)
                    if item and (
                            item.flags() & Qt.ItemFlag.ItemIsEditable):
                        item.setText(value.strip())

    def delete_selected(self):
        for item in self.selectedItems():
            if item and item.flags() & Qt.ItemFlag.ItemIsEditable:
                item.setText("")


def fill_records(table, rows):
    """Fill a read-only result table with mathematical display support."""
    from frontend.math_widgets import install_delegate, decorate_item
    install_delegate(table)
    headers = list(dict.fromkeys(key for row in rows for key in row))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, key in enumerate(headers):
            value = row.get(key)
            text = "—" if value is None else f"{value:.6g}" if isinstance(value, float) else str(value)
            table.setItem(i, j, decorate_item(QTableWidgetItem(text), value))
    table.resizeRowsToContents()
