"""Role-aware wording and independently enabled objective performance limits."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QGroupBox
from backend.domain.models import ResponseItem
from backend.core.design_evaluation import evaluate_design
from backend.services import analysis_service, task_storage
from backend.reporting import report_engine
from frontend.main_window import MainWindow
from frontend.pages.definition_editors import ResponseEditor
from frontend.pages.optimization_page import OptimizationPage
from frontend.terminology import tooltip
from test_ui_constraints import APP, quadratic, oe


class ResponseSemanticsTests(unittest.TestCase):
    def test_role_changes_criterion_and_threshold_meaning_without_changing_value(self):
        editor = ResponseEditor(ResponseItem(name='Y', feature='望小', robust_limit='5'))
        self.addCleanup(editor.deleteLater)
        self.assertEqual(editor.feature.currentText(), '最小化')
        self.assertIn('目标鲁棒性阈值', editor.limit.toolTip())
        self.assertIn('不是标准差上限', editor.limit.toolTip())
        editor.constraint.click()
        self.assertEqual(editor.feature.currentText(), '不大于上限')
        self.assertEqual(editor.limit_label.text(), '约束上限')
        self.assertIn('约束阈值', editor.limit.toolTip())
        self.assertEqual(editor.collect().robust_limit, '5')
        self.assertEqual(editor.collect().feature, '望小')
        editor.feature.setCurrentIndex(editor.feature.findData('望目'))
        self.assertEqual(editor.feature.currentText(), '位于区间内')
        self.assertEqual(editor.lower_label.text(), '约束下限')
        editor.objective.click()
        self.assertEqual(editor.feature.currentText(), '趋近目标值')
        self.assertEqual(editor.lower_label.text(), '目标下限')

    def test_navigation_distinguishes_module_page_and_definition_group(self):
        window = MainWindow()
        window.task_actions.confirm_leave = lambda **kwargs: True
        self.addCleanup(window.close)
        for index in range(5):
            window.switch_page(index)
            self.assertNotEqual(window.btns_switch[index].text(), window.page_title.text())
        headings = [g.title() for g in window.page_MOD.results_workspace.findChildren(QGroupBox)]
        self.assertIn('问题参数', headings)
        self.assertNotIn('业务建模', headings)

    def test_objective_limit_is_optional_and_does_not_change_response_role(self):
        _, context = quadratic()
        context['_responses'][0].robust_limit = '.55'
        before = evaluate_design(context, {'X':.8}, 6, .5, use_constraints=True, k_constraint=1)
        self.assertEqual(before['infeas'], 0)
        scoped = dict(context, enforce_objective_limits=True)
        after = evaluate_design(scoped, {'X':.8}, 6, .5, use_constraints=True, k_constraint=1)
        self.assertGreater(after['infeas'], 0)
        self.assertEqual([r['name'] for r in after['objectives']], ['Y'])
        self.assertEqual(after['constraints'], [])
        point = analysis_service.evaluate_point(scoped, {'X':.8}, 6, 1)
        self.assertFalse(point['feasible'])
        self.assertLess(point['responses'][0]['约束余量'], 0)
        self.assertEqual(point['responses'][0]['约束来源'], '目标鲁棒性要求')

    def test_both_one_sided_and_interval_performance_limits(self):
        _, context = quadratic()
        response = context['_responses'][0]
        context['enforce_objective_limits'] = True
        for feature, bound in [('望大', '.55'), ('望小', '.3'), ('望目', '')]:
            response.feature, response.robust_limit = feature, bound
            response.lower, response.upper = '.55', '.75'
            result = analysis_service.evaluate_point(context, {'X':.8}, 6, 1)
            self.assertFalse(result['feasible'], feature)
            self.assertLess(result['responses'][0]['约束余量'], 0, feature)

    def test_three_strategies_enforce_performance_alongside_sigma_constraints(self):
        for mode in ('multi', 'weighted', 'constraint'):
            p, context = quadratic()
            p.responses[0].robust_limit = '.55'
            result = oe.robust_optimize(context, mode=mode, enforce_objective_limits=True,
                sigma_limits={'Y':.3} if mode == 'constraint' else None,
                k_design=6, k_constraint=1, pop=20, gen=12, seed=7)
            self.assertGreater(result['feasible_count'], 0)
            self.assertLessEqual(result['best']['infeas'], 1e-8)
            self.assertEqual(result['best']['responses'][0]['role'], '目标')
            self.assertEqual(result['objective_names'], ['Y'])
            self.assertEqual(result['constraint_names'], [])
            self.assertEqual(result['objective_limit_names'], ['Y'])
            records, index = analysis_service.optimization_schemes(context, result)
            row = records[index]['verification']['responses'][0]
            self.assertGreaterEqual(row['约束余量'], -1e-8)
            if mode == 'constraint':
                self.assertIsNotNone(row['标准差上限'])
                self.assertGreaterEqual(row['波动约束余量'], -1e-8)
            self.assertNotIn('enforce_objective_limits', context)

    def test_missing_invalid_and_impossible_objective_limits(self):
        _, context = quadratic()
        response = context['_responses'][0]
        for value in ('', 'nan', 'inf', 'bad'):
            response.robust_limit = value
            with self.assertRaises(ValueError):
                oe.robust_optimize(context, enforce_objective_limits=True, pop=8, gen=2)
        response.robust_limit = '10'
        result = oe.robust_optimize(context, enforce_objective_limits=True, pop=8, gen=2)
        self.assertEqual(result['feasible_count'], 0)
        self.assertFalse(result['front'])
        self.assertGreater(result['best']['infeas'], 0)

    def test_constraint_response_remains_mandatory_when_goal_option_is_off(self):
        _, context = quadratic()
        response = context['_responses'][0]
        response.kind, response.robust_limit = '约束', '.55'
        point = analysis_service.evaluate_point(context, {'X':.8}, 6, 1)
        self.assertFalse(point['feasible'])
        self.assertEqual(point['responses'][0]['约束来源'], '约束响应')

    def test_saved_task_restores_the_performance_constraint_and_report(self):
        p, _ = quadratic()
        p.responses[0].robust_limit = '.55'
        page = OptimizationPage(p)
        self.addCleanup(page.close)
        page.objective_limits_check.setChecked(True)
        page.robust_mode_combo.setCurrentIndex(page.robust_mode_combo.findData('weighted'))
        page.pop_spin.setValue(20)
        page.gen_spin.setValue(30)
        page._execute_workbench()
        self.assertTrue(p.workbench_result['settings']['enforce_objective_limits'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'goal-performance.rodas'
            task_storage.save_task(p, path)
            restored = task_storage.load_task(path)
            other = OptimizationPage(restored)
            self.addCleanup(other.close)
            other.controller.restore_results()
            self.assertTrue(other.objective_limits_check.isChecked())
            self.assertTrue(other._oe_context['enforce_objective_limits'])
            report = report_engine.build_current_report(report_engine.bundle(restored))
            html = report_engine.render_html(report)
            self.assertIn('目标鲁棒性阈值', html)
            self.assertIn('启用目标鲁棒性独立约束', html)
            self.assertNotIn('响应鲁棒性阈值', html)
            self.assertNotIn('目标特征', html)

    def test_strategy_explanation_matches_single_objective_formulations(self):
        text = tooltip('robust_strategy')
        self.assertNotIn('分别作为目标', text)
        self.assertIn('一个目标', text)
        self.assertIn('标准差', text)


if __name__ == '__main__':
    unittest.main()
