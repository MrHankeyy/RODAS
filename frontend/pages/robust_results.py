"""Optimization overview coordinated with two read-only detail pages."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton
from backend.services import analysis_service
from frontend.pages.result_overview import SummaryTable, label
from frontend.pages.optimization_details import (
    SchemeComparison, VariabilityVerification, clear_layout, share_indicator)


class RobustResults(QWidget):
    detail_requested = pyqtSignal(str)
    selection_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('contentZone')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 16, 16, 16)
        column.setSpacing(14)
        header = QHBoxLayout()
        self.heading = label('鲁棒优化结果总览', 'sectionHeading')
        header.addWidget(self.heading)
        column.addLayout(header)
        cards = QHBoxLayout()
        self.groups, self.bodies, self.buttons = {}, {}, {}
        for key, title in (('comparison', '方案对比'), ('verification', '波动核验')):
            group = QGroupBox(title)
            body = QVBoxLayout(group)
            content = QVBoxLayout()
            body.addLayout(content)
            body.addStretch()
            button = QPushButton('查看详情 →')
            button.clicked.connect(lambda checked=False, target=key: self._open_detail(target))
            body.addWidget(button)
            self.groups[key], self.bodies[key], self.buttons[key] = group, content, button
            cards.addWidget(group, 1)
        column.addLayout(cards)
        self.comparison, self.verification = SchemeComparison(), VariabilityVerification()
        for view in (self.comparison, self.verification):
            view.selection_requested.connect(self.select_scheme)
        self.clear()

    def clear(self):
        self.context, self.result, self.records = None, {}, []
        self.variance_cache = {}
        self.index = self.default_index = -1
        self.tables = {}
        for key, title in (('comparison', '方案对比'), ('verification', '波动核验')):
            self.groups[key].setTitle(title)
            self.groups[key].setToolTip('')
            clear_layout(self.bodies[key])
            self.bodies[key].addWidget(label('尚无优化结果'))
            self.buttons[key].setEnabled(False)
        self.comparison.clear()
        self.verification.clear()

    def set_result(self, context, result, selected_index=None):
        self.clear()
        self.records, self.default_index = analysis_service.optimization_schemes(context, result)
        if not self.records:
            if result.get('error'):
                for body in self.bodies.values():
                    clear_layout(body)
                    body.addWidget(label('优化失败：'+result['error']))
            return
        self.context, self.result = context, result
        self._render_overview()
        index = self.default_index if selected_index is None else selected_index
        self.select_scheme(index, publish=False)

    def _variance(self, index):
        if index not in self.variance_cache:
            self.variance_cache[index] = analysis_service.scheme_variance(self.context, self.result, self.records[index]['x'])
        return self.variance_cache[index]

    def _render_overview(self):
        record = self.records[self.default_index]
        check = record['verification']
        feasible = self.result['feasible_count'] > 0
        caption = '推荐解' if feasible else '候选解'
        for key, title in (('comparison', '方案对比'), ('verification', '波动核验')):
            clear_layout(self.bodies[key])
            self.groups[key].setTitle(f"{title} · {caption} {record['id']}"+(' · 未找到可行解' if not feasible else ''))
            self.buttons[key].setEnabled(True)
            self.buttons[key].setToolTip('查看推荐解详情；可在详情页切换其他方案。' if feasible else '查看当前候选解详情；该方案未通过全部约束。')
        self.groups['comparison'].setToolTip('推荐设计（Recommended Design）\n总览始终展示求解器默认返回方案，详情页切换不改变总览。')
        inputs = {f.name:f for f in self.context['inputs']}
        factors = [[n, v, inputs[n].unit] for n,v in record['x'].items()]
        self.tables['factors'] = SummaryTable(['设计变量', '推荐取值' if feasible else '候选取值', '单位'], factors)
        units = {r.name:r.unit for r in self.context['_responses']}
        responses = [[r['响应'], r['鲁棒均值'], r['传播标准差'], units[r['响应']]] for r in check['responses']]
        self.tables['responses'] = SummaryTable(['响应', '近似均值 μ', '标准差 σ', '单位'], responses)
        for key in ('factors', 'responses'):
            self.bodies['comparison'].addWidget(self.tables[key])
        sources = []
        for name, rows in self._variance(self.default_index).items():
            inputs = [r for r in rows if r['name'] != '模型残差']
            if inputs:
                top = max(inputs, key=lambda r:r['variance'])
                sources.append([name, top['name'], top['share']])
        table = SummaryTable(['响应', '主要输入', '方差份额'], sources)
        for i, row in enumerate(sources):
            table.item(i, 2).setForeground(QColor(Qt.GlobalColor.transparent))
            table.setCellWidget(i, 2, share_indicator(row[2]))
        self.tables['contributions'] = table
        self.bodies['verification'].addWidget(table)
        self.groups['verification'].setToolTip('主要输入方差贡献（Leading Input Variance Contribution）\n展示推荐方案中贡献最大的模型输入，份额以含模型残差的总方差为分母。完整分解见详情。')

    def _open_detail(self, key):
        self.select_scheme(self.default_index)
        self.detail_requested.emit(key)

    def select_scheme(self, index, publish=True):
        if not 0 <= index < len(self.records):
            return
        self.index = index
        variance = self._variance(index)
        self.comparison.render(self.context, self.result, self.records, index, self.default_index)
        self.verification.render(self.context, self.result, self.records, index, self.default_index, variance)
        if publish:
            self.selection_changed.emit(index)
