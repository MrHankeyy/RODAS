"""Shared section navigation and correctly anchored combo popup geometry."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QComboBox, QStyle, QStyleOptionComboBox, QWidget, QAbstractItemView
from backend.domain.models import FactorItem, ProjectData, ResponseItem
from frontend.main_window import MainWindow
from frontend.pages.configuration_page import ConfigurationPage
from frontend.pages.modeling_page import ModelingPage
from frontend.theme import ResultsWorkspace, install_theme

APP = QApplication.instance() or QApplication([])


class NavigationPopupTests(unittest.TestCase):
    def test_model_sections_preserve_all_tables_without_counts(self):
        p = ProjectData()
        page = ModelingPage(p)
        self.assertIsInstance(page.results_workspace, ResultsWorkspace)
        page.add_response_row()
        page.add_design_factor_row()
        page.add_environment_factor_row()
        page.responses.editors[0].name.setText("应力")
        for section, name in ((page.design_factors, "厚度"), (page.environment_factors, "温度")):
            editor = section.editors[0]
            editor.name.setText(name)
            if section is page.design_factors:
                editor.lower.setText('1')
                editor.upper.setText('2')
            for control, value in ((editor.delta_lower, '-.05'), (editor.delta_upper, '.05')):
                control.setText(value)
        for index in (2, 0, 1, 2):
            page.results_workspace.buttons[index].click()
            self.assertEqual(page.model_tabs.currentIndex(), index)
        self.assertEqual(page.results_workspace.buttons[1].text(), "设计因子")
        self.assertEqual(page.results_workspace.buttons[2].text(), "环境因子")
        page.sync_to_project_data()
        self.assertEqual([f.name for f in p.factors], ["厚度", "温度"])
        self.assertEqual(p.responses[0].name, "应力")
        self.assertFalse(hasattr(page, "factor_tabs"))
        page.close()

    def test_plan_navigation_preserves_each_draft_and_restores_saved_family(self):
        p = ProjectData(factors=[FactorItem(name=f"X{i}", param1="-1", param2="1") for i in range(3)],
                        responses=[ResponseItem(name="Y")])
        page = ConfigurationPage(p)
        self.assertFalse(hasattr(page, "method_combo"))
        page.f_repeat_spin.setValue(2)
        page.results_workspace.buttons[1].click()
        page.t_seed_spin.setValue(64)
        page.results_workspace.buttons[2].click()
        page.model_combo.setCurrentIndex(3)
        page.model_editors["ANN"].sample_count_spin.setValue(42)
        page.model_editors["ANN"].epoch_spin.setValue(1200)
        for index in (0, 1, 2):
            page.results_workspace.buttons[index].click()
            self.assertEqual(page.dynamic_params_widget.currentIndex(), index)
        self.assertEqual(page.f_repeat_spin.value(), 2)
        self.assertEqual(page.t_seed_spin.value(), 64)
        page._generate_by_method()
        restored = ConfigurationPage(p)
        self.assertEqual(restored.dynamic_params_widget.currentIndex(), 2)
        self.assertTrue(restored.results_workspace.buttons[2].isChecked())
        self.assertEqual(restored.model_editors["ANN"].epoch_spin.value(), 1200)
        self.assertEqual(len(p.doe_matrix), 42)
        page.close()
        restored.close()

    def test_small_window_keeps_plan_actions_visible_for_every_family(self):
        window = MainWindow()
        window.task_actions.confirm_leave = lambda **kwargs: True
        window.resize(1050, 700)
        window.show()
        window.switch_page(1)
        page = window.page_CFG
        for index in (0, 1, 2):
            page.results_workspace.buttons[index].click()
            APP.processEvents()
            rect = window.rect()
            position = page.gen_btn.mapTo(window, QPoint(0, 0))
            self.assertTrue(rect.contains(position))
            self.assertTrue(rect.contains(position + QPoint(page.gen_btn.width()-1, page.gen_btn.height()-1)))
            self.assertLess(position.y() + page.gen_btn.height(),
                            window.message_panel.mapTo(window, QPoint()).y())
            self.assertEqual(window.size().width(), 1050)
            self.assertEqual(window.size().height(), 700)
        window.close()

    def assert_list_popup(self, combo, below=True):
        option = QStyleOptionComboBox()
        option.initFrom(combo)
        self.assertEqual(combo.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup, option, combo), 0)
        combo.showPopup()
        APP.processEvents()
        view = combo.view()
        if below:
            bottom = combo.mapToGlobal(QPoint(0, combo.height()-1)).y()
            self.assertGreaterEqual(view.window().geometry().top(), bottom-1)
        for row in range(combo.count()):
            self.assertTrue(view.viewport().rect().contains(view.visualRect(combo.model().index(row, 0))))
        combo.hidePopup()

    def test_feature_popup_shows_all_choices_for_each_selected_item(self):
        window = MainWindow()
        window.task_actions.confirm_leave = lambda **kwargs: True
        window.resize(1050, 700)
        window.show()
        window.switch_page(0)
        page = window.page_MOD
        page.add_response_row()
        APP.processEvents()
        combo = page.responses.editors[0].feature
        for index in range(3):
            combo.setCurrentIndex(index)
            self.assert_list_popup(combo)
        self.assertEqual([combo.itemText(i) for i in range(combo.count())], ["望大", "望小", "望目"])
        window.close()

    def test_popup_stays_on_screen_when_below_space_is_insufficient(self):
        install_theme(APP)
        parent = QWidget()
        parent.resize(240, 65)
        area = APP.primaryScreen().availableGeometry()
        parent.move(area.left()+20, area.bottom()-75)
        combo = QComboBox(parent)
        combo.setGeometry(10, 15, 200, 35)
        combo.addItems(["望大", "望小", "望目"])
        parent.show()
        APP.processEvents()
        combo.setCurrentIndex(2)
        combo.showPopup()
        APP.processEvents()
        self.assertTrue(area.contains(combo.view().window().geometry()))
        combo.hidePopup()
        parent.close()

    def test_popup_tracks_scrolled_table_cell_and_formula_choice_sizes(self):
        window = MainWindow()
        window.task_actions.confirm_leave = lambda **kwargs: True
        window.resize(1050, 700)
        window.show()
        window.switch_page(0)
        page = window.page_MOD
        for _ in range(18):
            page.add_response_row()
        table = page.responses.table
        table.scrollTo(table.model().index(17, 3), QAbstractItemView.ScrollHint.PositionAtBottom)
        APP.processEvents()
        combo = page.responses.editors[17].feature
        combo.setCurrentIndex(2)
        self.assert_list_popup(combo)
        window.switch_page(1)
        APP.processEvents()
        window.page_CFG.screen_kind_combo.setCurrentIndex(3)
        self.assert_list_popup(window.page_CFG.screen_kind_combo)
        window.close()


if __name__ == "__main__":
    unittest.main()
