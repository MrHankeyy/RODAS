"""Numeric editing contracts and their integration with page actions."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QPoint, QPointF, QSignalBlocker, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QAbstractSpinBox, QLineEdit, QVBoxLayout, QWidget

from backend.domain.models import FactorItem, ProjectData, ResponseItem
from frontend.main_window import MainWindow
from frontend.numeric_inputs import commit_numeric_inputs, numeric_input
from frontend.pages.configuration_page import ConfigurationPage
from frontend.pages.optimization_page import OptimizationPage
from frontend.pages.workbench_diagnostics import WorkbenchDiagnostics

APP = QApplication.instance() or QApplication([])


def type_number(control, text):
    control.lineEdit().selectAll()
    QTest.keyClicks(control.lineEdit(), text)


class NumericInputTests(unittest.TestCase):
    def test_typing_commits_once_on_enter_or_focus_loss(self):
        for kind, text, expected in ((int, "500", 500), (float, "0.125", .125)):
            with self.subTest(kind=kind):
                parent = QWidget()
                layout = QVBoxLayout(parent)
                control = numeric_input(kind, -1000, 1000, 1, decimals=4)
                other = QLineEdit()
                layout.addWidget(control)
                layout.addWidget(other)
                parent.show()
                control.setFocus()
                APP.processEvents()
                changes = QSignalSpy(control.valueChanged)
                type_number(control, text)
                self.assertEqual(control.value(), 1)
                self.assertEqual(len(changes), 0)
                QTest.keyClick(control, Qt.Key.Key_Return)
                self.assertEqual(control.value(), expected)
                self.assertEqual(len(changes), 1)
                type_number(control, "2")
                self.assertEqual(len(changes), 1)
                other.setFocus()
                APP.processEvents()
                self.assertEqual(control.value(), 2)
                self.assertEqual(len(changes), 2)
                parent.close()

    def test_integer_steps_immediately_and_stops_at_boundaries(self):
        control = numeric_input(int, -2, 2, 0)
        changes = QSignalSpy(control.valueChanged)
        QTest.keyClick(control, Qt.Key.Key_Up)
        self.assertEqual(control.value(), 1)
        self.assertEqual(len(changes), 1)
        control.stepUp()
        control.stepUp()
        self.assertEqual(control.value(), 2)
        control.setValue(-2)
        control.stepDown()
        self.assertEqual(control.value(), -2)
        self.assertIs(type(control.value()), int)

    def test_decimal_has_no_button_keyboard_or_wheel_increment(self):
        control = numeric_input(float, -1, 1, .25, decimals=4)
        self.assertEqual(control.buttonSymbols(), QAbstractSpinBox.ButtonSymbols.NoButtons)
        changes = QSignalSpy(control.valueChanged)
        for key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            QTest.keyClick(control, key)
        control.stepUp()
        control.stepDown()
        wheel = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, 120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        APP.sendEvent(control, wheel)
        self.assertFalse(wheel.isAccepted())
        self.assertEqual(control.value(), .25)
        self.assertEqual(len(changes), 0)
        control.lineEdit().selectAll()
        control.lineEdit().insert("1e-4")  # Paste a complete scientific-notation value.
        control.interpretText()
        self.assertEqual(control.value(), .0001)

    def test_invalid_edits_restore_and_bulk_fill_can_block_signals(self):
        parent = QWidget()
        control = numeric_input(float, -1, 1, .25, decimals=4)
        control.setParent(parent)
        changes = QSignalSpy(control.valueChanged)
        for invalid in ("", "abc", "nan", "5"):
            control.lineEdit().setText(invalid)
            commit_numeric_inputs(parent)
            self.assertEqual(control.value(), .25)
        self.assertEqual(len(changes), 0)
        with QSignalBlocker(control):
            control.setValue(-.125)
        self.assertEqual(len(changes), 0)
        self.assertEqual(control.value(), -.125)
        control.setRange(-.1, .1)
        self.assertEqual(control.value(), -.1)
        control.setValue(5)
        self.assertEqual(control.value(), .1)

    def test_all_page_spin_controls_use_completed_edit_policy(self):
        window = MainWindow()
        controls = window.findChildren(QAbstractSpinBox)
        self.assertGreater(len(controls), 30)
        self.assertTrue(all(not control.keyboardTracking() for control in controls))
        window.close()

    def test_generation_commits_classical_and_model_fields_without_focus_loss(self):
        project = ProjectData(factors=[FactorItem(name=f"X{i}", param1="-1", param2="1")
                                       for i in range(3)], responses=[ResponseItem(name="Y")])
        page = ConfigurationPage(project)
        type_number(page.f_repeat_spin, "2")
        type_number(page.f_seed_spin, "135")
        self.assertEqual(page.f_repeat_spin.value(), 1)
        plan = page._build_plan()
        self.assertEqual(plan.params["seed"], 135)
        self.assertEqual(plan.params["meta"]["replicates"], 2)
        editor = page.model_editors["ANN"]
        type_number(editor.epoch_spin, "1500")
        type_number(editor.lr_spin, "0.0125")
        self.assertEqual(editor.collect_config(commit=False)["model_params"]["epochs"], 500)
        config = editor.collect_config()
        self.assertEqual(config["model_params"]["epochs"], 1500)
        self.assertEqual(config["model_params"]["learning_rate"], .0125)
        page.close()

    def test_optimization_commits_before_checking_inputs(self):
        page = OptimizationPage(ProjectData())
        type_number(page.pop_spin, "120")
        type_number(page.k_design_spin, "4.25")
        self.assertEqual(page.pop_spin.value(), 80)
        page._check_inputs()
        self.assertEqual(page.pop_spin.value(), 120)
        self.assertEqual(page.k_design_spin.value(), 4.25)
        page.close()

    def test_dynamic_factor_bounds_and_point_evaluation_commit(self):
        project = ProjectData(factors=[FactorItem(name="X", param1="-2", param2="3")])
        context = {"_project": project, "models": {"Y": {}}}
        panel = WorkbenchDiagnostics()
        with patch("frontend.pages.workbench_diagnostics.oe.design_inputs", return_value=project.factors):
            panel.set_context(context, snapshot={"data": []})
        control = panel.controls["X"]
        self.assertEqual((control.minimum(), control.maximum(), control.decimals()), (-2, 3, 8))
        self.assertEqual(control.value(), .5)
        type_number(control, "-1.23456789")
        self.assertEqual(control.value(), .5)
        result = {"feasible": True, "responses": [], "note": "checked"}
        with patch("frontend.pages.workbench_diagnostics.analysis_service.evaluate_point",
                   return_value=result) as evaluate:
            panel.evaluate_point()
        self.assertEqual(evaluate.call_args.args[1], {"X": -1.23456789})
        self.assertEqual(panel.snapshot["point_evaluation"], result)
        panel.close()


if __name__ == "__main__":
    unittest.main()
