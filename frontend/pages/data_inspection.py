"""Shared raw-data inspection and descriptive statistics, without model context."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox,
                            QTableWidget, QHeaderView, QProgressBar, QFileDialog)
from backend.services.data_service import data_overview
from backend.core.workbench_analysis import descriptive
from frontend.pages.result_overview import SummaryTable, label
from frontend.pages.result_summary import named
from frontend.pages.table_widgets import fill_records
from frontend.workspace import dialog_path
from frontend.notifications import Notice
from backend.infrastructure import file_io


class DataInspection(QWidget):
    """Two views share the same saved-data boundary and refresh interaction."""
    issue_requested = pyqtSignal(int, str)

    def __init__(self, project, kind, parent=None):
        super().__init__(parent)
        self.project, self.kind = project, kind
        self.column = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.notice = label(role="muted")
        bar.addWidget(self.notice, 1)
        refresh = QPushButton("刷新检查" if kind == "check" else "刷新统计")
        refresh.clicked.connect(lambda: self.refresh(self.dirty))
        bar.addWidget(refresh)
        if kind == "statistics":
            export = QPushButton("导出统计 CSV")
            export.clicked.connect(self.export_statistics)
            bar.addWidget(export)
        self.column.addLayout(bar)
        if kind == "check":
            self.readiness_group = QGroupBox("数据完整度")
            self.readiness_layout = QVBoxLayout(self.readiness_group)
            self.column.addWidget(self.readiness_group)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.column.addWidget(self.table, 1)
        if kind == "check":
            self.table.setToolTip("双击问题行，定位到试验数据中的对应单元格")
            self.table.cellDoubleClicked.connect(self._locate_issue)
        self.refresh()

    def refresh(self, dirty=False, data=None):
        self.dirty = dirty
        data = data_overview(self.project) if data is None else data
        if dirty:
            message = "有未保存修改；以下为已保存数据，请先保存响应数据。"
        elif not self.project.doe_matrix:
            message = "当前没有试验数据。"
        elif not data["readiness"]:
            message = "尚未定义响应，请先在业务建模中添加响应。"
        elif self.kind == "statistics":
            message = "基于已保存的实测响应；未拟合模型。"
        else:
            message = "检查已通过，响应数据完整。" if data["ready"] else "请补齐或修正下方列出的响应数据。"
        self.notice.setText(message)
        if self.kind == "statistics":
            fill_records(self.table, descriptive(self.project))
            return
        while self.readiness_layout.count():
            old = self.readiness_layout.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        names = {r.name: named(r) for r in self.project.responses if r.name}
        self.readiness_table = SummaryTable(["响应", "数据完整度", "状态"],
            [[names[name], "", "完整" if total and n == total else "待填入"]
             for name, n, total in data["readiness"]])
        self.progress_bars = []
        for i, (name, n, total) in enumerate(data["readiness"]):
            progress = QProgressBar()
            progress.setRange(0, total or 1)
            progress.setValue(n)
            progress.setFormat(f"{n} / {total}")
            progress.setAccessibleName(f"{names[name]} 已填入 {n} / {total}")
            self.readiness_table.setCellWidget(i, 1, progress)
            self.progress_bars.append(progress)
        self.readiness_layout.addWidget(self.readiness_table)
        self.issues = data["issues"]
        fill_records(self.table, self.issues)

    def export_statistics(self):
        rows = descriptive(self.project)
        if not rows:
            Notice.information(self, "暂无统计", "请先定义响应并载入数据。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出描述统计", dialog_path(self, "描述统计.csv"), "CSV (*.csv)")
        if path:
            try:
                file_io.write_csv_records(path, rows)
            except OSError as exc:
                Notice.warning(self, "导出失败", str(exc))

    def _locate_issue(self, row, _column):
        issue = self.issues[row]
        self.issue_requested.emit(issue["数据行"] - 1, issue["响应"])
