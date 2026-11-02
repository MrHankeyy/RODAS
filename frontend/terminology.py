"""Central user-facing terminology and tooltip formatting."""
from PyQt6.QtCore import Qt


# key: (Chinese display name, English full name, optional abbreviation)
TERMS = {
    "task_robust": ("基于代理模型的鲁棒性优化设计", "Surrogate-Based Robust Design Optimization", "SBRDO"),
    "taguchi_design": ("田口设计", "Taguchi Design", ""),
    "factor_screening": ("因子筛选", "Factor Screening", ""),
    "screening_design": ("筛选试验设计", "Screening Design", ""),
    "full_factorial": ("全因子设计", "Full Factorial Design", ""),
    "half_fraction": ("二分之一部分因子设计", "One-Half Fractional Factorial Design", ""),
    "quarter_fraction": ("四分之一部分因子设计", "One-Quarter Fractional Factorial Design", ""),
    "plackett_burman": ("普拉克特–伯曼设计", "Plackett–Burman Design", "PB"),
    "quadratic_response_surface": ("二次响应面模型", "Quadratic Response Surface Model", ""),
    "kriging": ("克里金模型", "Kriging Model", ""),
    "svr": ("支持向量回归模型", "Support Vector Regression Model", "SVR"),
    "bpnn": ("神经网络模型", "Neural Network Model", "NN"),
    "ccd": ("中心复合设计", "Central Composite Design", "CCD"),
    "bbd": ("博克斯–贝恩肯设计", "Box–Behnken Design", "BBD"),
    "full_quadratic_model": ("完整二次模型", "Full Quadratic Model", ""),
    "gaussian_correlation": ("高斯相关函数", "Gaussian Correlation Function", ""),
    "exponential_correlation": ("指数相关函数", "Exponential Correlation Function", ""),
    "matern_32_correlation": ("马特恩三分之二相关函数", "Matérn 3/2 Correlation Function", ""),
    "ordinary_trend": ("常数趋势", "Ordinary Trend", ""),
    "linear_trend": ("一次趋势", "Linear Trend", ""),
    "quadratic_trend": ("二次趋势", "Quadratic Trend", ""),
    "rbf_kernel": ("径向基函数核", "Radial Basis Function Kernel", "RBF"),
    "polynomial_kernel": ("多项式核", "Polynomial Kernel", ""),
    "sigmoid_kernel": ("双曲正切核", "Sigmoid Kernel", ""),
    "logistic_sigmoid": ("逻辑S形函数", "Logistic Sigmoid Function", ""),
    "hyperbolic_tangent": ("双曲正切函数", "Hyperbolic Tangent Function", "tanh"),
    "relu": ("修正线性单元", "Rectified Linear Unit", "ReLU"),
    "lhs": ("拉丁超立方采样", "Latin Hypercube Sampling", "LHS"),
    "maximin_lhs": ("最大最小距离优化拉丁超立方采样", "Maximin Latin Hypercube Sampling", "Maximin LHS"),
    "sobol": ("索博尔序列", "Sobol Sequence", ""),
    "uniform_grid": ("均匀网格采样", "Uniform Grid Sampling", ""),
    "low_dimensional_combination": ("低维组合采样", "Low-Dimensional Combination Sampling", ""),
    "random_sampling": ("随机采样", "Random Sampling", ""),
    "robust_strategy": ("鲁棒优化策略", "Robust Optimization Strategy", ""),
    "multiobjective_nsga2": ("多目标优化（帕累托）", "Pareto Multi-Objective Optimization", ""),
    "weighted_single_objective": ("加权目标优化", "Weighted-Objective Optimization", ""),
    "constrained_optimization": ("波动约束优化", "Variability-Constrained Optimization", ""),
    "robust_optimization": ("鲁棒性优化设计", "Robust Design Optimization", "RDO"),
    "regression_significance_lof": ("统计检验", "Statistical Tests", ""),
    "holdout_validation": ("留出法验证", "Holdout Validation", ""),
    "cross_validation_residuals": ("验证与残差", "Validation and Residuals", ""),
    "model_coefficients": ("模型与系数", "Model and Coefficients", ""),
    "local_variance_contribution": ("局部方差贡献分析", "Local Variance Contribution Analysis", ""),
    "main_effect_analysis": ("主效应分析", "Main-Effect Analysis", ""),
    "taguchi_analysis": ("田口分析", "Taguchi Analysis", ""),
    "steepest_descent": ("最陡下降搜索", "Steepest Descent Search", ""),
    "one_pass_ofat": ("单轮单因子搜索", "One-Pass One-Factor-at-a-Time Search", "OFAT"),
    "adaptive_ofat": ("自适应单因子搜索", "Adaptive One-Factor-at-a-Time Search", "AOFAT"),
    "compromise_solution": ("折中解", "Compromise Solution", ""),
    "desirability_loss": ("望性损失", "Desirability Loss", ""),
    "mean_desirability": ("平均望性", "Mean Desirability", ""),
    "normalized_standard_deviation": ("归一化标准差", "Normalized Standard Deviation", ""),
    "desirability_loss_weight": ("望性损失权重", "Desirability Loss Weight", ""),
    "variability_weight": ("波动权重", "Variability Weight", ""),
    "constraint_margin_multiplier": ("约束裕量系数", "Constraint Margin Multiplier", ""),
    "interval_std_factor": ("区间标准差换算系数", "Interval-to-Standard-Deviation Conversion Factor", ""),
    "response_limit": ("响应阈值", "Response Limit", ""),
    "main_effect": ("主效应", "Main Effect", ""),
    "squared_main_effect_share": ("主效应平方占比", "Squared Main-Effect Share", ""),
    "holdout_r2": ("测试集决定系数", "Test-Set Coefficient of Determination", "R²"),
    "adjusted_r2": ("调整决定系数", "Adjusted Coefficient of Determination", "Adjusted R²"),
    "nmae": ("归一化平均绝对误差", "Normalized Mean Absolute Error", "NMAE"),
    "r2": ("决定系数", "Coefficient of Determination", "R²"),
    "rmse": ("均方根误差", "Root Mean Squared Error", "RMSE"),
    "anova": ("回归方差分析", "Analysis of Variance", "ANOVA"),
    "snr": ("信噪比", "Signal-to-Noise Ratio", "S/N"),
    "doe": ("试验设计", "Design of Experiments", "DOE"),
}


