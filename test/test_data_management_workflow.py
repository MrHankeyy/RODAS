"""Raw data analysis is shared across workflows and never trains a model."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QGroupBox, QLabel
from backend.domain.models import FactorItem, ProjectData, ResponseItem
from backend.services.data_service import data_overview
from frontend.main_window import MainWindow
from frontend.pages.data_management_page import DataManagementPage
from frontend.pages.result_overview import ResultOverview
from frontend.theme import ResultsWorkspace

APP = QApplication.instance() or QApplication([])


def project(method="响应曲面设计"):
    return ProjectData(design_method=method, factors=[FactorItem(name="X")],
                       responses=[ResponseItem(name="Y", unit="mm")],
                       doe_matrix=[{"Run_ID": 1, "X": 0, "Y": 1},
                                   {"Run_ID": 2, "X": 1, "Y": ""}])


class DataManagementTests(unittest.TestCase):
    def test_three_workflows_share_checks_and_statistics_without_model(self):
        for method in ("两水平筛选设计", "田口稳健设计", "代理模型建模 · Kriging"):
            with self.subTest(method=method), patch(
                    "backend.services.model_service.train_surrogates", side_effect=AssertionError("trained")), patch(
                    "backend.engines.optimizer.build_models", side_effect=AssertionError("fitted")):
                page = DataManagementPage(project(method))
                page.load_doe_matrix()
                self.assertIsInstance(page.results_workspace, ResultsWorkspace)
                self.assertEqual([page.tabs.tabText(i) for i in range(3)], ["试验数据", "数据检查", "描述统计"])
                for index in (1, 2, 0):
                    page.results_workspace.buttons[index].click()
                    self.assertEqual(page.tabs.currentIndex(), index)
                    self.assertTrue(page.results_workspace.buttons[index].isChecked())
                self.assertEqual(page.check_view.progress_bars[0].value(), 1)
                table = page.statistics_view.table
                headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
                self.assertEqual(table.item(0, headers.index("均值")).text(), "1")
                self.assertEqual(table.item(0, headers.index("样本标准差")).text(), "—")
                page.close()

    def test_missing_nonfinite_and_nonnumeric_values_have_problem_locations(self):
        p = project()
        p.doe_matrix = [{"Y": value} for value in (1, "", None, "nan", float("inf"), "abc")]
        p.doe_matrix.append({})
        result = data_overview(p)
        self.assertEqual(result["readiness"], [("Y", 1, 7)])
        self.assertEqual([r["数据行"] for r in result["issues"]], list(range(2, 8)))
        self.assertFalse(result["ready"])
        page = DataManagementPage(p)
        page.load_doe_matrix()
        page.tabs.setCurrentIndex(1)
        page.check_view._locate_issue(0, 0)
        self.assertEqual(page.tabs.currentIndex(), 0)
        self.assertEqual(page.table.currentRow(), 1)
        self.assertEqual(page.table.horizontalHeaderItem(page.table.currentColumn()).text(), "Y")
        page.close()

    def test_dirty_draft_preserved_and_statistics_refresh_after_save(self):
        p = project()
        p.rsm_result = {"old": True}
        page = DataManagementPage(p)
        page.show()
        APP.processEvents()
        page.table.item(1, 2).setText("3")
        page.tabs.setCurrentIndex(2)
        self.assertIn("未保存", page.statistics_view.notice.text())
        self.assertEqual(page.check_view.progress_bars[0].value(), 1)
        page.hide()
        page.show()
        self.assertEqual(page.table.item(1, 2).text(), "3")
        with patch("frontend.pages.data_management_page.Notice.information"):
            page.save_results()
        self.assertEqual(p.doe_matrix[1]["Y"], 3)
        self.assertEqual(page.check_view.progress_bars[0].value(), 2)
        self.assertNotIn("未保存", page.statistics_view.notice.text())
        self.assertFalse(p.rsm_result)
        self.assertFalse(page.table.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable)
        page.close()

    def test_scheme_frame_and_saved_statistics_csv(self):
        page = DataManagementPage(project())
        self.assertIs(page.title_label.parent(), page.scheme_group)
        self.assertFalse(any(g.title() == "试验数据 · 因子列只读，响应列可编辑"
                             for g in page.findChildren(QGroupBox)))
        root = Path(__file__).resolve().parents[1] / "temp"
        with tempfile.TemporaryDirectory(dir=root) as directory:
            target = Path(directory) / "stats.csv"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")):
                page.statistics_view.export_statistics()
            self.assertIn("均值", target.read_text(encoding="utf-8-sig"))
        page.close()

    def test_replaced_and_cleared_datasets_refresh_without_stale_rows(self):
        p = project()
        page = DataManagementPage(p)
        page.show()
        APP.processEvents()
        page.hide()
        p.doe_matrix = [{"Run_ID": 1, "X": 2, "Y": 7}]
        page.show()
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(page.table.item(0, 2).text(), "7")
        page.hide()
        p.doe_matrix = []
        page.show()
        self.assertEqual(page.table.rowCount(), 0)
        self.assertEqual(page.check_view.progress_bars[0].value(), 0)
        self.assertIn("没有试验数据", page.statistics_view.notice.text())
        page.close()

    def test_headings_use_tooltips_and_data_details_are_removed_from_four(self):
        window = MainWindow()
        window.show()
        for index, (title, description) in enumerate(window.PAGE_INFO):
            window.switch_page(index)
            self.assertEqual(window.page_title.toolTip(), description)
            self.assertIn(description, window.btns_switch[index].toolTip())
            self.assertFalse(any(label.text() == description and label.isVisible()
                                 for label in window.module_heading.findChildren(QLabel)))
        opt = window.page_OPT
        self.assertFalse(hasattr(opt.overview, "readiness_table"))
        self.assertNotIn("data", opt.diagnostics_panel.tables)
        self.assertEqual(opt.stats_btn.text(), "建模与模型诊断")
        opt.overview.data_button.click()
        self.assertEqual(window.stacked_widget.currentIndex(), 2)
        window.close()


if __name__ == "__main__":
    unittest.main()
