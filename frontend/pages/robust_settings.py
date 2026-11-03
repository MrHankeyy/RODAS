"""Grouped robust-optimization settings; explanations live in hover text."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QGroupBox, QGridLayout, QHBoxLayout, QVBoxLayout,
    QLabel, QComboBox, QTableWidget, QHeaderView,
)
from frontend.numeric_inputs import numeric_input
from frontend.terminology import add_combo_item, apply, tooltip


def build_settings(owner, layout):
    def group(title):
        box = QGroupBox(title)
        column = QVBoxLayout(box)
        column.setContentsMargins(6, 8, 6, 8)
        column.setSpacing(10)
        layout.addWidget(box)
        return box, column

    def field(title, control, english, explanation):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        text = f"{title}（{english}）\n{explanation}"
        caption = QLabel(title + "：")
        caption.setToolTip(text)
        control.setToolTip(text)
        control.setAccessibleDescription(text)
        control.setMinimumWidth(92)
        control.setMaximumWidth(150)
        row.addWidget(caption)
        row.addWidget(control)
        row.addStretch()
        return widget

    owner.strategy_group, strategy = group("优化策略")
    row = QHBoxLayout()
    row.addWidget(apply(QLabel(), "robust_strategy"))
    owner.robust_mode_combo = QComboBox()
    for term, value in (("multiobjective_nsga2", "multi"),
                        ("constrained_optimization", "constraint"),
                        ("weighted_single_objective", "weighted")):
        add_combo_item(owner.robust_mode_combo, term, value)
    row.addWidget(owner.robust_mode_combo)
    row.addStretch()
    strategy.addLayout(row)
    owner.weight_spin = numeric_input(float, 0, 1, .5)
    owner.weight_fields = field("目标损失权重 λ", owner.weight_spin, "Target Loss Weight",
                               "将归一化目标损失与波动加权求和；波动权重为 1−λ。")
    owner.variability_weight = QLabel()
    owner.variability_weight.setToolTip(tooltip("variability_weight") + "\n波动权重等于 1−λ。")
    owner.weight_fields.layout().insertWidget(2, owner.variability_weight)
    owner.weight_spin.valueChanged.connect(
        lambda value: owner.variability_weight.setText(f"波动权重：{1-value:.2f}"))
    owner.variability_weight.setText("波动权重：0.50")
    strategy.addWidget(owner.weight_fields)
    owner.sigma_limits_group = QGroupBox("响应波动上限")
    owner.sigma_limits_group.setToolTip(
        "响应波动上限（Response Variability Limit）\n为每个目标响应设置标准差上限；"
        "满足波动限制后继续优化目标表现。标准差由输入不确定性传播和模型残差共同估计。")
    limits_layout = QVBoxLayout(owner.sigma_limits_group)
    limits_layout.setContentsMargins(4, 6, 4, 4)
    owner.sigma_limits_table = QTableWidget(0, 3)
    owner.sigma_limits_table.setHorizontalHeaderLabels(["目标响应", "标准差上限", "单位"])
    owner.sigma_limits_table.verticalHeader().hide()
    header = owner.sigma_limits_table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    owner.sigma_limits_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    owner.sigma_limits_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    owner.sigma_limits_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    owner.sigma_limits_table.horizontalHeaderItem(1).setToolTip(
        "标准差上限（Standard Deviation Limit）\n填写大于零的数值，单位同响应；此值限制波动程度。")
    owner.sigma_limit_inputs = {}
    owner.sigma_limits_group.layout().addWidget(owner.sigma_limits_table)
    strategy.addWidget(owner.sigma_limits_group)

    owner._update_uncertainty_tooltip()

    owner.genetic_group, genetic = group("遗传算法设置")
    owner.genetic_group.setToolTip(
        "遗传算法设置（Genetic Algorithm Settings，GA）\n采用非支配排序遗传算法（NSGA-II）、"
        "二元锦标赛选择、模拟二进制交叉和多项式变异。")
    owner.pop_spin = numeric_input(int, 20, 300, 80)
    owner.gen_spin = numeric_input(int, 30, 1000, 160)
    owner.seed_spin = numeric_input(int, 0, 2147483647, 7)
    owner.crossover_spin = numeric_input(float, 0, 1, .5, decimals=3)
    owner.mutation_mode_combo = QComboBox()
    owner.mutation_mode_combo.addItem("自动（1/设计因子数）", "auto")
    owner.mutation_mode_combo.addItem("手动设置", "manual")
    owner.mutation_spin = numeric_input(float, 0, 1, .5, decimals=6)
    owner.eta_c_spin = numeric_input(float, .01, 1000, 15)
    owner.eta_m_spin = numeric_input(float, .01, 1000, 20)
    fields = [
        ("种群数", owner.pop_spin, "Population Size", "每一代保留的候选方案数量。"),
        ("代数", owner.gen_spin, "Number of Generations", "遗传算法执行的迭代代数。"),
        ("随机种子", owner.seed_spin, "Random Seed", "相同输入与参数使用相同种子可复现计算。"),
        ("逐变量交叉概率", owner.crossover_spin, "Per-Variable Crossover Probability", "每对父代中，各设计变量参与模拟二进制交叉的概率。"),
        ("变异概率设置", owner.mutation_mode_combo, "Mutation Probability Setting", "自动时，每个变量的变异概率为 1÷参与优化的设计因子数；也可手动指定。"),
        ("逐变量变异概率", owner.mutation_spin, "Per-Variable Mutation Probability", "每个设计变量发生多项式变异的概率；自动时显示当前计算值。"),
        ("交叉分布指数", owner.eta_c_spin, "Crossover Distribution Index", "控制交叉产生的后代分散程度，数值越大通常越靠近父代。"),
        ("变异分布指数", owner.eta_m_spin, "Mutation Distribution Index", "控制变异幅度，数值越大通常越偏向小幅变异。"),
    ]
    grid = QGridLayout()
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(12)
    for index, args in enumerate(fields):
        grid.addWidget(field(*args), index // 2, index % 2)
    owner.mutation_mode_combo.setMaximumWidth(190)
    genetic.addLayout(grid)
    owner.mutation_mode_combo.currentIndexChanged.connect(owner._update_mutation_probability)
    owner._update_mutation_probability()
