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
from frontend.pages.result_overview import ResultOverview, label
from frontend.pages.analysis_results import AnalysisResults
from frontend.pages.robust_results import RobustResults
from backend.reporting.math_format import rich_text
from frontend.math_widgets import MathTextEdit
from frontend.numeric_inputs import numeric_input
from frontend.terminology import add_combo_item, apply, name, tooltip


def build(owner):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 顶部：状态 + 主执行按钮
        top = QHBoxLayout()
        owner.status_label = QLabel("尚未运行鲁棒性优化设计")
        owner.status_label.setProperty("role", "muted")
        owner.status_label.setWordWrap(True)
        top.addWidget(owner.status_label, 1)

        owner.run_all_btn = QPushButton("执行鲁棒性优化设计")
        owner.run_all_btn.setToolTip(tooltip("robust_optimization"))
        owner.run_all_btn.setMinimumWidth(225)
        owner.run_all_btn.clicked.connect(owner._run_primary_action)
        owner.stats_btn = QPushButton("建模与模型诊断", owner)
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
        owner.tabs.addTab(owner.tab_overview, "方案与结果汇总")
        index = owner.tabs.addTab(owner.tab_robust, name("robust_optimization"))
        owner.tabs.setTabToolTip(index, tooltip("robust_optimization"))
        index = owner.tabs.addTab(owner.tab_signif, name("regression_significance_lof"))
        owner.tabs.setTabToolTip(index, tooltip("regression_significance_lof"))
        index = owner.tabs.addTab(owner.tab_cv, name("cross_validation_residuals"))
        owner.tabs.setTabToolTip(index, tooltip("cross_validation_residuals"))
        owner.tabs.addTab(owner.tab_param, "参数取值")
        index = owner.tabs.addTab(owner.tab_tol, name("local_variance_contribution"))
        owner.tabs.setTabToolTip(index, tooltip("local_variance_contribution"))
        index = owner.tabs.addTab(owner.tab_model, name("model_coefficients"))
        owner.tabs.setTabToolTip(index, tooltip("model_coefficients"))
        owner.tabs.addTab(owner.tab_tools, "优化工具集")
        owner.screening_panel = DesignResultsPanel("screening")
        owner.taguchi_panel = DesignResultsPanel("taguchi")
        index = owner.tabs.addTab(owner.screening_panel, name("main_effect_analysis"))
        owner.tabs.setTabToolTip(index, tooltip("main_effect_analysis"))
        index = owner.tabs.addTab(owner.taguchi_panel, name("taguchi_analysis"))
        owner.tabs.setTabToolTip(index, tooltip("taguchi_analysis"))
        from frontend.theme import ResultsWorkspace, primary
        owner.results_workspace = ResultsWorkspace(owner.tabs)
        main_layout.addWidget(owner.results_workspace, 1)
        primary(owner.run_all_btn)

        owner.setLayout(main_layout)
        owner._oe_context = None
        owner._update_method_actions()
        for control in (owner.k_design_spin, owner.k_constraint_spin, owner.weight_spin, owner.pop_spin, owner.gen_spin,
                        owner.seed_spin, owner.crossover_spin, owner.mutation_spin, owner.eta_c_spin, owner.eta_m_spin):
            control.valueChanged.connect(owner._settings_changed)
        owner.robust_mode_combo.currentTextChanged.connect(owner._settings_changed)
        owner.mutation_mode_combo.currentIndexChanged.connect(owner._settings_changed)

def build_overview_tab(owner):
        layout = QVBoxLayout(owner.tab_overview)
        owner.overview = ResultOverview()
        owner.model_overview = owner.overview.model_overview
        owner.model_overview.detail_requested.connect(owner._show_model_detail)
        layout.addWidget(owner.overview)
        owner._refresh_view()

def build_robust_tab(owner):
        from PyQt6.QtWidgets import QScrollArea
        from frontend.pages.robust_settings import build_settings
        layout = QVBoxLayout(owner.tab_robust)
        layout.addWidget(label(name('robust_optimization'), 'heading'))
        owner.robust_scroll = QScrollArea()
        owner.robust_scroll.setWidgetResizable(True)
        owner.robust_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(18)
        build_settings(owner, column)
        owner.robust_mode_combo.currentTextChanged.connect(owner._on_robust_mode)
        owner._on_robust_mode()
        owner.pareto_fig = Figure(figsize=(5, 3.6), dpi=100, layout="constrained")
        owner.pareto_canvas = FigureCanvas(owner.pareto_fig)
        owner.robust_results = RobustResults(owner.pareto_canvas)
        column.addWidget(owner.robust_results)
        column.addStretch()
        owner.robust_scroll.setWidget(content)
        layout.addWidget(owner.robust_scroll)

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
        for term, value in (("steepest_descent", "最陡下降搜索"),
                            ("one_pass_ofat", "单轮单因子搜索"),
                            ("adaptive_ofat", "自适应单因子搜索")):
            add_combo_item(owner.tool_combo, term, value)
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
        owner.tool_start = QComboBox(); owner.tool_start.addItems(["优化返回点", "区间中心"])
        head.addWidget(owner.tool_start)
        owner.tool_weight = numeric_input(float, 0, 1, .5)
        weight_label = apply(QLabel(), "desirability_loss_weight")
        weight_label.setText(weight_label.text() + " λ")
        head.addWidget(weight_label); head.addWidget(owner.tool_weight)
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
