"""Response-specific analysis views using the shared read-only result components."""
import math
import numpy as np
from scipy import stats

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget, QPushButton, QFileDialog, QToolTip,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from backend.core.factors import factor_limits
from backend.reporting.math_format import Math, formula_html, polynomial
from frontend.pages.result_overview import SummaryTable, label
from frontend.pages.table_widgets import ContentColumnBalancer
from frontend.pages.result_summary import display, named
from frontend.terminology import name as term_name, tooltip, statistic_name, statistic_tooltip


class DiagnosticCanvas(FigureCanvas):
    """Use a native delayed tooltip for the subplot under the pointer."""

    def __init__(self, figure):
        super().__init__(figure)
        self.axis_tooltips = {}
        self.mpl_connect('motion_notify_event', self._update_tooltip)
        self.mpl_connect('figure_leave_event', self._clear_tooltip)

    def _update_tooltip(self, event):
        text = self.axis_tooltips.get(event.inaxes, '')
        if text != self.toolTip():
            QToolTip.hideText()
            self.setToolTip(text)

    def _clear_tooltip(self, _event):
        QToolTip.hideText()
        self.setToolTip('')


class AnalysisResults(QWidget):
    """Shared response selector and sections; rendering never fits a model."""
    TITLES = {"significance": "统计检验", "validation": "验证与残差", "model": "模型与系数"}

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        layout = QVBoxLayout(self)
        heading = label(self.TITLES[kind], "heading")
        if kind == "significance":
            heading.setToolTip(tooltip("regression_significance_lof"))
        elif kind == "validation":
            heading.setToolTip(tooltip("cross_validation_residuals"))
        else:
            heading.setToolTip(tooltip("model_coefficients"))
        self.heading = heading
        layout.addWidget(heading)
        toolbar = QHBoxLayout()
        toolbar.addWidget(label("响应："))
        self.response = QComboBox()
        self.response.setMinimumWidth(180)
        self.response.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        toolbar.addWidget(self.response)
        toolbar.addStretch()
        self.model_label = label(role="muted")
        self.model_label.setWordWrap(False)
        toolbar.addWidget(self.model_label)
        if kind == 'validation':
            export = QPushButton('导出诊断图')
            export.clicked.connect(self.export_plot)
            toolbar.addWidget(export)
        export_table = QPushButton('导出系数 CSV' if kind == 'model' else '导出当前统计 CSV')
        export_table.clicked.connect(self.export_csv)
        toolbar.addWidget(export_table)
        layout.addLayout(toolbar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.column = QVBoxLayout(content)
        self.column.setContentsMargins(0, 0, 4, 4)
        self.column.setSpacing(12)
        scroll.setWidget(content)
        layout.addWidget(scroll)
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
            definitions = {item.name: named(item) for item in context["_responses"]}
            for name in context["models"]:
                self.response.addItem(definitions.get(name, name), name)
        self.response.setCurrentIndex(max(0, self.response.findData(previous)))
        self.response.setEnabled(self.response.count() > 0)
        self.response.blockSignals(False)
        self.render()

    def section(self, title, headers=(), rows=(), message="", missing_reasons=None):
        group = QGroupBox(title)
        box = QVBoxLayout(group)
        if headers:
            table = SummaryTable(headers, rows, missing_reasons=missing_reasons)
            box.addWidget(table)
            self.result_tables.append((title, table))
        if message:
            box.addWidget(label(message, "badge"))
        self.column.addWidget(group)
        return box

    def render(self):
        while self.column.count():
            item = self.column.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.figure = None
        self.result_tables = []
        name = self.response.currentData()
        if not self.context or name not in self.context["models"]:
            self.model_label.setText("尚未分析")
            self.column.addWidget(label("尚无分析结果。请先填入响应数据，再点击「建模与模型诊断」。", "badge"))
        else:
            model = self.context["models"][name]
            proxy = "predict_fn" in model
            model_type = model.get("model_type", "RSM")
            model_term = {"RSM": "quadratic_response_surface", "Kriging": "kriging",
                          "SVR": "svr", "ANN": "bpnn"}.get(model_type)
            display_model = term_name(model_term) if model_term else model_type
            self.model_label.setText("当前模型：" + display_model)
            self.model_label.setToolTip(tooltip(model_term) if model_term else "")
            diagnostic = self.snapshot.get("responses", {}).get(name, {})
            measures = {row["统计量"]: row["值"] for row in diagnostic.get("summary", [])}
            if self.kind == "significance":
                self.significance(proxy, measures, diagnostic.get('missing_reasons', {}).get('summary', {}))
            elif self.kind == "validation":
                self.validation(name, proxy, diagnostic)
            else:
                self.model(name, model, proxy, diagnostic)
        self.column.addStretch()

    def significance(self, proxy, values, reasons):
        if proxy:
            self.section("当前模型不适用此检验", message=(
                "克里金模型、支持向量回归模型和神经网络模型的预测器不直接套用多项式回归方差分析或失拟检验。"
                "请在「验证与残差」查看留出集验证结果。"))
            return
        if not values:
            self.section("检验不可估计", message="没有可用的观测与拟合统计量。")
            return
        for prefix, title, numerator, denominator in (
            ("回归", "回归整体显著性", values.get("参数数", 1) - 1, values.get("残差自由度")),
            ("失拟", "失拟检验", values.get("失拟自由度"), values.get("纯误差自由度")),
        ):
            p = values.get(prefix + " p")
            available = p is not None and math.isfinite(p)
            if not available:
                if prefix == "回归":
                    reason = "残差自由度不足或残差数值上为零，无法计算有效 F / p 值。"
                elif not denominator:
                    reason = "没有重复试验点，无法独立估计纯误差。"
                elif not numerator or numerator <= 0:
                    reason = "失拟自由度不足，无法独立估计失拟误差。"
                else:
                    reason = "重复点纯误差为零或数值上接近零，无法计算有效 F / p 值。"
                box = self.section(title, message='检验不可估计')
                box.parentWidget().setToolTip(reasons.get(prefix + ' p', reason))
                continue
            conclusion = ("回归整体显著" if p < .05 else "未检出回归整体显著") if prefix == "回归" else (
                "检出显著失拟，建议检查模型形式" if p < .05 else "未检出显著失拟，不等于证明模型充分")
            box = self.section(title, ["检验", "检验统计量", "自由度（分子 / 分母）", "概率值"],
                               [["回归模型" if prefix == "回归" else "失拟 / 纯误差", values.get(prefix + " F"),
                                 f"{numerator} / {denominator}", "< 0.001" if p < .001 else display(p)]],
                               conclusion)
            box.parentWidget().setToolTip('按概率值小于0.05判断。' + (
                '整体显著性不代表每个模型项都显著，也不直接代表预测精度。' if prefix == '回归' else
                '未检出显著失拟不等于证明模型充分，需结合验证误差与残差图。'))
        rows = [[statistic_name(key), values.get(key)] for key in (
            '回归平方和', '残差平方和', '总平方和', '纯误差平方和',
            '残差自由度', '纯误差自由度', '失拟自由度')]
        self.section('变异分解与自由度', ['统计量', '值'], rows)

    def validation(self, name, proxy, diagnostic):
        result = self.snapshot.get("validation", {}).get(name, {})
        values = {row['统计量']: row['值'] for row in diagnostic.get('summary', [])}
        reasons = diagnostic.get('missing_reasons', {}).get('summary', {})
        response = next((item for item in self.context['_responses'] if item.name == name), None)
        unit = f"（{response.unit}）" if response and response.unit else ""
        rows = [[('留出集验证' if proxy else f"{display(result.get('folds'))}折交叉验证"),
                 result.get('r2'), result.get('rmse'), result.get('samples')]]
        missing = {}
        for column, key in ((1, 'r2'), (2, 'rmse')):
            if result.get(key) is None:
                missing[0, column] = result.get('message') or (
                    '验证响应全部相同，无法计算决定系数。' if key == 'r2' and result.get('samples')
                    else '当前验证指标不可估计。')
        if not proxy:
            rows.append(['留一验证', values.get('预测 R² (LOO)'), values.get('LOO RMSE'),
                         values.get('样本数') if values.get('LOO PRESS') is not None else None])
            for column, key in ((1, '预测 R² (LOO)'), (2, 'LOO RMSE'), (3, 'LOO PRESS')):
                if key in reasons:
                    missing[1, column] = reasons[key]
        box = self.section('验证结果', ['验证方式', '决定系数', '均方根误差' + unit, '有效验证样本数'],
                           rows, missing_reasons=missing)
        box.parentWidget().setToolTip('留出验证集未参与训练；当前未执行分折验证。' if proxy else
            '分折验证与留一验证分别计算，在同一张表中展示；验证样本不足或矩阵秩不足时不降阶替代。')
        if result.get('message'):
            box.addWidget(label('当前验证不可估计', 'muted'))
            box.parentWidget().setToolTip(result['message'])
        keys = ('R²', 'RMSE', 'MAE', '最大绝对误差', '残差均值', '残差样本标准差',
                '残差 Shapiro p') if proxy else (
                'R²', 'RMSE', 'MAE', '最大绝对误差', '残差均值', '残差样本标准差',
                'LOO PRESS', '残差 Shapiro p')
        self.section('误差与残差概况 · ' + ('留出验证集' if proxy else '训练集'),
                     ['统计量', '值'], [[statistic_name(key), values[key]] for key in keys if key in values],
                     missing_reasons={(i, 1): reasons[key] for i, key in
                         enumerate(key for key in keys if key in values) if key in reasons})
        rows = diagnostic.get('observations', [])
        if not rows:
            self.section('暂无图表数据', message='没有匹配的有限观测与预测。')
            return
        self.heading.setToolTip(tooltip('cross_validation_residuals') + '\n' + diagnostic.get('source', '') + (
            '。图表和上方指标均来自留出集。' if proxy else
            '。上方指标来自分折验证与留一验证，图表为训练集拟合结果。') +
            '残差＝观测值－预测值；矩阵行序不一定是实际试验时间。')
        self.figure = Figure(figsize=(8, 6.2), dpi=100, layout='constrained')
        canvas = DiagnosticCanvas(self.figure)
        canvas.setMinimumHeight(540)
        actual = np.array([row['实测'] for row in rows])
        predicted = np.array([row['预测'] for row in rows])
        residual = actual - predicted
        fit, errors, normal, sequence = self.figure.subplots(2, 2).flat
        groups = diagnostic['prediction_groups']
        fit_x = np.array([group['预测'] for group in groups])
        fit_y = np.array([group['观测均值'] for group in groups])
        spread = np.array([group['观测标准差'] if group['观测标准差'] is not None else 0 for group in groups])
        fit.scatter(fit_x, fit_y, s=22, color='#246da4', alpha=.75)
        repeated = np.array([group['观测数'] > 1 for group in groups])
        if repeated.any():
            fit.errorbar(fit_x[repeated], fit_y[repeated], yerr=spread[repeated], fmt='none',
                         capsize=3, color='#246da4', alpha=.75)
        limits = [min((fit_y - spread).min(), fit_x.min()), max((fit_y + spread).max(), fit_x.max())]
        fit.plot(limits, limits, '--', color='#8495a6')
        fit.set(xlabel='预测值' + unit, ylabel='观测均值' + unit,
                title='留出集：观测均值与预测值' if proxy else '训练集：观测均值与预测值')
        errors.scatter(predicted, residual, s=22, color='#246da4', alpha=.75)
        errors.axhline(0, linestyle='--', color='#8495a6')
        errors.set(xlabel='预测值' + unit, ylabel='残差' + unit, title='残差与预测值')
        if len(residual) > 1:
            stats.probplot(residual, dist='norm', plot=normal)
        normal.set(title='残差正态分位图', xlabel='理论分位数', ylabel='残差分位数' + unit)
        sequence.plot([row['序号'] for row in rows], residual, 'o-', ms=3, color='#246da4')
        sequence.axhline(0, linestyle='--', color='#8495a6')
        sequence.set(title='残差序列图', xlabel='数据序号', ylabel='残差' + unit)
        for axes in (fit, errors, normal, sequence):
            axes.grid(alpha=.15)
        canvas.axis_tooltips = {
            fit: '观测均值与预测值（Mean Observed versus Predicted Values）\n'
                 '按全部模型输入相同分组。横轴为预测值，纵轴为观测均值，竖向误差棒为组内样本标准差（±1倍）。'
                 '只有一次观测时不绘制误差棒；误差棒不是均值置信区间。',
            errors: '残差与预测值（Residuals versus Predicted Values）\n'
                    '保留每次观测，残差＝观测值－预测值。用于检查偏差模式和误差散布是否随预测值变化。',
            normal: '残差正态分位图（Normal Quantile–Quantile Plot，Q–Q）\n'
                    '使用全部逐次残差，辅助检查分布是否接近正态；接近参考直线不等于证明正态。',
            sequence: '残差序列图（Residual Sequence Plot）\n'
                      '按数据序号展示逐次残差。矩阵行序不一定是实际试验时间，不作为时间独立性检验。',
        }
        self.column.addWidget(canvas)
        canvas.draw_idle()

    def model(self, name, model, proxy, diagnostic):
        inputs = self.context["inputs"]
        if proxy:
            model_type = model.get("model_type")
            model_term = {"Kriging": "kriging", "SVR": "svr", "ANN": "bpnn"}.get(model_type)
            self.section("已训练预测器", ["项目", "内容"], [
                ["模型类型", term_name(model_term) if model_term else "代理模型"], ["输出响应", self.response.currentText()],
                ["输入变量", "、".join(item.name for item in inputs)],
                ["后续优化", "直接调用当前模型的预测器"],
                ["不确定性传播", "数值梯度与对角海森矩阵近似"]],
                "该模型不提供二次多项式回归方程。")
            bounds = self.context["_project"].surrogate_config.get("bounds") or {}
            self.section("模型输入", ["因子", "抽样下限", "抽样上限", "单位"],
                         [[item.name, *(bounds.get(item.name) or factor_limits(item)), item.unit] for item in inputs])
            return
        names = self.context["names"]
        terms, pieces, coding = polynomial(name, model, names)
        box = self.section("拟合方程 · 编码变量")
        equation = label(role="badge")
        equation.setHtml(' '.join(formula_html(piece) for piece in pieces))
        equation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(equation)
        units = {item.name: item.unit for item in inputs}
        self.section("输入编码关系", ["实际变量", "编码变量", "换算关系"], [
            [f"{factor}（{units[factor]}）" if units.get(factor) else factor,
             Math(f'z_{factor}', relation.latex.split('=')[0]), relation]
            for factor, relation in zip(names, coding)])
        columns = ['估计值', '标准误', 't', '未校正 p', '95%下限', '95%上限']
        rows = [[term] + [row[key] for key in columns]
                for term, row in zip(terms, diagnostic.get('coefficients', []))]
        reasons = diagnostic.get('missing_reasons', {}).get('coefficients', [])
        box = self.section('模型系数与区间', ['编码项'] + [statistic_name(key) for key in columns], rows,
            missing_reasons={(i, columns.index(key) + 1): reason
                for i, missing in enumerate(reasons) for key, reason in missing.items()})
        box.parentWidget().setToolTip('系数对应编码变量。区间为普通最小二乘条件推断，假设独立同方差正态误差；概率值未校正多重比较。')
        table = self.result_tables[-1][1]
        table.column_balancer = ContentColumnBalancer(table)

    def export_plot(self):
        if self.figure is None:
            return
        from frontend.workspace import dialog_path
        path, _ = QFileDialog.getSaveFileName(self, '导出诊断图', dialog_path(self), 'PNG (*.png);;SVG (*.svg)')
        if path:
            self._export(lambda: self.figure.savefig(path, dpi=180, bbox_inches='tight'))

    def export_csv(self):
        if not self.result_tables:
            return
        from frontend.workspace import dialog_path
        from backend.infrastructure import file_io
        tables = self.result_tables[-1:] if self.kind == 'model' else self.result_tables
        records = []
        for title, table in tables:
            headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
            for r in range(table.rowCount()):
                records.append({'分节': title, **{key: table.item(r, c).text() for c, key in enumerate(headers)}})
        headers = list(dict.fromkeys(key for row in records for key in row))
        path, _ = QFileDialog.getSaveFileName(self, '导出当前统计', dialog_path(self), 'CSV (*.csv)')
        if path:
            self._export(lambda: file_io.write_csv_table(path, headers, [[row.get(key, '') for key in headers] for row in records]))

    def _export(self, write):
        from frontend.notifications import Notice
        try:
            write()
        except (OSError, ValueError) as exc:
            Notice.warning(self, '导出失败', str(exc))
