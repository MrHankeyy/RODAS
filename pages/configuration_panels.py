"""Option panel builders for the design configuration page."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QSpinBox, QDoubleSpinBox,
)


def _publish(owner, controls):
    for name, widget in controls.items():
        setattr(owner, name, widget)


def screening(owner):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    row = QHBoxLayout()
    row.addWidget(QLabel("设计族："))
    kind = QComboBox()
    kind.addItems([
        "全因子 2^k（小因子数）", "部分析因 1/2 分数",
        "部分析因 1/4 分数", "Plackett-Burman（12/20 次）"])
    row.addWidget(kind)
    row.addSpacing(24)
    row.addWidget(QLabel("报告重点主效应数："))
    top_n = QSpinBox()
    top_n.setRange(1, 10)
    top_n.setValue(5)
    row.addWidget(top_n)
    row.addStretch()
    layout.addLayout(row)

    row = QHBoxLayout()
    row.addWidget(QLabel("中心点补充数："))
    centers = QSpinBox()
    centers.setRange(0, 10)
    centers.setValue(2)
    row.addWidget(centers)
    row.addSpacing(24)
    row.addWidget(QLabel("整表重复次数："))
    repeats = QSpinBox()
    repeats.setRange(1, 5)
    repeats.setValue(1)
    row.addWidget(repeats)
    row.addSpacing(24)
    row.addWidget(QLabel("试验顺序："))
    order = QComboBox()
    order.addItems(["随机", "保持相同"])
    row.addWidget(order)
    row.addSpacing(24)
    row.addWidget(QLabel("随机种子："))
    seed = QSpinBox()
    seed.setRange(0, 99999)
    seed.setValue(123)
    row.addWidget(seed)
    row.addStretch()
    layout.addLayout(row)
    hint = QLabel("中心点用于检验曲率并估计纯误差；PB 设计主效应与双因子交互存在部分混杂。")
    hint.setStyleSheet("color:#666;")
    layout.addWidget(hint)
    _publish(owner, {
        "screen_kind_combo": kind, "f_topn_spin": top_n,
        "f_center_spin": centers, "f_repeat_spin": repeats,
        "f_order_combo": order, "f_seed_spin": seed,
        "screen_center_hint": hint})
    return widget


def response_surface(owner):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    row = QHBoxLayout()
    row.addWidget(QLabel("曲面设计类型："))
    design_type = QComboBox()
    design_type.addItems(["中心复合设计 (CCD)", "Box-Behnken 设计 (BBD)"])
    row.addWidget(design_type)
    row.addSpacing(24)
    row.addWidget(QLabel("CCD 轴值（α）："))
    alpha_mode = QComboBox()
    alpha_mode.addItems([
        "可旋转（α=2^(k/4)，推荐）", "位于表面（面心，α=1）", "用户指定 α"])
    row.addWidget(alpha_mode)
    alpha = QDoubleSpinBox()
    alpha.setRange(0.5, 5.0)
    alpha.setDecimals(3)
    alpha.setValue(1.414)
    alpha.setEnabled(False)
    row.addWidget(alpha)
    row.addStretch()
    layout.addLayout(row)

    row = QHBoxLayout()
    row.addWidget(QLabel("中心点数量："))
    centers = QSpinBox()
    centers.setRange(0, 20)
    centers.setValue(3)
    row.addWidget(centers)
    row.addSpacing(24)
    row.addWidget(QLabel("整表重复次数："))
    repeats = QSpinBox()
    repeats.setRange(1, 5)
    repeats.setValue(1)
    row.addWidget(repeats)
    row.addSpacing(24)
    row.addWidget(QLabel("试验顺序："))
    order = QComboBox()
    order.addItems(["随机", "保持相同"])
    row.addWidget(order)
    row.addSpacing(24)
    row.addWidget(QLabel("随机种子："))
    seed = QSpinBox()
    seed.setRange(0, 99999)
    seed.setValue(456)
    row.addWidget(seed)
    row.addStretch()
    layout.addLayout(row)
    hint = QLabel(
        "CCD＝立方点＋轴点＋中心点；可旋转 α 使预测方差只依赖到中心的距离。"
        "BBD 每个因子仅 3 个水平、不含立方体顶点。")
    hint.setStyleSheet("color:#666;")
    layout.addWidget(hint)
    _publish(owner, {
        "rsm_type_combo": design_type, "rsm_alpha_combo": alpha_mode,
        "rsm_alpha_spin": alpha, "rsm_center_spin": centers,
        "rsm_repeat_spin": repeats, "rsm_order_combo": order,
        "rsm_seed_spin": seed, "rsm_hint": hint})
    design_type.currentTextChanged.connect(owner._on_rsm_type)
    alpha_mode.currentTextChanged.connect(owner._on_alpha_mode)
    return widget


def taguchi(owner):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    row = QHBoxLayout()
    row.addWidget(QLabel("因子水平数："))
    levels = QComboBox()
    levels.addItems(["2 水平", "3 水平"])
    row.addWidget(levels)
    row.addSpacing(20)
    row.addWidget(QLabel("内表（控制因子）："))
    inner = QComboBox()
    inner.addItems([
        "自动推荐", "L4 (2^3)", "L8 (2^7)", "L9 (3^4)",
        "L12 (2^11)", "L16 (2^15)", "L27 (3^13)"])
    row.addWidget(inner)
    row.addSpacing(20)
    row.addWidget(QLabel("外表（噪声因子）："))
    outer = QComboBox()
    outer.addItems([
        "无（仅内表）", "自动推荐", "L4 (2^3)", "L8 (2^7)",
        "L9 (3^4)", "L12 (2^11)", "L16 (2^15)"])
    row.addWidget(outer)
    row.addStretch()
    layout.addLayout(row)

    options = QHBoxLayout()
    options.addWidget(QLabel("噪声因子水平数："))
    noise_levels = QComboBox()
    noise_levels.addItems(["2 水平", "3 水平"])
    options.addWidget(noise_levels)
    options.addWidget(QLabel("整表重复次数："))
    repeats = QSpinBox()
    repeats.setRange(1, 10)
    options.addWidget(repeats)
    options.addWidget(QLabel("试验顺序："))
    order = QComboBox()
    order.addItems(["随机", "保持相同"])
    options.addWidget(order)
    layout.addLayout(options)

    row = QHBoxLayout()
    row.addWidget(QLabel("信噪比目标："))
    snr = QComboBox()
    snr.addItems([
        "按各响应目标特征自动", "望大（越大越好）",
        "望小（越小越好）", "望目（名义最好）"])
    row.addWidget(snr)
    row.addSpacing(24)
    row.addWidget(QLabel("随机种子："))
    seed = QSpinBox()
    seed.setRange(0, 99999)
    seed.setValue(789)
    row.addWidget(seed)
    row.addStretch()
    layout.addLayout(row)
    hint = QLabel(
        "内表安排控制因子（设计因子）、外表安排噪声因子（环境因子）；"
        "完整试验＝内表×外表叉积。环境因子列将自动填充外表水平。")
    hint.setStyleSheet("color:#666;")
    layout.addWidget(hint)
    _publish(owner, {
        "t_levels_combo": levels, "t_inner_combo": inner,
        "t_outer_combo": outer, "t_noise_levels_combo": noise_levels,
        "t_repeat_spin": repeats, "t_order_combo": order,
        "t_snr_combo": snr, "t_seed_spin": seed, "t_hint": hint})
    levels.currentTextChanged.connect(owner._on_taguchi_levels)
    noise_levels.currentTextChanged.connect(owner._on_taguchi_levels)
    return widget


def surrogate(owner):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    info = QLabel()
    layout.addWidget(info)
    row = QHBoxLayout()
    button = QPushButton("打开建模设置窗口…")
    button.clicked.connect(owner._open_surrogate_dialog)
    row.addWidget(button)
    status = QLabel("尚未设置模型参数")
    status.setStyleSheet("color:#b45309;")
    row.addWidget(status)
    row.addStretch()
    layout.addLayout(row)
    hint = QLabel(
        "设置窗口包含两部分：① 试验设计（变量维度/上下界、样本点数、抽样方法）；"
        "② 模型参数（相关/回归函数、核函数与 C/g 搜索、网络结构与寻优等）。")
    hint.setStyleSheet("color:#666;")
    layout.addWidget(hint)
    _publish(owner, {
        "surrogate_info_label": info, "surrogate_open_btn": button,
        "surrogate_status": status, "surrogate_hint": hint})
    return widget
