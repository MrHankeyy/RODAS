"""优化历程：策略命名一致、逐代记录完整、面板与快照同步。"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication

from backend.engines import optimizer as oe
from backend.services import analysis_service
from frontend.pages.optimization_page import OptimizationPage
from test_workbench_analysis import make_context

APP = QApplication.instance() or QApplication([])

TERM_KEYS = {'multi': 'multiobjective_nsga2',
             'constraint': 'constrained_optimization',
             'weighted': 'weighted_single_objective'}


class OptimizationHistoryTests(unittest.TestCase):
    def test_strategy_items_are_parallel_method_names(self):
        project, _ = make_context()
        page = OptimizationPage(project)
        self.addCleanup(page.close)
        combo = page.robust_mode_combo
        self.assertEqual([combo.itemData(i) for i in range(combo.count())],
                         ['multi', 'constraint', 'weighted'])
        self.assertEqual([combo.itemText(i) for i in range(combo.count())],
                         ['帕累托前沿法', '波动约束法', '加权和法'])
        from frontend.terminology import name, tooltip
        for index in range(combo.count()):
            key = TERM_KEYS[combo.itemData(index)]
            self.assertEqual(combo.itemText(index), name(key))
            self.assertTrue(combo.itemData(index, 3))  # per-item tooltip present
            self.assertIn(name(key), tooltip(key))
        self.assertIn('多目标', tooltip('robust_strategy'))

    def test_every_generation_is_recorded(self):
        _, context = make_context()
        result = oe.robust_optimize(context, mode='multi', pop=10, gen=6, seed=5)
        history = result['history']
        self.assertEqual([record['gen'] for record in history], [1, 2, 3, 4, 5, 6])
        self.assertEqual(result['history_objectives'], ['望性损失', '归一化标准差'])
        for record in history:
            self.assertEqual(len(record['best']), 2)
            self.assertEqual(len(record['mean']), 2)
            self.assertLessEqual(record['best'][0], record['mean'][0] + 1e-9)
            self.assertLessEqual(record['best'][1], record['mean'][1] + 1e-9)
            self.assertLessEqual(record['feasible'], result['population_size'])
            self.assertGreaterEqual(record['evaluated'], 10)

    def test_single_objective_modes_record_one_series(self):
        _, context = make_context()
        for mode, label, limits in (('weighted', '加权目标和', None),
                                    ('constraint', '望性损失', {'Y': 5.0})):
            result = oe.robust_optimize(context, mode=mode, pop=8, gen=3, seed=7,
                                        sigma_limits=limits)
            if result.get('error'):
                self.skipTest(result['error'])
            self.assertEqual(result['history_objectives'], [label])
            self.assertTrue(all(len(record['best']) == 1 for record in result['history']))

    def test_panel_matches_history_and_clears(self):
        project, context = make_context()
        page = OptimizationPage(project)
        self.addCleanup(page.close)
        result = oe.robust_optimize(context, mode='multi', pop=10, gen=5, seed=3)
        page.history_panel.set_result(result)
        table = page.history_panel.table
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        self.assertEqual(headers, ['代数', '望性损失', '归一化标准差', '可行解数', '累计评估'])
        self.assertEqual(table.rowCount(), 5)
        self.assertFalse(table.isHidden())
        self.assertEqual(len(page.history_panel.figure.axes), 2)
        self.assertIn('5 代', page.history_panel.summary.text())
        page.history_panel.clear()
        self.assertEqual(table.rowCount(), 0)
        self.assertTrue(table.isHidden())
        self.assertEqual(page.history_panel.figure.axes[0].texts[0].get_text()[:4], '尚无优化')

    def test_history_is_stored_in_the_workbench_snapshot(self):
        project, context = make_context()
        result = oe.robust_optimize(context, mode='multi', pop=8, gen=3, seed=11)
        bundle = analysis_service.analyze(project, context, result)
        stored = bundle['snapshot']['optimization']
        self.assertEqual(len(stored['history']), 3)
        self.assertEqual(stored['history_objectives'], ['望性损失', '归一化标准差'])


class AutoStopTests(unittest.TestCase):
    def test_auto_stop_ends_early_and_records_the_reason(self):
        _, context = make_context()
        result = oe.robust_optimize(context, mode='multi', pop=10, gen=40, seed=3,
                                    auto_stop=True, stall_generations=5, tolerance=.02)
        self.assertTrue(result['auto_stop'])
        self.assertEqual(result['stop_reason'], 'stall')
        self.assertLess(result['generations_run'], 40)
        self.assertEqual(len(result['history']), result['generations_run'])
        self.assertIn('hv', result['history'][0])

    def test_switch_off_runs_the_fixed_generation_count(self):
        _, context = make_context()
        result = oe.robust_optimize(context, mode='multi', pop=10, gen=12, seed=3)
        self.assertFalse(result['auto_stop'])
        self.assertEqual(result['stop_reason'], 'max_generations')
        self.assertEqual(result['generations_run'], 12)

    def test_stall_window_must_be_smaller_than_generations(self):
        _, context = make_context()
        with self.assertRaises(ValueError):
            oe.robust_optimize(context, mode='multi', pop=8, gen=10, seed=1,
                               auto_stop=True, stall_generations=10)

    def test_panel_switch_controls_inputs_and_settings(self):
        project, _ = make_context()
        page = OptimizationPage(project)
        self.addCleanup(page.close)
        self.assertFalse(page.auto_stop_check.isChecked())
        self.assertFalse(page.stall_gen_spin.isEnabled())
        self.assertFalse(page.tolerance_spin.isEnabled())
        self.assertFalse(page._optimizer_settings()['auto_stop'])
        page.auto_stop_check.setChecked(True)
        self.assertTrue(page.stall_gen_spin.isEnabled())
        page.stall_gen_spin.setValue(15)
        page.tolerance_spin.setValue(.5)
        settings = page._optimizer_settings()
        self.assertTrue(settings['auto_stop'])
        self.assertEqual(settings['stall_generations'], 15)
        self.assertAlmostEqual(settings['tolerance'], .005)
        self.assertAlmostEqual(page._analysis_settings()['tolerance'], .005)


if __name__ == "__main__":
    unittest.main()
