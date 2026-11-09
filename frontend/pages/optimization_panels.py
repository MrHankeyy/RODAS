"""UI construction for OptimizationPage."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QGroupBox, QTextEdit, QMessageBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame,
    QLineEdit,
)

from frontend.pages.design_results import DesignResultsPanel
from frontend.pages.taguchi_results import TaguchiResultsPanel
from frontend.pages.result_overview import ResultOverview, label
from frontend.pages.analysis_results import AnalysisResults
from frontend.pages.robust_results import RobustResults
from frontend.pages.optimization_history import OptimizationHistory
from frontend.numeric_inputs import numeric_input
from frontend.terminology import add_combo_item, apply, name, tooltip


def build(owner):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 顶部：状态 + 主执行按钮
        top = QHBoxLayout()
        owner.primary_actions = top
        owner.status_label = QLabel("尚未运行鲁棒优化设计")
        owner.status_label.setProperty("role", "muted")
        owner.status_label.setWordWrap(True)
        top.addWidget(owner.status_label, 1)

        owner.run_all_btn = QPushButton("执行鲁棒优化设计")
        owner.run_all_btn.setToolTip(tooltip("robust_optimization"))
        owner.run_all_btn.setMinimumWidth(225)
        owner.run_all_btn.clicked.connect(owner._run_primary_action)
        owner.stats_btn = QPushButton("代理模型构建", owner)
        owner.stats_btn.clicked.connect(owner.run_statistics)
        top.addWidget(owner.run_all_btn)
        main_layout.addLayout(top)

        from frontend.theme import ResultTabs
        owner.tabs = ResultTabs()
        owner.tabs.setUsesScrollButtons(True)
        owner.tab_overview = QWidget(); owner._build_overview_tab()
        owner.tab_robust = QWidget(); owner._build_robust_tab()
        owner.tab_signif = QWidget(); owner._build_signif_tab()
        owner.tab_cv = QWidget(); owner._build_cv_tab()
        owner.tab_model = QWidget(); owner._build_model_tab()
        owner.tabs.addTab(owner.tab_overview, "方案与结果汇总")
        index = owner.tabs.addTab(owner.tab_robust, name("robust_optimization"))
        owner.tabs.setTabToolTip(index, tooltip("robust_optimization"))
        index = owner.tabs.addTab(owner.tab_signif, name("regression_significance_lof"))
        owner.tabs.setTabToolTip(index, tooltip("regression_significance_lof"))
        index = owner.tabs.addTab(owner.tab_cv, name("cross_validation_residuals"))
        owner.tabs.setTabToolTip(index, tooltip("cross_validation_residuals"))
        index = owner.tabs.addTab(owner.tab_model, name("model_coefficients"))
        owner.tabs.setTabToolTip(index, tooltip("model_coefficients"))
        owner.tabs.addTab(owner.robust_results.comparison, "方案对比")
        owner.tabs.addTab(owner.robust_results.verification, "波动核验")
        owner.screening_panel = DesignResultsPanel("screening")
        owner.taguchi_panel = TaguchiResultsPanel(owner.project_data)
        index = owner.tabs.addTab(owner.screening_panel, name("main_effect_analysis"))
        owner.tabs.setTabToolTip(index, tooltip("main_effect_analysis"))
        index = owner.tabs.addTab(owner.taguchi_panel, name("taguchi_analysis"))
        owner.tabs.setTabToolTip(index, tooltip("taguchi_analysis"))
        owner.tab_history = QWidget(); owner._build_history_tab()
        index = owner.tabs.addTab(owner.history_panel, name("optimization_history"))
        owner.tabs.setTabToolTip(index, tooltip("optimization_history"))
        from frontend.theme import ResultsWorkspace, primary
        owner.results_workspace = ResultsWorkspace(owner.tabs)
        main_layout.addWidget(owner.results_workspace, 1)
        primary(owner.run_all_btn)
        primary(owner.stats_btn)

        owner.setLayout(main_layout)
        owner._oe_context = None
        owner._update_method_actions()
        owner.tabs.currentChanged.connect(owner._update_method_actions)
        for control in (owner.weight_spin, owner.pop_spin, owner.gen_spin,
                        owner.seed_spin, owner.crossover_spin, owner.mutation_spin,
                        owner.eta_c_spin, owner.eta_m_spin,
                        owner.stall_gen_spin, owner.tolerance_spin):
            control.valueChanged.connect(owner._settings_changed)
        owner.auto_stop_check.toggled.connect(owner._settings_changed)
        owner.robust_mode_combo.currentTextChanged.connect(owner._settings_changed)
        owner.mutation_mode_combo.currentIndexChanged.connect(owner._settings_changed)

def build_overview_tab(owner):
        layout = QVBoxLayout(owner.tab_overview)
        owner.overview = ResultOverview()
        owner.overview.settings_header.addWidget(owner.stats_btn)
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
        content.setObjectName('resultsSurface')
        column = QVBoxLayout(content)
        column.setContentsMargins(8, 6, 8, 12)
        column.setSpacing(24)
        from frontend.theme import content_zone
        owner.robust_settings_zone, settings_layout = content_zone()
        owner.robust_settings_header = QHBoxLayout()
        owner.robust_settings_heading = label('鲁棒优化设置', 'sectionHeading')
        owner.robust_settings_header.addWidget(owner.robust_settings_heading)
        owner.robust_settings_header.addStretch()
        settings_layout.addLayout(owner.robust_settings_header)
        build_settings(owner, settings_layout)
        column.addWidget(owner.robust_settings_zone)
        owner.robust_mode_combo.currentTextChanged.connect(owner._on_robust_mode)
        owner._on_robust_mode()
        owner.robust_results = RobustResults()
        owner.robust_results.detail_requested.connect(
            lambda key: owner.tabs.setCurrentWidget(getattr(owner.robust_results, key)))
        for view in (owner.robust_results.comparison, owner.robust_results.verification):
            view.overview_requested.connect(lambda: owner.tabs.setCurrentWidget(owner.tab_robust))
        owner.robust_results.selection_changed.connect(
            lambda index: owner.project_service.update_workbench(optimization_view_index=index))
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


def build_model_tab(owner):
        layout = QVBoxLayout(owner.tab_model)
        owner.model_panel = AnalysisResults("model")
        layout.addWidget(owner.model_panel)


def build_history_tab(owner):
        layout = QVBoxLayout(owner.tab_history)
        layout.setContentsMargins(0, 0, 0, 0)
        owner.history_panel = OptimizationHistory()
        layout.addWidget(owner.history_panel)
