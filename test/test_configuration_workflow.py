"""Supported model/DOE choices, inline drafts and atomic generation."""
import os
import unittest
from copy import deepcopy
from dataclasses import asdict
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from backend.domain.models import ProjectData, FactorItem, ResponseItem
from backend.services import design_service, model_service
from frontend.pages.configuration_page import ConfigurationPage
from frontend.pages.optimization_page import OptimizationPage
from frontend.notifications import Notice

APP = QApplication.instance() or QApplication([])


def project(k=3):
    return ProjectData(factors=[FactorItem(name=f"X{i}", param1="-1", param2="1") for i in range(k)],
                       responses=[ResponseItem(name="Y")])


def method(model):
    return "响应曲面设计" if model == "RSM" else f"代理模型建模 · {model}"


def config(model, design):
    return dict(model=model, doe_method=design, sample_count=32, centers=3,
                alpha_mode="face", alpha=1, seed=17, model_params={})


class ConfigurationWorkflowTests(unittest.TestCase):
    def test_models_offer_and_accept_only_their_original_design_choices(self):
        p = project()
        page = ConfigurationPage(p)
        for model in ("RSM", "Kriging", "SVR", "ANN"):
            allowed = ("CCD", "BBD") if model == "RSM" else design_service.SAMPLING_METHODS
            combo = page.model_editors[model].doe_method_combo
            self.assertEqual(tuple(combo.itemText(i) for i in range(combo.count())), allowed)
            for design in allowed:
                with self.subTest(model=model, design=design):
                    plan = design_service.model_plan(p, method(model), config(model, design))
                    preview = design_service.model_plan(p, method(model), config(model, design), preview=True)
                    self.assertEqual(len(plan.rows), preview.params["meta"]["total_runs"])
                    self.assertEqual(plan.params["doe_method"], design)
                    self.assertEqual(plan.params["model_config"]["model"], model)
            forbidden = design_service.SAMPLING_METHODS if model == "RSM" else ("CCD", "BBD")
            for design in forbidden:
                for preview in (False, True):
                    with self.assertRaisesRegex(ValueError, "仅支持"):
                        design_service.model_plan(p, method(model), config(model, design), preview=preview)
        page.close()

    def test_supported_combinations_reach_real_model_training_and_overview(self):
        for model, design in [("RSM", "CCD"), ("RSM", "BBD"),
                              *[(m, "Latin Hypercube (LHS)") for m in ("Kriging", "SVR", "ANN")]]:
            with self.subTest(model=model, design=design):
                p = project()
                plan = design_service.model_plan(p, method(model), config(model, design))
                design_service.commit_plan(p, plan)
                for row in p.doe_matrix:
                    row["Y"] = 5 + row["X0"] + row["X1"]**2 + row["X0"]*row["X2"]
                page = OptimizationPage(p)
                if model == "RSM":
                    page._run_rsm()
                    self.assertAlmostEqual(p.rsm_result["fit"]["Y"]["r2"], 1)
                else:
                    page._run_surrogate()
                    self.assertNotIn("error", p.surrogate_result["responses"]["Y"])
                page._refresh_view()
                self.assertEqual(page.overview.status_label.text(), "分析已完成")
                self.assertTrue(page.overview.result_tables)
                page.close()

    def test_keyboard_entry_drafts_and_generated_config_restore(self):
        p = project()
        page = ConfigurationPage(p)
        self.assertEqual(page.dynamic_params_widget.count(), 3)
        page.dynamic_params_widget.setCurrentIndex(2)
        page.model_combo.setCurrentIndex(3)
        editor = page.model_editors["ANN"]
        editor.sample_count_spin.lineEdit().selectAll()
        QTest.keyClicks(editor.sample_count_spin.lineEdit(), "42")
        editor.hidden_nodes_spin.setValue(12)
        editor.seed_spin.setValue(64)
        page.model_combo.setCurrentIndex(1)
        page.model_combo.setCurrentIndex(3)
        self.assertEqual(editor.sample_count_spin.lineEdit().text(), "42")
        with patch.object(Notice, "information"), patch.object(Notice, "warning") as failed:
            page.gen_btn.click()
            failed.assert_not_called()
        self.assertEqual(len(p.doe_matrix), 42)
        self.assertEqual(p.surrogate_config["sample_count"], 42)
        self.assertEqual(p.surrogate_config["seed"], 64)
        restored = ConfigurationPage(p)
        self.assertEqual(restored.model_combo.currentIndex(), 3)
        self.assertEqual(restored.model_editors["ANN"].hidden_nodes_spin.value(), 12)
        editor.hidden_nodes_spin.setValue(14)
        self.assertIn("尚未重新生成", page.config_status.text())
        self.assertEqual(p.surrogate_config["model_params"]["hidden_nodes"], 12)
        restored.close()
        page.close()

    def test_invalid_generation_preserves_previous_dataset_and_results(self):
        p = project(2)
        page = ConfigurationPage(p)
        page._generate_by_method("响应曲面设计")
        p.rsm_result["fit"] = {"Y": {"r2": .9}}
        snapshot = deepcopy(asdict(p))
        editor = page.model_editors["RSM"]
        editor.bounds_table.item(0, 2).setText("-1")  # upper bound equals lower bound
        with patch.object(Notice, "warning") as failed:
            page.gen_btn.click()
            failed.assert_called_once()
        self.assertEqual(asdict(p), snapshot)
        editor.bounds_table.item(0, 2).setText("1")
        editor.doe_method_combo.setCurrentText("BBD")
        with self.assertRaisesRegex(ValueError, "BBD|Box|因子"):
            page._build_plan()
        editor.doe_method_combo.setCurrentText("CCD")
        editor.bounds_table.item(0, 1).setText("nan")
        with self.assertRaisesRegex(ValueError, "范围无效"):
            page._build_plan()
        page.close()

    def test_range_seed_repeats_and_fixed_factors_are_preserved(self):
        p = project()
        p.factors.append(FactorItem(name="FIX", param1="0", param2="1", is_fixed=True, fixed_value=".4"))
        cfg = {**config("RSM", "CCD"), "bounds": {"X0": [2, 4]}, "replicates": 2}
        a = design_service.model_plan(p, method("RSM"), cfg)
        b = design_service.model_plan(p, method("RSM"), cfg)
        self.assertEqual(a.rows, b.rows)
        self.assertEqual(len(a.rows), 34)
        self.assertEqual({r["X0"] for r in a.rows}, {2, 3, 4})
        design_service.commit_plan(p, a)
        self.assertTrue(all(row["FIX"] == .4 for row in p.doe_matrix))
        restored = ConfigurationPage(p)
        plan = restored._build_plan()
        self.assertEqual(len(plan.rows), 34)
        self.assertEqual(plan.rows, a.rows)
        restored.close()

    def test_kriging_trend_requires_identifiable_training_subset(self):
        cfg = config("Kriging", "Latin Hypercube (LHS)")
        cfg.update(sample_count=6, model_params={"trend": "二次趋势"})
        with self.assertRaisesRegex(ValueError, "趋势项"):
            design_service.model_plan(project(), method("Kriging"), cfg)

    def test_classical_settings_restore_and_clear_old_surrogate_configuration(self):
        p = project()
        p.surrogate_config = config("SVR", "Latin Hypercube (LHS)")
        plan = design_service.screening_plan(p, "两水平筛选设计", "full", 32, 4, 2, False, 2)
        design_service.commit_plan(p, plan)
        page = ConfigurationPage(p)
        self.assertEqual(page.f_center_spin.value(), 4)
        self.assertEqual(page.f_repeat_spin.value(), 2)
        self.assertEqual(page.f_seed_spin.value(), 32)
        self.assertEqual(page.f_order_combo.currentText(), "保持相同")
        self.assertFalse(p.surrogate_config)
        page.close()

    def test_problem_refresh_updates_default_ranges_and_preserves_custom_ranges(self):
        p = project()
        page = ConfigurationPage(p)
        editor = page.model_editors["RSM"]
        editor.bounds_table.item(0, 1).setText("-0.5")
        p.factors[0].param1 = "-2"
        p.factors[1].param1 = "-2"
        page.update_info_display()
        self.assertEqual(editor.bounds_table.item(0, 1).text(), "-0.5")
        self.assertEqual(editor.bounds_table.item(1, 1).text(), "-2.0")
        p.factors.append(FactorItem(name="NEW", param1="2", param2="3"))
        page.update_info_display()
        self.assertEqual(editor.bounds_table.rowCount(), 4)
        page.close()

    def test_previous_cross_combination_is_preserved_as_data_and_marked_as_draft(self):
        p = project()
        p.design_method = method("Kriging")
        p.surrogate_config = config("Kriging", "CCD")
        p.doe_matrix = [{"X0": 0, "X1": 0, "X2": 0, "Y": 5}]
        snapshot = deepcopy(asdict(p))
        page = ConfigurationPage(p)
        self.assertEqual(page.model_editors["Kriging"].doe_method_combo.currentText(), "Latin Hypercube (LHS)")
        self.assertIn("重新生成", page.config_status.text())
        self.assertIsNone(page._applied_state)
        self.assertEqual(asdict(p), snapshot)
        page.close()


if __name__ == "__main__":
    unittest.main()
