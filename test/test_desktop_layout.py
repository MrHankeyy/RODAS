"""Navigation and resizing contracts; computation regression lives in engine tests."""
import os
import sys
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtCore import Qt
from frontend.main_window import MainWindow
from frontend.pages.modeling_page import FIXED_VALUE_HELP

APP = QApplication.instance() or QApplication([])


class DesktopLayoutTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.window.task_actions.confirm_leave = lambda **kwargs: True
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()

    def test_workflow_heading_and_small_window(self):
        self.window.resize(1100, 760)
        for index in range(5):
            self.window.btns_switch[index].click()
            APP.processEvents()
            self.assertEqual(self.window.stacked_widget.currentIndex(), index)
            self.assertEqual(self.window.page_title.text(), self.window.PAGE_INFO[index][0])
            self.assertEqual(self.window.width(), 1100)
            self.assertEqual(sum(b.property('active') for b in self.window.btns_switch), 1)

    def test_result_navigation_tracks_visible_method_pages(self):
        page = self.window.page_OPT
        for method, wanted, unwanted in [('筛选设计', 8, 9), ('田口设计', 9, 8), ('响应曲面设计', 1, 8)]:
            page.project_data.design_method = method
            page._update_method_actions()
            workspace = page.results_workspace
            self.assertNotIn('整体数据分析', [page.tabs.tabText(i) for i in range(page.tabs.count())])
            self.assertIn(wanted, workspace.buttons)
            self.assertNotIn(unwanted, workspace.buttons)
            workspace.buttons[wanted].click()
            self.assertEqual(page.tabs.currentIndex(), wanted)
            page.tabs.setCurrentIndex(0)
            self.assertTrue(workspace.buttons[0].isChecked())
            self.assertEqual(sum(button.isChecked() for button in workspace.buttons.values()), 1)

    def test_configuration_controls_preserve_full_panel_width(self):
        self.window.resize(1900, 1000)
        self.window.on_switch_module('方案配置', 1)
        page = self.window.page_CFG
        self.assertFalse(hasattr(page, 'info_group'))
        page.dynamic_params_widget.setCurrentIndex(2)
        for model in range(4):
            page.model_combo.setCurrentIndex(model)
            APP.processEvents()
            editor = page.model_stack.currentWidget()
            expected = (page.model_stack.width(), editor.width())
            designs = ('CCD', 'BBD') if model == 0 else ('Latin Hypercube (LHS)', '均匀网格抽样')
            for design in designs:
                editor.doe_method_combo.setCurrentText(design)
                for alpha in (1, 2, 0):
                    editor.alpha_mode_combo.setCurrentIndex(alpha)
                    self.assertEqual((page.model_stack.width(), editor.width()), expected)
                    APP.processEvents()
                    self.assertEqual((page.model_stack.width(), editor.width()), expected)

    def test_model_sections_preserve_rows_without_counts(self):
        page = self.window.page_MOD
        page.add_design_factor_row()
        page.add_environment_factor_row()
        page.environment_factor_table.cellWidget(0, 0).setText('温度')
        page.model_tabs.setCurrentIndex(2)
        self.assertEqual(page.model_tabs.tabText(2), '环境因子')
        page.model_tabs.setCurrentIndex(1)
        self.assertEqual(page.environment_factor_table.cellWidget(0, 0).text(), '温度')
        self.assertEqual(
            page.design_factor_table.horizontalHeader().section_tooltip(5),
            FIXED_VALUE_HELP,
        )
        self.assertEqual(
            page.design_factor_table.cellWidget(0, 5).toolTip(),
            FIXED_VALUE_HELP,
        )
        self.assertNotIn(
            FIXED_VALUE_HELP,
            [label.text() for label in page.findChildren(QLabel)],
        )

    def test_message_collapse_preserves_content(self):
        self.window.fold_messages.click()
        self.assertTrue(self.window.message_view.isHidden())
        self.window._post_message('成功', '保存', '已完成')
        self.window.fold_messages.click()
        self.assertFalse(self.window.message_view.isHidden())
        self.assertIn('已完成', self.window.message_view.toPlainText())


if __name__ == '__main__':
    unittest.main()
