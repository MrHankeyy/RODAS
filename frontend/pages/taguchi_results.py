from backend.domain.response_terms import criterion_name
"""Structured Taguchi results with actual grouped observations and local drilldown."""
import math
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QPushButton, QComboBox, QTabWidget, QFileDialog)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from backend.core.design_analysis import taguchi_observations
from backend.domain.models import RUN_ID
from backend.infrastructure import file_io
from frontend.notifications import Notice
from frontend.workspace import dialog_path, table_save_path
from frontend.theme import content_zone
from frontend.pages.result_overview import label, SummaryTable
from frontend.pages.result_summary import named
from frontend.pages.table_widgets import fill_records, ContentColumnBalancer


class TaguchiResultsPanel(QScrollArea):
    def __init__(self, project):
        super().__init__()
        self.project, self.result, self.selected_inner = project, {}, None
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('resultsSurface')
        column = QVBoxLayout(content)
        column.setSpacing(24)
        column.addWidget(label('田口分析', 'heading'))
        settings, body = content_zone()
        self.settings_header = QHBoxLayout()
        self.settings_header.addWidget(label('分析设置', 'sectionHeading'))
        self.settings_header.addStretch()
        body.addLayout(self.settings_header)
        group = QGroupBox('响应与评价')
        row = QGridLayout(group)
        row.addWidget(label('响应'), 0, 0)
        self.response_combo = QComboBox()
        row.addWidget(self.response_combo, 1, 0)
        row.addWidget(label('优化方向'), 0, 1)
        self.feature_label = label()
        row.addWidget(self.feature_label, 1, 1)
        row.addWidget(label('信噪比评价方式'), 0, 2)
        self.evaluation = label()
        row.addWidget(self.evaluation, 1, 2)
        body.addWidget(group)
        column.addWidget(settings)
        results, body = content_zone()
        header = QHBoxLayout()
        header.addWidget(label('田口分析结果', 'sectionHeading'))
        self.status = label()
        header.addWidget(self.status, 1)
        body.addLayout(header)
        self.message = label('尚未计算田口分析。')
        body.addWidget(self.message)
        self.summary = QWidget()
        cards = QHBoxLayout(self.summary)
        cards.setContentsMargins(0, 0, 0, 0)
        self.candidate_group = QGroupBox('候选水平组合 · 待确认')
        self.candidate_group.setToolTip('候选水平组合（Candidate Level Combination）\n按响应分别选取；采用主效应可加假设，必须进行新的独立确认试验。')
        self.observed_group = QGroupBox('对应内表组 · 实际观测')
        self.observed_group.setToolTip('实际观测（Observed Results）\n仅显示内表中已有组合的观测统计，不把加性预测当作实测结果。')
        self.candidate_table = self._new_table()
        self.observed_table = self._new_table()
        self.candidate_message, self.observed_message = label(), label()
        for group, table, message, stretch in ((self.candidate_group,self.candidate_table,self.candidate_message,1),
                                               (self.observed_group,self.observed_table,self.observed_message,2)):
            box = QVBoxLayout(group)
            box.addWidget(table)
            box.addWidget(message)
            box.addStretch()
            cards.addWidget(group, stretch)
        body.addWidget(self.summary)
        self.details = QTabWidget()
        self.level_page, self.runs_page = QWidget(), QWidget()
        levels, runs = QVBoxLayout(self.level_page), QVBoxLayout(self.runs_page)
        row = QHBoxLayout()
        row.addWidget(label('绘图因子：'))
        self.factor_combo = QComboBox()
        row.addWidget(self.factor_combo)
        row.addStretch()
        levels.addLayout(row)
        self.fig = Figure(figsize=(7, 2.8), layout='constrained')
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setFixedHeight(280)
        self.canvas.setToolTip('水平响应图（Level Response Plot）\n均值与信噪比分别展示；方框标记候选水平。水平信噪比是相关内表组信噪比的算术平均。')
        levels.addWidget(self.canvas)
        self.table = self._new_table()
        levels.addWidget(self.table)
        self.runs_table = self._new_table()
        runs.addWidget(self.runs_table)
        runs.addWidget(label('内表组表现 · 均值与波动', 'sectionHeading'))
        self.run_figure = Figure(figsize=(7, 2.4), layout='constrained')
        self.run_canvas = FigureCanvasQTAgg(self.run_figure)
        self.run_canvas.setFixedHeight(240)
        self.run_canvas.setToolTip('内表组波动（Inner-run Variability）\n误差棒为±1倍样本标准差，包含环境差异及观测随机误差，不是均值置信区间。紫色点为当前查看组。')
        runs.addWidget(self.run_canvas)
        self.group_heading = label(role='sectionHeading')
        runs.addWidget(self.group_heading)
        self.environment_table = self._new_table()
        self.environment_table.setToolTip('环境内重复（Within-environment Replication）\n每行固定同一控制与噪声条件，标准差来自该条件下的重复观测；单次观测不估计标准差。')
        runs.addWidget(self.environment_table)
        self.raw_toggle = QPushButton('展开原始观测')
        self.raw_toggle.setCheckable(True)
        runs.addWidget(self.raw_toggle)
        self.raw_table = self._new_table()
        self.raw_table.hide()
        runs.addWidget(self.raw_table)
        self.raw_toggle.toggled.connect(self._toggle_raw)
        self.details.addTab(self.level_page, '水平响应')
        self.details.addTab(self.runs_page, '试验组统计')
        self.export_button = QPushButton('导出当前表')
        self.details.setCornerWidget(self.export_button)
        self.export_button.clicked.connect(self.export_table)
        self.details.currentChanged.connect(self._fit_tabs)
        body.addWidget(self.details)
        column.addWidget(results)
        column.addStretch()
        self.setWidget(content)
        self.response_combo.currentIndexChanged.connect(self.render)
        self.factor_combo.currentIndexChanged.connect(self._plot_levels)
        self.set_result({})

    @staticmethod
    def _new_table():
        table = SummaryTable([], [])
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return table

    def _fill(self, table, headers, rows):
        table.export_data = headers, rows
        fill_records(table, [dict(zip(headers, row)) for row in rows])
        if not rows:
            table.setColumnCount(len(headers))
            table.setHorizontalHeaderLabels(headers)
        table.resizeColumnsToContents()
        widths = [table.columnWidth(i) for i in range(table.columnCount())]
        if hasattr(table, 'column_balancer'):
            table.column_balancer.minimum_widths = widths
            table.column_balancer.fit_columns()
        else:
            table.column_balancer = ContentColumnBalancer(table)
        table.setFixedHeight(table.horizontalHeader().height()+sum(table.rowHeight(i) for i in range(len(rows)))+22)

    def set_result(self, result):
        if self.result != (result or {}):
            self.selected_inner = None
        self.result = result or {}
        old = self.response_combo.currentData()
        self.response_combo.blockSignals(True)
        self.response_combo.clear()
        definitions = {r.name:r for r in self.project.responses}
        for name in dict.fromkeys([*self.result.get('response_analysis', {}), *self.result.get('errors', {})]):
            self.response_combo.addItem(named(definitions[name])+' · '+definitions[name].kind, name)
        if self.response_combo.findData(old) >= 0:
            self.response_combo.setCurrentIndex(self.response_combo.findData(old))
        self.response_combo.blockSignals(False)
        self.render()

    def render(self, *_args):
        self.name = self.response_combo.currentData()
        self.item = self.result.get('response_analysis', {}).get(self.name, {})
        item = self.item
        self.status.setText(self.result.get('analysis_status', '尚无分析结果'))
        self.summary.setVisible(bool(item))
        self.details.setVisible(bool(item))
        self.message.setVisible(not item)
        self.message.setText(self.result.get('errors', {}).get(self.name, '请填入响应数据后计算田口分析。'))
        self.export_button.setEnabled(bool(item))
        if not item:
            for table in (self.table,self.runs_table,self.raw_table,self.environment_table,self.candidate_table,self.observed_table):
                self._fill(table, [], [])
            self.factor_combo.clear()
            self.evaluation.clear()
            self.feature_label.clear()
            for figure, canvas in ((self.fig,self.canvas),(self.run_figure,self.run_canvas)):
                figure.clear()
                canvas.draw_idle()
            return
        response = next(r for r in self.project.responses if r.name == self.name)
        self.unit = response.unit
        self.feature_label.setText(criterion_name('目标', item['feature']))
        self.evaluation.setText(item['feature']+'型'+item['metric_label'] if item['has_replication'] else item['metric_label'])
        self.evaluation.setToolTip('信噪比（Signal-to-Noise Ratio，S/N）\n'+item['note'])
        self.candidate_group.setToolTip('候选水平组合（Candidate Level Combination）\n'+self.result.get('recommendation',''))
        best = item['best_levels']
        inputs = {f.name:f for f in self.project.factors}
        self._fill(self.candidate_table, ['控制因子','候选水平','单位'], [[n,v,inputs[n].unit] for n,v in best.items()])
        self.candidate_table.setVisible(bool(best))
        self.candidate_message.setVisible(not best)
        self.candidate_message.setText('该响应仅报告观测结果，不生成候选组合。')
        observed = next((r for r in item['runs'] if best and all(math.isclose(r['settings'][n],v) for n,v in best.items())), None)
        self.observed_table.setVisible(bool(observed))
        self.observed_message.setVisible(not observed)
        self.observed_message.setText('候选组合未在内表中出现，暂无对应观测统计。' if best else '请在下方查看各内表组的观测统计。')
        self.observed_group.setTitle(f"内表组 {observed['inner']} · {named(response)} · 实际观测" if observed else '对应内表组 · 实际观测')
        if observed:
            self._fill(self.observed_table, ['响应','均值','标准差',item['metric_label'],'观测数'],
                       [[self.name,observed['mean'],observed['std'],observed['metric'],observed['n']]])
        else:
            self._fill(self.observed_table, [], [])
        factor_names = list(dict.fromkeys(r['factor'] for r in item['levels']))
        old = self.factor_combo.currentData()
        self.factor_combo.blockSignals(True)
        self.factor_combo.clear()
        for n in factor_names:
            self.factor_combo.addItem(named(inputs[n]), n)
        if self.factor_combo.findData(old) >= 0:
            self.factor_combo.setCurrentIndex(self.factor_combo.findData(old))
        self.factor_combo.blockSignals(False)
        unit = f'（{self.unit}）' if self.unit else ''
        self._fill(self.table, ['因子（单位）','实际水平','均值'+unit,'平均组内标准差'+unit,item['metric_label'],'内表组数','候选水平'],
                   [[named(inputs[r['factor']]),r['level_value'],r['mean'],r['std'],r['metric'],r['n'],'是' if r['recommended'] else '—'] for r in item['levels']])
        self.table.horizontalHeaderItem(3).setToolTip('平均组内标准差（Average Within-run Standard Deviation）\n该水平关联内表组的样本标准差之算术平均，不是合并全部观测后计算的标准差。')
        controls = list(item['runs'][0]['settings'])
        self._fill(self.runs_table, ['内表组',*[named(inputs[n]) for n in controls],'观测数','均值'+unit,'标准差'+unit,item['metric_label'],'观测明细'],
                   [[r['inner'],*[r['settings'][n] for n in controls],r['n'],r['mean'],r['std'],r['metric'],''] for r in item['runs']])
        if self.selected_inner not in [r['inner'] for r in item['runs']]:
            self.selected_inner = observed['inner'] if observed else item['runs'][0]['inner']
        for i, row in enumerate(item['runs']):
            button = QPushButton('查看')
            button.clicked.connect(lambda checked=False, inner=row['inner']: self.select_inner(inner))
            self.runs_table.setCellWidget(i,self.runs_table.columnCount()-1,button)
        self._plot_levels()
        self.select_inner(self.selected_inner)
        self._fit_tabs()

    def _plot_levels(self, *_args):
        self.fig.clear()
        rows = [r for r in self.item.get('levels', []) if r['factor'] == self.factor_combo.currentData()]
        if rows:
            for i, (key, title) in enumerate((('mean',f'均值（{self.unit}）'),('metric',self.item['metric_label']))):
                ax = self.fig.add_subplot(1,2,i+1)
                finite_rows = [r for r in rows if math.isfinite(r[key])]
                ax.plot([r['level_value'] for r in rows], [r[key] if math.isfinite(r[key]) else float('nan') for r in rows], 'o-', color='#275ce4')
                chosen = [r for r in finite_rows if r['recommended']]
                ax.scatter([r['level_value'] for r in chosen],[r[key] for r in chosen], marker='s', facecolors='none',edgecolors='#275ce4',s=90,zorder=3)
                if len(finite_rows) != len(rows):
                    ax.text(.02,.96,'零损失信噪比=+∞，详见表格',transform=ax.transAxes,va='top')
                ax.set_title(title)
                ax.set_xlabel(self.factor_combo.currentText())
                ax.set_ylabel(title)
                ax.grid(alpha=.2)
        self.canvas.draw_idle()

    def select_inner(self, inner):
        self.selected_inner = inner
        noise, environments, raw = taguchi_observations(self.project,self.name,inner)
        inputs = {f.name:f for f in self.project.factors}
        unit = f'（{self.unit}）' if self.unit else ''
        self._fill(self.environment_table, ['外表组',*[named(inputs[n]) for n in noise],'观测数','均值'+unit,'组内标准差'+unit], environments)
        self._fill(self.raw_table, [RUN_ID,'外表组','重复组',*[named(inputs[n]) for n in noise],self.name+unit], raw)
        self.group_heading.setText(f'内表组 {inner} · 环境与重复观测')
        self.raw_toggle.setText(f"{'收起' if self.raw_toggle.isChecked() else '展开'}该组的{len(raw)}次原始观测")
        for i, r in enumerate(self.item['runs']):
            self.runs_table.cellWidget(i,self.runs_table.columnCount()-1).setText('当前查看' if r['inner']==inner else '查看')
        self.run_figure.clear()
        ax = self.run_figure.add_subplot(111)
        runs = self.item['runs']
        ax.errorbar([r['inner'] for r in runs],[r['mean'] for r in runs],yerr=[r['std'] or 0 for r in runs],fmt='o',capsize=4,color='#275ce4')
        chosen = next(r for r in runs if r['inner']==inner)
        ax.scatter([inner],[chosen['mean']],color='#b32bbd',s=70,zorder=3)
        ax.set_xticks([r['inner'] for r in runs])
        ax.set_xlabel('内表组号')
        ax.set_ylabel('均值'+unit)
        ax.grid(axis='y',alpha=.2)
        self.run_canvas.draw_idle()
        self._fit_tabs()

    def _toggle_raw(self, checked):
        self.raw_table.setVisible(checked)
        if self.item:
            self.raw_toggle.setText(f"{'收起' if checked else '展开'}该组的{self.raw_table.rowCount()}次原始观测")
        self._fit_tabs()

    def _fit_tabs(self, *_args):
        QTimer.singleShot(0, self._apply_tab_height)

    def _apply_tab_height(self):
        page = self.details.currentWidget()
        page.layout().activate()
        self.details.setFixedHeight(page.sizeHint().height()+self.details.tabBar().sizeHint().height()+8)

    def export_table(self):
        table = self.table if self.details.currentIndex()==0 else self.runs_table
        path, selected = QFileDialog.getSaveFileName(
            self, '导出田口统计', dialog_path(self, '田口统计.csv'), file_io.TABLE_FILTER)
        if path:
            path = table_save_path(path, selected)
            try:
                headers, rows = table.export_data
                if table is self.runs_table:
                    headers, rows = headers[:-1], [r[:-1] for r in rows]
                file_io.write_table(path, headers, rows)
            except OSError as exc:
                Notice.warning(self,'导出失败',str(exc))
