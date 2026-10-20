"""UI workflow coordinator for the optimization page."""
from PyQt6.QtWidgets import QMessageBox

from backend.engines import design_analysis as da
from backend.engines import doe as engine
from backend.engines import optimizer as oe
from backend.reporting import report_engine as reports
import logging

from frontend.notifications import Notice
from frontend.pages.qt_tasks import OptimizationWorker
from frontend.pages.workbench_diagnostics import WorkbenchDiagnostics
from backend.services import analysis_service, model_service


class OptimizationController:
    def __init__(self, page):
        self.page = page

    def run_optimization(self):
        page = self.page
        page._check_inputs()
        method = page._method()
        if not method:
            Notice.warning(page, "无方案", "请先在【方案配置】生成试验方案。")
            return
        try:
            if "筛选" in method:
                page._run_screening()
            elif "响应曲面" in method:
                page._run_rsm()
            elif "田口" in method:
                page._run_taguchi()
            elif "代理模型" in method:
                page._run_surrogate()
        except Exception as exc:  # noqa: BLE001
            page.project_service.record_operation("后端分析", "失败", message=str(exc))
            Notice.critical(page, "分析失败", f"后端分析出错：{exc}")
            return
        page.status_label.setText("分析完成：结果已更新")
        page._refresh_view()
        if "筛选" in method:
            page.tabs.setCurrentWidget(page.screening_panel)
            page._finish_classic(page.project_data.screening_result)
            return
        if "田口" in method:
            page.tabs.setCurrentWidget(page.taguchi_panel)
            page._finish_classic(page.project_data.taguchi_result)
            return
        Notice.information(
            page, "分析完成",
            "后端分析已完成，当前方案的摘要与结果已自动更新。"
            "可前往【分析报告】查看并导出报告。")
        page.optimization_finished.emit()

    def _check_inputs(self):
        page = self.page
        page.project_service.ensure_current()
        signature = page.project_service.input_signature()
        if signature != page._input_signature:
            page._input_signature = signature
            page._oe_context = None
            page._robust_res = {}
            page._param_res = {}
            page._resid_data = {}
            page.diagnostics_panel.clear()
            page.screening_panel.set_result({})
            page.taguchi_panel.set_result({})
            page.tol_table.setRowCount(0)
            page.tool_table.setRowCount(0)
            for name in ("robust_text", "signif_text", "cv_text", "param_text", "tol_text", "model_text", "tool_text"):
                getattr(page, name).clear()
            for name in ("pareto", "resid", "factor"):
                fig, canvas = getattr(page, name + "_fig", None), getattr(page, name + "_canvas", None)
                if fig is not None:
                    fig.clear()
                    canvas.draw()
            page.status_label.setText("输入已更新，请重新执行当前方案分析。")
            page._refresh_view()

    def run_workbench(self):
        page = self.page
        if getattr(page, "_worker", None) is not None:
            return
        if any(x in page._method() for x in ("筛选", "田口")):
            page.run_optimization()
            return
        from frontend.notifications import bus
        try:
            page._check_inputs()
            bus.post("进度", "模型准备", "检查数据与当前模型配置")
            context = page._prepare_context()
            mode = {"多目标 NSGA-II":"multi", "加权单目标":"weighted", "约束型":"constraint"}[page.robust_mode_combo.currentText()]
            limits = page._sigma_limits() if mode == "constraint" else {}
            page.project_service.clear_workbench()
            page._run_signature = page.project_service.input_signature()
            page._worker = OptimizationWorker(context, dict(mode=mode, pop=page.pop_spin.value(), gen=page.gen_spin.value(),
                weight=page.weight_spin.value(), k_design=page.k_design_spin.value(), k_constraint=page.k_constraint_spin.value(),
                seed=7, sigma_limits=limits), page)
            page.setEnabled(False)
            page._worker.progress.connect(lambda done,total: bus.post("进度", "鲁棒优化", f"已完成 {done}/{total} 代"))
            page._worker.result_ready.connect(page._optimization_ready)
            page._worker.failed.connect(page._optimization_failed)
            page._worker.finished.connect(page._worker_finished)
            page.status_label.setText("正在后台计算，进度见下方消息面板…")
            page._worker.start()
        except Exception as exc:
            page._optimization_failed(str(exc))

    def _worker_finished(self):
        page = self.page
        worker = page._worker
        page._worker = None
        worker.deleteLater()
        page.setEnabled(True)

    def _optimization_failed(self, message):
        page = self.page
        page.status_label.setText("优化失败：" + message)
        page._oe_context = None
        page._robust_res = {}
        page.robust_text.clear()
        page.project_service.clear_workbench()
        Notice.warning(page, "优化失败", message)

    def _optimization_ready(self, robust):
        page = self.page
        try:
            if page.project_service.input_signature() != page._run_signature:
                raise ValueError("计算期间输入已改变，本次结果已丢弃，请重新运行。")
            if robust.get("error"):
                raise ValueError(robust["error"])
            page._oe_context["sigma_limits"] = robust.get("sigma_limits", {})
            page._robust_res = robust
            page.robust_text.setText(robust["text"])
            page._plot_pareto(robust)
            page._update_analysis(page._oe_context, robust)
            page.status_label.setText("计算完成" if robust["feasible_count"] else "计算完成，未找到可行候选")
            page.optimization_finished.emit()
        except Exception as exc:
            page._optimization_failed(str(exc))

    def _execute_workbench(self):
        page = self.page
        page._check_inputs()
        if any(x in page._method() for x in ("筛选", "田口")):
            page.run_optimization()
            return
        context = page._prepare_context()
        mode = {"多目标 NSGA-II": "multi", "加权单目标": "weighted",
                "约束型": "constraint"}[page.robust_mode_combo.currentText()]
        pop = page.pop_spin.value()
        gen = page.gen_spin.value()
        weight = page.weight_spin.value()
        kd = page.k_design_spin.value()
        kc = page.k_constraint_spin.value()
        page.status_label.setText("正在执行鲁棒优化与稳定性分析…（可能稍候）")
        robust = oe.robust_optimize(context, mode=mode, pop=pop, gen=gen,
                                    weight=weight, k_design=kd,
                                    k_constraint=kc, seed=7, sigma_limits=page._sigma_limits() if mode == "constraint" else None)
        if robust.get("error"):
            raise ValueError(robust["error"])
        context["sigma_limits"] = robust.get("sigma_limits", {})
        page._robust_res = robust
        page.robust_text.setText(robust.get("text", robust.get("error", "")))
        page._plot_pareto(robust)
    
        page._update_analysis(context, robust)
    
        page.status_label.setText("分析完成：全部工作台已更新")
        Notice.information(
            page, "稳定性设计分析完成",
            "已执行鲁棒优化与全套稳定性分析。可切换标签页查看帕累托/Knee点、推荐取值、"
            "容差贡献与模型方程，或使用优化工具集做更深入的取值探索。")
        page.optimization_finished.emit()

    def _prepare_context(self):
        page = self.page
        page._oe_context = None
        if "代理模型" in page._method():
            saved = page.project_data.surrogate_result or {}
            if saved.get("signature") != page._surrogate_signature():
                page._run_surrogate()
            context, errors = page._build_surrogate_context()
        elif "响应曲面" in page._method():
            context, errors = page._run_rsm(), []
        else:
            context, errors = oe.build_models(page.project_data)
        if errors or not context or not context["models"]:
            raise ValueError("\n".join(errors or ["缺少可建模的响应数据。"]))
    
        page._oe_context = context
        return context

    def run_statistics(self):
        page = self.page
        page._check_inputs()
        page.stats_btn.setEnabled(False)
        try:
            context = page._prepare_context()
            page._robust_res = {}
            page.robust_text.clear()
            page._plot_pareto({})
            page._update_analysis(context, {})
            page.tabs.setCurrentWidget(page.diagnostics_panel)
            page.status_label.setText("建模与统计分析完成，未执行鲁棒优化。")
            page.optimization_finished.emit()
        except Exception as exc:
            page.project_service.record_operation("工作台统计分析", "失败", {"settings": page._analysis_settings()}, message=str(exc))
            logging.exception("统计分析失败")
            page.status_label.setText(f"统计分析失败：{exc}")
            Notice.warning(page, "统计分析失败", str(exc))
        finally:
            page.stats_btn.setEnabled(True)

    def _update_analysis(self, context, robust):
        page = self.page
        kd = page.k_design_spin.value()
        kc = page.k_constraint_spin.value()
        bundle = analysis_service.analyze(
            page.project_data, context, robust, kd, kc)
    
        page._refresh_view()
        page.signif_text.setPlainText(bundle["anova_text"])
        page._resid_data = bundle["residual_data"]
        page.cv_text.setPlainText(bundle["validation_text"])
        page._plot_residual(page._resid_data)
    
        page._param_res = bundle["parameter_design"]
        page.param_text.setText(page._param_res.get("text", ""))
        page._plot_factor(page._param_res.get("factor_plots", []))
        page.tol_text.setText(bundle["tolerance_text"])
        page.model_text.setPlainText(bundle["model_text"])
    
        page.diagnostics_panel.set_context(
            context, robust, kd, kc, snapshot=bundle["snapshot"])
        page.diagnostics_panel.fill(
            page.tol_table,
            [{"响应": name, "因子": row["name"],
              "局部方差": row["variance"], "份额 %": row["share"]}
             for name, rows in bundle["tolerance"].items()
             for row in rows])
    
        service = page.project_service
        service.publish_results(
            expected_signature=getattr(page, "_run_signature", None),
            workbench_result=reports.serializable(bundle["snapshot"]))
        failed = bool(robust and robust.get("feasible_count", 0) == 0)
        service.record_operation(
            "鲁棒优化与统计分析" if robust else "工作台统计分析",
            "未通过" if failed else "完成",
            {"results": reports.results(page.project_data)},
            "未找到可行候选" if failed else "计算完成，工程结论待确认")

    def _run_tool(self):
        page = self.page
        page._check_inputs()
        if not page._oe_context:
            Notice.warning(
                page, "无模型", "请先点击【执行稳定性设计与鲁棒优化】。")
            return
        tool = page.tool_combo.currentText()
        k_design = page.k_design_spin.value()
        start = (page._param_res or {}).get("recommended")
        if page.tool_start.currentText() == "手动核验点":
            start = (
                page.diagnostics_panel.snapshot.get("point_evaluation")
                or {}).get("point")
            if not start:
                Notice.warning(
                    page, "缺少起点", "请先在统计诊断页计算手动设计点。")
                return
        elif page.tool_start.currentText() == "区间中心":
            start = None
        if not start:
            page.tool_start.setCurrentText("区间中心")
            design_inputs = oe.design_inputs(page._oe_context)
            start = {
                factor.name: sum(engine.factor_limits(factor)) / 2.0
                for factor in design_inputs
            }
    
        service = page.project_service
        try:
            method = (
                "最陡上升" if "最陡上升" in tool else
                "EVOP" if "EVOP" in tool else "AOFAT")
            result = analysis_service.run_local_search(
                page._oe_context, start, k_design,
                page.k_constraint_spin.value(), page.tool_weight.value(),
                method, page.tool_steps.value(), page.tool_step.value())
            page.tool_text.setPlainText(result["text"])
            page.diagnostics_panel.fill(
                page.tool_table,
                [{"轮次": row["iteration"], **row["x"],
                  "望性": row["mean"], "归一标准差": row["std"],
                  "约束违反": row["violation"], "加权损失": row["score"],
                  "可行": row["feasible"]}
                 for row in result["trials"]])
            page.diagnostics_panel.snapshot["local_search"] = result
            service.update_workbench(
                local_search=reports.serializable(result))
            service.record_operation(
                "局部探索",
                "完成" if result["best"]["feasible"] else "未通过",
                {"workbench": reports.serializable(
                    page.diagnostics_panel.snapshot)},
                result["text"])
        except Exception as exc:
            page.tool_table.setRowCount(0)
            page.tool_text.setPlainText(f"探索失败：{exc}")
            service.record_operation("局部探索", "失败", message=str(exc))