# Chinese display name: (English name, abbreviation or symbol, short explanation)
STATISTICS = {
    "模型类型": ("Model Type", "", "当前已训练模型的类型"),
    "训练样本数": ("Training Sample Size", "", "参与当前模型训练的数据条数"),
    "有效验证样本数": ("Validation Sample Size", "", "参与有效验证的数据条数"),
    "交叉验证决定系数": ("Cross-Validated Coefficient of Determination", "CV R²", "基于分折留出预测计算的决定系数"),
    "交叉验证均方根误差": ("Cross-Validated Root Mean Squared Error", "CV RMSE", "分折留出预测的误差大小，单位同响应"),
    "编码项": ("Coded Model Term", "", "系数对应的编码变量模型项"),
    "估计值": ("Coefficient Estimate", "", "当前模型项的系数估计"),
    "标准误": ("Standard Error", "SE", "系数估计的标准误差"),
    "系数检验统计量": ("Coefficient t-statistic", "t", "系数估计值与标准误的比值"),
    "检验统计量": ("F-statistic", "F", "整体回归或失拟检验的统计量"),
    "概率值": ("p-value", "p", "在零假设下观察到当前或更极端统计量的概率"),
    "未校正概率值": ("Unadjusted p-value", "p", "检验系数是否为零，未校正多重比较"),
    "95%下限": ("Lower Confidence Limit", "", "系数95%置信区间下限，不是响应预测区间"),
    "95%上限": ("Upper Confidence Limit", "", "系数95%置信区间上限，不是响应预测区间"),
    "响应": ("Response", "", "当前统计所对应的响应变量"),
    "有效数": ("Valid Count", "", "可用于统计的有效数值个数"),
    "缺失或无效": ("Missing or Invalid Count", "", "缺失、非数值或非有限值的个数"),
    "最小值": ("Minimum", "", "有效数据中的最小数值"),
    "第一四分位数": ("First Quartile", "Q1", "数据的25%分位数"),
    "中位数": ("Median", "Q2", "数据的50%分位数"),
    "第三四分位数": ("Third Quartile", "Q3", "数据的75%分位数"),
    "最大值": ("Maximum", "", "有效数据中的最大数值"),
    "均值": ("Arithmetic Mean", "", "有效数据的算术平均值"),
    "样本标准差": ("Sample Standard Deviation", "SD", "衡量数据围绕均值的离散程度"),
    "四分位距": ("Interquartile Range", "IQR", "第三与第一四分位数之差"),
    "偏度": ("Skewness", "", "衡量分布不对称，正值表示右偏"),
    "超额峰度": ("Excess Kurtosis", "", "衡量尾部厚重程度，正态分布为零"),
    "拟合决定系数": ("In-Sample Coefficient of Determination", "R²", "衡量模型对拟合数据的解释程度"),
    "调整决定系数": ("Adjusted Coefficient of Determination", "Adjusted R²", "考虑参数数量后的决定系数"),
    "拟合均方根误差": ("In-Sample Root Mean Squared Error", "RMSE", "拟合误差大小，单位同响应"),
    "测试集决定系数": ("Test-Set Coefficient of Determination", "R²", "衡量模型对测试数据的解释程度"),
    "归一化平均绝对误差": ("Normalized Mean Absolute Error", "NMAE", "按实测绝对值均值归一化的误差"),
    "因子": ("Factor", "", "对响应影响进行分析的输入变量"),
    "主效应": ("Main Effect", "", "高水平与低水平的平均响应之差"),
    "主效应平方占比": ("Squared Main-Effect Share", "", "各主效应平方占总和的比例"),
    "控制因子": ("Control Factor", "", "可主动设置水平的试验因子"),
    "候选水平": ("Candidate Level", "", "主效应分析推荐的因子取值"),
    "内表组": ("Inner Array Run", "", "田口内表中的控制因子组合"),
    "标准差": ("Standard Deviation", "SD", "衡量数据围绕均值的离散程度"),
    "信噪比": ("Signal-to-Noise Ratio", "S/N", "综合反映目标特征与波动的指标"),
    "均值指标": ("Mean-Based Metric", "", "无重复观测时用于比较水平的指标"),
    "数据来源": ("Data Source", "", "当前统计使用的训练集或验证集"),
    "样本数": ("Sample Size", "", "参与当前统计计算的数据条数"),
    "决定系数": ("Coefficient of Determination", "R²", "衡量模型解释响应变异的程度"),
    "均方根误差": ("Root Mean Squared Error", "RMSE", "衡量预测误差大小，单位同响应"),
    "平均绝对误差": ("Mean Absolute Error", "MAE", "预测值与实测值的绝对误差均值"),
    "最大绝对误差": ("Maximum Absolute Error", "", "所有预测中最大的绝对误差"),
    "残差均值": ("Mean Residual", "", "实测值减预测值所得差值的均值"),
    "残差样本标准差": ("Sample Standard Deviation of Residuals", "", "衡量残差围绕其均值的离散程度"),
    "参数数量": ("Number of Parameters", "", "模型估计的系数数量，含常数项"),
    "残差自由度": ("Residual Degrees of Freedom", "", "样本数减去模型参数数量"),
    "设计矩阵条件数": ("Condition Number of the Design Matrix", "", "衡量矩阵对数值扰动的敏感程度"),
    "回归平方和": ("Regression Sum of Squares", "SSR", "模型解释的响应变异总量"),
    "残差平方和": ("Residual Sum of Squares", "SSE", "实测值与预测值之差的平方和"),
    "总平方和": ("Total Sum of Squares", "SST", "实测值偏离其均值的平方和"),
    "回归检验统计量": ("Regression F-statistic", "F", "比较回归解释量与残差变异"),
    "回归检验概率值": ("Regression p-value", "p", "越小越支持模型整体具有解释力"),
    "纯误差自由度": ("Pure Error Degrees of Freedom", "", "重复试验提供的误差自由度"),
    "纯误差平方和": ("Pure Error Sum of Squares", "", "相同输入下重复响应的组内平方和"),
    "失拟自由度": ("Lack-of-Fit Degrees of Freedom", "", "残差自由度减去纯误差自由度"),
    "失拟检验统计量": ("Lack-of-Fit F-statistic", "F", "比较模型失拟与重复试验误差"),
    "失拟检验概率值": ("Lack-of-Fit p-value", "p", "越小越提示模型形式可能不合适"),
    "留一预测残差平方和": ("Leave-One-Out Prediction Residual Sum of Squares", "LOO PRESS", "逐点留出预测误差的平方和"),
    "留一预测均方根误差": ("Leave-One-Out Root Mean Squared Error", "LOO RMSE", "留一验证的预测误差，单位同响应"),
    "留一预测决定系数": ("Leave-One-Out Predicted Coefficient of Determination", "LOO R²", "衡量留一验证中的预测解释程度"),
    "残差正态性检验概率值": ("Shapiro–Wilk Test p-value", "p", "越小越提示残差偏离正态分布"),
}

