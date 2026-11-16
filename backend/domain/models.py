from dataclasses import asdict, dataclass, field

TASK_TYPES = {
    "robust": "基于代理模型的鲁棒优化设计",
    "taguchi": "田口设计",
}
RUN_ID = "试验序号"


def factor_title(source, task_type="robust"):
    if task_type == "taguchi":
        return "控制因子" if source == "设计" else "噪声因子"
    return "设计变量" if source == "设计" else "不确定性参数"


@dataclass
class ResponseItem:
    name: str = ""
    kind: str = "目标"
    feature: str = "望小"
    lower: str = ""
    upper: str = ""
    robust_limit: str = ""
    unit: str = ""
    target: str = ""


@dataclass
class FactorItem:
    name: str = ""
    source: str = "设计"
    uncertainty: str = "区间"
    distribution: str = "无"
    param1: str = ""
    param2: str = ""
    fixed_value: str = ""
    is_fixed: bool = False
    unit: str = ""
    nominal_lower: str = ""
    nominal_upper: str = ""


def factor_definition(factor):
    values = asdict(factor)
    if not factor.nominal_lower and not factor.nominal_upper:
        values.pop("nominal_lower")
        values.pop("nominal_upper")
    return values


@dataclass
class ProjectData:
    responses: list[ResponseItem] = field(default_factory=list)
    factors: list[FactorItem] = field(default_factory=list)

    design_method: str = ""
    design_params: dict = field(default_factory=dict)
    doe_matrix: list[dict] = field(default_factory=list)

    taguchi_result: dict = field(default_factory=dict)

    rsm_result: dict = field(default_factory=dict)
    surrogate_config: dict = field(default_factory=dict)
    surrogate_result: dict = field(default_factory=dict)
    workbench_result: dict = field(default_factory=dict)
    report_metadata: dict = field(default_factory=dict)
    report_history: list[dict] = field(default_factory=list)
    task_type: str = ""
