"""Welcome navigation preserves work; one directory drives all file dialogs."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget
from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtTest import QTest
from backend.domain.models import FactorItem, ProjectData, TASK_TYPES
from backend.services import task_storage
from backend.services.project_service import ProjectService
from frontend.main_window import MainWindow
from frontend.pages.welcome_page import CHINESE_NAME, brand_pixmap
from frontend.terminology import tooltip
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
        self.window.task_actions.confirm_leave = lambda **kwargs: True
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
        factor = w.page_MOD.design_factors.editors[0]
        for control, value in ((factor.lower, '1'), (factor.upper, '2'),
                               (factor.delta_lower, '-.05'), (factor.delta_upper, '.05')):
            control.setText(value)
        editor = factor.name
        editor.setText('翼梁厚度')
        w.brand_button.click()
        self.assertFalse(w.project_data.factors)
        w.page_MOD.save_btn.click()
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

    def test_new_task_hover_keeps_choices_open_across_children_and_collapses_outside(self):
        w = self.window
        card = w.welcome_page.new_task_card
        project = w.project_data
        outside = w.welcome_page.action_buttons['读取已有任务']
        QTest.mouseMove(outside, QPoint(5, 5))
        APP.processEvents()
        geometry = card.geometry()
        QTest.mouseMove(card, card.rect().center())
        APP.processEvents()
        self.assertIs(card.currentWidget(), card.options)
        self.assertEqual([button.text() for button in card.buttons.values()], list(TASK_TYPES.values()))
        term_keys = {'robust': 'task_robust', 'taguchi': 'taguchi_design',
                     'factorial': 'factor_screening'}
        for key, button in card.buttons.items():
            self.assertEqual(button.toolTip(), tooltip(term_keys[key]))
        for button in card.buttons.values():
            QTest.mouseMove(button, button.rect().center())
            APP.processEvents()
            self.assertTrue(button.isVisible())
            self.assertIs(card.currentWidget(), card.options)
        self.assertEqual(card.geometry(), geometry)
        self.assertIs(w.project_data, project)
        self.assertEqual(project.task_type, '')
        QTest.mouseMove(outside, QPoint(5, 5))
        APP.processEvents()
        self.assertIs(card.currentWidget(), card.cover)

    def test_new_task_click_and_keyboard_can_reveal_and_close_choices(self):
        card = self.window.welcome_page.new_task_card
        card.cover.click()
        self.assertIs(card.currentWidget(), card.options)
        self.assertIs(APP.focusWidget(), card.buttons['robust'])
        QTest.keyClick(card.buttons['robust'], Qt.Key.Key_Escape)
        self.assertIs(card.currentWidget(), card.cover)

    def test_three_task_choices_create_matching_empty_tasks_and_keep_workspace(self):
        w = self.window
        self.workspace.set_directory(self.root)
        for kind, family in (('robust', 2), ('taguchi', 1), ('factorial', 0)):
            w.show_welcome()
            card = w.welcome_page.new_task_card
            card.cover.click()
            card.buttons[kind].click()
            APP.processEvents()
            self.assertEqual(w.project_data.task_type, kind)
            self.assertEqual(w.stacked_widget.currentIndex(), 0)
            self.assertEqual(w.page_CFG.dynamic_params_widget.currentIndex(), family)
            self.assertEqual(list(w.page_CFG.results_workspace.buttons), [family])
            self.assertEqual(w.page_MOD.design_factors.table.columnCount(), 8 if kind == 'robust' else 5)
            self.assertEqual(w.page_MOD.responses.table.columnCount(), {'robust': 7, 'taguchi': 5, 'factorial': 3}[kind])
            self.assertEqual(w.page_MOD.model_tabs.count(), 2 if kind == 'factorial' else 3)
            self.assertFalse(w.project_data.design_method)
            self.assertFalse(w.project_data.doe_matrix)
            self.assertEqual(self.workspace.directory, str(self.root))
            self.assertIn(TASK_TYPES[kind], w.windowTitle())

    def test_task_choice_survives_archive_and_workspace_rebuild(self):
        w = self.window
        self.assertTrue(w.task_actions.new('taguchi'))
        self.assertEqual(ProjectService.for_project(w.project_data).input_snapshot().task_type, 'taguchi')
        path = self.root / 'taguchi.rodas'
        task_storage.save_task(w.project_data, path)
        restored = task_storage.load_task(path)
        self.assertEqual(restored.task_type, 'taguchi')
        w.task_actions._replace(restored, path)
        self.assertEqual(w.page_CFG.dynamic_params_widget.currentIndex(), 1)
        self.assertEqual(list(w.page_CFG.results_workspace.buttons), [1])

    def test_environment_width_is_stable_across_repeated_new_tasks_and_file_reads(self):
        w = self.window
        paths = {kind: self.root / (kind + '-layout.rodas') for kind in TASK_TYPES}
        for kind, path in paths.items():
            task_storage.save_task(ProjectData(task_type=kind), path)
        for width, height in ((1050, 700), (1920, 1080)):
            w.resize(width, height)
            APP.processEvents()
            measurements = {}
            for action, kind in (('new', 'robust'), ('read', 'taguchi'), ('new', 'factorial'),
                                 ('read', 'robust'), ('new', 'taguchi'), ('read', 'factorial'),
                                 ('new', 'robust'), ('read', 'robust')):
                if action == 'new':
                    w.show_welcome()
                    card = w.welcome_page.new_task_card
                    card.cover.click()
                    card.buttons[kind].click()
                else:
                    with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(paths[kind]), '')):
                        self.assertTrue(w.task_actions.open())
                    w.switch_page(0)
                for _ in range(4):
                    w.page_MOD.add_response_row()
                    w.page_MOD.add_design_factor_row()
                    if kind != 'factorial':
                        w.page_MOD.add_environment_factor_row()
                for index, section in enumerate(w.page_MOD.sections):
                    w.page_MOD.model_tabs.setCurrentIndex(index)
                    QTest.qWait(1)
                    APP.processEvents()
                    table = section.table
                    measurements.setdefault((kind, index), []).append(table.width())
                    self.assertEqual(table.width(), section.width() - 20, measurements)
                    self.assertEqual(sum(table.columnWidth(i) for i in range(table.columnCount())), table.viewport().width())
                self.assertEqual(w.stacked_widget.width(), w.centralWidget().width())
                self.assertEqual(w.workspace_splitter.count(), 2)
            for section_key, values in measurements.items():
                self.assertEqual(len(set(values)), 1, (width, section_key, measurements))

    def test_cancel_new_task_choice_keeps_current_project(self):
        w = self.window
        project = w.project_data
        card = w.welcome_page.new_task_card
        card.cover.click()
        with patch.object(w.task_actions, 'confirm_leave', return_value=False) as confirm:
            card.buttons['factorial'].click()
            confirm.assert_called_once()
        self.assertIs(w.project_data, project)
        self.assertEqual(project.task_type, '')
        self.assertIs(w.stacked_widget.currentWidget(), w.welcome_page)

    def test_startup_new_and_read_never_show_internal_controls_as_windows(self):
        shown = []

        class WindowShows(QObject):
            def eventFilter(self, obj, event):
                if (event.type() == QEvent.Type.Show and isinstance(obj, QWidget)
                        and obj.isWindow() and not isinstance(obj, MainWindow)):
                    shown.append(type(obj).__name__)
                return False

        observer = WindowShows()
        APP.installEventFilter(observer)
        fresh = None
        try:
            fresh = MainWindow()
            fresh.task_actions.confirm_leave = lambda **kwargs: True
            fresh.show()
            APP.processEvents()
            self.assertEqual(shown, [])
            path = self.root / 'no-window-flash.rodas'
            for kind in TASK_TYPES:
                fresh.show_welcome()
                card = fresh.welcome_page.new_task_card
                card.cover.click()
                card.buttons[kind].click()
                APP.processEvents()
                self.assertEqual(shown, [], kind)
                task_storage.save_task(fresh.project_data, path)
                with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path), '')):
                    self.assertTrue(fresh.task_actions.open())
                APP.processEvents()
                self.assertEqual(shown, [], kind)
        finally:
            APP.removeEventFilter(observer)
            if fresh is not None:
                fresh.close()

    def test_new_session_starts_empty_and_does_not_write_configuration(self):
        self.window.project_data.factors = [FactorItem(name='X')]
        self.workspace.set_directory(self.root)
        self.assertEqual(self.window.project_data.factors[0].name, 'X')
        self.assertEqual(list(self.root.iterdir()), [])
        fresh_window = MainWindow()
        fresh_window.task_actions.confirm_leave = lambda **kwargs: True
        try:
            self.assertEqual(fresh_window.workspace.directory, '')
            self.assertEqual(fresh_window.workspace.file_path('report.pdf'), 'report.pdf')
        finally:
            fresh_window.close()


if __name__ == '__main__':
    unittest.main()
