from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidgetItem, QGroupBox, QFileDialog
)
from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QSignalBlocker
from backend.infrastructure import file_io
from backend.domain.models import ProjectData
from backend.services.project_service import ProjectService
from frontend.pages.table_widgets import ExcelLikeTableWidget
from frontend.workspace import dialog_path
from frontend.theme import ResultTabs, ResultsWorkspace
from frontend.pages.data_inspection import DataInspection
from backend.services.data_service import data_overview

class DataManagementPage(QWidget):
    def __init__(self, project_data: ProjectData):
        super().__init__()
        self.project_data = project_data
        self._dirty = False
        self._loaded_signature = None
        self.init_ui()

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        self.scheme_group = QGroupBox("当前方案")
        scheme_layout = QVBoxLayout(self.scheme_group)
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        scheme_layout.addWidget(self.title_label)
        root.addWidget(self.scheme_group)
        self.tabs = ResultTabs()
        trial = QWidget()
        main_layout = QVBoxLayout(trial)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16,12,16,12)

        # ========= 顶部控制栏 =========
        ctrl_layout = QHBoxLayout()
        
        self.load_btn = QPushButton("加载当前试验矩阵")
        self.load_btn.setStyleSheet("background-color: #6c757d; color: white;")
        self.load_btn.clicked.connect(self.load_doe_matrix)
        
        self.export_btn = QPushButton("导出 CSV")
        self.export_btn.clicked.connect(self.export_to_csv)
        
        self.import_btn = QPushButton("导入 CSV")
        self.import_btn.clicked.connect(self.import_from_csv)
        
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.load_btn)
        ctrl_layout.addWidget(self.export_btn)
        ctrl_layout.addWidget(self.import_btn)
        main_layout.addLayout(ctrl_layout)

        # ========= 数据表格区 =========
        table_group = QGroupBox()
        table_layout = QVBoxLayout()
        
        self.table = ExcelLikeTableWidget()
        self.table.setToolTip("因子列只读，响应列可编辑")
        self.table.itemChanged.connect(self._mark_dirty)
        table_layout.addWidget(self.table)
        
        table_group.setLayout(table_layout)
        main_layout.addWidget(table_group, 1)

        # ========= 底部按钮区 =========
        btn_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("保存响应数据")
        self.save_btn.setMinimumWidth(200)
        self.save_btn.setStyleSheet("font-weight: bold; background-color: #2b78e4; color: white;")
        self.save_btn.clicked.connect(self.save_results)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        main_layout.addLayout(btn_layout)

        self.check_view = DataInspection(self.project_data, "check")
        self.statistics_view = DataInspection(self.project_data, "statistics")
        self.check_view.issue_requested.connect(self._locate_issue)
        for view, title in ((trial, "试验数据"), (self.check_view, "数据检查"),
                            (self.statistics_view, "描述统计")):
            self.tabs.addTab(view, title)
        self.results_workspace = ResultsWorkspace(self.tabs, [("数据管理", [0, 1, 2])])
        root.addWidget(self.results_workspace, 1)
        self.tabs.currentChanged.connect(self._refresh_views)
        from frontend.theme import primary
        self.load_btn.setStyleSheet("")
        primary(self.save_btn)
        self._refresh_views()

    def _refresh_views(self, *_args):
        data = data_overview(self.project_data)
        information = data["information"]
        self.title_label.setText("　 |　 ".join(f"{name}：{value}" for name, value in information))
        self.check_view.refresh(self._dirty, data)
        self.statistics_view.refresh(self._dirty, data)

    def _mark_dirty(self, *_args):
        self._dirty = True
        for view in (self.check_view, self.statistics_view):
            view.dirty = True
            view.notice.setText("有未保存修改；以下为已保存数据，请先保存响应数据。")

    def _locate_issue(self, row, response):
        self.tabs.setCurrentIndex(0)
        for column in range(self.table.columnCount()):
            if self.table.horizontalHeaderItem(column).text() == response:
                self.table.setCurrentCell(row, column)
                self.table.scrollToItem(self.table.item(row, column))
                self.table.setFocus()
                break

    def showEvent(self, event):
        super().showEvent(event)
        signature = ProjectService.for_project(self.project_data).input_signature()
        if signature != self._loaded_signature:
            if self.project_data.doe_matrix:
                self.load_doe_matrix()
            else:
                with QSignalBlocker(self.table):
                    self.table.setRowCount(0)
                self._dirty = False
                self._loaded_signature = signature
        self._refresh_views()

    def load_doe_matrix(self):
        matrix = self.project_data.doe_matrix
        if not matrix:
            Notice.warning(self, "无数据", "后端中未找到DOE点列，请先进入【方案配置】生成DOE实验方案！")
            return
            
        
        # Include response columns even when an imported row is missing them.
        columns = list(dict.fromkeys([key for row in matrix for key in row]
                                    + [r.name for r in self.project_data.responses if r.name]))
        blocker = QSignalBlocker(self.table)
        self.table.setColumnCount(len(columns))
        self.table.setRowCount(len(matrix))
        self.table.setHorizontalHeaderLabels(columns)
        
        factors = [f.name for f in self.project_data.factors if f.name]
        responses = [r.name for r in self.project_data.responses if r.name]

        for r_idx, row_dict in enumerate(matrix):
            for c_idx, col_name in enumerate(columns):
                val = row_dict.get(col_name, "")
                text = "" if val is None else str(val)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if isinstance(val, (int, float)):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                
                # 如果是因子列或者是ID，设为只读并标背色；
                # 如果是响应列，允许编辑以便填入结果
                if col_name in factors or col_name == "Run_ID" or col_name.startswith(("内表", "外表", "重复组号")):
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    item.setBackground(QtGui.QColor("#e9ecef"))
                elif col_name in responses:
                    item.setBackground(QtGui.QColor("#ffffff"))

                self.table.setItem(r_idx, c_idx, item)
                
        self.table.resizeColumnsToContents()
        for column in range(self.table.columnCount()):
            self.table.setColumnWidth(column, max(110, min(240, self.table.columnWidth(column))))
        del blocker
        self._dirty = False
        self._loaded_signature = ProjectService.for_project(self.project_data).input_signature()
        self._refresh_views()

    def save_results(self):
        """Validate and atomically publish response values through ProjectService."""
        if self.table.rowCount() == 0:
            return
        columns = [self.table.horizontalHeaderItem(i).text()
                   for i in range(self.table.columnCount())]
        rows = []
        for row_index in range(self.table.rowCount()):
            row = {}
            for column_index, name in enumerate(columns):
                item = self.table.item(row_index, column_index)
                row[name] = item.text() if item else ""
            rows.append(row)
        service = ProjectService.for_project(self.project_data)
        try:
            service.update_responses(rows)
        except ValueError as exc:
            Notice.warning(self, "转换错误", str(exc))
            return
        service.record_operation(
            "试验响应保存", message="响应已保存到当前项目内存，可开始分析。")
        self._dirty = False
        self._loaded_signature = service.input_signature()
        self._refresh_views()
        Notice.information(
            self, "成功", "实验数据保存成功，已同步至后端底座，可进入下一阶段！")

    def export_to_csv(self):
        if not self.project_data.doe_matrix:
            Notice.warning(self, "警告", "没有可导出的数据！")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出CSV", dialog_path(self), "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            file_io.write_csv_records(
                file_path, self.project_data.doe_matrix)
            Notice.information(
                self, "成功",
                "DOE表导出成功！你可以将该表发给仿真脚本加载执行。")
        except Exception as exc:
            Notice.critical(self, "错误", f"导出失败: {exc}")

    def import_from_csv(self):
        """导入外部算好的 CSV (如流体仿真自动生成的带结果列的文件)"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入测试结果 CSV", dialog_path(self), "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            imported_data = file_io.read_csv_records(file_path)
            service = ProjectService.for_project(self.project_data)
            service.replace_dataset(imported_data)
            service.record_operation(
                "CSV试验导入",
                message=f"导入 {len(imported_data)} 行；来源文件 {Path(file_path).name}")
            self.load_doe_matrix()
            Notice.information(
                self, "成功",
                "外部实验数据导入成功并已填入表格！请点击下方保存确认接轨后端！")
        except ValueError as exc:
            Notice.warning(self, "格式错误", str(exc))
        except Exception as exc:
            Notice.critical(self, "错误", f"导入失败: {exc}")

from frontend.notifications import Notice
