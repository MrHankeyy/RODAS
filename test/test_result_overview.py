"""Overview contracts: valid data, response-specific results and stale-state clearing."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QComboBox

from backend.domain.models import ProjectData, ResponseItem
from frontend.pages.optimization_page import OptimizationPage
from frontend.pages.result_overview import ResultOverview
from frontend.pages.result_summary import overview

APP = QApplication.instance() or QApplication([])


class ResultOverviewTests(unittest.TestCase):
    def project(self, method="代理模型建模 · Kriging"):
        return ProjectData(design_method=method, responses=[ResponseItem(name="Y", unit="mm")],
                           doe_matrix=[{"Y": 1}, {"Y": 2}])

    def test_data_readiness_rejects_blank_nan_and_infinity(self):
        project = self.project()
        project.doe_matrix += [{"Y": ""}, {"Y": "nan"}, {"Y": float("inf")}, {}]
        view = ResultOverview()
        view.set_project(project)
        self.assertEqual(overview(project)["readiness"], [("Y（mm）", 2, 6)])
        self.assertFalse(hasattr(view, "readiness_table"))
        self.assertEqual(view.status_label.text(), "等待响应数据")
        self.assertFalse(view.result_tables)
        view.close()

    def test_empty_plan_and_ready_data_have_distinct_next_actions(self):
        self.assertEqual(overview(ProjectData())["status"], "尚未生成方案")
        for method, action in [("两水平筛选设计", "计算筛选主效应"),
                               ("田口稳健设计", "计算田口信噪比"),
                               ("响应曲面设计", "建模与模型诊断")]:
            with self.subTest(method=method):
                data = overview(self.project(method))
                self.assertEqual(data["status"], "等待分析")
                self.assertIn(action, data["next_step"])

    def test_all_surrogate_models_share_test_set_columns(self):
        view = ResultOverview()
        for model in ("Kriging", "SVR", "ANN"):
            project = self.project(f"代理模型建模 · {model}")
            project.surrogate_result = {"responses": {"Y": {"r2_test": .97, "mape_test_%": 2.1,
                "train_samples": 8, "test_samples": 2, "params": {"model": model}}}}
            view.set_project(project)
            self.assertEqual(view.status_label.text(), "分析已完成")
            self.assertEqual(view.result_tables[0].horizontalHeaderItem(1).text(), "测试集 R²")
            self.assertEqual(view.result_tables[0].item(0, 1).text(), "0.97")
        self.assertFalse(view.findChildren(QComboBox))
        view.close()

    def test_rsm_uses_fit_metrics_and_keeps_partial_failures_visible(self):
        project = self.project("响应曲面设计")
        project.responses.append(ResponseItem(name="Z"))
        for row in project.doe_matrix:
            row["Z"] = 1
        project.rsm_result = {"fit": {"Y": {"r2": .99, "adj_r2": .98, "rmse": .01},
                                      "Z": {"error": "数据不足"}}}
        data = overview(project)
        self.assertEqual(data["status"], "部分响应分析失败")
        self.assertEqual(data["sections"][0]["headers"][1], "拟合 R²")
        self.assertIn("数据不足", data["sections"][1]["message"])

    def test_screening_preserves_signed_effects_for_each_response(self):
        project = self.project("两水平筛选设计")
        project.design_params = {"top_n": 1}
        project.screening_result = {"response_analysis": {name: {"effects": [
            {"name": "h", "effect": -2, "share": 80}, {"name": "b", "effect": 1, "share": 20}]}
            for name in ("Y", "Z")}}
        sections = overview(project)["sections"]
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["rows"], [["h", -2, 80]])

    def test_taguchi_never_assigns_observed_statistics_to_untested_combination(self):
        project = self.project("田口稳健设计")
        item = {"best_levels": {"b": 60, "h": 110}, "runs": [
            {"inner": 1, "settings": {"b": 40, "h": 90}, "mean": .6, "std": .1, "metric": 4}],
            "has_replication": True}
        project.taguchi_result = {"response_analysis": {"Y": item}}
        data = overview(project)
        self.assertIn("候选组合尚未试验", data["sections"][1]["message"])
        item["runs"][0]["settings"] = item["best_levels"]
        self.assertIn("已试验统计", overview(project)["sections"][1]["title"])

    def test_switching_plan_removes_old_result_tables(self):
        project = self.project()
        page = OptimizationPage(project)
        project.surrogate_result = {"responses": {"Y": {"r2_test": .97, "params": {"kernel": "RBF"}}}}
        page._refresh_view()
        self.assertEqual(len(page.overview.result_tables), 1)
        project.design_method = "两水平筛选设计"
        page._check_inputs()
        self.assertFalse(project.surrogate_result)
        self.assertFalse(page.overview.result_tables)
        page.close()


if __name__ == "__main__":
    unittest.main()
