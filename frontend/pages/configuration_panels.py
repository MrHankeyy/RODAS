"""Option panel builders for the design configuration page."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox,
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
