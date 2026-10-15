"""设计优化页面：把方案配置生成的设计在填入响应数据后做后端分析并展示。

支持的结果视图：
- 方案设计摘要与设计诊断；
- 两水平筛选（± 对比主效应 / 方差贡献）；
- 响应曲面（二次模型拟合、拟合优度、优选设置）；
- 田口稳健设计（均值响应表、S/N 表、稳健最优水平组合）；
- 代理模型训练（Kriging / SVR / BPANN 的误差与耗时）。
"""
from __future__ import annotations

import math
import statistics
import json
import logging
from dataclasses import asdict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QGroupBox, QTextEdit, QMessageBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QDoubleSpinBox, QFrame, QLineEdit
)
from PyQt6.QtCore import pyqtSignal

from rams.engines import doe as engine
from rams.engines import optimizer as oe
from rams.engines import design_analysis as da
from rams.ui.pages.design_results import DesignResultsPanel
from rams.ui.pages.workbench_diagnostics import WorkbenchDiagnostics
from rams.ui.pages.qt_tasks import OptimizationWorker
from rams.ui.pages.optimization_controller import OptimizationController
from rams.ui.pages import optimization_panels, optimization_plots, result_text
from rams.engines import workbench as wa
from rams.reporting import report_engine as reports
from rams.domain.models import ProjectData
from rams.services import analysis_service, model_service
from rams.services.project_service import ProjectService

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False


