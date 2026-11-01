"""Inline, reusable model and experiment configuration components."""
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QComboBox, QAbstractSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal

from backend.engines.doe import factor_limits
from backend.services.design_service import MODEL_DESIGNS
from frontend.numeric_inputs import numeric_input, commit_numeric_inputs
from frontend.terminology import add_combo_item, name, tooltip


MODEL_TITLES = {
    "RSM": name("quadratic_response_surface"),
    "Kriging": name("kriging"),
    "SVR": name("svr"),
    "ANN": name("bpnn"),
}
MODEL_TERM_KEYS = {
    "RSM": "quadratic_response_surface", "Kriging": "kriging",
    "SVR": "svr", "ANN": "bpnn",
}
DESIGN_TERM_KEYS = {
    "CCD": "ccd", "BBD": "bbd",
    "Latin Hypercube (LHS)": "lhs", "最优 LHS": "maximin_lhs",
    "低差异序列 SOBOL": "sobol", "均匀网格抽样": "uniform_grid",
    "稀疏配点法": "low_dimensional_combination", "随机抽样": "random_sampling",
}


class ModelConfiguration(QWidget):
    """Shared inline DOE editor with model-specific parameter controls."""
    changed = pyqtSignal()

    def __init__(self, model_key, factors, parent=None, config=None):
        super().__init__(parent)
        self.model_key = model_key
        self.factors = list(factors)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.range_group = QGroupBox("因子与试验范围")
        bounds_layout = QVBoxLayout(self.range_group)
        self.bounds_table = QTableWidget(0, 3)
        self.bounds_table.setHorizontalHeaderLabels(["模型输入（单位）", "抽样下限", "抽样上限"])
        self.bounds_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bounds_table.verticalHeader().hide()
        self.bounds_table.horizontalHeader().geometriesChanged.connect(self._fit_bounds_table)
        self.bounds_table.verticalHeader().geometriesChanged.connect(self._fit_bounds_table)
        bounds_layout.addWidget(self.bounds_table)
        root.addWidget(self.range_group)
        self.set_factors(factors)
        group = QGroupBox("试验设计")
        layout = QVBoxLayout(group)
        row = QHBoxLayout()
        row.addWidget(QLabel("试验设计方法："))
        self.doe_method_combo = QComboBox()
        for design in MODEL_DESIGNS[model_key]:
            add_combo_item(self.doe_method_combo, DESIGN_TERM_KEYS[design], design)
        row.addWidget(self.doe_method_combo)
        self.sample_label = QLabel("基础样本点数：")
        row.addWidget(self.sample_label)
        self.sample_count_spin = numeric_input(int, 1, 20000, 50)
        row.addWidget(self.sample_count_spin)
        row.addStretch()
        layout.addLayout(row)
        self.structured = QWidget()
        row = QHBoxLayout(self.structured)
        row.setContentsMargins(0, 0, 0, 0)
        axis_label = QLabel("轴值 α：")
        axis_label.setToolTip(tooltip("ccd"))
        row.addWidget(axis_label)
        self.alpha_mode_combo = QComboBox()
        self.alpha_mode_combo.addItem("面心（α=1）", "face")
        self.alpha_mode_combo.addItem("可旋转", "rotatable")
        self.alpha_mode_combo.addItem("自定义 α", "custom")
        row.addWidget(self.alpha_mode_combo)
        self.alpha_spin = numeric_input(float, .5, 5, 1, decimals=3)
        row.addWidget(self.alpha_spin)
        row.addWidget(QLabel("中心点数量："))
        self.centers_spin = numeric_input(int, 0, 20, 3)
        row.addWidget(self.centers_spin)
        row.addStretch()
        layout.addWidget(self.structured)
        row = QHBoxLayout()
        row.addWidget(QLabel("整表重复次数："))
        self.repeats_spin = numeric_input(int, 1, 10, 1)
        row.addWidget(self.repeats_spin)
        row.addWidget(QLabel("试验顺序："))
        self.order_combo = QComboBox()
        self.order_combo.addItems(["随机", "保持相同"])
        row.addWidget(self.order_combo)
        row.addWidget(QLabel("随机种子："))
        self.seed_spin = numeric_input(int, 0, 99999, 456 if model_key == "RSM" else 123)
        row.addWidget(self.seed_spin)
        row.addStretch()
        layout.addLayout(row)
        root.addWidget(group)
        root.addWidget(self._build_model_group())
        self._load_config(config)
        self._on_design_changed()
        self.doe_method_combo.currentTextChanged.connect(self._on_design_changed)
        self.alpha_mode_combo.currentTextChanged.connect(self._on_design_changed)
        for control in self.findChildren(QComboBox):
            control.currentIndexChanged.connect(lambda *_args: self.changed.emit())
        for control in self.findChildren(QAbstractSpinBox):
            control.valueChanged.connect(lambda *_args: self.changed.emit())
        self.bounds_table.itemChanged.connect(lambda *_args: self.changed.emit())

    def set_factors(self, factors):
        old = {f.name: [self.bounds_table.item(i, col).text() for col in (1, 2)]
               for i, f in enumerate(self.factors) if i < self.bounds_table.rowCount()}
        defaults = getattr(self, "_range_defaults", {})
        self.factors = list(factors)
        self.bounds_table.blockSignals(True)
        self.bounds_table.setRowCount(len(self.factors))
        for i, factor in enumerate(self.factors):
            values = old.get(factor.name, factor_limits(factor))
            try:
                if tuple(map(float, values)) == defaults.get(factor.name):
                    values = factor_limits(factor)
            except ValueError:
                pass
            name = f"{factor.name}（{factor.unit}）" if factor.unit else factor.name
            self.bounds_table.setItem(i, 0, QTableWidgetItem(name))
            self.bounds_table.item(i, 0).setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            for col, value in enumerate(values, 1):
                self.bounds_table.setItem(i, col, QTableWidgetItem(str(value)))
        self.bounds_table.blockSignals(False)
        self._fit_bounds_table()
        self._range_defaults = {f.name: factor_limits(f) for f in self.factors}

    def _fit_bounds_table(self):
        height = (self.bounds_table.horizontalHeader().sizeHint().height()
                  + sum(self.bounds_table.rowHeight(i) for i in range(self.bounds_table.rowCount()))
                  + 2 * self.bounds_table.frameWidth())
        self.bounds_table.setFixedHeight(min(145, height))

    def _on_design_changed(self, *_args):
        design = self.doe_method_combo.currentData()
        structured = design in ("CCD", "BBD")
        limits = ["低水平", "高水平"] if structured else ["抽样下限", "抽样上限"]
        self.bounds_table.setHorizontalHeaderLabels(["模型输入（单位）", *limits])
        self.structured.setVisible(structured)
        self.sample_label.setVisible(not structured)
        self.sample_count_spin.setVisible(not structured)
        self.alpha_mode_combo.setEnabled(design == "CCD")
        self.alpha_spin.setEnabled(design == "CCD" and self.alpha_mode_combo.currentData() == "custom")

    def _build_model_group(self):
        group = QGroupBox("模型设置")
        layout = QVBoxLayout(group)
        key = self.model_key

        if key == "RSM":
            row = QHBoxLayout()
            row.addWidget(QLabel("模型形式："))
            self.rsm_model_combo = QComboBox()
            add_combo_item(self.rsm_model_combo, "full_quadratic_model", "full_quadratic")
            row.addWidget(self.rsm_model_combo)
            row.addStretch()
            layout.addLayout(row)
        elif key == "Kriging":
            row = QHBoxLayout()
            row.addWidget(QLabel("相关函数："))
            self.corr_combo = QComboBox()
            for term, value in (("gaussian_correlation", "Gaussian（高斯）"),
                                ("exponential_correlation", "指数 Exponential"),
                                ("matern_32_correlation", "Matern 3/2")):
                add_combo_item(self.corr_combo, term, value)
            row.addWidget(self.corr_combo)
            row.addSpacing(20)
            row.addWidget(QLabel("回归函数（趋势项）："))
            self.regress_combo = QComboBox()
            for term, value in (("ordinary_trend", "常数（Ordinary）"),
                                ("linear_trend", "一次趋势"),
                                ("quadratic_trend", "二次趋势")):
                add_combo_item(self.regress_combo, term, value)
            row.addWidget(self.regress_combo)
            row.addStretch()
            layout.addLayout(row)
        elif key == "SVR":
            row = QHBoxLayout()
            row.addWidget(QLabel("核函数："))
            self.kernel_combo = QComboBox()
            for term, value in (("rbf_kernel", "RBF 核"),
                                ("polynomial_kernel", "多项式核"),
                                ("sigmoid_kernel", "Sigmoid 核")):
                add_combo_item(self.kernel_combo, term, value)
            row.addWidget(self.kernel_combo)
            row.addSpacing(20)
            row.addWidget(QLabel("多项式次数："))
            self.poly_degree_spin = numeric_input(int, 1, 5, 3)
            self.poly_degree_spin.setEnabled(False)
            row.addWidget(self.poly_degree_spin)
            row.addStretch()
            layout.addLayout(row)
            self.kernel_combo.currentTextChanged.connect(
                lambda _t: self.poly_degree_spin.setEnabled(
                    self.kernel_combo.currentData() == "多项式核"))

            grid = QVBoxLayout()
            c_row = QHBoxLayout()
            c_row.addWidget(QLabel("惩罚系数 C 搜索范围："))
            self.c_min = numeric_input(float, 0.01, 100000.0, 0.1, decimals=3)
            self.c_max = numeric_input(float, 0.1, 1000000.0, 100.0, decimals=3)
            self.c_step = numeric_input(float, 0.01, 10000.0, 10.0, decimals=3)
            c_row.addWidget(self.c_min)
            c_row.addWidget(QLabel("~"))
            c_row.addWidget(self.c_max)
            c_row.addWidget(QLabel("搜索步长："))
            c_row.addWidget(self.c_step)
            c_row.addStretch()
            grid.addLayout(c_row)

            g_row = QHBoxLayout()
            g_row.addWidget(QLabel("核参数 g（γ）搜索范围："))
            self.g_min = numeric_input(float, 0.0001, 100.0, 0.01, decimals=4)
            self.g_max = numeric_input(float, 0.01, 10000.0, 10.0, decimals=3)
            self.g_step = numeric_input(float, 0.0001, 100.0, 1.0, decimals=4)
            g_row.addWidget(self.g_min)
            g_row.addWidget(QLabel("~"))
            g_row.addWidget(self.g_max)
            g_row.addWidget(QLabel("搜索步长："))
            g_row.addWidget(self.g_step)
            g_row.addStretch()
            grid.addLayout(g_row)
            layout.addLayout(grid)
            group.setToolTip("C 与 γ 按给定范围和步长网格寻优，ε-SVR 误差带取 0.05。"
                             "依赖加载、训练或预测失败时明确报错，不更换模型。")

        else:  # ANN
            row = QHBoxLayout()
            row.addWidget(QLabel("网络参数设置方法："))
            self.net_mode_combo = QComboBox()
            self.net_mode_combo.addItems(["手动设置", "自动寻优"])
            row.addWidget(self.net_mode_combo)
            row.addStretch()
            layout.addLayout(row)

            self.manual_widget = QWidget()
            manual_row = QHBoxLayout(self.manual_widget)
            manual_row.setContentsMargins(0, 0, 0, 0)
            manual_row.addWidget(QLabel("隐含层层数："))
            self.hidden_layers_spin = numeric_input(int, 1, 5, 1)
            manual_row.addWidget(self.hidden_layers_spin)
            manual_row.addSpacing(20)
            manual_row.addWidget(QLabel("隐含层节点数："))
            self.hidden_nodes_spin = numeric_input(int, 1, 500, 8)
            manual_row.addWidget(self.hidden_nodes_spin)
            manual_row.addStretch()
            layout.addWidget(self.manual_widget)

            self.auto_widget = QWidget()
            auto_row = QHBoxLayout(self.auto_widget)
            auto_row.setContentsMargins(0, 0, 0, 0)
            auto_row.addWidget(QLabel("隐含层节点搜索区间："))
            self.node_min_spin = numeric_input(int, 1, 200, 2)
            self.node_max_spin = numeric_input(int, 2, 500, 30)
            auto_row.addWidget(self.node_min_spin)
            auto_row.addWidget(QLabel("~"))
            auto_row.addWidget(self.node_max_spin)
            auto_row.addSpacing(15)
            auto_row.addWidget(QLabel("遍历步长："))
            self.node_step_spin = numeric_input(int, 1, 50, 2)
            auto_row.addWidget(self.node_step_spin)
            auto_row.addStretch()
            layout.addWidget(self.auto_widget)
            self.auto_widget.setVisible(False)

            row2 = QHBoxLayout()
            row2.addWidget(QLabel("激活函数："))
            self.act_combo = QComboBox()
            for term, value in (("logistic_sigmoid", "sigmoid"),
                                ("hyperbolic_tangent", "tanh"),
                                ("relu", "relu")):
                add_combo_item(self.act_combo, term, value)
            row2.addWidget(self.act_combo)
            row2.addSpacing(20)
            row2.addWidget(QLabel("学习率："))
            self.lr_spin = numeric_input(float, 0.0001, 1.0, 0.05, decimals=4)
            row2.addWidget(self.lr_spin)
            row2.addSpacing(20)
            row2.addWidget(QLabel("训练代数："))
            self.epoch_spin = numeric_input(int, 10, 20000, 500)
            row2.addWidget(self.epoch_spin)
            row2.addStretch()
            layout.addLayout(row2)
            self.net_mode_combo.currentTextChanged.connect(self._on_net_mode)
        return group

    def _on_net_mode(self, text):
        manual = text == "手动设置"
        self.manual_widget.setVisible(manual)
        self.auto_widget.setVisible(not manual)

    # ------------------------------------------------------------------ 数据
    def _load_config(self, config):
        """Restore saved settings without changing the caller's configuration."""
        if not config or config.get("model") != self.model_key:
            return

        def restore_combo(combo, value):
            if value is None:
                return
            index = combo.findData(value)
            if index < 0:
                index = combo.findText(str(value))
            if index < 0:
                index = next((i for i in range(combo.count())
                              if combo.itemText(i).startswith(str(value))), -1)
            if index >= 0:
                combo.setCurrentIndex(index)

        if "sample_count" in config:
            self.sample_count_spin.setValue(int(config["sample_count"]))
        restore_combo(self.doe_method_combo, config.get("doe_method"))
        bounds = config.get("bounds") or {}
        for row, factor in enumerate(self.factors):
            if factor.name in bounds:
                lo, hi = bounds[factor.name]
                self.bounds_table.item(row, 1).setText(str(lo))
                self.bounds_table.item(row, 2).setText(str(hi))

        self.seed_spin.setValue(config.get("seed", self.seed_spin.value()))
        self.repeats_spin.setValue(config.get("replicates", 1))
        self.order_combo.setCurrentIndex(0 if config.get("randomize", True) else 1)
        self.centers_spin.setValue(config.get("centers", 3))
        self.alpha_spin.setValue(config.get("alpha", 1))
        index = self.alpha_mode_combo.findData(config.get("alpha_mode", "face"))
        self.alpha_mode_combo.setCurrentIndex(max(index, 0))
        params = config.get("model_params", config)
        if self.model_key == "Kriging":
            restore_combo(self.corr_combo, params.get("correlation"))
            restore_combo(self.regress_combo, params.get("trend"))
        elif self.model_key == "SVR":
            restore_combo(self.kernel_combo, params.get("kernel"))
            for name in ("poly_degree", "c_min", "c_max", "c_step", "g_min", "g_max", "g_step"):
                if name in params:
                    control = self.poly_degree_spin if name == "poly_degree" else getattr(self, name)
                    control.setValue(params[name])
        elif self.model_key == "ANN":
            for name, control in (("hidden_layers", self.hidden_layers_spin),
                                  ("hidden_nodes", self.hidden_nodes_spin),
                                  ("learning_rate", self.lr_spin), ("epochs", self.epoch_spin)):
                if name in params:
                    control.setValue(params[name])
            restore_combo(self.act_combo, params.get("activation"))
            search = params.get("node_search")
            if search:
                for control, value in zip((self.node_min_spin, self.node_max_spin, self.node_step_spin), search):
                    control.setValue(value)
            restore_combo(self.net_mode_combo, params.get("net_mode") or
                          ("自动寻优" if search else "手动设置"))

    def _bounds(self):
        result = {}
        for r, f in enumerate(self.factors):
            try:
                result[f.name] = [float(self.bounds_table.item(r, col).text()) for col in (1, 2)]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"因子 {f.name} 的试验范围必须填写数字。") from exc
        return result

    def collect_config(self, commit=True):
        if commit:
            commit_numeric_inputs(self)
        model_cfg = {}
        if self.model_key == "Kriging":
            model_cfg = {
                "correlation": self.corr_combo.currentData(),
                "trend": self.regress_combo.currentData(),
            }
        elif self.model_key == "SVR":
            model_cfg = {
                "kernel": self.kernel_combo.currentData(),
                "poly_degree": self.poly_degree_spin.value(),
                "c_min": self.c_min.value(), "c_max": self.c_max.value(),
                "c_step": self.c_step.value(), "g_min": self.g_min.value(),
                "g_max": self.g_max.value(), "g_step": self.g_step.value(),
            }
        elif self.model_key == "ANN":
            node_search = None
            if self.net_mode_combo.currentText() == "自动寻优":
                node_search = [self.node_min_spin.value(), self.node_max_spin.value(),
                               self.node_step_spin.value()]
            model_cfg = {
                "hidden_layers": self.hidden_layers_spin.value(),
                "hidden_nodes": self.hidden_nodes_spin.value(),
                "activation": self.act_combo.currentData(),
                "learning_rate": self.lr_spin.value(),
                "epochs": self.epoch_spin.value(),
                "node_search": node_search,
                "net_mode": self.net_mode_combo.currentText(),
            }
        return {
            "model": self.model_key,
            "model_params": model_cfg,
            "sample_count": self.sample_count_spin.value(),
            "doe_method": self.doe_method_combo.currentData(),
            "bounds": self._bounds(),
            "alpha_mode": self.alpha_mode_combo.currentData(), "alpha": self.alpha_spin.value(),
            "centers": self.centers_spin.value(), "replicates": self.repeats_spin.value(),
            "seed": self.seed_spin.value(), "randomize": self.order_combo.currentIndex() == 0,
        }

