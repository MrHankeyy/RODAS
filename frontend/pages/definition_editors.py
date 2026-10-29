"""Shared compact tables and conditional fields for business definitions."""
import math
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLineEdit, QComboBox, QCheckBox, QAbstractItemView,
)
from backend.domain.models import FactorItem, ResponseItem
from backend.core.factors import factor_limits
from frontend.numeric_inputs import numeric_text_input
from frontend.pages.table_widgets import BalancedColumnsTable


def stacked(*widgets):
    stack = QStackedWidget()
    for widget in widgets:
        stack.addWidget(widget)
    return stack


def field_row(*definitions):
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(6, 0, 6, 0)
    layout.setSpacing(6)
    for label, control in definitions:
        label = QLabel(label) if isinstance(label, str) else label
        label.setProperty("role", "muted")
        layout.addWidget(label)
        layout.addWidget(control, 1)
    return widget


def centered(control):
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(control, alignment=Qt.AlignmentFlag.AlignCenter)
    return widget


def number(control, label):
    try:
        value = float(control.text().strip())
        if math.isfinite(value):
            return value
    except ValueError:
        pass
    raise ValueError(f"{label}：请填写有限数字。")


class DefinitionTable(QWidget):
    changed = pyqtSignal()

    def __init__(self, title, factory, headers, minimum_widths):
        super().__init__()
        self.factory, self.editors = factory, []
        self.add_btn = QPushButton("+  新增" + title)
        self.add_btn.clicked.connect(lambda: self.add())
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 12, 10, 10)
        head = QHBoxLayout()
        head.addWidget(QLabel(title))
        head.addStretch()
        head.addWidget(self.add_btn)
        root.addLayout(head)
        self.table = BalancedColumnsTable(minimum_widths, fixed_columns=(len(headers)-2, len(headers)-1))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

    def add(self, item=None):
        editor = self.factory(item)
        editor.setParent(self)
        editor.hide()
        self.editors.append(editor)
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, cell in enumerate(editor.cells):
            self.table.setCellWidget(row, column, cell)
            for control in (cell, *cell.findChildren(QWidget)):
                if isinstance(control, QLineEdit):
                    control.textChanged.connect(self.changed)
                elif isinstance(control, QComboBox):
                    control.currentTextChanged.connect(self.changed)
                elif isinstance(control, QCheckBox):
                    control.toggled.connect(self.changed)
        editor.delete_btn = QPushButton("删除")
        editor.delete_btn.clicked.connect(lambda checked=False, e=editor: self.remove(e))
        self.table.setCellWidget(row, self.table.columnCount()-1, editor.delete_btn)
        editor.changed.connect(self.changed)
        self.set_current_index(row)
        self.changed.emit()
        return editor

    def set_current_index(self, index):
        self.table.setCurrentCell(index, 0)

    def remove(self, editor):
        row = self.editors.index(editor)
        self.editors.pop(row)
        self.table.removeRow(row)
        editor.deleteLater()
        self.changed.emit()

    def clear(self):
        for editor in list(self.editors):
            self.remove(editor)


class FactorEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, source, item=None):
        super().__init__()
        self.source = source
        item = item or FactorItem(source=source)
        self.name, self.unit = QLineEdit(item.name), QLineEdit(item.unit)
        design = source == "设计"
        separate = bool(item.nominal_lower or item.nominal_upper)
        if design:
            self.lower = numeric_text_input(item.nominal_lower)
            self.upper = numeric_text_input(item.nominal_upper)
            if not separate and item.name:
                lo, hi = factor_limits(item)
                self.lower.setText(str(lo))
                self.upper.setText(str(hi))
        p1, p2 = item.param1, item.param2
        if not design and separate:
            center = (float(item.nominal_lower) + float(item.nominal_upper)) / 2
            p1 = repr(center + float(p1))
            if item.uncertainty == "区间":
                p2 = repr(center + float(p2))
        defined = separate or not design
        self.delta_lower = numeric_text_input(p1 if defined and item.uncertainty == "区间" else "")
        self.delta_upper = numeric_text_input(p2 if defined and item.uncertainty == "区间" else "")
        self.mean = numeric_text_input(p1 if defined and item.uncertainty == "概率" else "0")
        self.stddev = numeric_text_input()
        if item.uncertainty == "概率" and item.param2:
            self.stddev.setText(format(math.sqrt(float(item.param2)), '.15g'))
        self.stddev_original = (self.stddev.text(), item.param2)
        self.distribution = QComboBox()
        self.distribution.addItems(["正态分布", "均匀分布"])
        self.distribution.setCurrentText(item.distribution)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["区间", "概率"])
        self.uniform_lower, self.uniform_upper = numeric_text_input(), numeric_text_input()
        if item.uncertainty == "概率" and item.distribution == "均匀分布":
            try:
                mean, variance = float(self.mean.text()), float(item.param2)
                half_width = math.sqrt(variance) * math.sqrt(3)
                self.uniform_lower.setText(format(mean - half_width, '.15g'))
                self.uniform_upper.setText(format(mean + half_width, '.15g'))
            except (ValueError, OverflowError):
                pass
        self.uniform_original = (self.uniform_lower.text(), self.uniform_upper.text(),
                                 self.mean.text(), item.param2)
        no_distribution = QComboBox()
        no_distribution.addItem("无")
        no_distribution.setEnabled(False)
        self.distribution_cell = stacked(no_distribution, self.distribution)
        self.parameters = stacked(field_row(("下界", self.delta_lower), ("上界", self.delta_upper)),
                                  field_row(("均值", self.mean), ("标准差", self.stddev)),
                                  field_row(("下界", self.uniform_lower), ("上界", self.uniform_upper)))
        self.cells = (self.name,) + ((self.lower, self.upper) if design else ()) + (
            self.type_combo, self.distribution_cell, self.parameters, self.unit)
        self.type_combo.currentIndexChanged.connect(self.set_mode)
        self.distribution.currentTextChanged.connect(self.update_inline_parameters)
        self.set_mode(1 if item.uncertainty == "概率" else 0)
        self.unit.textChanged.connect(self.update_units)
        self.update_units()

    def update_units(self):
        unit = self.unit.text().strip()
        design = self.source == "设计"
        prefix = "不确定性偏差" if design else "环境实际取值"
        if design:
            self.lower.setToolTip("名义设计下限" + ("（" + unit + "）" if unit else ""))
            self.upper.setToolTip("名义设计上限" + ("（" + unit + "）" if unit else ""))
        for control, label in ((self.delta_lower, prefix + "下界"), (self.delta_upper, prefix + "上界"),
                               (self.mean, prefix + "均值"), (self.uniform_lower, "均匀分布" + prefix + "下界"),
                               (self.uniform_upper, "均匀分布" + prefix + "上界")):
            control.setToolTip(label + ("（" + unit + "）" if unit else ""))
        self.stddev.setToolTip(prefix + "标准差" + ("（" + unit + "）" if unit else ""))

    def update_inline_parameters(self):
        probability = self.type_combo.currentIndex() == 1
        self.parameters.setCurrentIndex(2 if probability and self.distribution.currentText() == "均匀分布"
                                        else int(probability))
        self.changed.emit()

    def set_mode(self, index):
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentIndex(index)
        self.type_combo.blockSignals(False)
        self.distribution_cell.setCurrentIndex(index)
        self.update_inline_parameters()

    def collect(self):
        name = self.name.text().strip()
        if not name:
            raise ValueError("请填写因子名称。")
        design = self.source == "设计"
        if design:
            lower, upper = number(self.lower, name + "名义下限"), number(self.upper, name + "名义上限")
            if lower >= upper:
                raise ValueError(f"{name}：名义下限须小于名义上限。")
        parameter = "偏差" if design else "环境取值"
        probability = self.parameters.currentIndex() != 0
        first, second = (self.mean, self.stddev) if probability else (self.delta_lower, self.delta_upper)
        uniform_bounds = self.parameters.currentIndex() == 2
        if uniform_bounds:
            first, second = self.uniform_lower, self.uniform_upper
        p1, p2 = number(first, name + parameter + "参数"), number(second, name + parameter + "参数")
        if probability and not uniform_bounds and p2 < 0:
            raise ValueError(f"{name}：{parameter}标准差不能为负数。")
        if (not probability or uniform_bounds) and p1 > p2:
            raise ValueError(f"{name}：{parameter}下界不能大于上界。")
        param1, param2 = first.text().strip(), second.text().strip()
        if probability and not uniform_bounds:
            variance = p2 * p2
            if not math.isfinite(variance):
                raise ValueError(f"{name}：标准差过大，无法计算有限方差。")
            param2 = self.stddev_original[1] if param2 == self.stddev_original[0] else repr(variance)
        if uniform_bounds:
            mean, sigma = p1 / 2 + p2 / 2, (p2 - p1) / math.sqrt(12)
            variance = sigma * sigma
            if not math.isfinite(variance):
                raise ValueError(f"{name}：均匀分布{parameter}范围过大，无法换算有限方差。")
            # Task files and propagation retain their existing mean/variance convention.
            param1, param2 = (self.uniform_original[2:] if (param1, param2) == self.uniform_original[:2]
                              else (repr(mean), repr(variance)))
        return FactorItem(name=name, source=self.source, unit=self.unit.text().strip(),
                          nominal_lower=self.lower.text().strip() if design else "",
                          nominal_upper=self.upper.text().strip() if design else "",
                          uncertainty="概率" if probability else "区间",
                          distribution=self.distribution.currentText() if probability else "无",
                          param1=param1, param2=param2)


