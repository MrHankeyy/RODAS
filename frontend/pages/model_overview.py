"""Model overview grouped by the three detailed result views."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QComboBox, QPushButton, QFileDialog
from backend.infrastructure import file_io
from frontend.pages.result_overview import SummaryTable, label
from frontend.pages.result_summary import display, named
from frontend.terminology import statistic_name, statistic_tooltip, name, tooltip


GROUPS = (
    ('significance', '统计检验', ('回归 F', '回归 p', '失拟 F', '失拟 p',
     '回归平方和', '残差平方和', '总平方和', '纯误差平方和',
     '残差自由度', '纯误差自由度', '失拟自由度')),
    ('validation', '验证与残差', ('R²', 'RMSE', 'MAE', '最大绝对误差',
     '残差均值', '残差样本标准差', '交叉验证决定系数', '交叉验证均方根误差',
     '有效验证样本数', 'LOO PRESS', 'LOO RMSE', '预测 R² (LOO)', '残差 Shapiro p')),
    ('model', '模型与系数', ('模型类型', '样本数', '训练样本数', '参数数', '设计矩阵条件数')),
)


class FitStatistics(QWidget):
    detail_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.records, self.labels, self.values = [], {}, {}
        self.cards, self.tables, self.buttons = [], [], {}
        self._columns = 0

    def clear(self):
        while self.column.count():
            widget = self.column.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        self.records, self.labels, self.values = [], {}, {}
        self.cards, self.tables, self.buttons = [], [], {}

    def set_statistics(self, records, reasons):
        self.records, self.reasons = records, reasons
        self._render()

    def _render(self):
        records, reasons = self.records, self.reasons
        self.clear()
        self.records = records
        values = {row['统计量']: row['值'] for row in records}
        self._columns = 2 if self.width() >= 680 else 1
        for key, title, keys in GROUPS:
            group = QGroupBox(title)
            layout = QVBoxLayout(group)
            head = QHBoxLayout()
            head.addStretch()
            button = QPushButton('查看详情 →')
            button.setToolTip(f'查看{title}的详细结果，保留当前响应。')
            button.clicked.connect(lambda _checked=False, target=key: self.detail_requested.emit(target))
            head.addWidget(button)
            layout.addLayout(head)
            self.buttons[key] = button
            keys = [item for item in keys if item in values]
            if keys:
                rows, missing = [], {}
                for start in range(0, len(keys), self._columns):
                    row = []
                    for offset, item in enumerate(keys[start:start + self._columns]):
                        row.extend([statistic_name(item), values[item]])
                        if item in reasons:
                            missing[len(rows), offset * 2 + 1] = reasons[item]
                    rows.append(row + [''] * (self._columns * 2 - len(row)))
                table = SummaryTable(['统计量', '值'] * self._columns, rows,
                    formatter=lambda value: display(value, precision=6), missing_reasons=missing)
                table.horizontalHeader().hide()
                for index, item in enumerate(keys):
                    r, c = index // self._columns, index % self._columns * 2
                    self.labels[item] = table.item(r, c)
                    self.labels[item].setToolTip(statistic_tooltip(item))
                    self.values[item] = table.item(r, c + 1)
                table.resizeRowsToContents()
                table.setFixedHeight(sum(table.rowHeight(i) for i in range(table.rowCount())) + 4)
                layout.addWidget(table)
                self.tables.append(table)
            else:
                layout.addWidget(label('当前模型不适用此检验。', 'muted'))
            self.column.addWidget(group)
            self.cards.append(group)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 2 if self.width() >= 680 else 1
        if self.records and columns != self._columns:
            self._render()

    def csv_rows(self):
        return [[statistic_name(row['统计量']), display(row['值'], precision=6)] for row in self.records]


class ModelOverview(QWidget):
    detail_requested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.context, self.snapshot = None, {}
        self.setObjectName('contentZone')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        head = QHBoxLayout()
        self.heading = label('建模结果总览', 'sectionHeading')
        head.addWidget(self.heading)
        layout.addLayout(head)
        head = QHBoxLayout()
        head.addWidget(label('响应'))
        self.response = QComboBox()
        head.addWidget(self.response, 1)
        self.export_buttons = []
        for caption, slot in (('导出当前统计 CSV', self.export_csv), ('导出完整统计 JSON', self.export_json)):
            button = QPushButton(caption)
            button.clicked.connect(slot)
            head.addWidget(button)
            self.export_buttons.append(button)
        layout.addLayout(head)
        self.empty_state = label('暂无建模结果', 'muted')
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setMinimumHeight(120)
        layout.addWidget(self.empty_state)
        self.summary = FitStatistics()
        layout.addWidget(self.summary)
        self.summary.detail_requested.connect(
            lambda key: self.detail_requested.emit(key, self.response.currentData()))
        self.response.currentIndexChanged.connect(self.render)
        self.clear()

    def clear(self):
        self.set_result(None, {})

    def set_result(self, context, snapshot):
        previous = self.response.currentData()
        self.context, self.snapshot = context, snapshot
        self.response.blockSignals(True)
        self.response.clear()
        if context:
            definitions = {item.name: named(item) for item in context['_responses']}
            for response in context['models']:
                self.response.addItem(definitions.get(response, response), response)
        self.response.setCurrentIndex(max(0, self.response.findData(previous)))
        self.response.blockSignals(False)
        self.render()

    def render(self):
        response = self.response.currentData()
        diagnostic = self.snapshot.get('responses', {}).get(response)
        available = bool(self.context and diagnostic)
        self.empty_state.setVisible(not available)
        self.response.setEnabled(available)
        for button in self.export_buttons:
            button.setEnabled(available)
        if not available:
            self.summary.clear()
            self.heading.setToolTip('模型或输入更新后，执行“代理模型构建”刷新统计。')
            return
        model = self.context['models'][response]
        proxy = 'predict_fn' in model
        self.heading.setToolTip(diagnostic['source'] + ('。代理模型不报告普通最小二乘系数检验。' if proxy else
            '。交叉验证指标来自分折验证；留一指标来自留一验证，两者均不同于训练集拟合。'))
        records = list(diagnostic['summary'])
        reasons = dict(diagnostic.get('missing_reasons', {}).get('summary', {}))
        model_term = {'RSM': 'quadratic_response_surface', 'Kriging': 'kriging',
                      'SVR': 'svr', 'ANN': 'bpnn'}.get(model.get('model_type', 'RSM'))
        records.append({'统计量': '模型类型', '值': name(model_term) if model_term else model.get('model_type')})
        validation = self.snapshot.get('validation', {}).get(response, {})
        if proxy:
            records.append({'统计量': '训练样本数', '值': validation.get('train_samples')})
        else:
            for key, source in (('交叉验证决定系数', 'r2'), ('交叉验证均方根误差', 'rmse'), ('有效验证样本数', 'samples')):
                records.append({'统计量': key, '值': validation.get(source)})
                if validation.get(source) is None:
                    reasons[key] = validation.get('message') or ('验证响应全部相同，无法计算决定系数。'
                        if source == 'r2' and validation.get('samples') else '当前分折验证结果不可估计。')
        self.summary.set_statistics(records, reasons)
        if model_term:
            self.summary.values['模型类型'].setToolTip(tooltip(model_term))

    def export_csv(self):
        if not self.summary.records:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出当前统计', self._dialog_path(), 'CSV (*.csv)')
        if path:
            self._export(lambda: file_io.write_csv_table(path, ['统计量', '值'], self.summary.csv_rows()))

    def export_json(self):
        if not self.snapshot:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出完整统计', self._dialog_path(), 'JSON (*.json)')
        if path:
            from backend.core.workbench_analysis import clean_json
            self._export(lambda: file_io.write_json(path, clean_json(self.snapshot)))

    def _dialog_path(self):
        from frontend.workspace import dialog_path
        return dialog_path(self)

    def _export(self, write):
        from frontend.notifications import Notice
        try:
            write()
        except OSError as exc:
            Notice.warning(self, '导出失败', str(exc))
