"""Regression coverage for response-specific analysis views and validation provenance."""
import unittest
from unittest.mock import patch

import numpy as np
from PyQt6.QtWidgets import QGroupBox, QLabel

from backend.core.statistics import cross_validation, validation_results
from backend.domain.models import ResponseItem
from backend.engines import optimizer as oe
from backend.services import analysis_service
from frontend.pages.analysis_results import AnalysisResults
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
        self.assertIn("没有重复试验点", visible_text(widget))
        repeated = project.doe_matrix[0].copy()
        project.doe_matrix.extend([repeated.copy(), repeated.copy()])
        context, _ = oe.build_models(project)
        widget.set_result(context, analysis_service.build_snapshot(context))
        self.assertIn("重复点纯误差为零", visible_text(widget))
        project.doe_matrix[-1]["Y"] += .1
        context, _ = oe.build_models(project)
        widget.set_result(context, analysis_service.build_snapshot(context))
        tables = [table for table in widget.findChildren(SummaryTable) if table.isVisibleTo(widget)]
        self.assertEqual(len(tables), 2)
        self.assertIn("按 p < 0.05", visible_text(widget))

    def test_proxy_holdout_metrics_use_actual_pairs_not_saved_training_scores(self):
        _, context = make_context()
        context["models"]["Y"] = {
            "predict_fn": lambda x: 0, "model_type": "Kriging", "rmse": 999,
            "validation": {"actual": [1, 2, 3], "predicted": [1, 2, 4],
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
        self.assertIn("留出集", widget.figure.axes[0].get_title())
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
        np.testing.assert_allclose(widget.figure.axes[0].collections[0].get_offsets()[:, 0], [r["实测"] for r in expected])
        self.assertIn("kg", widget.figure.axes[1].get_ylabel())
        self.assertIn("训练集", widget.figure.axes[0].get_title())
        self.assertIn("上方指标来自分折验证", visible_text(widget))

    def test_model_coding_coefficients_and_clearing_stale_results(self):
        _, context = make_context()
        widget = self.panel("model", context)
        tables = [table for table in widget.findChildren(SummaryTable) if table.isVisibleTo(widget)]
        self.assertEqual(tables[0].item(0, 1).text(), "z_A")
        self.assertEqual(tables[0].item(1, 1).text(), "z_B")
        coefficient_table = tables[-1]
        values = []
        for column in (1, 3):
            values.extend(float(coefficient_table.item(row, column).text())
                          for row in range(coefficient_table.rowCount())
                          if coefficient_table.item(row, column).text())
        np.testing.assert_allclose(values, context["models"]["Y"]["coef"], rtol=5e-5, atol=1e-9)
        widget.clear()
        self.assertEqual(widget.response.count(), 0)
        self.assertIn("尚无分析结果", visible_text(widget))

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
