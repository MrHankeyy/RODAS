"""Shared numeric editors: commit typed values on Enter or focus loss."""
from PyQt6.QtCore import QLocale
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox, QSpinBox, QLineEdit


class DecimalInput(QDoubleSpinBox):
    """Manual decimal entry without button, keyboard or wheel stepping."""

    def stepEnabled(self):
        return QAbstractSpinBox.StepEnabledFlag.StepNone

    def stepBy(self, steps):
        pass

    def wheelEvent(self, event):
        event.ignore()


def numeric_input(kind, minimum, maximum, value, *, decimals=2, step=1):
    """Create an int/float editor with native validation and value signals."""
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
    """Flush pending edits before an action reads its numeric parameters."""
    for control in parent.findChildren(QAbstractSpinBox):
        control.interpretText()


def numeric_text_input(value=""):
    """Optional/scientific decimal draft, validated when the definition is saved."""
    control = QLineEdit(str(value))
    validator = QDoubleValidator(control)
    validator.setLocale(QLocale.c())
    validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
    control.setValidator(validator)
    return control
