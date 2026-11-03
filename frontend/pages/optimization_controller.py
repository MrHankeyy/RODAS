"""UI workflow coordinator for the optimization page."""
from PyQt6.QtWidgets import QMessageBox

from backend.engines import design_analysis as da
from backend.engines import doe as engine
from backend.core.design_evaluation import DEFAULT_K_DESIGN, DEFAULT_K_CONSTRAINT
from backend.engines import optimizer as oe
from backend.reporting import report_engine as reports
import logging

from frontend.notifications import Notice
from frontend.numeric_inputs import commit_numeric_inputs
from frontend.pages.qt_tasks import OptimizationWorker
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
            elif any(text in method for text in ("响应面", "响应曲面")):
                page._run_rsm()
            elif "田口" in method:
                page._run_taguchi()
            elif "代理模型" in method:
                result = page._run_surrogate()
                errors = [f"响应 {name}：{item['error']}" for name, item in result["responses"].items() if item.get("error")]
                if errors:
                    raise ValueError("\n".join(errors))
        except Exception as exc:  # noqa: BLE001
            page.status_label.setText(f"分析失败：{exc}")
            page._refresh_view()
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
        commit_numeric_inputs(page)
        page.project_service.ensure_current()
        signature = page.project_service.input_signature()
        if signature != page._input_signature:
            page._input_signature = signature
            page._oe_context = None
            page._robust_res = {}
            page.model_overview.clear()
            page.screening_panel.set_result({})
            page.taguchi_panel.set_result({})
            for name in ("robust_results", "signif_panel", "cv_panel", "model_panel"):
                getattr(page, name).clear()
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
            settings = page._optimizer_settings()
            page.project_service.clear_workbench()
            page._run_signature = page.project_service.input_signature()
            page._worker = OptimizationWorker(context, settings, page)
            page.setEnabled(False)
            page._worker.progress.connect(lambda done,total: bus.post("进度", "鲁棒性优化设计", f"已完成 {done}/{total} 代"))
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
        page.robust_results.clear()
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
        page.status_label.setText("正在执行鲁棒性优化设计与统计分析…（可能稍候）")
        robust = oe.robust_optimize(context, **page._optimizer_settings())
        if robust.get("error"):
            raise ValueError(robust["error"])
        context["sigma_limits"] = robust.get("sigma_limits", {})
        page._robust_res = robust
    
        page._update_analysis(context, robust)
    
        page.status_label.setText("分析完成：全部工作台已更新")
        Notice.information(
            page, "鲁棒性优化设计分析完成",
            "已执行鲁棒性优化设计与统计分析。可切换标签页查看帕累托前沿、折中解、推荐取值、"
            "方案对比、波动核验与模型方程。")
        page.optimization_finished.emit()

    def _prepare_context(self):
        page = self.page
        page._oe_context = None
        if "代理模型" in page._method():
            saved = page.project_data.surrogate_result or {}
            if saved.get("signature") != page._surrogate_signature():
                page._run_surrogate()
            context, errors = page._build_surrogate_context()
        elif any(text in page._method() for text in ("响应面", "响应曲面")):
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
            page.robust_results.clear()
            page._update_analysis(context, {})
            page.tabs.setCurrentWidget(page.tab_overview)
            page.status_label.setText("建模与统计分析完成，未执行鲁棒性优化设计。")
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
        kd = DEFAULT_K_DESIGN
        kc = DEFAULT_K_CONSTRAINT
        bundle = analysis_service.analyze(
            page.project_data, context, robust, kd, kc)
        bundle['snapshot']['settings'] = page._analysis_settings()
        page.robust_results.set_result(context, robust)
    
        page._refresh_view()
        for panel in (page.signif_panel, page.cv_panel, page.model_panel):
            panel.set_result(context, bundle["snapshot"])
    
        page.model_overview.set_result(context, bundle["snapshot"])
        service = page.project_service
        service.publish_results(
            expected_signature=getattr(page, "_run_signature", None),
            workbench_result=reports.serializable(bundle["snapshot"]))
        failed = bool(robust and robust.get("feasible_count", 0) == 0)
        service.record_operation(
            "鲁棒性优化设计与统计分析" if robust else "工作台统计分析",
            "未通过" if failed else "完成",
            {"results": reports.results(page.project_data)},
            "未找到可行候选" if failed else "计算完成，工程结论待确认")

    def restore_results(self):
        """Repopulate saved views using restored predictors; never fit a model."""
        page = self.page
        project = page.project_data
        snapshot = project.workbench_result
        settings = snapshot.get('settings', {})
        for key, control in (('population', page.pop_spin), ('generations', page.gen_spin),
                             ('weight', page.weight_spin), ('seed', page.seed_spin),
                             ('pc', page.crossover_spin), ('eta_c', page.eta_c_spin),
                             ('eta_m', page.eta_m_spin)):
            if key in settings:
                control.setValue(settings[key])
        if 'mode' in settings:
            index = page.robust_mode_combo.findData(settings['mode'])
            if index >= 0:
                page.robust_mode_combo.setCurrentIndex(index)
        if 'mutation_mode' in settings:
            page.mutation_mode_combo.setCurrentIndex(page.mutation_mode_combo.findData(settings['mutation_mode']))
        if settings.get('mutation_mode') == 'manual':
            page.mutation_spin.setValue(settings['pm'])
        for name, editor in page.sigma_limit_inputs.items():
            if name in settings.get('sigma_limits', {}):
                editor.setText(settings['sigma_limits'][name])
        page._refresh_view()
        page.screening_panel.set_result(project.screening_result)
        page.taguchi_panel.set_result(project.taguchi_result)
        context = None
        if project.surrogate_result:
            context, _ = model_service.build_surrogate_context(project)
        elif page.project_service.model_cache.get('rsm'):
            context = model_service.build_rsm_context(project)
        if context is None:
            return
        page._oe_context = context
        robust = snapshot.get('optimization', {})
        context['sigma_limits'] = robust.get('sigma_limits', {})
        page._robust_res = robust
        page.robust_results.set_result(context, robust, snapshot.get('optimization_view_index'))
        if snapshot:
            for panel in (page.signif_panel, page.cv_panel, page.model_panel):
                panel.set_result(context, snapshot)
            page.model_overview.set_result(context, snapshot)
        page.status_label.setText('已恢复任务中的模型与结果，可直接预测或继续分析。')
