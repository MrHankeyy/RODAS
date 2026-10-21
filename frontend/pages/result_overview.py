"""Reusable Qt overview: information, readiness and result tables."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from frontend.pages.result_summary import display, overview
from frontend.math_widgets import MathLabel, install_delegate, decorate_item


def label(text="", role=None):
    widget = MathLabel(text)
    widget.setWordWrap(True)
    if role:
        widget.setProperty("role", role)
    return widget


class SummaryTable(QTableWidget):
    """Read-only summary table that grows with its rows inside the page scroll area."""
    def __init__(self, headers, rows, parent=None):
        super().__init__(len(rows), len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        install_delegate(self)
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                self.setItem(i, j, decorate_item(QTableWidgetItem(display(value)), value))
        self.resizeRowsToContents()
        self.setFixedHeight(self.horizontalHeader().height() + sum(self.rowHeight(i) for i in range(len(rows))) + 4)


class ResultOverview(QScrollArea):
    """One view shared by screening, Taguchi, RSM and every surrogate model."""
    data_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.column = QVBoxLayout(content)
        self.column.setContentsMargins(8, 6, 8, 12)
        self.column.setSpacing(12)
        self.status_label = label(role="badge")
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.status_label)
        self.data_button = QPushButton("前往数据管理")
        self.data_button.clicked.connect(self.data_requested.emit)
        row.addWidget(self.data_button)
        self.column.addLayout(row)
        self.info = QGroupBox("方案信息")
        info_layout = QHBoxLayout(self.info)
        self.info_values = []
        for _ in range(3):
            field = QVBoxLayout()
            caption, value = label(role="muted"), label()
            field.addWidget(caption)
            field.addWidget(value)
            info_layout.addLayout(field, 1)
            self.info_values.append((caption, value))
        self.column.addWidget(self.info)
        self.next_step = label(role="muted")
        self.column.addWidget(self.next_step)
        self.body = QVBoxLayout()
        self.column.addLayout(self.body)
        self.column.addStretch()
        self.setWidget(content)

    def _section(self, title):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        self.body.addWidget(group)
        return layout

    def set_project(self, project):
        data = overview(project)
        for (caption, value), (name, text) in zip(self.info_values, data["information"]):
            caption.setText(name)
            value.setText(text)
        self.status_label.setText(data["status"])
        self.next_step.setText(data["next_step"])
        self.data_button.setVisible(data["status"] in ("尚未生成方案", "等待响应数据"))
        while self.body.count():
            old = self.body.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        self.result_tables = []
        for section in data["sections"]:
            layout = self._section(section["title"])
            if section["rows"]:
                table = SummaryTable(section["headers"], section["rows"])
                layout.addWidget(table)
                self.result_tables.append(table)
            if section["message"]:
                layout.addWidget(label(section["message"], "muted"))