class OptimizationPage(QWidget):
    optimization_finished = pyqtSignal()

    VIEWS = [
        "方案设计摘要",
        "筛选设计结果",
        "响应曲面结果",
        "田口稳健结果",
        "代理模型训练结果",
    ]

    def __init__(self, project_data: ProjectData):
        super().__init__()
        self.project_data = project_data
        self.project_service = ProjectService.for_project(project_data)
        self.project_service.ensure_current()
        self._input_signature = self.project_service.input_signature()
        self.controller = OptimizationController(self)
        self.init_ui()

    # ------------------------------------------------------------------ UI
    def init_ui(self):
        return optimization_panels.build(self)

    def _settings_changed(self, *_args):
        if self._oe_context:
            self.diagnostics_panel.clear()
            self._oe_context = None
            self._robust_res = {}
            self.project_service.clear_workbench()
            self.robust_text.clear()
            self.status_label.setText(
                "优化参数已改变；已有优化结果属于先前设置，请重新执行。")

    def _update_method_actions(self):
        """按方案类型切换主动作，避免把筛选/田口误导成鲁棒优化。"""
        if hasattr(self, "uncertainty_label"):
            self._update_uncertainty_label()
        method = self._method()
        is_screening = "筛选" in method
        is_taguchi = "田口" in method
        is_special = is_screening or is_taguchi
        if is_screening:
            self.run_all_btn.setText("筛选设计：计算主效应")
            self.run_btn.setText("计算筛选主效应")
        elif is_taguchi:
            self.run_all_btn.setText("田口设计：计算信噪比")
            self.run_btn.setText("计算田口信噪比")
        else:
            self.run_all_btn.setText("执行稳定性设计与鲁棒优化")
            self.run_btn.setText("更新方案汇总")
        for index in (1, 3, 4, 5, 6, 7, 8):
            self.tabs.setTabVisible(index, not is_special)
        self.tabs.setTabVisible(9, is_screening)
        self.tabs.setTabVisible(10, is_taguchi)
        self.tabs.setTabVisible(11, not is_special)
        self.stats_btn.setVisible(not is_special)
        if hasattr(self, "results_workspace"):
            self.results_workspace.refresh()
        if hasattr(self, "level_table"):
            self.level_table.setVisible(not is_special)
        self.run_all_btn.setToolTip(
            "筛选设计只计算因子敏感度，不执行优化"
            if is_screening else
            "田口设计根据内表×外表响应计算 S/N 并推荐稳健水平"
            if is_taguchi else
            "响应曲面和代理模型进入鲁棒优化工作台")

    def _run_primary_action(self):
        """顶部主按钮：筛选/田口走专用分析，其余方案走鲁棒优化。"""
        method = self._method()
        if "筛选" in method or "田口" in method:
            self.run_optimization()
        else:
            self.run_workbench()

    def _build_overview_tab(self):
        return optimization_panels.build_overview_tab(self)

    def _build_robust_tab(self):
        return optimization_panels.build_robust_tab(self)

    def _on_robust_mode(self, text):
        self.sigma_limits_table.setVisible(text == "约束型")
        if text == "约束型":
            self.sigma_limits_table.blockSignals(True)
            saved = {self.sigma_limits_table.item(i,0).data(256): self.sigma_limits_table.item(i,1).text()
                     for i in range(self.sigma_limits_table.rowCount()) if self.sigma_limits_table.item(i,1)}
            responses = [r for r in self.project_data.responses if not oe.self_is_constraint(r) or "目标" in r.kind]
            self.sigma_limits_table.setRowCount(len(responses))
            from PyQt6.QtCore import Qt
            for i,r in enumerate(responses):
                label = QTableWidgetItem(r.name + (" (" + r.unit + ")" if r.unit else ""))
                label.setData(256, r.name)
                label.setFlags(label.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.sigma_limits_table.setItem(i,0,label)
                self.sigma_limits_table.setItem(i,1,QTableWidgetItem(saved.get(r.name,"")))
            self.sigma_limits_table.blockSignals(False)
        self.weight_spin.setEnabled("加权" in text)
        self.k_constraint_spin.setEnabled(True)

    def _sigma_limits(self):
        if self.robust_mode_combo.currentText() != "约束型":
            return {}
        limits = {}
        for i in range(self.sigma_limits_table.rowCount()):
            name = self.sigma_limits_table.item(i, 0).data(256)
            try:
                value = float(self.sigma_limits_table.item(i, 1).text())
            except (ValueError, AttributeError):
                raise ValueError(f"请填写 {name} 的允许最大标准差。")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} 的标准差上限必须是有限正数。")
            limits[name] = value
        return limits

    def _update_uncertainty_label(self, *_args):
        sigmas = [f"{f.name}: σ={oe._sigma_of_factor(f, self.k_design_spin.value()):.6g}"
                  for f in self.project_data.factors if f.name]
        self.uncertainty_label.setText("当前输入标准差（区间设计因子 σ=区间宽度/(2k)）：" + "；".join(sigmas))

    def _new_text(self):
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("font-family:Consolas,'Microsoft YaHei';font-size:13px;")
        return text

    def _build_data_tab(self):
        return optimization_panels.build_data_tab(self)

    def _refresh_data_analysis(self):
        self._check_inputs()
        WorkbenchDiagnostics.fill(self.data_stats_table, wa.descriptive(self.project_data))
        self.data_overall_label.setText(oe.describe_data(self.project_data) + "\n分组 F/p 为单因素描述，未控制其他因子，不用于多因子效应归因。")
        self._fill_level_table(oe.level_stats(self.project_data))

    def _build_signif_tab(self):
        return optimization_panels.build_signif_tab(self)

    def _build_cv_tab(self):
        return optimization_panels.build_cv_tab(self)

    def _build_param_tab(self):
        return optimization_panels.build_param_tab(self)

    def _build_tol_tab(self):
        return optimization_panels.build_tol_tab(self)

    def _build_model_tab(self):
        return optimization_panels.build_model_tab(self)

    def _build_tools_tab(self):
        return optimization_panels.build_tools_tab(self)

    # ------------------------------------------------------------- 公共工具
    def _responses(self):
        return [r for r in self.project_data.responses if r.name]

    def _matrix(self):
        return self.project_data.doe_matrix or []

    def _method(self):
        return self.project_data.design_method or ""

    # ------------------------------------------------------------- 视图调度
    def _refresh_view(self, text):
        self._update_method_actions()
        if "方案设计摘要" in text:
            self.result_text.setPlainText(self._summary_text())
        elif "筛选" in text:
            self.result_text.setPlainText(self._screening_text())
        elif "响应曲面" in text:
            self.result_text.setPlainText(self._rsm_text())
        elif "田口" in text:
            self.result_text.setPlainText(self._taguchi_text())
        else:
            self.result_text.setPlainText(self._surrogate_text())

    # ------------------------------------------------------------- 结果文本
    def _summary_text(self):
        return result_text.summary(self.project_data)

    def _screening_text(self):
        return result_text.screening(self.project_data)

    def _rsm_text(self):
        return result_text.response_surface(self.project_data)

    def _taguchi_text(self):
        return result_text.taguchi(self.project_data)

    def _surrogate_text(self):
        return result_text.surrogate(self.project_data)

    # ------------------------------------------------------------- 后端执行
    def run_optimization(self):
        return self.controller.run_optimization()

    def _factors_for_doe(self):
        return da.active_controls(self.project_data)

    def _finish_classic(self, result):
        self.status_label.setText(result.get("analysis_status", "分析完成"))
        self.data_overall_label.setText(oe.describe_data(self.project_data) + "\n水平分组为单因子描述，未控制其他因子；F/p 不可估计时留空，不用于多因子效应归因。")
        self._fill_level_table(oe.level_stats(self.project_data))
        self.optimization_finished.emit()

    def _check_inputs(self):
        return self.controller._check_inputs()

    def showEvent(self, event):
        super().showEvent(event)
        self._check_inputs()
        self._update_method_actions()
        self._on_robust_mode(self.robust_mode_combo.currentText())
        self.screening_panel.set_result(self.project_data.screening_result)
        self.taguchi_panel.set_result(self.project_data.taguchi_result)
        self._refresh_data_analysis()

    # ------------------------------------------------------------- 筛选分析
    def _run_screening(self):
        service = self.project_service
        result = da.screening(self.project_data)
        service.publish_results(screening_result=result)
        self.screening_panel.set_result(result)
        service.record_operation(
            "筛选分析", "部分完成" if result.get("errors") else "完成",
            {"results": {"screening": result}})

    # ------------------------------------------------------------- 响应曲面
    def _run_rsm(self):
        context = model_service.build_rsm_context(self.project_data)
        self._oe_context = context
        result = self._store_rsm_fit(context)
        self.project_service.record_operation(
            "响应曲面建模", payload={"results": {"rsm": result}})
        return context

    def _store_rsm_fit(self, context):
        result = model_service.rsm_result(self.project_data, context)
        self.project_service.publish_results(
            rsm_result=result)
        return result

    # ------------------------------------------------------------- 田口分析
    def _run_taguchi(self):
        service = self.project_service
        result = da.taguchi(self.project_data)
        service.publish_results(taguchi_result=result)
        self.taguchi_panel.set_result(result)
        service.record_operation(
            "田口分析", "部分完成" if result.get("errors") else "完成",
            {"results": {"taguchi": result}})

    # ------------------------------------------------------------- 代理模型
    def _surrogate_signature(self):
        return model_service.surrogate_signature(self.project_data)

    def _run_surrogate(self):
        service = self.project_service
        result = model_service.train_surrogates(self.project_data)
        service.publish_results(surrogate_result=result)
        for name, response_result in result["responses"].items():
            score = response_result.get("r2_test")
            if score is not None and (
                    not math.isfinite(score) or score < .6):
                Notice.warning(
                    self, "代理预测精度偏低",
                    f"{name} 留出集 R²={score}。请检查异常样本、补充采样或"
                    "调整模型参数；优化候选应另做确认。")
        service.record_operation(
            "代理模型训练",
            "部分完成" if any(
                item.get("error") for item in result["responses"].values())
            else "完成",
            {"results": {"surrogate": result}})
        return result

    def _build_surrogate_context(self):
        """把已训练的代理预测器接入鲁棒优化上下文。"""
        return model_service.build_surrogate_context(self.project_data)

    # ============================================================ 工作台
    def _analysis_settings(self):
        return {"mode": self.robust_mode_combo.currentText(), "k_design": self.k_design_spin.value(),
                "k_constraint": self.k_constraint_spin.value(), "weight": self.weight_spin.value(),
                "sigma_limits": {self.sigma_limits_table.item(i,0).data(256): self.sigma_limits_table.item(i,1).text() for i in range(self.sigma_limits_table.rowCount()) if self.sigma_limits_table.item(i,1)}, "population": self.pop_spin.value(), "generations": self.gen_spin.value(), "seed": 7}

    def run_workbench(self):
        return self.controller.run_workbench()

    def _worker_finished(self):
        return self.controller._worker_finished()

    def _optimization_failed(self, message):
        return self.controller._optimization_failed(message)

    def _optimization_ready(self, robust):
        return self.controller._optimization_ready(robust)

    def _execute_workbench(self):
        return self.controller._execute_workbench()

    def _prepare_context(self):
        return self.controller._prepare_context()

    def run_statistics(self):
        return self.controller.run_statistics()

    def _update_analysis(self, context, robust):
        return self.controller._update_analysis(context, robust)

    def _fill_level_table(self, ls):
        rows = ls.get("rows", [])
        self.level_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [r["factor"], f"{r['level']:.4g}", r["response"],
                    f"{r['mean']:.4g}", f"{r['var']:.4g}" if math.isfinite(r["var"]) else "不可估计", f"{r['range']:.4g}",
                    str(r["n"]), f"{r['F']:.4g}" if math.isfinite(r["F"]) else "不可估计", f"{r['p']:.4g}" if math.isfinite(r["p"]) else "不可估计"]
            for j, v in enumerate(vals):
                self.level_table.setItem(i, j, QTableWidgetItem(v))

    def _plot_pareto(self, robust):
        optimization_plots.pareto(
            self.pareto_fig, self.pareto_canvas, robust)

    def _plot_residual(self, residual_data):
        optimization_plots.residual(
            self.resid_fig, self.resid_canvas, residual_data)

    def _plot_factor(self, plots):
        optimization_plots.factor_effects(
            self.factor_fig, self.factor_canvas, plots)

    def _run_tool(self):
        return self.controller._run_tool()

from rams.ui.notifications import Notice
