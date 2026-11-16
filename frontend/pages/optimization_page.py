
from __future__ import annotations

import math

import matplotlib
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QTableWidgetItem,
    QWidget,
)

from backend.core.design_evaluation import DEFAULT_K_CONSTRAINT, DEFAULT_K_DESIGN
from backend.domain.models import ProjectData
from backend.engines import design_analysis as da
from backend.engines import optimizer as oe
from backend.reporting.math_format import PLOT_STYLE
from backend.services import model_service
from backend.services.project_service import ProjectService
from frontend.notifications import Notice
from frontend.pages import optimization_panels
from frontend.pages.optimization_controller import OptimizationController

matplotlib.use("QtAgg")
matplotlib.rcParams.update(PLOT_STYLE)


class OptimizationPage(QWidget):
    optimization_finished = pyqtSignal()

    def __init__(self, project_data: ProjectData):
        super().__init__()
        self.project_data = project_data
        self.project_service = ProjectService.for_project(project_data)
        self.project_service.ensure_current()
        self._input_signature = self.project_service.input_signature()
        self.controller = OptimizationController(self)
        self.init_ui()

    def init_ui(self):
        return optimization_panels.build(self)

    def _settings_changed(self, *_args):
        if self._oe_context:
            self.model_overview.clear()
            self._oe_context = None
            self._robust_res = {}
            self.robust_results.clear()
            self.history_panel.clear()
            self.status_label.setText("优化参数已改变；已有优化结果属于先前设置，请重新执行。")

    def _update_method_actions(self):
        if hasattr(self, "strategy_group"):
            self._update_uncertainty_tooltip()
            self._update_mutation_probability()
        method = self._method()
        is_taguchi = "田口" in method
        if is_taguchi:
            self.run_all_btn.setText("执行田口分析")
        else:
            self.run_all_btn.setText("执行鲁棒优化设计")
        for index in (1, 2, 3, 4, 5, 6, 8):
            self.tabs.setTabVisible(index, not is_taguchi)
        self.tabs.setTabVisible(7, is_taguchi)
        self.stats_btn.setVisible(not is_taguchi)
        if hasattr(self, "robust_settings_header"):
            actions = (
                self.taguchi_panel.settings_header
                if is_taguchi and self.tabs.currentWidget() is self.taguchi_panel
                else self.primary_actions
                if is_taguchi
                else self.robust_settings_header
            )
            if actions.indexOf(self.run_all_btn) < 0:
                actions.addWidget(self.run_all_btn)
        if hasattr(self, "results_workspace"):
            self.results_workspace.refresh()
        self.run_all_btn.setToolTip(
            "田口设计根据内表×外表响应计算信噪比并推荐稳健水平"
            if is_taguchi
            else "二次响应面模型和代理模型进入鲁棒优化设计工作台"
        )

    def _run_primary_action(self):
        method = self._method()
        if "田口" in method:
            self.run_optimization()
        else:
            self.run_workbench()

    def _build_overview_tab(self):
        return optimization_panels.build_overview_tab(self)

    def _show_model_detail(self, kind, response):
        panel = {
            "significance": self.signif_panel,
            "validation": self.cv_panel,
            "model": self.model_panel,
        }[kind]
        panel.response.setCurrentIndex(panel.response.findData(response))
        self.tabs.setCurrentWidget(panel.parentWidget())

    def _build_robust_tab(self):
        return optimization_panels.build_robust_tab(self)

    def _on_robust_mode(self, _text=None):
        mode = self.robust_mode_combo.currentData()
        self.sigma_limits_group.setVisible(mode == "constraint")
        if mode == "constraint":
            from frontend.numeric_inputs import numeric_text_input

            saved = {name: editor.text() for name, editor in self.sigma_limit_inputs.items()}
            responses = [
                r
                for r in self.project_data.responses
                if r.name and (not oe.self_is_constraint(r) or "目标" in r.kind)
            ]
            self.sigma_limit_inputs = {}
            self.sigma_limits_table.setRowCount(0)
            self.sigma_limits_table.setRowCount(len(responses))
            for i, r in enumerate(responses):
                self.sigma_limits_table.setItem(i, 0, QTableWidgetItem(r.name))
                self.sigma_limits_table.setItem(i, 2, QTableWidgetItem(r.unit or "—"))
                editor = numeric_text_input(saved.get(r.name, ""))
                editor.setPlaceholderText("请输入正数")
                editor.setStyleSheet(
                    "QLineEdit { border:1px solid #bdcbd8; border-radius:3px; "
                    "margin:3px 8px; padding:3px 7px; background:#f8fbfe; }"
                )
                editor.setToolTip(
                    f"{r.name} 的标准差上限（Standard Deviation Limit）\n"
                    f"单位：{r.unit or '无量纲'}。填写大于零的数值，限制该响应的波动程度。"
                )
                editor.textChanged.connect(self._settings_changed)
                self.sigma_limit_inputs[r.name] = editor
                self.sigma_limits_table.setCellWidget(i, 1, editor)
                self.sigma_limits_table.setRowHeight(i, 38)
            self.sigma_limits_table.setFixedHeight(
                self.sigma_limits_table.horizontalHeader().height()
                + 38 * min(max(len(responses), 1), 5)
                + 4
            )
        self.weight_fields.setVisible(mode == "weighted")
        self.weight_spin.setEnabled(mode == "weighted")

    def _sigma_limits(self):
        if self.robust_mode_combo.currentData() != "constraint":
            return {}
        limits = {}
        for name, editor in self.sigma_limit_inputs.items():
            try:
                value = float(editor.text())
            except (ValueError, AttributeError):
                raise ValueError(f"请填写 {name} 的允许最大标准差。")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} 的标准差上限必须是有限正数。")
            limits[name] = value
        return limits

    def _update_uncertainty_tooltip(self, *_args):
        sigmas = [
            f"{f.name}: σ={oe._sigma_of_factor(f, DEFAULT_K_DESIGN):.6g}"
            for f in self.project_data.factors
            if f.name
        ]
        self.strategy_group.setToolTip(
            "鲁棒优化设置（Robust Optimization Settings）\n"
            "约束裕量系数固定为1。区间不确定性等价为区间上的均匀分布，标准差=区间宽度/√12，"
            "对应换算系数√3；设计变量采用偏差区间，不确定性参数采用实际区间。"
            "概率输入直接采用所定义的方差，响应传播继续使用局部二阶矩近似。\n当前输入标准差："
            + "；".join(sigmas)
        )
        self.robust_settings_heading.setToolTip(self.strategy_group.toolTip())

    def _update_mutation_probability(self, *_args):
        automatic = self.mutation_mode_combo.currentData() == "auto"
        self.mutation_spin.setEnabled(not automatic)
        if automatic:
            count = len([f for f in self.project_data.factors if f.name and f.source == "设计"])
            self.mutation_spin.setValue(1.0 / max(count, 1))

    def _on_auto_stop(self, enabled):
        for control in (self.stall_gen_spin, self.tolerance_spin):
            control.setEnabled(bool(enabled))

    def _optimizer_settings(self):
        return dict(
            mode=self.robust_mode_combo.currentData(),
            pop=self.pop_spin.value(),
            gen=self.gen_spin.value(),
            weight=self.weight_spin.value(),
            k_design=DEFAULT_K_DESIGN,
            k_constraint=DEFAULT_K_CONSTRAINT,
            seed=self.seed_spin.value(),
            pc=self.crossover_spin.value(),
            pm=None
            if self.mutation_mode_combo.currentData() == "auto"
            else self.mutation_spin.value(),
            eta_c=self.eta_c_spin.value(),
            eta_m=self.eta_m_spin.value(),
            auto_stop=self.auto_stop_check.isChecked(),
            stall_generations=self.stall_gen_spin.value(),
            tolerance=round(self.tolerance_spin.value() / 100.0, 6),
            sigma_limits=self._sigma_limits(),
            enforce_objective_limits=self.objective_limits_check.isChecked(),
        )

    def _build_signif_tab(self):
        return optimization_panels.build_signif_tab(self)

    def _build_cv_tab(self):
        return optimization_panels.build_cv_tab(self)

    def _build_model_tab(self):
        return optimization_panels.build_model_tab(self)

    def _build_history_tab(self):
        return optimization_panels.build_history_tab(self)

    def _responses(self):
        return [r for r in self.project_data.responses if r.name]

    def _method(self):
        return self.project_data.design_method or ""

    def _refresh_view(self):
        self._update_method_actions()
        self.overview.set_project(self.project_data)

    def run_optimization(self):
        return self.controller.run_optimization()

    def _finish_classic(self, result):
        self.status_label.setText(result.get("analysis_status", "分析完成"))
        self.optimization_finished.emit()

    def _check_inputs(self):
        return self.controller._check_inputs()

    def showEvent(self, event):
        super().showEvent(event)
        self._check_inputs()
        self._update_method_actions()
        self._on_robust_mode(self.robust_mode_combo.currentText())
        self.taguchi_panel.set_result(self.project_data.taguchi_result)

    def _run_rsm(self):
        context = model_service.build_rsm_context(self.project_data)
        self._oe_context = context
        result = self._store_rsm_fit(context)
        self.project_service.record_operation(
            "二次响应面建模", payload={"results": {"rsm": result}}
        )
        return context

    def _store_rsm_fit(self, context):
        result = model_service.rsm_result(self.project_data, context)
        self.project_service.publish_results(rsm_result=result)
        return result

    def _run_taguchi(self):
        service = self.project_service
        result = da.taguchi(self.project_data)
        service.publish_results(taguchi_result=result)
        self.taguchi_panel.set_result(result)
        service.record_operation(
            "田口分析",
            "部分完成" if result.get("errors") else "完成",
            {"results": {"taguchi": result}},
        )

    def _surrogate_signature(self):
        return model_service.surrogate_signature(self.project_data)

    def _run_surrogate(self):
        service = self.project_service
        result = model_service.train_surrogates(self.project_data)
        service.publish_results(surrogate_result=result)
        failures = [
            f"{name}：{item['error']}"
            for name, item in result["responses"].items()
            if item.get("error")
        ]
        if failures:
            self._oe_context = None
            self._robust_res = {}
            self.robust_results.clear()
            self.history_panel.clear()
            service.clear_workbench()
        for name, response_result in result["responses"].items():
            score = response_result.get("r2_test")
            if score is not None and (not math.isfinite(score) or score < 0.6):
                Notice.warning(
                    self,
                    "代理预测精度偏低",
                    f"{name} 测试集决定系数={score}。请检查异常样本、补充采样或"
                    "调整模型参数；优化候选应另做确认。",
                )
        service.record_operation(
            "代理模型训练",
            ("失败" if len(failures) == len(result["responses"]) else "部分完成")
            if failures
            else "完成",
            {"results": {"surrogate": result}},
            message="\n".join(failures),
        )
        return result

    def _build_surrogate_context(self):
        return model_service.build_surrogate_context(self.project_data)

    def _analysis_settings(self):
        return {
            "enforce_objective_limits": self.objective_limits_check.isChecked(),
            "mode": self.robust_mode_combo.currentData(),
            "k_design": DEFAULT_K_DESIGN,
            "k_constraint": DEFAULT_K_CONSTRAINT,
            "weight": self.weight_spin.value(),
            "sigma_limits": {
                name: editor.text() for name, editor in self.sigma_limit_inputs.items()
            },
            "population": self.pop_spin.value(),
            "generations": self.gen_spin.value(),
            "seed": self.seed_spin.value(),
            "pc": self.crossover_spin.value(),
            "mutation_mode": self.mutation_mode_combo.currentData(),
            "pm": self.mutation_spin.value(),
            "eta_c": self.eta_c_spin.value(),
            "eta_m": self.eta_m_spin.value(),
            "auto_stop": self.auto_stop_check.isChecked(),
            "stall_generations": self.stall_gen_spin.value(),
            "tolerance": round(self.tolerance_spin.value() / 100.0, 6),
        }

    def run_workbench(self):
        return self.controller.run_workbench()

    def _worker_finished(self):
        return self.controller._worker_finished()

    def _optimization_failed(self, message):
        return self.controller._optimization_failed(message)

    def _optimization_ready(self, robust):
        return self.controller._optimization_ready(robust)

    def _prepare_context(self):
        return self.controller._prepare_context()

    def run_statistics(self):
        return self.controller.run_statistics()

    def _update_analysis(self, context, robust):
        return self.controller._update_analysis(context, robust)
