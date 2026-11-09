"""Model workflow navigation, provenance, exports and restoration contracts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PyQt6.QtWidgets import QFileDialog
from backend.domain.models import ResponseItem
from backend.engines import optimizer as oe
from backend.services import task_storage
from frontend.pages.optimization_page import OptimizationPage
from test_workbench_analysis import APP, make_context


class ModelLayoutTests(unittest.TestCase):
    def make_page(self):
        project, _ = make_context()
        project.responses.append(ResponseItem(name='M', unit='kg'))
        for row in project.doe_matrix:
            row['M'] = row['Y'] * 3
        page = OptimizationPage(project)
        self.addCleanup(page.close)
        page.run_statistics()
        return project, page

    def test_overview_links_preserve_response_and_do_not_compute(self):
        _, page = self.make_page()
        self.assertIs(page.tabs.currentWidget(), page.tab_overview)
        self.assertEqual([page.tabs.tabText(i) for i in (2, 3, 4)],
                         ['统计检验', '验证与残差', '模型与系数'])
        self.assertEqual([group.title() for group in page.model_overview.summary.cards],
                         ['统计检验', '验证与残差', '模型与系数'])
        self.assertEqual(page.tabs.count(), 10)
        overview = page.model_overview
        overview.response.setCurrentIndex(overview.response.findData('M'))
        with patch.object(oe, 'build_models', side_effect=AssertionError('navigation refitted')):
            for kind, panel, tab in (('significance', page.signif_panel, page.tab_signif),
                                     ('validation', page.cv_panel, page.tab_cv),
                                     ('model', page.model_panel, page.tab_model)):
                overview.summary.buttons[kind].click()
                self.assertIs(page.tabs.currentWidget(), tab)
                self.assertEqual(panel.response.currentData(), 'M')
        self.assertEqual(len(page.cv_panel.figure.axes), 4)
        self.assertEqual(page.cv_panel.result_tables[0][1].rowCount(), 2)

    def test_task_specific_navigation_and_removed_manual_start(self):
        _, page = self.make_page()
        for method, wanted, absent in (('筛选设计', 7, 8), ('田口设计', 8, 7), ('二次响应面模型', 1, 7)):
            page.project_data.design_method = method
            page._check_inputs()
            self.assertIn(wanted, page.results_workspace.buttons)
            self.assertNotIn(absent, page.results_workspace.buttons)
            for i in (2, 3, 4):
                self.assertEqual(page.tabs.isTabVisible(i), wanted == 1)
        self.assertFalse(hasattr(page, 'tool_start'))
        self.assertFalse(hasattr(page, 'diagnostics_panel'))

    def test_save_restore_keeps_coefficients_intervals_and_missing_reasons(self):
        project, page = self.make_page()
        expected = project.workbench_result['responses']['M']['coefficients']
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp') as directory:
            path = Path(directory) / 'model.rodas'
            task_storage.save_task(project, path)
            loaded = task_storage.load_task(path)
            restored = OptimizationPage(loaded)
            self.addCleanup(restored.close)
            with patch.object(oe, 'build_models', side_effect=AssertionError('restore refitted')):
                restored.controller.restore_results()
            restored.model_overview.response.setCurrentIndex(restored.model_overview.response.findData('M'))
            restored.model_overview.summary.buttons['model'].click()
            table = restored.model_panel.result_tables[-1][1]
            np.testing.assert_allclose([float(table.item(i, 1).text()) for i in range(table.rowCount())],
                [row['估计值'] for row in expected], rtol=5e-5)
            self.assertTrue(table.horizontalHeaderItem(5).toolTip())
            csv_path = Path(directory) / 'coefficients.csv'
            with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(csv_path), '')):
                restored.model_panel.export_csv()
            self.assertIn('95%上限', csv_path.read_text(encoding='utf-8-sig'))
            restored.cv_panel.response.setCurrentIndex(restored.cv_panel.response.findData('M'))
            image = Path(directory) / 'residuals.png'
            with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(image), '')):
                restored.cv_panel.export_plot()
            self.assertGreater(image.stat().st_size, 1000)


if __name__ == '__main__':
    unittest.main()