STATISTIC_ALIASES = {
    "t": "系数检验统计量", "未校正 p": "未校正概率值",
    "R²": "决定系数", "RMSE": "均方根误差", "MAE": "平均绝对误差",
    "参数数": "参数数量", "回归 F": "回归检验统计量", "回归 p": "回归检验概率值",
    "失拟 F": "失拟检验统计量", "失拟 p": "失拟检验概率值",
    "LOO PRESS": "留一预测残差平方和", "LOO RMSE": "留一预测均方根误差",
    "预测 R² (LOO)": "留一预测决定系数", "残差 Shapiro p": "残差正态性检验概率值",
}


def statistic_name(text):
    return STATISTIC_ALIASES.get(text, text)


def statistic_tooltip(text):
    chinese = statistic_name(text).split('（')[0]
    term = STATISTICS.get(chinese)
    if term is None:
        return ""
    english, abbreviation, explanation = term
    suffix = f"，{abbreviation}" if abbreviation else ""
    return f"{chinese}（{english}{suffix}）\n{explanation}"


def name(key):
    return TERMS[key][0]


def tooltip(key):
    chinese, english, abbreviation = TERMS[key]
    statistical = statistic_tooltip(chinese)
    if statistical:
        return statistical
    suffix = f"，{abbreviation}" if abbreviation else ""
    explanation = {
        "robust_strategy": "选择如何在优化中处理响应的目标表现与波动性；三种策略均遵守业务建模中定义的响应约束。",
        "multiobjective_nsga2": "将目标表现与波动性分别作为优化目标，得到多个折中方案。",
        "constrained_optimization": "为波动性设置上限，在满足限制的条件下优化目标表现。",
        "weighted_single_objective": "将归一化的目标损失与波动性按权重合成为一个优化目标。",
    }.get(key, "")
    return f"{chinese}（{english}{suffix}）" + ("\n" + explanation if explanation else "")


