"""Welcome navigation preserves work; one directory drives all file dialogs."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication, QFileDialog
from backend.domain.models import FactorItem
from frontend.main_window import MainWindow
from frontend.pages.welcome_page import CHINESE_NAME, brand_pixmap
from frontend.workspace import Workspace, dialog_path

APP = QApplication.instance() or QApplication([])


class WelcomeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / 'temp'
        temporary_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.root = Path(self.temp.name)
        self.workspace = Workspace()
        self.window = MainWindow(self.workspace)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        APP.processEvents()
        self.temp.cleanup()

    def test_startup_and_round_trip_preserve_inputs_and_results(self):
        w = self.window
        self.assertIs(w.stacked_widget.currentWidget(), w.welcome_page)
        self.assertTrue(w.brand_button.property('active'))
        self.assertFalse(any(b.property('active') for b in w.btns_switch))
        self.assertTrue(w.module_heading.isHidden())
        self.assertTrue(w.message_panel.isHidden())
        w.btns_switch[0].click()
        w.page_MOD.add_design_factor_row()
        editor = w.page_MOD.design_factor_table.cellWidget(0, 0)
        editor.setText('翼梁厚度')
        w.brand_button.click()
        self.assertEqual(w.project_data.factors[0].name, '翼梁厚度')
        w.btns_switch[3].click()
        w.project_data.workbench_result = {'sentinel': [1, 2, 3]}
        w.brand_button.click()
        w.btns_switch[0].click()
        self.assertEqual(editor.text(), '翼梁厚度')
        self.assertEqual(w.project_data.workbench_result, {'sentinel': [1, 2, 3]})
        w.btns_switch[3].click()
        self.assertFalse(w.module_heading.isHidden())
        self.assertFalse(w.message_panel.isHidden())

    def test_single_line_name_and_approved_brand_asset(self):
        w = self.window
        w.resize(1050, 700)
        APP.processEvents()
        self.assertEqual(w.welcome_page.title.text(), CHINESE_NAME)
        self.assertFalse(w.welcome_page.title.wordWrap())
        label = w.welcome_page.title
        self.assertGreaterEqual(label.width(), label.fontMetrics().horizontalAdvance(CHINESE_NAME))
        for width, height in [(1440, 940), (1050, 700)]:
            w.resize(width, height)
            APP.processEvents()
            text_width = label.fontMetrics().horizontalAdvance(CHINESE_NAME)
            self.assertGreaterEqual(text_width, w.welcome_page.logo.pixmap().width())
            self.assertLessEqual(text_width, label.width())
        self.assertEqual(w.brand_button.text(), '开始')
        self.assertFalse(brand_pixmap().isNull())
        self.assertFalse(w.windowIcon().isNull())
        self.assertTrue(w.windowTitle().startswith('RODAS'))
        self.assertEqual(list(w.welcome_page.action_buttons),
                         ['读取已有任务', '新建任务', '设置工作目录', '教程'])
        self.assertTrue(all(button.height() >= 108
                            for button in w.welcome_page.action_buttons.values()))

    def test_directory_cancel_change_and_every_module(self):
        w = self.window
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=''):
            w.welcome_page.action_buttons['设置工作目录'].click()
        self.assertEqual(self.workspace.directory, '')
        target = self.root / '结构分析任务'
        target.mkdir()
        original_cwd = Path.cwd()
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)):
            w.welcome_page.action_buttons['设置工作目录'].click()
        self.assertEqual(Path.cwd(), original_cwd)
        for index in range(5):
            w.btns_switch[index].click()
            APP.processEvents()
            self.assertTrue(w.directory_button.isVisible())
            self.assertEqual(w.directory_button.toolTip(), str(target.resolve()))
            self.assertEqual(dialog_path(w.stacked_widget.currentWidget(), 'data.csv'),
                             str(target / 'data.csv'))
        w.brand_button.click()
        self.assertTrue(w.directory_button.isVisible())
        self.assertEqual(Workspace().directory, '')
        with self.assertRaises(ValueError):
            self.workspace.set_directory(target / 'does-not-exist')
        self.assertEqual(self.workspace.directory, str(target.resolve()))

    def test_existing_file_actions_use_latest_directory(self):
        w = self.window
        self.workspace.set_directory(self.root)
        w.project_data.doe_matrix = [{'Run_ID': 1, 'X': 2}]
        with patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')) as dialog:
            w.page_DM.export_to_csv()
        self.assertEqual(dialog.call_args.args[2], str(self.root))
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')) as dialog:
            w.page_DM.import_from_csv()
        self.assertEqual(dialog.call_args.args[2], str(self.root))
        panel = w.page_OPT.diagnostics_panel
        panel.context = {'available': True}
        with patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')) as dialog:
            panel.export_json()
        self.assertEqual(dialog.call_args.args[2], str(self.root))
        with patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')) as dialog:
            panel.export_plot()
        self.assertEqual(dialog.call_args.args[2], str(self.root))
        with patch.object(w.page_REP, 'run_analysis'), patch.object(
                QFileDialog, 'getSaveFileName', return_value=('', '')) as dialog:
            w.page_REP.report_html = '<p>result</p>'
            w.page_REP.export_html()
        self.assertEqual(dialog.call_args.args[2], str(self.root / '设计结果报告.html'))
        next_directory = self.root / 'second'
        next_directory.mkdir()
        self.workspace.set_directory(next_directory)
        self.assertEqual(dialog_path(panel), str(next_directory))

    def test_new_session_starts_empty_and_does_not_write_configuration(self):
        self.window.project_data.factors = [FactorItem(name='X')]
        self.workspace.set_directory(self.root)
        self.assertEqual(self.window.project_data.factors[0].name, 'X')
        self.assertEqual(list(self.root.iterdir()), [])
        fresh_window = MainWindow()
        try:
            self.assertEqual(fresh_window.workspace.directory, '')
            self.assertEqual(fresh_window.workspace.file_path('report.pdf'), 'report.pdf')
        finally:
            fresh_window.close()


if __name__ == '__main__':
    unittest.main()
