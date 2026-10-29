"""Explicit business-definition submission with shared compact tables."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from backend.services.project_service import ProjectService
from frontend.notifications import Notice
from frontend.pages.definition_editors import FactorTable, ResponseTable
from frontend.theme import ResultTabs, ResultsWorkspace, primary


class ModelingPage(QWidget):
    model_saved = pyqtSignal()

    def __init__(self, project_data):
        super().__init__()
        self.project_data = project_data
        self.responses = ResponseTable()
        self.design_factors = FactorTable("设计")
        self.environment_factors = FactorTable("环境")
        self.sections = (self.responses, self.design_factors, self.environment_factors)
        self.model_tabs = ResultTabs()
        for section, title in zip(self.sections, ("响应", "设计因子", "环境因子")):
            self.model_tabs.addTab(section, title)
        self.results_workspace = ResultsWorkspace(self.model_tabs, [("业务建模", [0, 1, 2])])
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.addWidget(self.results_workspace, 1)
        row = QHBoxLayout()
        self.save_status_label = QLabel()
        self.save_status_label.setProperty("role", "muted")
        row.addWidget(self.save_status_label)
        row.addStretch()
        self.save_btn = QPushButton("保存业务模型数据")
        self.save_btn.setObjectName("save_model_btn")
        self.save_btn.clicked.connect(self.on_save_clicked)
        primary(self.save_btn)
        row.addWidget(self.save_btn)
        root.addLayout(row)
        for section in self.sections:
            section.changed.connect(self._draft_changed)

    def _draft_changed(self):
        self.save_status_label.clear()

    def add_response_row(self):
        return self.responses.add()

    def add_design_factor_row(self):
        return self.design_factors.add()

    def add_environment_factor_row(self):
        return self.environment_factors.add()

    def load_project_data(self):
        for section in self.sections:
            section.clear()
        for response in self.project_data.responses:
            self.responses.add(response)
        for factor in self.project_data.factors:
            section = self.design_factors if factor.source == "设计" else self.environment_factors
            section.add(factor)
        for section in self.sections:
            if section.editors:
                section.set_current_index(0)
        self.save_status_label.clear()

    def sync_to_project_data(self):
        responses = [editor.collect() for editor in self.responses.editors]
        factors = [editor.collect() for section in self.sections[1:] for editor in section.editors]
        names = [item.name for item in responses + factors]
        if len(set(names)) != len(names):
            raise ValueError("响应与因子的名称不能重复。")
        return ProjectService.for_project(self.project_data).update_definition(factors=factors, responses=responses)

    def on_save_clicked(self):
        try:
            self.sync_to_project_data()
        except ValueError as exc:
            Notice.warning(self, "业务建模数据校验未通过", str(exc))
            return
        ProjectService.for_project(self.project_data).record_operation("业务模型保存")
        self.model_saved.emit()
        self.save_status_label.setText("已保存")
