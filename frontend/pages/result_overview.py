"""Reusable Qt overview: information, readiness, result tables and folded details."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QProgressBar,
    QScrollArea, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from frontend.pages.result_summary import display, overview


def label(text="", role=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
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
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                self.setItem(i, j, QTableWidgetItem(display(value)))
        self.resizeRowsToContents()
        self.setFixedHeight(self.horizontalHeader().height() + sum(self.rowHeight(i) for i in range(len(rows))) + 4)


class ResultOverview(QScrollArea):
    """One view shared by screening, Taguchi, RSM and every surrogate model."""
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
        self.body = QVBoxLayout()
        self.column.addLayout(self.body)
        self.details_toggle = QToolButton()
        self.details_toggle.setText("查看方案与分析详情")
        self.details_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details_toggle.setCheckable(True)
        self.details_toggle.toggled.connect(self._toggle_details)
        self.column.addWidget(self.details_toggle)
        self.details_panel = QWidget()
        self.details_layout = QFormLayout(self.details_panel)
        self.details_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.details_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.column.addWidget(self.details_panel)
        self.column.addStretch()
        self.setWidget(content)
        self._method = None
        self._toggle_details(False)

    def _toggle_details(self, expanded):
        self.details_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.details_panel.setVisible(expanded)

    def _section(self, title):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        self.body.addWidget(group)
        return layout

    def set_project(self, project):
        data = overview(project)
        if self._method != project.design_method:
            self.details_toggle.setChecked(False)
            self._method = project.design_method
        for (caption, value), (name, text) in zip(self.info_values, data["information"]):
            caption.setText(name)
            value.setText(text)
        self.status_label.setText(data["status"])
        while self.body.count():
            old = self.body.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        readiness = self._section("数据准备")
        self.readiness_table = SummaryTable(["响应", "数据完整度", "状态"],
            [[name, "", "完整" if total and count == total else "待填入"]
             for name, count, total in data["readiness"]])
        self.progress_bars = []
        for i, (name, count, total) in enumerate(data["readiness"]):
            progress = QProgressBar()
            progress.setRange(0, total or 1)
            progress.setValue(count)
            progress.setFormat(f"{count} / {total}")
            progress.setAccessibleName(f"{name} 已填入 {count} / {total}")
            self.readiness_table.setCellWidget(i, 1, progress)
            self.progress_bars.append(progress)
        readiness.addWidget(self.readiness_table)
        self.next_step = label(data["next_step"], "muted")
        readiness.addWidget(self.next_step)
        self.result_tables = []
        for section in data["sections"]:
            layout = self._section(section["title"])
            if section["rows"]:
                table = SummaryTable(section["headers"], section["rows"])
                layout.addWidget(table)
                self.result_tables.append(table)
            if section["message"]:
                layout.addWidget(label(section["message"], "muted"))
        while self.details_layout.rowCount():
            self.details_layout.removeRow(0)
        for name, value in data["details"]:
            if value:
                self.details_layout.addRow(label(name, "muted"), label(value))
        self.details_toggle.setVisible(bool(data["details"]))
