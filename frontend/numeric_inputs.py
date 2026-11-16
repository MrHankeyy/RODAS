
from PyQt6.QtCore import QLocale
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox, QLineEdit, QSpinBox


class DecimalInput(QDoubleSpinBox):

    def stepEnabled(self):
        return QAbstractSpinBox.StepEnabledFlag.StepNone

    def stepBy(self, steps):
        pass

    def wheelEvent(self, event):
        event.ignore()


def numeric_input(kind, minimum, maximum, value, *, decimals=2, step=1):
    control = QSpinBox() if kind is int else DecimalInput()
    if kind is float:
        control.setDecimals(decimals)
        control.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    else:
        control.setSingleStep(step)
    control.setKeyboardTracking(False)
    control.setRange(minimum, maximum)
    control.setValue(value)
    return control


def commit_numeric_inputs(parent):
    for control in parent.findChildren(QAbstractSpinBox):
        control.interpretText()


def numeric_text_input(value=""):
    control = QLineEdit(str(value))
    validator = QDoubleValidator(control)
    validator.setLocale(QLocale.c())
    validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
    control.setValidator(validator)
    return control
