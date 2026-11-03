"""Result presentation follows solver feasibility and preserves constraint units."""
import unittest
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from backend.engines import optimizer as oe
from backend.services import analysis_service
from frontend.pages.robust_results import RobustResults
from test_ui_constraints import APP, quadratic


class RobustResultsTests(unittest.TestCase):
    def panel(self, context, mode="constraint", limit=.1):
        result = oe.robust_optimize(context, mode=mode, sigma_limits={"Y": limit}, pop=20, gen=5, k_design=6)
        widget = RobustResults()
        self.addCleanup(widget.deleteLater)
        widget.set_result(context, result)
        return widget, result

    def test_feasible_and_infeasible_candidates_are_distinguished(self):
        _, context = quadratic()
        context["_responses"][0].unit = "mm"
        for limit, status in ((.1, "通过核验"), (.001, "未找到可行解")):
            with self.subTest(limit=limit):
                widget, result = self.panel(context, limit=limit)
                self.assertIn('推荐解' if result['feasible_count'] else status, widget.groups['comparison'].title())
                table = widget.comparison.tables["constraints"]
                self.assertEqual(table.item(0, 5).text(), "通过" if result["feasible_count"] else "违反")
                self.assertEqual(table.item(0, 6).text(), "mm")
                self.assertAlmostEqual(float(widget.comparison.tables["responses"].item(0, 3).text()),
                                       result["best"]["responses"][0]["sigma"], places=5)

    def test_response_limits_in_all_directions_and_dual_roles(self):
        _, context = quadratic()
        response = context["_responses"][0]
        response.kind = "目标+约束"
        for feature, bound in (("望小", "2"), ("望大", "-1"), ("望目", "")):
            with self.subTest(feature=feature):
                response.feature, response.robust_limit = feature, bound
                response.lower, response.upper = "-1", "2"
                widget, _ = self.panel(context)
                table = widget.comparison.tables["constraints"]
                self.assertEqual(table.rowCount(), 2)
                self.assertTrue(all(table.item(i, 5).text() == "通过" for i in range(2)))
                self.assertEqual(widget.comparison.tables["responses"].item(0, 1).text(), "目标+约束")

    def test_other_modes_and_clear(self):
        _, context = quadratic()
        for mode in ("multi", "weighted"):
            with self.subTest(mode=mode):
                widget, _ = self.panel(context, mode)
                self.assertNotIn("constraints", widget.verification.tables)
                self.assertNotIn("settings", widget.comparison.tables)
                self.assertEqual(widget.heading.text(), "鲁棒优化结果总览")
                widget.clear()
                self.assertFalse(widget.records)
                self.assertFalse(widget.comparison.tables)
                self.assertFalse(widget.verification.tables)
                self.assertFalse(widget.tables)
                self.assertTrue(all(not b.isEnabled() for b in widget.buttons.values()))


if __name__ == "__main__":
    unittest.main()
