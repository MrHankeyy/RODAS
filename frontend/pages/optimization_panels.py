"""UI construction for OptimizationPage."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QGroupBox, QTextEdit, QMessageBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame,
    QLineEdit,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from frontend.pages.design_results import DesignResultsPanel
from frontend.pages.result_overview import ResultOverview
from frontend.pages.analysis_results import AnalysisResults
from frontend.pages.robust_results import RobustResults
from backend.reporting.math_format import rich_text
from frontend.math_widgets import MathTextEdit
from frontend.numeric_inputs import numeric_input
from frontend.pages.workbench_diagnostics import WorkbenchDiagnostics


def build(owner):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 顶部：状态 + 主执行按钮
        top = QHBoxLayout()
        owner.status_label = QLabel("尚未运行稳定性设计与鲁棒优化")
        owner.status_label.setProperty("role", "muted")
        owner.status_label.setWordWrap(True)
        top.addWidget(owner.status_label, 1)

        owner.run_all_btn = QPushButton("执行稳定性设计与鲁棒优化")
        owner.run_all_btn.setMinimumWidth(225)
        owner.run_all_btn.clicked.connect(owner._run_primary_action)
        owner.stats_btn = QPushButton("建模与模型诊断")
        owner.stats_btn.clicked.connect(owner.run_statistics)
        top.addWidget(owner.stats_btn)
        top.addWidget(owner.run_all_btn)
        main_layout.addLayout(top)

        from frontend.theme import ResultTabs
        owner.tabs = ResultTabs()
        owner.tabs.setUsesScrollButtons(True)
        owner.tab_overview = QWidget(); owner._build_overview_tab()
        owner.tab_robust = QWidget(); owner._build_robust_tab()
        owner.tab_signif = QWidget(); owner._build_signif_tab()
        owner.tab_cv = QWidget(); owner._build_cv_tab()
        owner.tab_param = QWidget(); owner._build_param_tab()
        owner.tab_tol = QWidget(); owner._build_tol_tab()
        owner.tab_model = QWidget(); owner._build_model_tab()
        owner.tab_tools = QWidget(); owner._build_tools_tab()
        owner.tabs.addTab(owner.tab_overview, "方案/结果汇总")
        owner.tabs.addTab(owner.tab_robust, "鲁棒优化设计")
        owner.tabs.addTab(owner.tab_signif, "显著性/LOF")
        owner.tabs.addTab(owner.tab_cv, "交叉验证与残差")
        owner.tabs.addTab(owner.tab_param, "参数取值")
        owner.tabs.addTab(owner.tab_tol, "容差贡献")
        owner.tabs.addTab(owner.tab_model, "模型提取")
        owner.tabs.addTab(owner.tab_tools, "优化工具集")
        owner.screening_panel = DesignResultsPanel("screening")
        owner.taguchi_panel = DesignResultsPanel("taguchi")
        owner.tabs.addTab(owner.screening_panel, "筛选主效应")
        owner.tabs.addTab(owner.taguchi_panel, "田口稳健分析")
        owner.diagnostics_panel = WorkbenchDiagnostics()
        owner.tabs.addTab(owner.diagnostics_panel, "模型诊断与核验")
        from frontend.theme import ResultsWorkspace, primary
        owner.results_workspace = ResultsWorkspace(owner.tabs)
        main_layout.addWidget(owner.results_workspace, 1)
        primary(owner.run_all_btn)

        owner.setLayout(main_layout)
        owner._oe_context = None
        owner._update_method_actions()
        for control in (owner.k_design_spin, owner.k_constraint_spin, owner.weight_spin, owner.pop_spin, owner.gen_spin):
            control.valueChanged.connect(owner._settings_changed)
        owner.robust_mode_combo.currentTextChanged.connect(owner._settings_changed)
        owner.sigma_limits_table.itemChanged.connect(owner._settings_changed)

def build_overview_tab(owner):
        layout = QVBoxLayout(owner.tab_overview)
        head = QHBoxLayout()
        head.addWidget(QLabel("方案 / 结果汇总"))
        head.addStretch()
        layout.addLayout(head)
        owner.overview = ResultOverview()
        layout.addWidget(owner.overview)
        owner._refresh_view()

def build_robust_tab(owner):
        layout = QVBoxLayout(owner.tab_robust)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("优化模式："))
        owner.robust_mode_combo = QComboBox()
        owner.robust_mode_combo.addItems(["多目标 NSGA-II", "加权单目标", "约束型"])
        controls.addWidget(owner.robust_mode_combo)
        controls.addSpacing(16)
        controls.addWidget(QLabel("种群数："))
        owner.pop_spin = numeric_input(int, 20, 300, 80)
        controls.addWidget(owner.pop_spin)
        controls.addSpacing(8)
        controls.addWidget(QLabel("代数："))
        owner.gen_spin = numeric_input(int, 30, 1000, 160)
        controls.addWidget(owner.gen_spin)
        controls.addStretch()
        layout.addLayout(controls)

        controls2 = QHBoxLayout()
        controls2.addWidget(QLabel("均值权重 λ："))
        owner.weight_spin = numeric_input(float, 0.0, 1.0, 0.5)
        controls2.addWidget(owner.weight_spin)
        controls2.addSpacing(16)
        controls2.addWidget(QLabel("约束安全系数 k："))
        owner.k_constraint_spin = numeric_input(float, 1.0, 10.0, 6.0)
        owner.k_constraint_spin.setToolTip(rich_text("在所有优化模式中执行已勾选约束。例如望小约束：均值 + k×标准差 ≤ 上限。"))
        controls2.addWidget(owner.k_constraint_spin)
        controls2.addSpacing(8)
        controls2.addWidget(QLabel("区间偏差换算系数 k："))
        owner.k_design_spin = numeric_input(float, 1.0, 10.0, 6.0)
        owner.k_design_spin.setToolTip("当前仍采用矩近似：设计因子用偏差宽度/(2k)，环境因子用实际区间宽度/(2k)换算标准差；均不由名义设计范围推导。概率输入直接采用所填方差，并非区间最坏情况传播。")
        controls2.addWidget(owner.k_design_spin)
        controls2.addStretch()
        layout.addLayout(controls2)
        owner.sigma_limits_table = QTableWidget(0, 2)
        owner.sigma_limits_table.setHorizontalHeaderLabels(["目标响应（原单位）", "允许的最大标准差 σ"])
        owner.sigma_limits_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        owner.sigma_limits_table.setFixedHeight(85)
        layout.addWidget(owner.sigma_limits_table)
        owner.uncertainty_label = QLabel()
        owner.uncertainty_label.setWordWrap(True)
        layout.addWidget(owner.uncertainty_label)
        owner.k_design_spin.valueChanged.connect(owner._update_uncertainty_label)
        owner._update_uncertainty_label()

        owner.robust_mode_combo.currentTextChanged.connect(owner._on_robust_mode)
        owner._on_robust_mode(owner.robust_mode_combo.currentText())
        owner.pareto_fig = Figure(figsize=(5, 3.6), dpi=100, layout="constrained")
        owner.pareto_canvas = FigureCanvas(owner.pareto_fig)
        owner.robust_results = RobustResults(owner.pareto_canvas)
        layout.addWidget(owner.robust_results, 1)

def build_signif_tab(owner):
        layout = QVBoxLayout(owner.tab_signif)
        owner.signif_panel = AnalysisResults("significance")
        layout.addWidget(owner.signif_panel)

def build_cv_tab(owner):
        layout = QVBoxLayout(owner.tab_cv)
        owner.cv_panel = AnalysisResults("validation")
        layout.addWidget(owner.cv_panel)

def build_param_tab(owner):
        layout = QVBoxLayout(owner.tab_param)
        owner.param_text = owner._new_text()
        owner.param_text.setMaximumHeight(150)
        layout.addWidget(owner.param_text)
        owner.factor_fig = Figure(figsize=(6, 4), dpi=100, layout="constrained")
        owner.factor_canvas = FigureCanvas(owner.factor_fig)
        layout.addWidget(owner.factor_canvas)

def build_tol_tab(owner):
        layout = QVBoxLayout(owner.tab_tol)
        owner.tol_text = owner._new_text()
        owner.tol_text.setMaximumHeight(150)
        owner.tol_text.setStyleSheet("background:#f7f9fb;border:1px solid #d9e0e7;padding:8px;")
        layout.addWidget(owner.tol_text)
        owner.tol_table = QTableWidget()
        owner.tol_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        owner.tol_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(owner.tol_table)

def build_model_tab(owner):
        layout = QVBoxLayout(owner.tab_model)
        owner.model_panel = AnalysisResults("model")
        layout.addWidget(owner.model_panel)

def build_tools_tab(owner):
        layout = QVBoxLayout(owner.tab_tools)
        head = QHBoxLayout()
        owner.tool_combo = QComboBox()
        owner.tool_combo.addItems(["最陡上升", "EVOP 演化操作", "自适应 AOFAT"])
        head.addWidget(QLabel("步数"))
        owner.tool_steps = numeric_input(int, 1, 100, 12)
        head.addWidget(owner.tool_steps)
        head.addWidget(QLabel("步长/因子跨度"))
        owner.tool_step = numeric_input(float, .001, .5, .1, decimals=3)
        head.addWidget(owner.tool_step)
        head.addStretch()
        layout.addLayout(head)
        head = QHBoxLayout()
        head.addWidget(QLabel("探索方法"))
        head.addWidget(owner.tool_combo)
        owner.tool_start = QComboBox(); owner.tool_start.addItems(["优化返回点", "手动核验点", "区间中心"])
        head.addWidget(owner.tool_start)
        owner.tool_weight = numeric_input(float, 0, 1, .5)
        head.addWidget(QLabel("均值权重 λ")); head.addWidget(owner.tool_weight)
        head.addStretch()
        owner.run_tool_btn = QPushButton("运行工具")
        owner.run_tool_btn.clicked.connect(owner._run_tool)
        head.addWidget(owner.run_tool_btn)
        layout.addLayout(head)
        owner.tool_text = owner._new_text()
        owner.tool_text.setMaximumHeight(150)
        owner.tool_text.setPlaceholderText("选择探索方法与起点后运行，结果和接受路径将在此显示。")
        layout.addWidget(owner.tool_text)
        owner.tool_table = QTableWidget()
        owner.tool_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        owner.tool_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(owner.tool_table)
