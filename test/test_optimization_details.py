"""True-front navigation, local verification, persistence and removed algorithms."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QGroupBox, QPushButton, QProgressBar
from backend.engines import optimizer as oe
from backend.services import analysis_service, task_storage
from frontend.pages.optimization_page import OptimizationPage
from frontend.pages.robust_results import RobustResults
from test_ui_constraints import APP, quadratic


class OptimizationDetailsTests(unittest.TestCase):
    def result(self, mode='multi', limit=.5):
        project, context = quadratic()
        result = oe.robust_optimize(context, mode=mode, sigma_limits={'Y':limit}, pop=12, gen=3, seed=7)
        return project, context, result

    def view(self, context, result):
        view = RobustResults()
        self.addCleanup(view.deleteLater)
        view.set_result(context, result)
        return view

    def test_only_actual_front_points_and_no_random_search_during_inspection(self):
        _, context, result = self.result()
        self.assertGreater(len(result['front']), 1)
        with (patch.object(oe, 'robust_optimize', side_effect=AssertionError('inspection optimized')),
              patch.object(np.random, 'default_rng', side_effect=AssertionError('inspection sampled'))):
            records, default = analysis_service.optimization_schemes(context, result)
            variance = analysis_service.scheme_variance(context, result, records[default]['x'])
        self.assertEqual([r['x'] for r in records], [r['x'] for r in result['front']])
        self.assertEqual(records[default]['x'], result['best']['x'])
        self.assertTrue(variance)

    def test_view_selection_synchronizes_three_pages_and_keeps_recommendation(self):
        _, context, result = self.result()
        original = copy.deepcopy(result)
        view = self.view(context, result)
        target = (view.default_index+1) % len(view.records)
        with patch.object(oe, 'build_models', side_effect=AssertionError('selection fitted')):
            view.select_scheme(target)
        self.assertEqual(view.comparison.selector.currentIndex(), target)
        self.assertEqual(view.verification.selector.currentIndex(), target)
        record = view.records[target]
        self.assertIn(view.records[view.default_index]['id'], view.groups['comparison'].title())
        row = record['verification']['responses'][0]
        variance = view.variance_cache[target]['Y']
        self.assertAlmostEqual(sum(v['variance'] for v in variance), row['传播标准差']**2)
        self.assertAlmostEqual(sum(v['share'] for v in variance), 100)
        self.assertAlmostEqual(float(view.comparison.tables['responses'].item(0, 3).text()), row['传播标准差'], delta=1e-5)
        self.assertEqual(result, original)

    def test_clear_and_reload_do_not_leave_stale_or_deleted_controls(self):
        _, context, result = self.result()
        view = self.view(context, result)
        for _ in range(3):
            view.clear()
            APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            APP.processEvents()
            self.assertFalse(view.records)
            self.assertFalse(view.comparison.tables)
            self.assertFalse(view.verification.tables)
            view.set_result(context, result)
            APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            APP.processEvents()
            view.select_scheme(0)
        titles = [g.title() for g in view.findChildren(QGroupBox)]
        self.assertNotIn('推荐设计指标', titles)
        self.assertEqual(len(view.buttons), 2)

    def test_detail_headers_table_widths_and_constraint_location(self):
        _, context, result = self.result()
        view = self.view(context, result)
        for detail in (view.comparison, view.verification):
            detail.show()
            self.addCleanup(detail.close)
            self.assertFalse(hasattr(detail, 'context_label'))
            self.assertIn(view.records[view.index]['id'], detail.selector.toolTip())
            for width in (820, 1210, 820):
                detail.resize(width, 700)
                for _ in range(3):
                    APP.processEvents()
                back = next(b for b in detail.findChildren(QPushButton) if b.text() == '返回总览')
                self.assertLess(back.width(), 180)
                if detail is view.comparison:
                    table = detail.tables['schemes']
                    minimums = table.column_balancer.minimum_widths
                    self.assertTrue(all(table.columnWidth(i) >= w for i, w in enumerate(minimums)))
                    if table.viewport().width() >= sum(minimums):
                        self.assertEqual(sum(table.columnWidth(i) for i in range(table.columnCount())), table.viewport().width())
            titles = [g.title() for g in detail.findChildren(QGroupBox)]
            self.assertEqual('约束核验' in titles, detail is view.comparison)

    def test_single_objective_modes_and_no_feasible_design_are_honest(self):
        for mode, limit in (('weighted', .5), ('constraint', .5), ('constraint', .001)):
            with self.subTest(mode=mode, limit=limit):
                _, context, result = self.result(mode, limit)
                view = self.view(context, result)
                self.assertEqual(len(view.records), 1)
                self.assertEqual(view.comparison.tables['schemes'].rowCount(), 1)
                self.assertTrue(view.comparison.canvas.isHidden())
                if not result['feasible_count']:
                    self.assertIn('未找到可行解', view.groups['comparison'].title())
                    self.assertEqual(view.comparison.tables['constraints'].item(0,5).text(), '违反')

    def test_selected_scheme_round_trip_without_fit_or_optimization(self):
        project, _, _ = self.result()
        page = OptimizationPage(project)
        self.addCleanup(page.close)
        page.pop_spin.setValue(20)
        page.gen_spin.setValue(30)
        page._execute_workbench()
        view = page.robust_results
        target = (view.default_index+1) % len(view.records)
        view.select_scheme(target)
        self.assertEqual(project.workbench_result['optimization_view_index'], target)
        self.assertNotIn('parameter_design', project.workbench_result)
        self.assertNotIn('local_search', project.workbench_result)
        expected = view.records[target]['x']
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'temp') as directory:
            path = Path(directory)/'details.rodas'
            task_storage.save_task(project, path)
            restored = OptimizationPage(task_storage.load_task(path))
            self.addCleanup(restored.close)
            with (patch.object(oe, 'build_models', side_effect=AssertionError('restore fitted')),
                  patch.object(oe, 'robust_optimize', side_effect=AssertionError('restore optimized'))):
                restored.controller.restore_results()
        self.assertEqual(restored.robust_results.index, target)
        self.assertEqual(restored.robust_results.records[target]['x'], expected)

    def test_overview_stays_on_recommendation_and_details_start_from_it(self):
        _, context, result = self.result()
        view = self.view(context, result)
        self.assertFalse(hasattr(view, 'status'))
        expected = [[view.tables[key].item(i,j).text()
                     for i in range(view.tables[key].rowCount()) for j in range(view.tables[key].columnCount())]
                    for key in ('factors','responses','contributions')]
        target = (view.default_index+1) % len(view.records)
        view.select_scheme(target)
        for key, values in zip(('factors','responses','contributions'), expected):
            self.assertEqual(values, [view.tables[key].item(i,j).text()
                             for i in range(view.tables[key].rowCount()) for j in range(view.tables[key].columnCount())])
        default = view.records[view.default_index]
        self.assertAlmostEqual(float(view.tables['factors'].item(0,1).text()), next(iter(default['x'].values())), delta=1e-5)
        variance = view.variance_cache[view.default_index]['Y']
        leading = max((r for r in variance if r['name'] != '模型残差'), key=lambda r:r['variance'])
        bar = view.tables['contributions'].cellWidget(0,2).findChild(QProgressBar)
        self.assertEqual(bar.value(), round(leading['share']*100))
        requests = []
        view.detail_requested.connect(requests.append)
        for key in ('comparison','verification'):
            view.select_scheme(target)
            view.buttons[key].click()
            self.assertEqual(view.index, view.default_index)
            self.assertEqual(requests[-1], key)

    def test_deleted_features_are_removed_from_engine_and_navigation(self):
        for name in ('parameter_design','_metric_at','local_search','steepest_ascent','evop_cycle','aofat_search','_design_bounds'):
            self.assertFalse(hasattr(oe, name), name)
        project, _, _ = self.result()
        page = OptimizationPage(project)
        self.addCleanup(page.close)
        self.assertEqual(page.tabs.count(), 10)
        for name in ('参数取值', '优化工具集', '局部方差贡献分析'):
            self.assertNotIn(name, [page.tabs.tabText(i) for i in range(page.tabs.count())])
        self.assertEqual([page.tabs.tabText(i) for i in (5,6)], ['方案对比','波动核验'])
        self.assertFalse(hasattr(page, 'tool_start'))
