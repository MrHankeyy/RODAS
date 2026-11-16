
import json
import math
from copy import deepcopy
from dataclasses import asdict

from backend.domain.models import RUN_ID, factor_definition

RESULT_FIELDS = ("taguchi_result", "rsm_result", "surrogate_result", "workbench_result")
INPUT_FIELDS = (
    "task_type",
    "responses",
    "factors",
    "design_method",
    "design_params",
    "doe_matrix",
    "surrogate_config",
)
_operation_sink = None


def _run_id_key(row):
    for key in row:
        text = key.strip()
        if text == RUN_ID or text.replace(" ", "_").replace("-", "_").lower() == "run_id":
            return key
    return None


def with_run_ids(rows):
    if not rows:
        return rows
    numbered = []
    for index, row in enumerate(rows, 1):
        source = _run_id_key(row)
        others = {key: value for key, value in row.items() if key != source}
        value = "" if source is None else str(row.get(source, "")).strip()
        numbered.append({RUN_ID: value or str(index), **others})
    return numbered


def set_operation_sink(callback):
    global _operation_sink
    _operation_sink = callback


def _input_signature(project):
    return json.dumps(
        {
            "factors": [factor_definition(f) for f in project.factors],
            "responses": [asdict(r) for r in project.responses],
            "method": project.design_method,
            "params": project.design_params,
            "matrix": project.doe_matrix,
            "surrogate": project.surrogate_config,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )


class ProjectService:
    def __init__(self, project):
        self._project = project
        self._signature = _input_signature(project)
        self.model_cache = {}

    @classmethod
    def for_project(cls, project):
        if not hasattr(project, "_project_service"):
            project._project_service = cls(project)
        return project._project_service

    def input_snapshot(self):
        from backend.domain.models import ProjectData

        return ProjectData(**{key: deepcopy(getattr(self._project, key)) for key in INPUT_FIELDS})

    def input_signature(self):
        return _input_signature(self._project)

    def ensure_current(self):
        current = self.input_signature()
        changed = current != self._signature
        if changed:
            self._invalidate()
        self._signature = current
        return changed

    def _invalidate(self):
        for name in RESULT_FIELDS:
            setattr(self._project, name, {})
        self.model_cache.clear()

    def _commit_inputs(self, **values):
        prepared = {key: deepcopy(value) for key, value in values.items()}
        for key, value in prepared.items():
            setattr(self._project, key, value)
        return self.ensure_current()

    def update_definition(self, factors, responses):
        return self._commit_inputs(factors=factors, responses=responses)

    def commit_design(self, method, params, matrix, initial_results=None, surrogate_config=None):
        values = dict(design_method=method, design_params=params, doe_matrix=matrix)
        if surrogate_config is not None:
            values["surrogate_config"] = surrogate_config
        self._commit_inputs(**values)
        self._invalidate()
        self.publish_results(**(initial_results or {}))

    def update_responses(self, rows, expected_signature=None):
        self._check_source(expected_signature)
        response_names = {r.name for r in self._project.responses if r.name}
        if len(rows) != len(self._project.doe_matrix):
            raise ValueError("试验行数已改变，请重新载入试验数据表。")
        pending = deepcopy(self._project.doe_matrix)
        for index, row in enumerate(rows):
            for name in response_names:
                value = row.get(name, "")
                try:
                    parsed = float(value) if str(value).strip() else ""
                    if parsed != "" and not math.isfinite(parsed):
                        raise ValueError("响应必须是有限数字")
                    pending[index][name] = parsed
                except (TypeError, ValueError):
                    raise ValueError(f"第 {index + 1} 行 {name} 列填入的必须是数字（且为有限值）！")
        return self._commit_inputs(doe_matrix=pending)

    def replace_dataset(self, rows):
        return self._commit_inputs(doe_matrix=with_run_ids(rows))

    def update_report_metadata(self, metadata):
        self._project.report_metadata = deepcopy(metadata)

    def _check_source(self, expected_signature):
        if expected_signature is not None and self.input_signature() != expected_signature:
            raise ValueError("计算期间输入已改变，本次结果已丢弃，请重新运行。")

    def publish_results(self, expected_signature=None, **results):
        unknown = set(results) - set(RESULT_FIELDS)
        if unknown:
            raise ValueError("不支持的结果字段：" + ", ".join(sorted(unknown)))
        self._check_source(expected_signature)
        self.ensure_current()
        prepared = {key: deepcopy(value) for key, value in results.items()}
        for key, value in prepared.items():
            setattr(self._project, key, value)

    def clear_workbench(self):
        self._project.workbench_result = {}

    def update_workbench(self, expected_signature=None, **values):
        self._check_source(expected_signature)
        self.ensure_current()
        self._project.workbench_result.update(deepcopy(values))

    def record_operation(self, stage, status="完成", payload=None, message=""):
        if _operation_sink is not None:
            level = (
                "错误"
                if status == "失败"
                else "提醒"
                if status in ("未通过", "部分完成")
                else "成功"
            )
            _operation_sink(level, stage, status + ("：" + message if message else ""))
