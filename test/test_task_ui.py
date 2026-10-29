"""Native menus, explicit commits, file lifecycle and saved-page restoration."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QFileDialog, QMenuBar, QMessageBox
from backend.domain.models import ProjectData
from backend.services import task_storage, model_service, analysis_service
from frontend.main_window import MainWindow
from test_workbench_analysis import APP, make_context


class TaskUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp')
        self.root = Path(self.temp.name)
        self.w = MainWindow()
        self.w.show()
        APP.processEvents()

    def tearDown(self):
        self.w.task_actions.confirm_leave = lambda **kwargs: True
        self.w.close()
        APP.processEvents()
        self.temp.cleanup()

    def save(self, name='task.rodas'):
        path = self.root / name
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.assertTrue(self.w.task_actions.save_as())
        return path

    def test_native_global_menu_and_keyboard_save(self):
        self.assertIsInstance(self.w.menuBar(), QMenuBar)
        actions = self.w.menuBar().actions()
        self.assertEqual([a.text() for a in actions], ['文件', '教程', '设置工作目录'])
        self.assertEqual([a.text() for a in actions[0].menu().actions()], ['保存', '另存为', '读取'])
        self.assertEqual(self.w.task_actions.actions['保存'].shortcut().toString(), 'Ctrl+S')
        for index in (self.w.welcome_index, 0, 1, 2, 3, 4):
            self.w.stacked_widget.setCurrentIndex(index)
            self.assertTrue(self.w.menuBar().isVisible())
        path = self.root / 'menu.rodas'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.w.task_actions.actions['保存'].trigger()
        self.assertTrue(path.is_file())

    def test_switching_and_global_save_never_submit_business_drafts(self):
        self.w.switch_page(0)
        page = self.w.page_MOD
        page.add_design_factor_row()
        editor = page.design_factors.editors[0]
        editor.name.setText('厚度')
        for control, value in ((editor.lower, '1'), (editor.upper, '2'),
                               (editor.delta_lower, '-.05'), (editor.delta_upper, '.05')):
            control.setText(value)
        self.w.switch_page(1)
        self.assertFalse(self.w.project_data.factors)
        self.w.switch_page(0)
        self.w.show_welcome()
        self.assertFalse(self.w.project_data.factors)
        path = self.save()
        self.assertFalse(task_storage.load_task(path).factors)
        self.assertEqual(editor.name.text(), '厚度')
        page.save_btn.click()
        self.assertEqual(self.w.project_data.factors[0].name, '厚度')
        self.w.task_actions.save()
        self.assertEqual(task_storage.load_task(path).factors[0].name, '厚度')

    def test_save_as_does_not_modify_old_file_or_working_directory(self):
        self.w.workspace.set_directory(self.root)
        first = self.save('first.rodas')
        old = first.read_bytes()
        self.w.project_data.report_metadata['project_name'] = '另一个版本'
        second = self.save('second.rodas')
        self.assertEqual(first.read_bytes(), old)
        self.assertEqual(self.w.task_actions.path, second.resolve())
        self.assertEqual(self.w.workspace.directory, str(self.root))
        self.assertEqual(task_storage.load_task(second).report_metadata['project_name'], '另一个版本')

    def test_close_cancel_and_cancelled_save_keep_window_open(self):
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.w.close())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Save), \
             patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
            self.assertFalse(self.w.close())
        path = self.root / 'close.rodas'
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Save), \
             patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.assertTrue(self.w.close())
        self.assertTrue(path.exists())

    def test_read_restores_definitions_models_and_views_without_training_or_directory_change(self):
        project, _ = make_context()
        context = model_service.build_rsm_context(project)
        project.workbench_result = analysis_service.analyze(project, context, {})['snapshot']
        path = self.root / 'loaded.rodas'
        task_storage.save_task(project, path)
        directory = self.root / 'output'
        directory.mkdir()
        self.w.workspace.set_directory(directory)
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path), '')), \
             patch.object(model_service.optimizer, 'build_models', side_effect=AssertionError('must not refit')):
            self.assertTrue(self.w.task_actions.open())
            self.assertEqual(task_storage.fingerprint(self.w.project_data), self.w.task_actions.saved_fingerprint)
            self.w.page_OPT._prepare_context()
        self.assertEqual(self.w.workspace.directory, str(directory))
        self.assertEqual(len(self.w.page_MOD.design_factors.editors), 2)
        self.assertEqual(self.w.page_MOD.responses.editors[0].name.text(), 'Y')
        self.assertIsNotNone(self.w.page_OPT.model_panel.context)
        self.assertIsNotNone(self.w.page_OPT.diagnostics_panel.context)
        self.w.switch_page(2)
        APP.processEvents()
        self.assertEqual(self.w.page_DM.table.rowCount(), len(project.doe_matrix))

    def test_invalid_read_and_cancelled_switch_preserve_active_task(self):
        original = self.w.project_data
        bad = self.root / 'bad.rodas'
        bad.write_text('invalid', encoding='utf-8')
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(bad), '')):
            self.assertFalse(self.w.task_actions.open())
        self.assertIs(self.w.project_data, original)
        valid = self.root / 'valid.rodas'
        task_storage.save_task(ProjectData(), valid)
        original.report_metadata['project_name'] = 'unsaved committed data'
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(valid), '')), \
             patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.w.task_actions.open())
        self.assertIs(self.w.project_data, original)

    def test_response_and_configuration_drafts_do_not_enter_archive(self):
        project, _ = make_context()
        self.w.task_actions._replace(project, None)
        self.w.switch_page(2)
        APP.processEvents()
        page = self.w.page_DM
        column = next(i for i in range(page.table.columnCount()) if page.table.horizontalHeaderItem(i).text() == 'Y')
        old = project.doe_matrix[0]['Y']
        page.table.item(0, column).setText('99999')
        self.w.page_CFG.model_editors['RSM'].centers_spin.setValue(17)
        path = self.save()
        restored = task_storage.load_task(path)
        self.assertEqual(restored.doe_matrix[0]['Y'], old)
        self.assertNotIn('17', str(restored.design_params))

    def test_optimization_and_report_drafts_do_not_replace_committed_settings(self):
        project, _ = make_context()
        self.w.task_actions._replace(project, None)
        self.w.page_OPT.run_statistics()
        generations = project.workbench_result['settings']['generations']
        self.w.page_OPT.gen_spin.setValue(generations + 1)
        self.w.page_REP.fields['author'].setText('not submitted')
        self.w.page_REP.run_analysis()
        path = self.save()
        restored = task_storage.load_task(path)
        self.assertEqual(restored.workbench_result['settings']['generations'], generations)
        self.assertNotIn('author', restored.report_metadata)

    def test_reopening_same_file_after_saving_keeps_the_newly_saved_data(self):
        path = self.save()
        self.w.project_data.report_metadata['project_name'] = 'updated'
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path), '')), \
             patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Save):
            self.assertTrue(self.w.task_actions.open())
        self.assertEqual(self.w.project_data.report_metadata['project_name'], 'updated')

    def test_ui_restore_failure_rolls_back_the_active_task_and_pages(self):
        original = self.w.project_data
        page = self.w.page_MOD
        project = ProjectData(report_metadata={'project_name': 42})
        path = self.root / 'bad-ui-data.rodas'
        task_storage.save_task(project, path)
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path), '')):
            self.assertFalse(self.w.task_actions.open())
        self.assertIs(self.w.project_data, original)
        self.assertIs(self.w.page_MOD, page)


if __name__ == '__main__':
    unittest.main()
