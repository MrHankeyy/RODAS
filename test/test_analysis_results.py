"""Regression coverage for response-specific analysis views and validation provenance."""
import unittest
from unittest.mock import patch

import numpy as np
from PyQt6.QtWidgets import QGroupBox, QLabel, QToolTip
from matplotlib.backend_bases import MouseEvent, LocationEvent

from backend.core.statistics import cross_validation, validation_results
from backend.domain.models import ResponseItem
from backend.engines import optimizer as oe
from backend.services import analysis_service
from frontend.pages.analysis_results import AnalysisResults, DiagnosticCanvas
from frontend.pages.optimization_page import OptimizationPage
from frontend.pages.result_overview import SummaryTable
from test_workbench_analysis import APP, make_context


def visible_text(panel):
    widgets = panel.findChildren(QLabel) + panel.findChildren(QGroupBox)
    return "\n".join(widget.text() if isinstance(widget, QLabel) else widget.title()
                     for widget in widgets if widget.isVisibleTo(panel))


class AnalysisResultsTests(unittest.TestCase):
    def panel(self, kind, context):
        widget = AnalysisResults(kind)
        self.addCleanup(widget.deleteLater)
        snapshot = analysis_service.build_snapshot(context)
        snapshot["validation"] = validation_results(context)
        widget.set_result(context, snapshot)
        return widget

    def test_lof_distinguishes_no_replicates_zero_error_and_estimable(self):
        project, context = make_context()
        widget = self.panel("significance", context)
        self.assertIn("没有相同输入", '\n'.join(group.toolTip() for group in widget.findChildren(QGroupBox)))
        repeated = project.doe_matrix[0].copy()
        project.doe_matrix.extend([repeated.copy(), repeated.copy()])
        context, _ = oe.build_models(project)
        widget.set_result(context, analysis_service.build_snapshot(context))
        self.assertIn("纯误差为零", '\n'.join(group.toolTip() for group in widget.findChildren(QGroupBox)))
        project.doe_matrix[-1]["Y"] += .1
        context, _ = oe.build_models(project)
        widget.set_result(context, analysis_service.build_snapshot(context))
        tables = [table for table in widget.findChildren(SummaryTable) if table.isVisibleTo(widget)]
        self.assertEqual(len(tables), 3)
        self.assertIn("按概率值小于0.05", '\n'.join(group.toolTip() for group in widget.findChildren(QGroupBox)))

    def test_proxy_holdout_metrics_use_actual_pairs_not_saved_training_scores(self):
        _, context = make_context()
        context["models"]["Y"] = {
            "predict_fn": lambda x: 0, "model_type": "Kriging", "rmse": 999,
            "validation": {"actual": [1, 2, 3], "predicted": [1, 2, 4],
                           "validation_inputs": [[0, 0], [1, 0], [2, 0]],
                           "r2_test": .99, "train_samples": 32},
        }
        results = validation_results(context)
        self.assertAlmostEqual(results["Y"]["rmse"], np.sqrt(1/3))
        self.assertAlmostEqual(results["Y"]["r2"], .5)
        self.assertIn("未执行 K 折", cross_validation(context, results))
        significance = self.panel("significance", context)
        self.assertIn("不适用", visible_text(significance))
        self.assertFalse(significance.findChildren(SummaryTable))
        widget = self.panel("validation", context)
        self.assertIn("测试集", widget.figure.axes[0].get_title())
        np.testing.assert_allclose(widget.figure.axes[1].collections[0].get_offsets()[:, 1], [0, 0, -1])
        model = self.panel("model", context)
        self.assertIn("不提供二次多项式", visible_text(model))

    def test_response_switch_reuses_results_and_updates_plot_and_units(self):
        project, context = make_context()
        project.responses.append(ResponseItem(name="M", unit="kg"))
        for row in project.doe_matrix:
            row["M"] = row["Y"] * 3
        context, _ = oe.build_models(project)
        widget = self.panel("validation", context)
        with patch("backend.core.statistics._fit_model", side_effect=AssertionError("render must not refit")):
            widget.response.setCurrentIndex(widget.response.findData("M"))
        expected = widget.snapshot["responses"]["M"]["observations"]
        offsets = widget.figure.axes[0].collections[0].get_offsets()
        np.testing.assert_allclose(offsets[:, 0], [r['预测'] for r in expected])
        np.testing.assert_allclose(offsets[:, 1], [r['实测'] for r in expected])
        self.assertIn('kg', widget.figure.axes[0].get_ylabel())
        self.assertIn("kg", widget.figure.axes[1].get_ylabel())
        self.assertIn("训练集", widget.figure.axes[0].get_title())
        self.assertEqual(len(widget.figure.axes), 4)
        self.assertIn("上方指标来自 K 折交叉验证", '\n'.join(label.toolTip() for label in widget.findChildren(QLabel)))
        validation = widget.result_tables[0][1]
        self.assertEqual(validation.rowCount(), 2)
        self.assertEqual(validation.item(1, 0).text(), '留一交叉验证')

    def test_model_coding_coefficients_and_clearing_stale_results(self):
        _, context = make_context()
        widget = self.panel("model", context)
        tables = [table for table in widget.findChildren(SummaryTable) if table.isVisibleTo(widget)]
        self.assertEqual(tables[0].item(0, 1).text(), "z_A")
        self.assertEqual(tables[0].item(1, 1).text(), "z_B")
        coefficient_table = tables[-1]
        values = []
        for column in (1,):
            values.extend(float(coefficient_table.item(row, column).text())
                          for row in range(coefficient_table.rowCount())
                          if coefficient_table.item(row, column).text())
        np.testing.assert_allclose(values, context["models"]["Y"]["coef"], rtol=5e-5, atol=1e-9)
        self.assertEqual(coefficient_table.columnCount(), 7)
        self.assertEqual(coefficient_table.horizontalHeaderItem(6).text(), '95%上限')
        self.assertIn('Confidence', coefficient_table.horizontalHeaderItem(6).toolTip())
        widget.clear()
        self.assertEqual(widget.response.count(), 0)
        self.assertIn("尚无分析结果", visible_text(widget))

    def test_replicate_means_have_vertical_sample_sd_bars_and_residuals_stay_raw(self):
        project, _ = make_context()
        first = project.doe_matrix[0].copy()
        project.doe_matrix.extend([{**first, 'Y': first['Y'] - .2},
                                   {**first, 'Y': first['Y'] + .2}])
        context, errors = oe.build_models(project)
        self.assertFalse(errors)
        widget = self.panel('validation', context)
        diagnostic = widget.snapshot['responses']['Y']
        groups = diagnostic['prediction_groups']
        self.assertEqual(len(groups), 35)
        self.assertEqual(groups[0]['观测数'], 3)
        self.assertAlmostEqual(groups[0]['观测均值'], first['Y'])
        self.assertAlmostEqual(groups[0]['观测标准差'], .2)
        self.assertIsNone(groups[1]['观测标准差'])
        fit, residuals = widget.figure.axes[:2]
        offsets = fit.collections[0].get_offsets()
        self.assertEqual(len(offsets), 35)
        self.assertEqual(len(residuals.collections[0].get_offsets()), 37)
        self.assertIn('预测值', fit.get_xlabel())
        self.assertIn('观测均值', fit.get_ylabel())
        segments = fit.containers[0].lines[2][0].get_segments()
        np.testing.assert_allclose(segments[0][:, 0], [groups[0]['预测']] * 2)
        np.testing.assert_allclose(segments[0][:, 1], [first['Y'] - .2, first['Y'] + .2])
        self.assertEqual(diagnostic['summary'][1]['值'], 37)

    def test_holdout_groups_use_all_inputs_not_equal_predictions(self):
        _, context = make_context()
        context['models']['Y'] = {'predict_fn': lambda x: 2, 'model_type': 'Kriging',
            'validation': {'actual': [1, 3, 10], 'predicted': [2, 2, 2],
                           'validation_inputs': [[0, 0], [0, 0], [0, 1]]}}
        widget = self.panel('validation', context)
        groups = widget.snapshot['responses']['Y']['prediction_groups']
        self.assertEqual([group['观测数'] for group in groups], [2, 1])
        np.testing.assert_allclose(widget.figure.axes[0].collections[0].get_offsets(), [[2, 2], [2, 10]])
        self.assertAlmostEqual(groups[0]['观测标准差'], np.sqrt(2))
        np.testing.assert_allclose(widget.figure.axes[1].collections[0].get_offsets()[:, 1], [-1, 1, 8])

    def test_hover_tooltip_follows_each_subplot_and_clears_in_margins(self):
        _, context = make_context()
        widget = self.panel('validation', context)
        canvas = widget.findChild(DiagnosticCanvas)
        canvas.draw()
        expected = ['观测均值与预测值', '残差与预测值', '残差正态分位图', '残差序列图']
        with patch.object(QToolTip, 'hideText') as hide:
            for axes, title in zip(widget.figure.axes, expected):
                x, y = axes.transAxes.transform((.5, .5))
                canvas.callbacks.process('motion_notify_event', MouseEvent('motion_notify_event', canvas, x, y))
                self.assertTrue(canvas.toolTip().startswith(title + '（'))
            canvas.callbacks.process('motion_notify_event', MouseEvent('motion_notify_event', canvas, 0, 0))
            self.assertFalse(canvas.toolTip())
            x, y = widget.figure.axes[0].transAxes.transform((.5, .5))
            canvas.callbacks.process('motion_notify_event', MouseEvent('motion_notify_event', canvas, x, y))
            canvas.callbacks.process('figure_leave_event', LocationEvent('figure_leave_event', canvas, 0, 0))
            self.assertFalse(canvas.toolTip())
            self.assertGreaterEqual(hide.call_count, 6)

    def test_coefficient_columns_share_growth_and_keep_numeric_content_visible(self):
        _, context = make_context()
        widget = self.panel('model', context)
        widget.show()
        previous = None
        for width in (880, 1480, 880, 1900):
            widget.resize(width, 700)
            for _ in range(5):
                APP.processEvents()
            table = widget.result_tables[-1][1]
            widths = [table.columnWidth(i) for i in range(table.columnCount())]
            self.assertFalse(table.horizontalHeader().stretchLastSection())
            self.assertEqual(sum(widths), table.viewport().width())
            for column, actual in enumerate(widths):
                self.assertGreaterEqual(actual, table.sizeHintForColumn(column))
            if previous:
                growth = [current - old for current, old in zip(widths, previous)]
                self.assertLessEqual(max(growth) - min(growth), 1)
            previous = widths
        widget.close()

    def test_rank_deficient_folds_are_unavailable_without_downgrading(self):
        project, _ = make_context()
        project.doe_matrix = [{"A": a, "B": b, "Y": 1+a+b*b}
                              for a, b in [(-1, -1), (-1, 1), (1, -1), (1, 1), (0, 0), (0, 1)]]
        context, errors = oe.build_models(project)
        self.assertFalse(errors)
        result = validation_results(context)["Y"]
        self.assertIsNone(result["rmse"])
        self.assertEqual(result["samples"], 0)
        self.assertIn("未降阶替代", result["message"])

    def test_input_edit_clears_all_three_pages(self):
        project, context = make_context()
        page = OptimizationPage(project)
        self.addCleanup(page.deleteLater)
        page._check_inputs()
        page._update_analysis(context, {})
        self.assertIsNotNone(page.cv_panel.figure)
        project.doe_matrix[0]["Y"] += 1
        page._check_inputs()
        for widget in (page.signif_panel, page.cv_panel, page.model_panel):
            self.assertIsNone(widget.context)
            self.assertIsNone(widget.figure)
            self.assertEqual(widget.response.count(), 0)


if __name__ == "__main__":
    unittest.main()
