"""Responsive grouped presentation of the existing diagnostic statistics."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel

from frontend.pages.result_overview import SummaryTable
from frontend.pages.result_summary import display
from frontend.terminology import statistic_name, statistic_tooltip


GROUPS = (
    ('拟合与误差', ('R²', 'RMSE', 'MAE', '最大绝对误差', '残差均值', '残差样本标准差')),
    ('模型与样本', ('样本数', '参数数', '残差自由度', '设计矩阵条件数', '纯误差自由度', '失拟自由度')),
    ('变异分解与显著性', ('回归平方和', '残差平方和', '总平方和', '纯误差平方和', '回归 F', '回归 p')),
    ('失拟与交叉验证', ('失拟 F', '失拟 p', 'LOO PRESS', 'LOO RMSE', '预测 R² (LOO)', '残差 Shapiro p')),
)


class FitStatistics(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(10, 10, 10, 10)
        column.setSpacing(12)
        source = QGroupBox()
        source_row = QHBoxLayout(source)
        caption = QLabel('数据来源')
        caption.setProperty('role', 'muted')
        caption.setToolTip(statistic_tooltip('数据来源'))
        self.source_value = QLabel()
        source_row.addWidget(caption)
        source_row.addWidget(self.source_value)
        source_row.addStretch()
        column.addWidget(source)
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        column.addLayout(self.grid)
        column.addStretch()
        self.setWidget(content)
        self.cards, self.tables = [], []
        self.records, self.labels, self.values = [], {}, {}

    def clear(self):
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        self.cards, self.tables = [], []
        self.records, self.labels, self.values = [], {}, {}
        self.source_value.clear()

    def set_statistics(self, records, reasons):
        self.clear()
        self.records = records
        remaining = {row['统计量']: row['值'] for row in records}
        source = remaining.pop('数据来源', '')
        self.source_value.setText('验证集' if source.startswith('留出') else '训练集' if source else '')
        sections = [(title, [key for key in keys if key in remaining]) for title, keys in GROUPS]
        known = {key for _title, keys in GROUPS for key in keys}
        sections.append(('其他统计', [key for key in remaining if key not in known]))
        for title, keys in sections:
            if not keys:
                continue
            group = QGroupBox(title)
            layout = QVBoxLayout(group)
            table = SummaryTable(['统计量', '值'], [[statistic_name(key), remaining[key]] for key in keys],
                formatter=lambda value: display(value, precision=6),
                missing_reasons={(index, 1): reasons[key] for index, key in enumerate(keys) if key in reasons})
            table.horizontalHeader().hide()
            table.horizontalHeader().sectionResized.connect(lambda *_args, target=table: self._fit_table(target))
            self._fit_table(table)
            layout.addWidget(table)
            for index, key in enumerate(keys):
                self.labels[key] = table.item(index, 0)
                self.labels[key].setToolTip(statistic_tooltip(key))
                self.values[key] = table.item(index, 1)
            self.cards.append(group)
            self.tables.append(table)
        self._reflow()

    @staticmethod
    def _fit_table(table):
        table.resizeRowsToContents()
        table.setFixedHeight(sum(table.rowHeight(i) for i in range(table.rowCount())) + 2 * table.frameWidth())

    def _reflow(self):
        columns = 2 if self.viewport().width() >= 680 else 1
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def csv_rows(self):
        return [[statistic_name(row['统计量']), self.source_value.text() if row['统计量'] == '数据来源'
                 else display(row['值'], precision=6)] for row in self.records]
