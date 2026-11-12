"""Supported model/DOE choices, inline drafts and atomic generation."""
import os
import unittest
from copy import deepcopy
from dataclasses import asdict
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QGroupBox, QLabel

from backend.domain.models import ProjectData, FactorItem, ResponseItem
from backend.services import design_service, model_service
from frontend.pages.configuration_page import ConfigurationPage
from frontend.pages.optimization_page import OptimizationPage
from frontend.notifications import Notice
from frontend.pages.model_configuration import DESIGN_TERM_KEYS, MODEL_TERM_KEYS
from frontend.terminology import name, tooltip
from frontend.theme import install_theme, polish_tables

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
    def test_repeated_model_switches_fit_without_editing_parameters(self):
        install_theme(APP)
        for count in (2, 8):
            p = project(count)
            p.task_type = 'robust'
            page = ConfigurationPage(p)
            self.addCleanup(page.close)
            polish_tables(page)
            page.show()
            for width, height in ((1050, 700), (1920, 1080), (1050, 700)):
                page.resize(width, height)
                for index in (0, 1, 2, 3, 0, 3, 2, 1, 0):
                    page.model_combo.setCurrentIndex(index)
                    for _ in range(4):
                        APP.processEvents()
                    editor = page.model_stack.currentWidget()
                    table = editor.bounds_table
                    with self.subTest(count=count, width=width, model=editor.model_key):
                        self.assertGreaterEqual(editor.height(), editor.sizeHint().height())
                        self.assertGreaterEqual(page.model_stack.height(), editor.height())
                        if count == 2:
                            self.assertGreaterEqual(table.viewport().height(),
                                sum(table.rowHeight(row) for row in range(count)))
                            self.assertEqual(table.verticalScrollBar().maximum(), 0)
                        else:
                            self.assertGreater(table.verticalScrollBar().maximum(), 0)
                        button = page.results_workspace.buttons[1]
                        self.assertGreaterEqual(button.width(), button.sizeHint().width())
            page.close()

    def test_trial_design_hints_are_removed_and_rsm_has_one_model_choice(self):
        page = ConfigurationPage(project())
        self.addCleanup(page.close)
        removed = ('CCD 的低高水平', 'BBD 使用三水平', '生成时检查样本数量',
                   '中心点用于检验曲率', '内表安排控制因子')
        self.assertFalse(any(any(text in label.text() for text in removed)
                             for label in page.findChildren(QLabel)))
        for editor in page.model_editors.values():
            trial = next(group for group in editor.findChildren(QGroupBox) if group.title() == '试验设计')
            self.assertFalse(any(label.property('role') == 'muted' for label in trial.findChildren(QLabel)))
        editor = page.model_editors['RSM']
        settings = next(group for group in editor.findChildren(QGroupBox) if group.title() == '模型设置')
        combo = settings.findChild(QComboBox)
        self.assertIs(combo, editor.rsm_model_combo)
        self.assertTrue(combo.isEnabled())
        self.assertEqual([combo.itemText(i) for i in range(combo.count())], ['完整二次模型'])

    def test_run_count_is_a_peer_group_and_updates_without_committing_drafts(self):
        p = project()
        page = ConfigurationPage(p)
        self.addCleanup(page.close)
        page.dynamic_params_widget.setCurrentIndex(1)
        editor = page.model_editors['RSM']
        self.assertIs(page.preview_group.parentWidget(), editor)
        self.assertEqual([editor.layout().itemAt(i).widget().title() for i in range(editor.layout().count())],
                         ['因子与试验范围', '试验设计', '模型设置', '试验规模'])
        self.assertIs(page.preview_label.parentWidget(), page.preview_group)
        self.assertIsNone(page.preview_label.property('role'))
        before = deepcopy(asdict(p))
        page._refresh_preview()
        self.assertEqual(page.preview_label.text(), '预计试验次数：17 次')
        editor.centers_spin.setValue(5)
        editor.repeats_spin.setValue(2)
        QTest.qWait(220)
        self.assertEqual(page.preview_label.text(), '预计试验次数：38 次')
        self.assertEqual(asdict(p), before)
        for category, content in ((0, page.t_scale_zone), (1, editor)) * 2:
            page.dynamic_params_widget.setCurrentIndex(category)
            page._refresh_preview()
            self.assertIs(page.preview_group.parentWidget(), content)
            self.assertIn('预计试验次数：', page.preview_label.text())
            self.assertNotIn('\n', page.preview_label.text())
            self.assertNotIn('所有设计点', page.preview_label.text())
        page.model_combo.setCurrentIndex(3)
        ann = page.model_editors['ANN']
        ann.sample_count_spin.setValue(42)
        page._refresh_preview()
        self.assertIs(page.preview_group.parentWidget(), ann)
        self.assertEqual(page.preview_label.text(), '预计试验次数：42 次')

    def test_invalid_preview_is_framed_and_recovers_after_fixing_the_range(self):
        page = ConfigurationPage(project())
        self.addCleanup(page.close)
        page.dynamic_params_widget.setCurrentIndex(1)
        editor = page.model_editors['RSM']
        editor.bounds_table.item(0, 2).setText('-1')
        page._refresh_preview()
        self.assertIs(page.preview_label.parentWidget(), page.preview_group)
        self.assertIn('当前配置不可生成', page.preview_label.text())
        editor.bounds_table.item(0, 2).setText('1')
        page._refresh_preview()
        self.assertEqual(page.preview_label.text(), '预计试验次数：17 次')

    def test_models_offer_and_accept_only_their_original_design_choices(self):
        p = project()
        page = ConfigurationPage(p)
        self.assertEqual(tuple(page.model_combo.itemText(i) for i in range(page.model_combo.count())),
                         tuple(name(MODEL_TERM_KEYS[key]) for key in page.MODEL_KEYS))
        self.assertEqual(tuple(page.model_combo.itemData(i, Qt.ItemDataRole.ToolTipRole)
                               for i in range(page.model_combo.count())),
                         tuple(tooltip(MODEL_TERM_KEYS[key]) for key in page.MODEL_KEYS))
        self.assertEqual(page.model_combo.toolTip(), tooltip(MODEL_TERM_KEYS["RSM"]))
        for model in ("RSM", "Kriging", "SVR", "ANN"):
            allowed = ("CCD", "BBD") if model == "RSM" else design_service.SAMPLING_METHODS
            combo = page.model_editors[model].doe_method_combo
            self.assertEqual(tuple(combo.itemData(i) for i in range(combo.count())), allowed)
            self.assertEqual(tuple(combo.itemText(i) for i in range(combo.count())),
                             tuple(name(DESIGN_TERM_KEYS[item]) for item in allowed))
            self.assertEqual(tuple(combo.itemData(i, Qt.ItemDataRole.ToolTipRole)
                                   for i in range(combo.count())),
                             tuple(tooltip(DESIGN_TERM_KEYS[item]) for item in allowed))
            self.assertEqual(combo.toolTip(), tooltip(DESIGN_TERM_KEYS[allowed[0]]))
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
                page.run_statistics()
                self.assertEqual(page.overview.status_label.text(), "分析已完成")
                self.assertTrue(page.model_overview.summary.tables)
                self.assertFalse(page.overview.result_tables)
                page.close()

    def test_keyboard_entry_drafts_and_generated_config_restore(self):
        p = project()
        page = ConfigurationPage(p)
        self.assertEqual(page.dynamic_params_widget.count(), 2)
        page.dynamic_params_widget.setCurrentIndex(1)
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
        editor.doe_method_combo.setCurrentIndex(editor.doe_method_combo.findData("BBD"))
        with self.assertRaisesRegex(ValueError, "博克斯|因子"):
            page._build_plan()
        editor.doe_method_combo.setCurrentIndex(editor.doe_method_combo.findData("CCD"))
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
        combo = page.model_editors["Kriging"].doe_method_combo
        self.assertEqual(combo.currentText(), "拉丁超立方采样")
        self.assertEqual(combo.currentData(), "Latin Hypercube (LHS)")
        self.assertIn("重新生成", page.config_status.text())
        self.assertIsNone(page._applied_state)
        self.assertEqual(asdict(p), snapshot)
        page.close()


if __name__ == "__main__":
    unittest.main()
