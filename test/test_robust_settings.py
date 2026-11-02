"""Robust strategy controls must affect computation and survive task storage."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PyQt6.QtWidgets import QLabel
from backend.core.optimization import nsga2, _sbx_crossover, _polynomial_mutation
from backend.engines import optimizer as oe
from backend.domain.models import ResponseItem
from backend.services import task_storage
from frontend.pages.optimization_page import OptimizationPage
from frontend.pages.qt_tasks import OptimizationWorker
from test_workbench_analysis import APP, make_context


class RobustSettingsTests(unittest.TestCase):
    def page(self):
        project, _ = make_context()
        page = OptimizationPage(project)
        self.addCleanup(page.close)
        return project, page

    def test_strategy_visibility_and_response_specific_numeric_limits(self):
        project, page = self.page()
        project.responses[0].unit = 'kg'
        project.responses.append(ResponseItem(name='D', unit='mm'))
        page.robust_mode_combo.setCurrentIndex(page.robust_mode_combo.findData('constraint'))
        self.assertFalse(page.sigma_limits_group.isHidden())
        self.assertTrue(page.weight_fields.isHidden())
        self.assertEqual(page.sigma_limits_table.columnCount(), 3)
        self.assertEqual(page.sigma_limits_table.item(0, 2).text(), 'kg')
        page.sigma_limit_inputs['Y'].setText('2e-3')
        page.sigma_limit_inputs['D'].setText('0.01')
        self.assertEqual(page._sigma_limits(), {'Y': .002, 'D': .01})
        for mode in ('weighted', 'multi', 'constraint'):
            page.robust_mode_combo.setCurrentIndex(page.robust_mode_combo.findData(mode))
            self.assertTrue(page.robust_mode_combo.toolTip())
        self.assertEqual(page._sigma_limits(), {'Y': .002, 'D': .01})
        page.sigma_limit_inputs['Y'].setText('0')
        with self.assertRaisesRegex(ValueError, '正数'):
            page._sigma_limits()
        self.assertFalse(hasattr(page, 'uncertainty_label'))
        self.assertIn('当前输入标准差', page.k_design_spin.toolTip())

    def test_automatic_mutation_tracks_design_count_and_manual_setting_invalidates(self):
        project, page = self.page()
        self.assertEqual(page.mutation_spin.value(), .5)
        self.assertFalse(page.mutation_spin.isEnabled())
        self.assertIsNone(page._optimizer_settings()['pm'])
        project.factors[1].source = '环境'
        page._update_mutation_probability()
        self.assertEqual(page.mutation_spin.value(), 1)
        page.mutation_mode_combo.setCurrentIndex(1)
        page.mutation_spin.setValue(.125)
        self.assertEqual(page._optimizer_settings()['pm'], .125)
        page._oe_context = {'previous': True}
        page.crossover_spin.setValue(.73)
        self.assertIsNone(page._oe_context)
        self.assertIn('优化参数已改变', page.status_label.text())

    def test_zero_variation_leaves_initial_population_and_nondefault_settings_forward(self):
        rng = np.random.default_rng(9)
        self.assertEqual(_sbx_crossover([.2], [.8], 15, [0], [1], rng, 0), ([.2], [.8]))
        self.assertEqual(_polynomial_mutation([.2], 20, 0, [0], [1], rng), [.2])
        def evaluate(x):
            return [sum(v*v for v in x)], {'r': {'infeas': 0}}
        _, history = nsga2(evaluate, [0, 0], [1, 1], pop=8, gen=3, pc=0, pm=0)
        self.assertEqual(len(history), 8)
        _, context = make_context()
        with patch('backend.core.optimization.nsga2', wraps=nsga2) as solver:
            result = oe.robust_optimize(context, pop=8, gen=2, seed=91,
                                       pc=.73, pm=.125, eta_c=8, eta_m=32)
        self.assertEqual(solver.call_args.kwargs['pc'], .73)
        self.assertEqual(solver.call_args.kwargs['pm'], .125)
        self.assertEqual(solver.call_args.kwargs['eta_c'], 8)
        self.assertEqual(solver.call_args.kwargs['eta_m'], 32)
        self.assertEqual(result['effective_pm'], .125)

    def test_invalid_algorithm_parameters_rejected(self):
        def evaluate(x):
            return [x[0]], {}
        for setting in ({'pc': -.1}, {'pc': None}, {'pm': 1.1}, {'pc': float('nan')},
                        {'eta_c': 0}, {'eta_m': float('inf')}):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                nsga2(evaluate, [0], [1], pop=8, gen=1, **setting)

    def test_sync_and_worker_use_identical_settings(self):
        _, page = self.page()
        page.seed_spin.setValue(91)
        page.crossover_spin.setValue(.73)
        page.eta_c_spin.setValue(8)
        page.eta_m_spin.setValue(32)
        page.mutation_mode_combo.setCurrentIndex(1)
        page.mutation_spin.setValue(.125)
        expected = page._optimizer_settings()
        class Captured(Exception):
            pass
        with patch.object(oe, 'robust_optimize', side_effect=Captured) as solver:
            with self.assertRaises(Captured):
                page._execute_workbench()
        self.assertEqual(solver.call_args.kwargs, expected)
        worker = OptimizationWorker(page._oe_context, expected)
        with patch.object(oe, 'robust_optimize', return_value={}) as solver:
            worker.run()
        actual = dict(solver.call_args.kwargs)
        self.assertTrue(callable(actual.pop('progress')))
        self.assertEqual(actual, expected)

    def test_computed_settings_round_trip_without_refitting(self):
        project, page = self.page()
        page.robust_mode_combo.setCurrentIndex(page.robust_mode_combo.findData('constraint'))
        page.sigma_limit_inputs['Y'].setText('3.2')
        page.pop_spin.setValue(20)
        page.gen_spin.setValue(30)
        page.seed_spin.setValue(91)
        page.crossover_spin.setValue(.73)
        page.eta_c_spin.setValue(8)
        page.eta_m_spin.setValue(32)
        page.mutation_mode_combo.setCurrentIndex(1)
        page.mutation_spin.setValue(.125)
        page._execute_workbench()
        expected = page._analysis_settings()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp') as directory:
            path = Path(directory) / 'settings.rodas'
            task_storage.save_task(project, path)
            restored = OptimizationPage(task_storage.load_task(path))
            self.addCleanup(restored.close)
            with patch.object(oe, 'build_models', side_effect=AssertionError('restore refitted')):
                restored.controller.restore_results()
        self.assertEqual(restored._analysis_settings(), expected)
        self.assertEqual(restored._robust_res['pc'], .73)
        self.assertEqual(restored._robust_res['eta_m'], 32)
        self.assertEqual(restored._robust_res['effective_pm'], .125)
        self.assertIn('settings', restored.robust_results.tables)

    def test_settings_fit_available_width_and_hover_definitions_are_specific(self):
        _, page = self.page()
        page.tabs.setCurrentWidget(page.tab_robust)
        page.show()
        for size in ((1050, 700), (1440, 940)):
            page.resize(*size)
            APP.processEvents()
            self.assertEqual(page.robust_scroll.horizontalScrollBar().maximum(), 0)
            self.assertLessEqual(page.genetic_group.width(), page.robust_scroll.viewport().width())
        for mode, word in (('multi', '折中'), ('constraint', '上限'), ('weighted', '权重')):
            page.robust_mode_combo.setCurrentIndex(page.robust_mode_combo.findData(mode))
            self.assertIn(word, page.robust_mode_combo.toolTip())
        self.assertTrue(any('鲁棒优化策略' == item.text() for item in page.findChildren(QLabel)))


if __name__ == '__main__':
    unittest.main()
