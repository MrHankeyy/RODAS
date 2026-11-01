from dataclasses import dataclass, field, asdict


TASK_TYPES = {
    'robust': '基于代理模型的鲁棒性优化设计',
    'taguchi': '田口设计',
    'factorial': '因子筛选',
}


@dataclass
class ResponseItem:
    name: str = ""
    kind: str = "目标"          # 目标 / 约束 / 目标+约束
    feature: str = "望小"       # 望大 / 望小 / 望目
    lower: str = ""             # 望目时: 响应阈值下界
    upper: str = ""             # 望目时: 响应阈值上界
    robust_limit: str = ""      # 响应阈值: 望大=要求最小值, 望小=要求最大值
    unit: str = ""
    target: str = ""           # 田口望目响应的目标值，与规格限分开


@dataclass
class FactorItem:
    name: str = ""
    source: str = "设计"        # 设计 / 环境
    uncertainty: str = "区间"   # 区间 或 概率
    distribution: str = "无"    # 正态分布, 均匀分布, 等
    param1: str = ""            # 设计：偏差下界/均值；环境：实际下界/均值
    param2: str = ""            # 设计：偏差上界/方差；环境：实际上界/方差
    fixed_value: str = ""       # 仅兼容已有任务；新编辑器不提供固定值
    is_fixed: bool = False      # 仅兼容旧任务的模型维度
    unit: str = ""
    nominal_lower: str = ""    # 设计的独立名义范围；环境留空
    nominal_upper: str = ""    # 环境旧任务可带名义范围，提交后转为实际取值参数


def factor_definition(factor):
    """Keep legacy input signatures stable when loading archives without nominal bounds."""
    values = asdict(factor)
    if not factor.nominal_lower and not factor.nominal_upper:
        values.pop('nominal_lower')
        values.pop('nominal_upper')
    return values


@dataclass
class ProjectData:
    responses: list[ResponseItem] = field(default_factory=list)
    factors: list[FactorItem] = field(default_factory=list)

    # 方案配置与DOE数据
    design_method: str = ""
    design_params: dict = field(default_factory=dict)
    doe_matrix: list[dict] = field(default_factory=list) # 存储生成的DOE表格数据与测试结果

    # 真实分析结果（筛选与田口）
    screening_result: dict = field(default_factory=dict)
    taguchi_result: dict = field(default_factory=dict)

    # 响应曲面 / 代理模型分析结果
    rsm_result: dict = field(default_factory=dict)
    surrogate_config: dict = field(default_factory=dict)   # 方案配置中选择的代理模型参数
    surrogate_result: dict = field(default_factory=dict)   # 后端训练/评估结果
    workbench_result: dict = field(default_factory=dict)   # 可序列化的工作台分析快照
    report_metadata: dict = field(default_factory=dict)
    report_history: list[dict] = field(default_factory=list)
    task_type: str = ""        # 创建任务时选择的主线；尚未生成试验方案
