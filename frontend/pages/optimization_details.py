"""Read-only details for real optimized schemes and their variance/constraints."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QWidget, QScrollArea, QVBoxLayout, QHBoxLayout,
    QGroupBox, QPushButton, QComboBox, QProgressBar)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from backend.reporting.math_format import Math, number
from frontend.pages.result_overview import SummaryTable, label
from frontend.pages.result_summary import display, named
from frontend.pages.table_widgets import ContentColumnBalancer
from frontend.pages import optimization_plots

CONSTRAINT_TOOLTIP = '约束核验（Constraint Verification）\n余量为负表示违反约束。μ±kσ是稳健带，不是预测置信区间。'


def clear_layout(layout):
    while layout.count():
        widget = layout.takeAt(0).widget()
        widget.hide()
        widget.deleteLater()


def section(layout, title, explanation=''):
    group = QGroupBox(title)
    group.setToolTip(explanation)
    body = QVBoxLayout(group)
    layout.addWidget(group)
    return body


def share_indicator(share):
    cell = QWidget()
    row = QHBoxLayout(cell)
    row.setContentsMargins(6, 0, 6, 0)
    bar = QProgressBar()
    bar.setRange(0, 10000)
    bar.setValue(round(share*100))
    bar.setTextVisible(False)
    bar.setFixedHeight(8)
    bar.setStyleSheet('QProgressBar { margin:0; }')
    row.addWidget(bar, 1)
    row.addWidget(label(f'{share:.2f}%'))
    return cell


def constraint_rows(context, verification):
    responses = {r.name: r for r in context['_responses']}
    rows = []
    for row in verification['responses']:
        response = responses[row['响应']]
        margin = row['约束余量']
        if margin is not None:
            if response.feature == '望目':
                metric = Math('μ±kσ', r'\mu\pm k\sigma')
                actual = f"[{display(row['均值−kσ'])}, {display(row['均值+kσ'])}]"
                bound = f'[{response.lower}, {response.upper}]'
            else:
                small = response.feature == '望小'
                metric = Math('μ+kσ' if small else 'μ−kσ', r'\mu+k\sigma' if small else r'\mu-k\sigma')
                actual = row['均值+kσ' if small else '均值−kσ']
                bound = Math(('≤ ' if small else '≥ ')+response.robust_limit,
                             (r'\leq ' if small else r'\geq ')+number(float(response.robust_limit)))
            rows.append([response.name, metric, actual, bound, margin, '通过' if margin >= 0 else '违反', response.unit])
        if row['标准差上限'] is not None:
            margin = row['波动约束余量']
            rows.append([response.name, Math('标准差 σ', r'\sigma'), row['传播标准差'],
                         Math('≤ '+display(row['标准差上限']), r'\leq '+number(row['标准差上限'])),
                         margin, '通过' if margin >= 0 else '违反', response.unit])
    return rows


class SchemeDetail(QScrollArea):
    selection_requested = pyqtSignal(int)
    overview_requested = pyqtSignal()

    def __init__(self, title):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('resultsSurface')
        column = QVBoxLayout(content)
        head = QHBoxLayout()
        head.addWidget(label(title, 'heading'))
        head.addStretch()
        back = QPushButton('返回总览')
        back.clicked.connect(self.overview_requested.emit)
        head.addWidget(back)
        column.addLayout(head)
        row = QHBoxLayout()
        row.addWidget(label('当前查看'))
        self.selector = QComboBox()
        self.selector.currentIndexChanged.connect(self.selection_requested.emit)
        row.addWidget(self.selector)
        row.addStretch()
        column.addLayout(row)
        self.body = QVBoxLayout()
        self.body.setSpacing(16)
        column.addLayout(self.body)
        column.addStretch()
        self.setWidget(content)
        self.clear()

    def clear(self):
        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.setEnabled(False)
        self.selector.blockSignals(False)
        self.selector.setToolTip('尚无优化结果')
        clear_layout(self.body)
        self.tables = {}

    def set_schemes(self, records, index, default, recommended):
        self.selector.blockSignals(True)
        self.selector.clear()
        for i, record in enumerate(records):
            self.selector.addItem(record['id']+(' · 默认推荐' if i == default and recommended else ''))
        self.selector.setCurrentIndex(index)
        self.selector.setVisible(len(records) > 1)
        self.selector.setEnabled(len(records) > 1)
        self.selector.blockSignals(False)
        self.selector.setToolTip(records[index]['id']+'　'+ ' / '.join(f'{k}={display(v)}' for k,v in records[index]['x'].items()))
        clear_layout(self.body)
        self.tables = {}

    def table(self, key, title, headers, rows, explanation=''):
        body = section(self.body, title, explanation)
        table = SummaryTable(headers, rows)
        body.addWidget(table)
        self.tables[key] = table
        return table


class SchemeComparison(SchemeDetail):
    def __init__(self):
        super().__init__('方案对比')
        self.figure = Figure(figsize=(6, 3), dpi=100, layout='constrained')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(270)
        self.canvas.mpl_connect('pick_event', self._pick)

    def clear(self):
        if hasattr(self, 'canvas'):
            self.canvas.setParent(self.widget())
            self.canvas.hide()
        super().clear()

    def _pick(self, event):
        if event.artist.get_label() == '帕累托前沿' and len(event.ind):
            self.selection_requested.emit(int(event.ind[0]))

    def render(self, context, result, records, index, default):
        self.canvas.setParent(self.widget())
        self.canvas.hide()
        self.set_schemes(records, index, default, result['feasible_count'] > 0)
        inputs = {f.name: f for f in context['inputs']}
        objectives = [r for r in context['_responses'] if r.name in result['objective_names']]
        current = records[index]
        if result['mode'] == 'multi' and result['front']:
            body = section(self.body, '帕累托前沿', '帕累托前沿（Pareto Front）\n点击前沿点可查看相应方案；默认推荐保持不变。')
            body.addWidget(self.canvas)
            self.canvas.show()
            plot = dict(result)
            if len(objectives) == 1:
                name = objectives[0].name
                points = []
                for record in records:
                    row = next(r for r in record['verification']['responses'] if r['响应'] == name)
                    points.append([row['鲁棒均值'], row['传播标准差']])
                plot.update(front=[{'obj': p} for p in points], front_scatter=points,
                            best={'obj': points[default]}, viewed={'obj': points[index]},
                            plot_labels=(named(objectives[0])+' · 均值', named(objectives[0])+' · 标准差'))
            else:
                plot['viewed'] = result['front'][index]
            optimization_plots.pareto(self.figure, self.canvas, plot)
        headers = ['方案'] + [named(inputs[n]) for n in result['design_names']]
        for response in objectives:
            headers += [named(response)+' · 均值', named(response)+' · 标准差']
        rows = []
        for i, record in enumerate(records):
            values = {r['响应']: r for r in record['verification']['responses']}
            row = [record['id']+(' · 推荐' if i == default and result['feasible_count'] else '')]
            row += [record['x'][n] for n in result['design_names']]
            for response in objectives:
                row += [values[response.name]['鲁棒均值'], values[response.name]['传播标准差']]
            rows.append(row+['通过' if record['verification']['feasible'] else '违反', ''])
        table = self.table('schemes', '帕累托方案' if result['mode'] == 'multi' and result['front'] else '本次求解方案', headers+['约束', '操作'], rows)
        table.setMinimumHeight(80)
        table.setMaximumHeight(300)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for i in range(len(records)):
            button = QPushButton('当前查看' if i == index else '查看')
            button.clicked.connect(lambda checked=False, target=i: self.selection_requested.emit(target))
            table.setCellWidget(i, table.columnCount()-1, button)
        table.column_balancer = ContentColumnBalancer(table)
        self.table('factors', '当前方案 · 设计因子与输入扰动', ['因子', '设计取值', '输入标准差 σ', '单位'],
                   [[n, v, result['input_sigmas'][n], inputs[n].unit] for n,v in current['x'].items()])
        self.table('responses', '当前方案 · 响应结果', ['响应', '角色', '近似均值 μ', '标准差 σ', '单位'],
                   [[r['响应'],r['角色'],r['鲁棒均值'],r['传播标准差'],next(v.unit for v in context['_responses'] if v.name == r['响应'])] for r in current['verification']['responses']],
                   '响应结果（Response Results）\n均值与标准差基于局部二阶矩近似，包含模型残差方差。')

        rows = constraint_rows(context, current['verification'])
        if rows:
            table = self.table('constraints', '约束核验', ['响应','核验项','计算值','允许范围','余量','判定','单位'], rows,
                               CONSTRAINT_TOOLTIP)
            for i, row in enumerate(rows):
                table.item(i, 5).setForeground(QColor('#19704b' if row[5] == '通过' else '#ba3348'))
        else:
            section(self.body, '约束核验', CONSTRAINT_TOOLTIP).addWidget(label('本次未设置响应约束或标准差上限。'))


class VariabilityVerification(SchemeDetail):
    def __init__(self):
        super().__init__('波动核验')
        self.response = QComboBox()
        self.response.currentIndexChanged.connect(self._render_variance)

    def clear(self):
        if hasattr(self, 'response'):
            self.response.setParent(self.widget())
            self.response.hide()
        super().clear()
        self.variance = {}

    def render(self, context, result, records, index, default, variance):
        self.response.setParent(self.widget())
        self.response.hide()
        self.set_schemes(records, index, default, result['feasible_count'] > 0)
        self.variance, self.responses = variance, {r.name: r for r in context['_responses']}
        body = section(self.body, '局部方差贡献', '局部方差贡献（Local Variance Contribution）\n按当前查看方案分解方差，包含模型残差；独立输入、对角二阶近似，不代表全局重要性。')
        selected = self.response.currentData()
        self.response.blockSignals(True)
        self.response.clear()
        for name in variance:
            self.response.addItem(named(self.responses[name]), name)
        if selected in variance:
            self.response.setCurrentIndex(self.response.findData(selected))
        self.response.blockSignals(False)
        body.addWidget(self.response)
        self.response.show()
        self.total = label()
        body.addWidget(self.total)
        self.variance_body = QVBoxLayout()
        body.addLayout(self.variance_body)
        self._render_variance()

    def _render_variance(self, *_args):
        name = self.response.currentData()
        if name not in self.variance:
            return
        clear_layout(self.variance_body)
        rows = self.variance[name]
        unit = self.responses[name].unit
        self.total.setText('总方差：'+display(sum(r['variance'] for r in rows))+(f' {unit}²' if unit else ''))
        table = SummaryTable(['来源', f'方差（{unit}²）' if unit else '方差', '份额 %'],
                             [[r['name'],r['variance'],r['share']] for r in rows])
        for i, row in enumerate(rows):
            table.item(i, 2).setForeground(QColor(Qt.GlobalColor.transparent))
            if row['name'] == '模型残差':
                table.item(i, 0).setToolTip('模型残差（Model Residual）\n观测值与拟合值之间的残差方差估计，包含试验随机误差及可能的模型失拟。')
            table.setCellWidget(i, 2, share_indicator(row['share']))
        self.variance_body.addWidget(table)
        self.tables['variance'] = table