def apply(widget, key):
    """Set a widget's visible Chinese name and bilingual term tooltip."""
    widget.setText(name(key))
    widget.setToolTip(tooltip(key))
    widget.setAccessibleDescription(tooltip(key))
    return widget


def add_combo_item(combo, key, data=None):
    """Add a Chinese-only combo item while retaining an independent internal value."""
    combo.addItem(name(key), data)
    index = combo.count() - 1
    combo.setItemData(index, tooltip(key), Qt.ItemDataRole.ToolTipRole)
    if not combo.property("termTooltipBound"):
        combo.currentIndexChanged.connect(lambda _index, target=combo: _sync_combo_tooltip(target))
        combo.setProperty("termTooltipBound", True)
    _sync_combo_tooltip(combo)
    return index


def _sync_combo_tooltip(combo):
    text = combo.itemData(combo.currentIndex(), Qt.ItemDataRole.ToolTipRole) or ""
    combo.setToolTip(text)
    combo.setAccessibleDescription(text)


def set_tab(tabs, index, key):
    tabs.setTabText(index, name(key))
    tabs.setTabToolTip(index, tooltip(key))


HEADER_TERMS = {
    "主效应": "main_effect",
    "主效应平方占比（%）": "squared_main_effect_share",
    "测试集决定系数": "holdout_r2",
    "调整决定系数": "adjusted_r2",
    "归一化平均绝对误差（%）": "nmae",
    "响应阈值": "response_limit",
    "信噪比（dB）": "snr",
}


def apply_header_tooltips(table):
    """Attach the approved bilingual expansion to known Chinese table headers."""
    for column in range(table.columnCount()):
        item = table.horizontalHeaderItem(column)
        key = HEADER_TERMS.get(item.text()) if item else None
        if item:
            item.setToolTip(statistic_tooltip(item.text()) or (tooltip(key) if key else ""))


CELL_TERMS = {
    "二次响应面模型": "quadratic_response_surface",
    "克里金模型": "kriging",
    "支持向量回归模型": "svr",
    "神经网络模型": "bpnn",
    "多目标优化（帕累托）": "multiobjective_nsga2",
    "加权目标优化": "weighted_single_objective",
    "波动约束优化": "constrained_optimization",
    "约束裕量系数 k": "constraint_margin_multiplier",
    "区间标准差换算系数 k": "interval_std_factor",
    "望性损失权重 λ": "desirability_loss_weight",
    "波动权重": "variability_weight",
    "平均望性": "mean_desirability",
    "归一化标准差": "normalized_standard_deviation",
}


def apply_item_tooltip(item):
    key = CELL_TERMS.get(item.text())
    if key:
        item.setToolTip(tooltip(key))
    elif statistical := statistic_tooltip(item.text()):
        item.setToolTip(statistical)
    return item
