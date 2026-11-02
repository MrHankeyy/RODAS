"""Reusable table widgets shared by workflow pages."""
from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QEvent, QTimer, QObject
from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QHeaderView


class BalancedColumnsTable(QTableWidget):
    """Share spare viewport width while preserving each column's usable minimum."""

    def __init__(self, minimum_widths, fixed_columns=()):
        super().__init__(0, len(minimum_widths))
        self.minimum_widths = tuple(minimum_widths)
        self.flexible_columns = [i for i in range(len(minimum_widths)) if i not in fixed_columns]
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.viewport().installEventFilter(self)
        self._resize_pending = False
        self._fit_columns()

    def eventFilter(self, watched, event):
        if watched is self.viewport() and event.type() == QEvent.Type.Resize and not self._resize_pending:
            self._resize_pending = True
            QTimer.singleShot(0, self._fit_columns)
        return super().eventFilter(watched, event)

    def _fit_columns(self):
        self._resize_pending = False
        self.horizontalHeader().setMinimumSectionSize(min(self.minimum_widths))
        widths = list(self.minimum_widths)
        if self.flexible_columns:
            extra, remainder = divmod(max(0, self.viewport().width() - sum(widths)), len(self.flexible_columns))
            for rank, column in enumerate(self.flexible_columns):
                widths[column] += extra + (rank < remainder)
        for column, width in enumerate(widths):
            if self.columnWidth(column) != width:
                self.setColumnWidth(column, width)


class ContentColumnBalancer(QObject):
    """Preserve measured content widths and share spare space across columns."""

    def __init__(self, table):
        super().__init__(table)
        self.table = table
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.resizeColumnsToContents()
        self.minimum_widths = [table.columnWidth(i) for i in range(table.columnCount())]
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.viewport().installEventFilter(self)
        self.pending = False
        self.fit_columns()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and not self.pending:
            self.pending = True
            QTimer.singleShot(0, self.fit_columns)
        return super().eventFilter(watched, event)

    def fit_columns(self):
        self.pending = False
        if not self.minimum_widths:
            return
        extra, remainder = divmod(max(0, self.table.viewport().width() - sum(self.minimum_widths)),
                                 len(self.minimum_widths))
        for column, minimum in enumerate(self.minimum_widths):
            self.table.setColumnWidth(column, minimum + extra + (column < remainder))


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


def fill_records(table, rows, *, statistic_columns=(), missing_reasons=None):
    """Fill a read-only result table with mathematical display support."""
    from frontend.math_widgets import install_delegate, decorate_item
    from frontend.terminology import apply_header_tooltips, statistic_name, statistic_tooltip
    install_delegate(table)
    headers = list(dict.fromkeys(key for row in rows for key in row))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    apply_header_tooltips(table)
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, key in enumerate(headers):
            value = row.get(key)
            text = "—" if value is None else f"{value:.6g}" if isinstance(value, float) else str(value)
            if key in statistic_columns:
                text = statistic_name(text)
            item = QTableWidgetItem(text)
            if key in statistic_columns:
                item.setToolTip(statistic_tooltip(text))
            if value is None:
                item.setToolTip(missing_reasons[i].get(key, '当前结果未提供该项数值。')
                                if missing_reasons else '当前结果未提供该项数值。')
            table.setItem(i, j, decorate_item(item, value if key not in statistic_columns else text))
    table.resizeRowsToContents()
