"""Approved page polish: merged analysis, titles, spacing and hover-only guidance."""
import unittest
import csv
import tempfile
from pathlib import Path
from unittest.mock import patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QFileDialog
from frontend.pages.result_overview import SummaryTable
from backend.domain.models import ResponseItem
from frontend.main_window import MainWindow
from frontend.pages.data_management_page import DataManagementPage
from frontend.pages.optimization_page import OptimizationPage
from test_workbench_analysis import APP, make_context


class PagePolishTests(unittest.TestCase):
    def test_merged_analysis_preserves_response_and_locates_saved_issues(self):
        project, _ = make_context()
        project.responses.append(ResponseItem(name='M', unit='kg'))
        for row in project.doe_matrix:
            row['M'] = row['Y'] * 2
        project.doe_matrix[0]['Y'] = ''
        page = DataManagementPage(project)
        self.addCleanup(page.close)
        page.load_doe_matrix()
        view = page.analysis_view
        view.response.setCurrentIndex(view.response.findData('M'))
        view.refresh()
        self.assertEqual(view.response.currentData(), 'M')
        self.assertEqual(view.stat_values['有效数'].text(), '35')
        self.assertEqual(len(view.stat_cards), 3)
        page.tabs.setCurrentIndex(1)
        button = view.issues_table.cellWidget(0, view.issues_table.columnCount()-1)
        self.assertIsInstance(button, QPushButton)
        button.click()
        self.assertEqual(page.tabs.currentIndex(), 0)
        self.assertEqual(page.table.currentRow(), 0)
        self.assertEqual(page.table.horizontalHeaderItem(page.table.currentColumn()).text(), 'Y')
        view.response.setCurrentIndex(view.response.findData('Y'))
        self.assertEqual(view.stat_values['有效数'].text(), '34')
        self.assertEqual(view.stat_values['缺失或无效'].text(), '1')

    def test_export_includes_valid_statistics_when_first_response_is_all_missing(self):
        project, _ = make_context()
        project.responses.append(ResponseItem(name='M', unit='kg'))
        for row in project.doe_matrix:
            row['M'], row['Y'] = row['Y'] * 2, ''
        page = DataManagementPage(project)
        self.addCleanup(page.close)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp') as directory:
            target = Path(directory) / 'statistics.csv'
            with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
                page.analysis_view.export_statistics()
            with target.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]['响应'], 'Y')
            self.assertEqual(rows[0]['均值'], '')
            self.assertAlmostEqual(float(rows[1]['均值']),
                                   sum(row['M'] for row in project.doe_matrix) / len(project.doe_matrix))

    def test_headings_zones_and_removed_notes_in_waiting_and_completed_states(self):
        project, _ = make_context()
        page = OptimizationPage(project)
        self.addCleanup(page.close)
        page.resize(1440, 940)
        page.show()
        page.tabs.setCurrentWidget(page.tab_overview)
        APP.processEvents()
        overview = page.overview
        self.assertEqual(overview.heading.text(), '方案与结果汇总')
        self.assertEqual(overview.heading.property('role'), 'heading')
        self.assertFalse(hasattr(overview, 'next_step'))
        self.assertFalse(hasattr(page.model_overview, 'source_value'))
        self.assertFalse(page.model_overview.empty_state.isHidden())
        self.assertGreaterEqual(page.model_overview.y()-overview.scheme_zone.geometry().bottom(), 24)
        self.assertEqual(overview.scheme_zone.objectName(), 'contentZone')
        self.assertEqual(page.model_overview.objectName(), 'contentZone')
        self.assertTrue(page.model_overview.testAttribute(Qt.WidgetAttribute.WA_StyledBackground))
        page.run_statistics()
        APP.processEvents()
        self.assertTrue(page.model_overview.empty_state.isHidden())
        self.assertIn('训练集', page.model_overview.heading.toolTip())
        self.assertTrue(any(label.text() == '鲁棒优化设计' and label.property('role') == 'heading'
                            for label in page.tab_robust.findChildren(QLabel)))
        self.assertIn('训练集', page.cv_panel.heading.toolTip())
        self.assertFalse(any(label.text().startswith('图表来源：') for label in page.cv_panel.findChildren(QLabel)))

    def test_business_headings_and_analysis_fit_small_and_large_windows(self):
        window = MainWindow()
        window.task_actions.confirm_leave = lambda **kwargs: True
        self.addCleanup(window.close)
        for section in window.page_MOD.sections:
            self.assertEqual(section.heading.text(), section.title)
            self.assertEqual(section.heading.property('role'), 'heading')
        window.show()
        project, _ = make_context()
        window.project_data.__dict__.update(project.__dict__)
        window.switch_page(2)
        page = window.page_DM
        page.load_doe_matrix()
        page.tabs.setCurrentIndex(1)
        for width, height in ((1050, 700), (1440, 940), (1050, 700)):
            window.resize(width, height)
            for _ in range(5):
                APP.processEvents()
            self.assertEqual(window.width(), width)
            view = page.analysis_view
            self.assertEqual(view.scroll.horizontalScrollBar().maximum(), 0)
            self.assertTrue(all(table.viewport().height() >= sum(table.rowHeight(i)
                for i in range(table.rowCount())) for card in view.stat_cards
                for table in card.findChildren(SummaryTable)))


if __name__ == '__main__':
    unittest.main()