class FactorTable(DefinitionTable):
    def __init__(self, source):
        design = source == "设计"
        headers = ["名称"] + (["名义下限", "名义上限"] if design else []) + [
            "不确定类型", "分布类型", "不确定性参数", "单位", "操作"]
        widths = (70, 80, 80, 90, 110, 250, 60, 64) if design else (100, 90, 110, 250, 60, 64)
        super().__init__(source + "因子", lambda item: FactorEditor(source, item),
                         headers, widths)
        if design:
            self.relation = QLabel("实际取值 = 名义设计值 + 不确定性偏差 Δ")
            self.relation.setProperty("role", "muted")
            self.layout().addWidget(self.relation)


class ResponseEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, item=None):
        super().__init__()
        item = item or ResponseItem(kind="目标")
        self.name, self.unit = QLineEdit(item.name), QLineEdit(item.unit)
        self.objective, self.constraint = QCheckBox(), QCheckBox()
        self.objective.setToolTip("作为优化目标")
        self.constraint.setToolTip("作为约束响应")
        self.objective.setChecked("目标" in item.kind)
        self.constraint.setChecked("约束" in item.kind)
        self.feature = QComboBox()
        self.feature.addItems(["望大", "望小", "望目"])
        self.feature.setCurrentText(item.feature)
        self.limit = numeric_text_input(item.robust_limit)
        self.lower, self.upper = numeric_text_input(item.lower), numeric_text_input(item.upper)
        self.limit_label = QLabel()
        self.limits = stacked(field_row((self.limit_label, self.limit)),
                              field_row(("下限", self.lower), ("上限", self.upper)))
        self.cells = (self.name, centered(self.objective), centered(self.constraint), self.feature,
                      self.limits, self.unit)
        self.feature.currentTextChanged.connect(self.update_feature)
        self.update_feature()

    def update_feature(self):
        feature = self.feature.currentText()
        self.limits.setCurrentIndex(1 if feature == "望目" else 0)
        self.limit_label.setText("下限" if feature == "望大" else "上限")
        self.limit.setToolTip("稳定要求" + self.limit_label.text())

    def collect(self):
        name = self.name.text().strip()
        if not name:
            raise ValueError("请填写响应名称。")
        if not self.objective.isChecked() and not self.constraint.isChecked():
            raise ValueError(f"{name}：请勾选目标或约束。")
        feature = self.feature.currentText()
        if feature == "望目":
            if number(self.lower, name + "下限") >= number(self.upper, name + "上限"):
                raise ValueError(f"{name}：稳定要求下限须小于上限。")
        elif self.limit.text().strip() or self.constraint.isChecked():
            number(self.limit, name + "稳定要求")
        kind = "+".join(text for text, control in (("目标", self.objective), ("约束", self.constraint)) if control.isChecked())
        return ResponseItem(name=name, unit=self.unit.text().strip(), kind=kind, feature=feature,
                            lower=self.lower.text().strip() if feature == "望目" else "",
                            upper=self.upper.text().strip() if feature == "望目" else "",
                            robust_limit=self.limit.text().strip() if feature != "望目" else "")


class ResponseTable(DefinitionTable):
    def __init__(self):
        super().__init__("响应", ResponseEditor,
                         ["名称", "目标响应", "约束响应", "目标特征", "稳定性阈值", "单位", "操作"],
                         (110, 80, 80, 100, 250, 60, 64))
