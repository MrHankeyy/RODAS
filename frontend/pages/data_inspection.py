"""Saved-data checks and descriptive statistics in one analysis page."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QToolButton, QGroupBox, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QComboBox, QFileDialog)
from backend.services.data_service import data_overview
from backend.core.workbench_analysis import descriptive, descriptive_missing_reasons
from backend.infrastructure import file_io
from frontend.pages.result_overview import SummaryTable, label
from frontend.pages.result_summary import named
from frontend.pages.table_widgets import fill_records
from frontend.terminology import statistic_tooltip
from frontend.workspace import dialog_path, table_save_path
from frontend.notifications import Notice
from frontend.theme import content_zone


STATISTIC_GROUPS = (
    ('样本与范围', ('有效数', '缺失或无效', '最小值', '最大值')),
    ('位置与离散', ('均值', '中位数', '样本标准差', '四分位距')),
    ('分布形态', ('第一四分位数', '第三四分位数', '偏度', '超额峰度')),
)


class DataAnalysis(QWidget):
    issue_requested = pyqtSignal(int, str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project, self.dirty, self.stat_cards = project, False, []
        root = QVBoxLayout(self)
        head = QHBoxLayout()
        self.heading = label('数据分析', 'heading')
        self.heading.setToolTip('数据分析（Data Analysis）\n检查和统计以已保存数据为准，不拟合模型。')
        head.addWidget(self.heading)
        head.addStretch()
        self.notice = label()
        head.addWidget(self.notice)
        for caption, slot in (('刷新分析', lambda: self.refresh(self.dirty)),
                              ('导出统计 CSV', self.export_statistics)):
            button = QPushButton(caption)
            button.clicked.connect(slot)
            head.addWidget(button)
        root.addLayout(head)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('resultsSurface')
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(24)
        checks, checks_layout = content_zone()
        self.readiness_group = QGroupBox('数据完整度')
        self.readiness_layout = QVBoxLayout(self.readiness_group)
        checks_layout.addWidget(self.readiness_group)
        self.issues_toggle = QToolButton()
        self.issues_toggle.setCheckable(True)
        self.issues_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.issues_toggle.toggled.connect(self._show_issues)
        checks_layout.addWidget(self.issues_toggle)
        self.issues_table = QTableWidget()
        self.issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.issues_table.setAlternatingRowColors(True)
        self.issues_table.verticalHeader().hide()
        self.issues_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.issues_table.setMaximumHeight(240)
        self.issues_table.cellDoubleClicked.connect(self._locate_issue)
        self.issues_table.setToolTip('双击问题行或点击“定位”，前往数据录入中的对应单元格。')
        checks_layout.addWidget(self.issues_table)
        column.addWidget(checks)
        statistics, stats_layout = content_zone()
        bar = QHBoxLayout()
        caption = label('描述统计', 'sectionHeading')
        caption.setToolTip('描述统计（Descriptive Statistics）\n基于已保存的原始响应；不足以计算的统计量显示原因。')
        bar.addWidget(caption)
        bar.addStretch()
        bar.addWidget(label('响应'))
        self.response = QComboBox()
        self.response.currentIndexChanged.connect(self._render_statistics)
        bar.addWidget(self.response)
        stats_layout.addLayout(bar)
        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(12)
        stats_layout.addLayout(self.stats_grid)
        column.addWidget(statistics)
        column.addStretch()
        self.scroll.setWidget(content)
        root.addWidget(self.scroll)
        self.refresh()

    def set_dirty(self, dirty):
        self.dirty = dirty
        defined = any(r.name for r in self.project.responses)
        text = ('有未保存修改；以下分析为已保存数据，请先保存响应数据。' if dirty else
                '当前没有试验数据。' if not self.project.doe_matrix else
                '尚未定义响应，请先在业务建模中添加响应。' if not defined else
                '检查已通过，响应数据完整。' if not self.issues else
                '请补齐或修正问题明细中列出的响应数据。')
        self.notice.setText('未保存修改' if dirty else '暂无数据' if not self.project.doe_matrix else
                            '未定义响应' if not defined else
                            f'发现 {len(self.issues)} 项问题' if self.issues else '检查通过')
        self.notice.setToolTip(text)

    def refresh(self, dirty=False, data=None):
        data = data_overview(self.project) if data is None else data
        self.issues = data['issues']
        self.set_dirty(dirty)
        while self.readiness_layout.count():
            old = self.readiness_layout.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        names = {r.name: named(r) for r in self.project.responses if r.name}
        self.readiness_table = SummaryTable(['响应', '有效数据', '完整度', '状态'],
            [[names[name], f'{n} / {total}', '', '完整' if total and n == total else '待填入']
             for name, n, total in data['readiness']])
        self.progress_bars = []
        for i, (name, n, total) in enumerate(data['readiness']):
            progress = QProgressBar()
            progress.setRange(0, total or 1)
            progress.setValue(n)
            progress.setFormat(f'{n} / {total}')
            progress.setAccessibleName(f'{names[name]} 已填入 {n} / {total}')
            self.readiness_table.setCellWidget(i, 2, progress)
            self.progress_bars.append(progress)
        self.readiness_layout.addWidget(self.readiness_table)
        fill_records(self.issues_table, self.issues)
        if self.issues:
            column = self.issues_table.columnCount()
            self.issues_table.insertColumn(column)
            self.issues_table.setHorizontalHeaderItem(column, QTableWidgetItem('操作'))
            for i in range(len(self.issues)):
                button = QPushButton('定位')
                button.clicked.connect(lambda _checked=False, row=i: self._locate_issue(row, 0))
                self.issues_table.setCellWidget(i, column, button)
        self.issues_toggle.setText(f'问题明细 · {len(self.issues)} 项')
        self.issues_toggle.setEnabled(bool(self.issues))
        self.issues_toggle.setChecked(bool(self.issues))
        self._show_issues(bool(self.issues))
        previous = self.response.currentData()
        self.rows = descriptive(self.project)
        self.missing = descriptive_missing_reasons(self.rows)
        self.response.blockSignals(True)
        self.response.clear()
        for row in self.rows:
            self.response.addItem(names[row['响应']], row['响应'])
        self.response.setCurrentIndex(max(0, self.response.findData(previous)))
        self.response.blockSignals(False)
        self._render_statistics()

    def _show_issues(self, shown):
        self.issues_toggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)
        self.issues_table.setVisible(shown)

    def _render_statistics(self, *_args):
        while self.stats_grid.count():
            old = self.stats_grid.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        self.stat_values, self.stat_labels, self.stat_cards = {}, {}, []
        index = self.response.currentIndex()
        if index < 0:
            return
        row, missing = self.rows[index], self.missing[index]
        for title, keys in STATISTIC_GROUPS:
            group = QGroupBox(title)
            layout = QVBoxLayout(group)
            table = SummaryTable(['统计量', '值'], [[key, row.get(key)] for key in keys],
                missing_reasons={(i, 1): missing.get(key, '该响应没有有效的有限数值，无法计算描述统计。')
                                 for i, key in enumerate(keys) if row.get(key) is None})
            table.horizontalHeader().hide()
            for i, key in enumerate(keys):
                self.stat_labels[key], self.stat_values[key] = table.item(i, 0), table.item(i, 1)
                self.stat_labels[key].setToolTip(statistic_tooltip(key))
            table.setFixedHeight(sum(table.rowHeight(i) for i in range(table.rowCount())) + 4)
            layout.addWidget(table)
            self.stat_cards.append(group)
        self._reflow()

    def _reflow(self):
        columns = 3 if self.width() >= 680 else 1
        for i, card in enumerate(self.stat_cards):
            self.stats_grid.addWidget(card, i // columns, i % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def export_statistics(self):
        rows = descriptive(self.project)
        if not rows:
            Notice.information(self, '暂无统计', '请先定义响应并载入数据。')
            return
        path, selected = QFileDialog.getSaveFileName(
            self, '导出描述统计', dialog_path(self, '描述统计.csv'), file_io.TABLE_FILTER)
        if path:
            path = table_save_path(path, selected)
            try:
                headers = list(dict.fromkeys(key for row in rows for key in row))
                file_io.write_table(path, headers,
                    [[row.get(key) for key in headers] for row in rows])
            except OSError as exc:
                Notice.warning(self, '导出失败', str(exc))

    def _locate_issue(self, row, _column):
        issue = self.issues[row]
        self.issue_requested.emit(issue['数据行'] - 1, issue['响应'])
