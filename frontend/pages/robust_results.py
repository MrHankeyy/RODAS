"""Structured robust-design results shared by all surrogate models and modes."""
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout, QWidget

from backend.reporting.math_format import Math, formula_html, number
from frontend.pages.result_overview import SummaryTable, label
from frontend.pages.result_summary import display
from frontend.terminology import name as term_name, tooltip


class RobustResults(QWidget):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        self.status = label(role="badge")
        column.addWidget(self.status)
        self.body = QVBoxLayout()
        column.addLayout(self.body)
        self.plot = QGroupBox("优化图表")
        QVBoxLayout(self.plot).addWidget(canvas)
        canvas.setFixedHeight(270)
        column.addWidget(self.plot)
        self.footer = QVBoxLayout()
        column.addLayout(self.footer)
        column.addStretch()
        self.clear()

    def clear(self):
        for layout in (self.body, self.footer):
            while layout.count():
                widget = layout.takeAt(0).widget()
                widget.hide()
                widget.deleteLater()
        self.tables = {}
        self.status.setText("尚无优化结果，请执行鲁棒性优化设计。")
        self.plot.hide()

    def _section(self, title, footer=False):
        group = QGroupBox(title)
        (self.footer if footer else self.body).addWidget(group)
        return QVBoxLayout(group)

    def _table(self, key, layout, headers, rows):
        table = SummaryTable(headers, rows)
        self.tables[key] = table
        layout.addWidget(table)
        return table

    def set_result(self, context, result, verification):
        self.clear()
        best = result.get("best")
        if not best:
            if result.get("error"):
                self.status.setText("优化失败：" + result["error"])
            return
        feasible = result.get("feasible_count", 0) > 0
        self.status.setText("推荐优化设计 · 已找到可行解" if feasible else
                            "未找到可行解 · 以下为违例最小的候选点，不作为推荐设计")
        self.plot.show()
        summary = self._section("推荐设计指标" if feasible else "候选点指标")
        cards = QHBoxLayout()
        for term, value, hint in (
            ("mean_desirability", best["mean_perf"], "越大越好；仅汇总目标响应"),
            ("normalized_standard_deviation", best["std_norm"], "越小越好；按响应数据极差归一化"),
            (None, best["infeas"], "越接近零越好"),
        ):
            card = QVBoxLayout()
            caption = label(term_name(term) if term else "约束违例", "muted")
            if term:
                caption.setToolTip(tooltip(term))
            card.addWidget(caption)
            card.addWidget(label(display(value), "heading"))
            card.addWidget(label(hint, "muted"))
            cards.addLayout(card, 1)
        summary.addLayout(cards)
        inputs = {item.name: item for item in context["inputs"]}
        responses = {item.name: item for item in context["_responses"]}
        self._table("factors", self._section("因子取值与输入扰动"),
                    ["因子", "设计取值", "输入标准差 σ", "单位"],
                    [[name, value, result.get("input_sigmas", {}).get(name), inputs[name].unit]
                     for name, value in best["x"].items()])
        response_section = self._section("响应表现")
        self._table("responses", response_section,
                    ["响应", "角色", "近似均值 μ", "标准差 σ", "望性 d", "单位"],
                    [[r["name"], r["role"], r["mu"], r["sigma"], r["d"], responses[r["name"]].unit]
                     for r in best["responses"]])
        response_section.addWidget(label("均值和标准差基于局部二阶近似；仅作为约束的响应不计入平均望性。", "muted"))
        checks = []
        for row in verification.get("responses", []):
            name = row["响应"]
            response = responses[name]
            margin = row["约束余量"]
            if margin is not None:
                if response.feature == "望目":
                    actual = f"[{display(row['均值−kσ'])}, {display(row['均值+kσ'])}]"
                    bound = f"[{display(float(response.lower))}, {display(float(response.upper))}]"
                    metric = Math("μ±kσ", r"\mu\pm k\sigma")
                else:
                    small = response.feature == "望小"
                    actual = row["均值+kσ" if small else "均值−kσ"]
                    limit = float(response.robust_limit)
                    bound = Math(("≤ " if small else "≥ ") + display(limit),
                                 (r"\leq " if small else r"\geq ") + number(limit))
                    metric = Math("μ+kσ" if small else "μ−kσ", r"\mu+k\sigma" if small else r"\mu-k\sigma")
                checks.append([name, metric, actual, bound, margin, "通过" if margin >= 0 else "违反", response.unit])
            if row["标准差上限"] is not None:
                margin = row["波动约束余量"]
                limit = row["标准差上限"]
                checks.append([name, Math("标准差 σ", r"\sigma"), row["传播标准差"],
                               Math("≤ " + display(limit), r"\leq " + number(limit)),
                               margin, "通过" if margin >= 0 else "违反", response.unit])
        section = self._section("约束核验")
        if checks:
            table = self._table("constraints", section,
                                ["响应", "核验项", "计算值", "允许范围", "余量", "判定", "单位"], checks)
            for i, row in enumerate(checks):
                table.item(i, 5).setForeground(QColor("#19704b" if row[5] == "通过" else "#ba3348"))
            note = label(role="muted")
            note.setHtml("余量为负表示违反约束。" + formula_html(r"\mu\pm k\sigma") + " 为稳健带，不是预测置信区间。")
            section.addWidget(note)
        else:
            section.addWidget(label("本次未设置响应约束或独立标准差约束。", "muted"))
        mode = result["mode"]
        settings = self._section("求解统计与设置", footer=True)
        rows = [["鲁棒优化策略", {"constraint": "波动约束优化", "multi": "多目标优化（帕累托）", "weighted": "加权目标优化"}[mode]],
                ["评估解 / 可行解", f"{result['evaluated_count']} / {result['feasible_count']}"],
                ["种群数 / 代数", f"{result['population_size']} / {result['generations']}"],
                ["随机种子", result['seed']],
                ["逐变量交叉概率", result['pc']],
                ["变异概率设置", "自动（1/设计因子数）" if result['pm'] is None else "手动设置"],
                ["逐变量变异概率", result['effective_pm']],
                ["交叉分布指数", result['eta_c']], ["变异分布指数", result['eta_m']],
                ["约束裕量系数 k", result["k_constraint"]], ["区间标准差换算系数 k", result["k_design"]],
                ["目标响应", "、".join(result.get("objective_names", [])) or "无"],
                ["约束响应", "、".join(result.get("constraint_names", [])) or "无"]]
        if mode == "multi":
            rows.append(["帕累托前沿解数", len(result.get("front", []))])
            if result.get("knee"):
                note = label("推荐设计选取帕累托前沿的折中解。", "muted")
                note.setToolTip(tooltip("compromise_solution"))
                settings.addWidget(note)
        if mode == "weighted":
            rows.extend([["望性损失权重 λ", result["weight"]], ["波动权重", 1 - result["weight"]]])
        self._table("settings", settings, ["项目", "本次计算设置 / 结果"], rows)
        environments = [[n, s, inputs[n].unit] for n, s in result.get("input_sigmas", {}).items() if n not in best["x"]]
        if environments:
            self._table("environment", settings, ["环境因子", "输入标准差 σ", "单位"], environments)
