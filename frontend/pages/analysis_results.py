"""Response-specific analysis views using the shared read-only result components."""
import math

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from backend.core.factors import factor_limits
from backend.reporting.math_format import Math, formula_html, polynomial
from frontend.pages.result_overview import SummaryTable, label
from frontend.pages.result_summary import display, named


class AnalysisResults(QWidget):
    """Shared response selector and sections; rendering never fits a model."""
    TITLES = {"significance": "显著性 / LOF", "validation": "交叉验证与残差", "model": "模型提取"}

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        layout = QVBoxLayout(self)
        layout.addWidget(label(self.TITLES[kind], "heading"))
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

    def section(self, title, headers=(), rows=(), message=""):
        group = QGroupBox(title)
        box = QVBoxLayout(group)
        if headers:
            box.addWidget(SummaryTable(headers, rows))
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
        name = self.response.currentData()
        if not self.context or name not in self.context["models"]:
            self.model_label.setText("尚未分析")
            self.column.addWidget(label("尚无分析结果。请先填入响应数据，再点击「建模与模型诊断」。", "badge"))
        else:
            model = self.context["models"][name]
            proxy = "predict_fn" in model
            self.model_label.setText("当前模型：" + model.get("model_type", "二次响应面"))
            diagnostic = self.snapshot.get("responses", {}).get(name, {})
            measures = {row["统计量"]: row["值"] for row in diagnostic.get("summary", [])}
            if self.kind == "significance":
                self.significance(proxy, measures)
            elif self.kind == "validation":
                self.validation(name, proxy, diagnostic)
            else:
                self.model(name, model, proxy)
        self.column.addStretch()

    def significance(self, proxy, values):
        if proxy:
            self.section("当前模型不适用此检验", message=(
                "Kriging、SVR、BP 的预测器不直接套用多项式回归 ANOVA / LOF。"
                "请在「交叉验证与残差」查看留出集验证结果。"))
            return
        if not values:
            self.section("检验不可估计", message="没有可用的观测与拟合统计量。")
            return
        for prefix, title, numerator, denominator in (
            ("回归", "回归整体显著性", values.get("参数数", 1) - 1, values.get("残差自由度")),
            ("失拟", "失拟检验（LOF）", values.get("失拟自由度"), values.get("纯误差自由度")),
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
                self.section(title, message="检验不可估计：" + reason)
                continue
            conclusion = ("回归整体显著" if p < .05 else "未检出回归整体显著") if prefix == "回归" else (
                "检出显著失拟，建议检查模型形式" if p < .05 else "未检出显著失拟，不等于证明模型充分")
            box = self.section(title, ["检验", "F 值", "自由度（分子 / 分母）", "p 值"],
                               [["回归模型" if prefix == "回归" else "失拟 / 纯误差", values.get(prefix + " F"),
                                 f"{numerator} / {denominator}", "< 0.001" if p < .001 else display(p)]],
                               conclusion + " · 按 p < 0.05 判断。")
            box.addWidget(label("整体显著性不代表每个模型项都显著，也不直接代表预测精度。" if prefix == "回归" else
                                "结合验证误差与残差图判断模型表现。", "muted"))

    def validation(self, name, proxy, diagnostic):
        result = self.snapshot.get("validation", {}).get(name, {})
        response = next((item for item in self.context["_responses"] if item.name == name), None)
        unit = f"（{response.unit}）" if response and response.unit else ""
        source = (f"留出集验证 · 训练样本 {display(result.get('train_samples'))} · 未执行 K 折验证" if proxy else
                  f"{display(result.get('folds'))} 折交叉验证 · 下方图表为本次拟合样本")
        self.column.addWidget(label("验证来源：" + source, "muted"))
        metrics = QHBoxLayout()
        for caption, value in (
            ("测试集 R²" if proxy else "CV-R²", result.get("r2")),
            (("测试集 RMSE" if proxy else "CV-RMSE") + unit, result.get("rmse")),
            ("有效验证样本数", result.get("samples")),
        ):
            group = QGroupBox(caption)
            box = QVBoxLayout(group)
            box.addWidget(label(display(value), "heading"))
            metrics.addWidget(group, 1)
        container = QWidget()
        container.setLayout(metrics)
        self.column.addWidget(container)
        if result.get("message"):
            self.column.addWidget(label(result["message"], "badge"))
        elif result.get("r2") is None and result.get("samples"):
            self.column.addWidget(label("响应为常数，R² 不可估计；请参考 RMSE。", "badge"))
        rows = diagnostic.get("observations", [])
        if not rows:
            self.section("暂无图表数据", message="没有匹配的有限观测与预测。")
            return
        self.figure = Figure(figsize=(8, 3.3), dpi=100, layout="constrained")
        canvas = FigureCanvas(self.figure)
        canvas.setMinimumHeight(310)
        actual = [row["实测"] for row in rows]
        predicted = [row["预测"] for row in rows]
        residual = [row["残差"] for row in rows]
        fit, errors = self.figure.subplots(1, 2)
        fit.scatter(actual, predicted, s=22, color="#246da4", alpha=.75)
        limits = [min(actual + predicted), max(actual + predicted)]
        fit.plot(limits, limits, "--", color="#8495a6", label=r"$y = x$")
        fit.set(xlabel="观测值" + unit, ylabel="预测值" + unit,
                title="留出集：预测与观测" if proxy else "训练集：拟合值与观测值")
        fit.legend(fontsize=8)
        errors.scatter(predicted, residual, s=22, color="#246da4", alpha=.75)
        errors.axhline(0, linestyle="--", color="#8495a6")
        errors.set(xlabel="预测值" + unit, ylabel="残差" + unit,
                   title="留出集：残差与预测值" if proxy else "训练集：拟合残差与预测值")
        for axes in (fit, errors):
            axes.grid(alpha=.15)
        self.column.addWidget(canvas)
        note = label("图表来源：" + diagnostic.get("source", "未知") +
            ("。图表和上方指标均来自留出集。" if proxy else "。上方指标来自分折验证，图表为训练集拟合结果。") +
            "残差 = 观测值 − 预测值。", "badge")
        self.column.addWidget(note)
        canvas.draw_idle()

    def model(self, name, model, proxy):
        inputs = self.context["inputs"]
        if proxy:
            self.section("已训练预测器", ["项目", "内容"], [
                ["模型类型", model.get("model_type", "代理模型")], ["输出响应", self.response.currentText()],
                ["输入变量", "、".join(item.name for item in inputs)],
                ["后续优化", "直接调用当前模型的预测器"],
                ["不确定性传播", "数值梯度与对角 Hessian 近似"]],
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
        coefficients = [[term, float(value)] for term, value in zip(terms, model["coef"])]
        middle = (len(coefficients) + 1) // 2
        rows = [row + (coefficients[i + middle] if i + middle < len(coefficients) else ["", ""])
                for i, row in enumerate(coefficients[:middle])]
        box = self.section("模型系数", ["模型项", "系数", "模型项", "系数"], rows)
        box.addWidget(label("系数对应编码变量；系数区间与推断见「模型诊断与核验」。", "muted"))
