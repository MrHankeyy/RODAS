"""Option panel builders for the design configuration page."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QGroupBox, QPushButton,
)
from frontend.numeric_inputs import numeric_input
from frontend.terminology import add_combo_item
from frontend.theme import content_zone
from frontend.pages.result_overview import label, SummaryTable
from frontend.pages.table_widgets import fill_records


def _publish(owner, controls):
    for name, widget in controls.items():
        setattr(owner, name, widget)


def taguchi(owner):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setSpacing(24)
    zone, body = content_zone()
    owner.t_settings_header = QHBoxLayout()
    owner.t_settings_header.addWidget(label('田口设计设置', 'sectionHeading'))
    owner.t_settings_header.addStretch()
    body.addLayout(owner.t_settings_header)
    layout.addWidget(zone)

    def group(title, explanation):
        box = QGroupBox(title)
        box.setToolTip(explanation)
        return box, QGridLayout(box)

    def field(grid, column, text, control):
        grid.addWidget(label(text), 0, column)
        grid.addWidget(control, 1, column)

    levels, noise_levels, inner, outer, order, snr = [QComboBox() for _ in range(6)]
    for control in (levels, noise_levels):
        control.addItems(['2 水平', '3 水平'])
    order.addItems(['随机', '保持相同'])
    snr.addItems(['按各响应目标特征自动', '望大（越大越好）', '望小（越小越好）', '望目（名义最好）'])
    repeats, seed = numeric_input(int, 1, 10, 1), numeric_input(int, 0, 99999, 789)
    inner_outer = QHBoxLayout()
    for title, explanation, controls in (
            ('内表设置 · 控制因子', '内表（Inner Array）\n安排可控制的设计因子水平。',
             [('因子水平数', levels), ('内表正交表', inner)]),
            ('外表设置 · 噪声因子', '外表（Outer Array）\n安排噪声因子水平，与内表交叉；无噪声因子时可不使用外表。',
             [('噪声因子水平数', noise_levels), ('外表正交表', outer)])):
        box, grid = group(title, explanation)
        for column, (text, control) in enumerate(controls):
            field(grid, column, text, control)
        inner_outer.addWidget(box, 1)
    body.addLayout(inner_outer)
    box, grid = group('重复与试验顺序', '整表重复（Full-design Replication）\n重复整个内表×外表组合；随机种子控制试验顺序，不控制观测随机误差。')
    for column, (text, control) in enumerate((('整表重复次数', repeats), ('试验顺序', order), ('随机种子', seed))):
        field(grid, column, text, control)
    order.currentIndexChanged.connect(lambda index: seed.setEnabled(index == 0))
    body.addWidget(box)
    box, grid = group('信噪比设置', '信噪比（Signal-to-Noise Ratio，S/N）\n按目标特征选择损失函数。望小型使用响应平方均值，信噪比越大表示均方损失越小。')
    field(grid, 0, '信噪比目标', snr)
    owner.t_response_label = label()
    owner.t_response_label.setToolTip('按当前业务响应和信噪比设置显示各响应的评价类型。')
    field(grid, 1, '当前响应的评价方式', owner.t_response_label)
    body.addWidget(box)
    owner.t_scale_zone, scale = content_zone()
    owner.t_scale_header = QHBoxLayout()
    owner.t_scale_header.addWidget(label('试验规模', 'sectionHeading'))
    scale.addLayout(owner.t_scale_header)
    layout.addWidget(owner.t_scale_zone)
    _publish(owner, dict(t_levels_combo=levels, t_inner_combo=inner, t_outer_combo=outer,
        t_noise_levels_combo=noise_levels, t_repeat_spin=repeats, t_order_combo=order,
        t_seed_spin=seed, t_snr_combo=snr))
    levels.currentTextChanged.connect(owner._on_taguchi_levels)
    noise_levels.currentTextChanged.connect(owner._on_taguchi_levels)
    return widget


class TaguchiPreview(QWidget):
    def __init__(self, project):
        super().__init__()
        self.project = project
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        self.counts = SummaryTable(['内表组数', '外表组数', '整表重复次数', '试验总次数'], [])
        self.observations = label()
        body.addWidget(self.counts)
        body.addWidget(self.observations)
        self.toggle = QPushButton('查看当前因子水平')
        self.toggle.setCheckable(True)
        body.addWidget(self.toggle)
        self.factors = SummaryTable(['类型', '因子', '实际水平', '单位'], [])
        self.factors.hide()
        self.toggle.toggled.connect(self.factors.setVisible)
        body.addWidget(self.factors)

    def set_plan(self, plan):
        meta = plan.params['meta'] if plan else {}
        fill_records(self.counts, [dict(zip(['内表组数','外表组数','整表重复次数','试验总次数'],
            [meta.get(k) for k in ('inner_runs','outer_runs','replicates','total_runs')]))])
        self.counts.setFixedHeight(self.counts.horizontalHeader().height()+self.counts.rowHeight(0)+4)
        self.observations.setText(f"{meta['inner_runs']} × {meta['outer_runs']} × {meta['replicates']}；每个内表组 {meta['outer_runs']*meta['replicates']} 次观测" if meta else '')
        units = {f.name:f.unit for f in self.project.factors}
        rows = [dict(类型=kind, 因子=name, 实际水平=' / '.join(f'{v:g}' for v in values), 单位=units[name])
                for kind, key in (('控制','factor_levels'),('噪声','noise_levels'))
                for name, values in meta.get(key, {}).items()]
        fill_records(self.factors, rows)
        self.factors.setFixedHeight(self.factors.horizontalHeader().height()+sum(self.factors.rowHeight(i) for i in range(len(rows)))+4)
