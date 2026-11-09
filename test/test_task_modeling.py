"""Task-specific business fields feed the existing DOE and archive workflows."""
import os
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox, QComboBox
from backend.core import design_analysis
from backend.domain.models import ProjectData
from backend.services import design_service, task_storage
from frontend.pages.modeling_page import ModelingPage

APP = QApplication.instance() or QApplication([])


def headers(section):
    return [section.table.horizontalHeaderItem(i).text() for i in range(section.table.columnCount())]


class TaskModelingTests(unittest.TestCase):
    def page(self, kind, project=None):
        project = project or ProjectData(task_type=kind)
        page = ModelingPage(project)
        page.load_project_data()
        self.addCleanup(page.close)
        return page, project

    def fill_classical(self, kind):
        page, project = self.page(kind)
        for name, low, high in (('b', '10', '20'), ('h', '40', '60')):
            editor = page.add_design_factor_row()
            editor.name.setText(name)
            editor.lower.setText(low)
            editor.upper.setText(high)
            editor.unit.setText('mm')
        if kind == 'taguchi':
            editor = page.add_environment_factor_row()
            editor.name.setText('T')
            editor.lower.setText('-20')
            editor.upper.setText('60')
            editor.unit.setText('℃')
        response = page.add_response_row()
        response.name.setText('Y')
        response.unit.setText('N')
        return page, project

    def test_task_fields_and_navigation_use_only_the_required_controls(self):
        for kind in ('robust', 'taguchi'):
            with self.subTest(kind=kind):
                page, _ = self.page(kind)
                design = page.add_design_factor_row()
                response = page.add_response_row()
                self.assertEqual(page.model_tabs.count(), 3)
                self.assertEqual(list(page.results_workspace.buttons), list(range(page.model_tabs.count())))
                if kind == 'robust':
                    self.assertEqual(page.design_factors.table.columnCount(), 8)
                    self.assertEqual(page.responses.table.columnCount(), 7)
                    self.assertTrue(hasattr(design, 'parameters'))
                    self.assertEqual(len(page.responses.findChildren(QCheckBox)), 2)
                    self.assertTrue(hasattr(page.design_factors, 'relation'))
                else:
                    levels = ['低水平值', '高水平值']
                    self.assertEqual(headers(page.design_factors), ['名称', *levels, '单位', '操作'])
                    self.assertFalse(page.design_factors.findChildren(QComboBox))
                    self.assertFalse(page.responses.findChildren(QCheckBox))
                    self.assertFalse(hasattr(page.design_factors, 'relation'))
                if kind == 'taguchi':
                    self.assertEqual(headers(page.responses), ['名称', '目标特征', '目标值', '单位', '操作'])
                    self.assertEqual(headers(page.environment_factors), ['名称', '低水平值', '高水平值', '单位', '操作'])
                    self.assertEqual([page.model_tabs.tabText(i) for i in range(3)], ['响应', '控制因子', '噪声因子'])
                    self.assertEqual(page.design_factors.add_btn.text(), '+  新增控制因子')
                    self.assertEqual(page.environment_factors.add_btn.text(), '+  新增噪声因子')
                for i, button in page.results_workspace.buttons.items():
                    self.assertEqual(button.text(), page.model_tabs.tabText(i))
                design.unit.setText('cm')
                self.assertIn('cm', design.lower.toolTip())
                if kind != 'robust':
                    self.assertIn(levels[0], design.lower.toolTip())

    def test_taguchi_bounds_generate_endpoints_and_evenly_spaced_midpoints(self):
        page, project = self.fill_classical('taguchi')
        page.save_btn.click()
        self.assertEqual(page.save_status_label.text(), '已保存')
        self.assertEqual((project.factors[0].param1, project.factors[0].param2), ('0', '0'))
        environment = project.factors[2]
        self.assertEqual((environment.nominal_lower, environment.nominal_upper), ('', ''))
        self.assertEqual((environment.param1, environment.param2), ('-20', '60'))
        for levels, inner, outer in ((2, 'L4', 'L4'), (3, 'L9', 'L9'), (2, 'L4', 'L9'), (3, 'L9', 'L4')):
            plan = design_service.taguchi_plan(project, '田口设计', inner, outer, levels,
                seed=1, replicates=1, randomize=False, snr_mode='按各响应目标特征自动')
            meta = plan.params['meta']
            self.assertEqual(meta['factor_levels']['b'], [10, 20] if levels == 2 else [10, 15, 20])
            self.assertEqual(meta['noise_levels']['T'], [-20, 60] if outer == 'L4' else [-20, 20, 60])

    def test_taguchi_response_only_requires_a_single_target_for_nominal_best(self):
        page, project = self.fill_classical('taguchi')
        response = page.responses.editors[0]
        for feature in ('望大', '望小'):
            response.feature.setCurrentText(feature)
            self.assertFalse(response.target.isEnabled())
            page.save_btn.click()
            self.assertEqual(project.responses[0].feature, feature)
            self.assertEqual(project.responses[0].robust_limit, '')
        before = task_storage.fingerprint(project)
        response.feature.setCurrentText('望目')
        self.assertTrue(response.target.isEnabled())
        with patch('frontend.pages.modeling_page.Notice.warning') as notice:
            page.save_btn.click()
            notice.assert_called_once()
        self.assertEqual(task_storage.fingerprint(project), before)
        response.target.setText('10')
        page.save_btn.click()
        item = project.responses[0]
        self.assertEqual((item.kind, item.target, item.lower, item.upper), ('目标', '10', '', ''))
        plan = design_service.taguchi_plan(project, '田口设计', 'L4', 'L4', 2,
            seed=1, replicates=1, randomize=False, snr_mode='按各响应目标特征自动')
        design_service.commit_plan(project, plan)
        for row in project.doe_matrix:
            row['Y'] = 10 + row['T'] / 100
        result = design_analysis.taguchi(project)
        self.assertFalse(result['errors'])
        self.assertEqual(result['response_analysis']['Y']['feature'], '望目')
        self.assertIn('目标偏差', result['response_analysis']['Y']['metric_label'])
        for run in result['response_analysis']['Y']['runs']:
            self.assertAlmostEqual(run['metric'], -10 * math.log10(.2))
        response.feature.setCurrentText('望小')
        page.save_btn.click()
        self.assertEqual(project.responses[0].target, '')
        response.feature.setCurrentText('望目')
        self.assertEqual(response.target.text(), '10')

    def test_target_disabled_state_is_visible_before_click_and_preserves_draft(self):
        page, _ = self.fill_classical('taguchi')
        page.show()
        page.model_tabs.setCurrentIndex(0)
        APP.processEvents()
        APP.processEvents()
        response = page.responses.editors[0]
        target = response.target
        before = target.geometry()
        self.assertTrue(target.isVisible())
        self.assertFalse(target.isEnabled())
        QTest.mouseClick(target, Qt.MouseButton.LeftButton)
        QTest.keyClicks(target, '123')
        self.assertEqual(target.text(), '')
        response.feature.setCurrentText('望目')
        APP.processEvents()
        self.assertTrue(target.isVisible())
        self.assertTrue(target.isEnabled())
        self.assertEqual(target.geometry(), before)
        QTest.mouseClick(target, Qt.MouseButton.LeftButton)
        QTest.keyClicks(target, '10')
        self.assertEqual(target.text(), '10')
        response.feature.setCurrentText('望大')
        APP.processEvents()
        self.assertTrue(target.isVisible())
        self.assertFalse(target.isEnabled())
        self.assertEqual(target.text(), '10')

    def test_all_business_columns_fill_viewport_without_blank_trailing_area(self):
        for kind in ('robust', 'taguchi'):
            page, _ = self.page(kind)
            page.show()
            for width in (1050, 1440, 1920, 1050):
                page.resize(width, 600)
                for index, section in enumerate(page.sections):
                    page.model_tabs.setCurrentIndex(index)
                    APP.processEvents()
                    APP.processEvents()
                    table = section.table
                    self.assertEqual(table.horizontalScrollBar().maximum(), 0)
                    column_widths = [table.columnWidth(i) for i in range(table.columnCount())]
                    self.assertEqual(sum(column_widths), table.viewport().width(), (kind, index, width, column_widths))
                    last = table.columnCount() - 1
                    header = table.horizontalHeader()
                    self.assertEqual(header.sectionViewportPosition(last) + header.sectionSize(last), table.viewport().width())
                    self.assertEqual(table.width(), section.contentsRect().width() - 20)
                    if kind == 'robust' and index == 2:
                        self.assertEqual(table.width(), section.contentsRect().width() - 20)
                        self.assertEqual(sum(table.columnWidth(i) for i in range(6)), table.viewport().width())
                        self.assertEqual([table.columnWidth(i) for i in (4, 5)], [60, 64])

    def test_target_accepts_zero_and_negative_values_and_rejects_nonfinite_input(self):
        page, project = self.fill_classical('taguchi')
        response = page.responses.editors[0]
        response.feature.setCurrentText('望目')
        for target in ('0', '-10', '1.25'):
            response.target.setText(target)
            page.save_btn.click()
            self.assertEqual(project.responses[0].target, target)
        before = task_storage.fingerprint(project)
        for target in ('', 'nan', 'inf', '1e309'):
            response.target.setText(target)
            with patch('frontend.pages.modeling_page.Notice.warning') as notice:
                page.save_btn.click()
                notice.assert_called_once()
            self.assertEqual(task_storage.fingerprint(project), before)

    def test_changed_target_invalidates_results_only_after_explicit_submission(self):
        page, project = self.fill_classical('taguchi')
        response = page.responses.editors[0]
        response.feature.setCurrentText('望目')
        response.target.setText('10')
        page.save_btn.click()
        project.taguchi_result = {'sentinel': 'existing result'}
        response.target.setText('11')
        page.model_tabs.setCurrentIndex(1)
        self.assertEqual(project.responses[0].target, '10')
        self.assertTrue(project.taguchi_result)
        page.save_btn.click()
        self.assertEqual(project.responses[0].target, '11')
        self.assertFalse(project.taguchi_result)

    def test_invalid_classical_bounds_and_names_cannot_partially_commit(self):
        for kind in ('taguchi',):
            page, project = self.fill_classical(kind)
            page.save_btn.click()
            before = task_storage.fingerprint(project)
            sections = page.sections[1:]
            for section in sections:
                editor = section.editors[0]
                original = editor.lower.text(), editor.upper.text()
                for lower, upper in (('', '20'), ('20', '10'), ('10', '10'), ('1e309', '20')):
                    editor.lower.setText(lower)
                    editor.upper.setText(upper)
                    with patch('frontend.pages.modeling_page.Notice.warning') as notice:
                        page.save_btn.click()
                        notice.assert_called_once()
                    self.assertEqual(task_storage.fingerprint(project), before)
                editor.lower.setText(original[0])
                editor.upper.setText(original[1])
            page.responses.editors[0].name.setText('b')
            with self.assertRaisesRegex(ValueError, '重复'):
                page.sync_to_project_data()
            self.assertEqual(task_storage.fingerprint(project), before)

    def test_classical_archive_and_reload_keep_only_submitted_values(self):
        for kind in ('taguchi',):
            page, project = self.fill_classical(kind)
            if kind == 'taguchi':
                response = page.responses.editors[0]
                response.feature.setCurrentText('望目')
                response.target.setText('10')
            page.save_btn.click()
            before = task_storage.fingerprint(project)
            page.design_factors.editors[0].lower.setText('11')
            if kind == 'taguchi':
                page.responses.editors[0].target.setText('99')
            page.model_tabs.setCurrentIndex(1)
            self.assertEqual(task_storage.fingerprint(project), before)
            with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'temp') as directory:
                path = Path(directory) / (kind + '.rodas')
                task_storage.save_task(project, path)
                restored = task_storage.load_task(path)
                other, _ = self.page(kind, restored)
                self.assertEqual(other.design_factors.editors[0].lower.text(), '10')
                self.assertEqual(headers(other.responses), headers(page.responses))
                if kind == 'taguchi':
                    self.assertEqual(other.responses.editors[0].target.text(), '10')
                other.save_btn.click()
                self.assertEqual(task_storage.fingerprint(restored), before)
            page.design_factors.editors[0].delete_btn.click()
            self.assertEqual(page.design_factors.editors[0].name.text(), 'h')
            page.load_project_data()
            self.assertEqual(page.design_factors.table.rowCount(), 2)


if __name__ == '__main__':
    unittest.main()
