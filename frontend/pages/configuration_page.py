"""Three parallel workflows with independent, inline model and DOE choices."""
from copy import deepcopy

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QGroupBox, QStackedWidget, QSizePolicy, QAbstractSpinBox, QSpinBox,
)

from backend.domain.models import ProjectData
from backend.services import design_service
from backend.services.project_service import ProjectService
from backend.reporting.math_format import rich_text
from frontend.notifications import Notice
from frontend.numeric_inputs import commit_numeric_inputs
from frontend.pages import configuration_panels
from frontend.pages.model_configuration import ModelConfiguration, MODEL_TITLES


class ConfigurationPage(QWidget):
    MODEL_KEYS = ("RSM", "Kriging", "SVR", "ANN")

    def __init__(self, project_data: ProjectData):
        super().__init__()
        self.project_data = project_data
        self._applied_state = None
        self._definition = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(180)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self.init_ui()

    def init_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(12)
        group = QGroupBox("方案配置")
        column = QVBoxLayout(group)
        row = QHBoxLayout()
        row.addWidget(QLabel("方案类型："))
        self.method_combo = QComboBox()
        self.method_combo.addItems(["因子筛选分析", "田口稳健设计", "代理建模与鲁棒优化"])
        row.addWidget(self.method_combo, 1)
        self.model_label = QLabel("模型类型：")
        row.addWidget(self.model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems([MODEL_TITLES[key] for key in self.MODEL_KEYS])
        row.addWidget(self.model_combo, 1)
        column.addLayout(row)
        self.dynamic_params_widget = QStackedWidget()
        self.dynamic_params_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.screening_widget = configuration_panels.screening(self)
        self.taguchi_widget = configuration_panels.taguchi(self)
        self.model_stack = QStackedWidget()
        self.model_editors = {}
        for key in self.MODEL_KEYS:
            editor = ModelConfiguration(key, self._design_factors(), config=self._saved_config(key))
            self.model_editors[key] = editor
            self.model_stack.addWidget(editor)
        for widget in (self.screening_widget, self.taguchi_widget, self.model_stack):
            self.dynamic_params_widget.addWidget(widget)
        column.addWidget(self.dynamic_params_widget)
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setProperty("role", "muted")
        column.addWidget(self.preview_label)
        self.config_status = QLabel("尚未生成试验方案")
        self.config_status.setWordWrap(True)
        self.config_status.setProperty("role", "badge")
        column.addWidget(self.config_status)
        main.addWidget(group)
        row = QHBoxLayout()
        row.addStretch()
        self.refresh_btn = QPushButton("刷新问题定义")
        self.refresh_btn.clicked.connect(self.update_info_display)
        row.addWidget(self.refresh_btn)
        self.gen_btn = QPushButton("生成试验方案")
        from frontend.theme import primary
        primary(self.gen_btn)
        self.gen_btn.clicked.connect(self.on_generate_clicked)
        row.addWidget(self.gen_btn)
        main.addLayout(row)
        main.addStretch()
        self._on_taguchi_levels()
        self.method_combo.currentIndexChanged.connect(self._on_selection_changed)
        self.model_combo.currentIndexChanged.connect(self._on_selection_changed)
        for editor in self.model_editors.values():
            editor.changed.connect(self._configuration_changed)
        for widget in (self.screening_widget, self.taguchi_widget):
            for control in widget.findChildren(QComboBox):
                control.currentIndexChanged.connect(self._configuration_changed)
            for control in widget.findChildren(QSpinBox):
                control.valueChanged.connect(self._configuration_changed)
        if self.project_data.design_method:
            self._select_method(self.project_data.design_method)
            self._restore_classical_settings()
        self.update_info_display()
        self._on_selection_changed()
        if self.project_data.doe_matrix:
            key = self.MODEL_KEYS[self.model_combo.currentIndex()]
            saved = self._saved_config(key) if self.method_combo.currentIndex() == 2 else None
            if saved and saved.get("doe_method") not in design_service.MODEL_DESIGNS[key]:
                self.config_status.setText("原方案使用了当前不支持的搭配；当前已选默认试验设计，重新生成后生效")
            else:
                self._applied_state = deepcopy(self._draft_state())
                self.config_status.setText("当前配置已生成试验方案")

    def _saved_config(self, key):
        saved = self.project_data.design_params.get("model_config", {})
        if saved.get("model") == key:
            return saved
        saved = self.project_data.surrogate_config or {}
        if saved.get("model") == key:
            return saved
        if key == "RSM" and "响应曲面" in self.project_data.design_method:
            meta = self.project_data.design_params.get("meta", {})
            return dict(model=key, doe_method="BBD" if "Box-Behnken" in meta.get("design", "") else "CCD",
                centers=meta.get("centers", 3), replicates=meta.get("replicates", 1),
                alpha=meta.get("alpha") or 1, alpha_mode="custom")
        return None

    def _selected_method(self):
        category = self.method_combo.currentIndex()
        if category == 0:
            return "两水平筛选设计（全因子/部分析因/PB）"
        if category == 1:
            return "田口稳健设计（内表×外表）"
        key = self.MODEL_KEYS[self.model_combo.currentIndex()]
        return "响应曲面设计" if key == "RSM" else f"代理模型建模 · {'BP 神经网络' if key == 'ANN' else key}"

    def _restore_classical_settings(self):
        params = self.project_data.design_params
        meta = params.get("meta", {})
        if self.method_combo.currentIndex() == 0:
            kind = meta.get("kind", "")
            self.screen_kind_combo.setCurrentIndex(1 if "1/2" in kind else 2 if "1/4" in kind else 3 if "Plackett" in kind else 0)
            self.f_topn_spin.setValue(params.get("top_n", 5))
            self.f_center_spin.setValue(meta.get("centers", 2))
            self.f_repeat_spin.setValue(meta.get("replicates", 1))
            self.f_seed_spin.setValue(params.get("seed", 123))
            self.f_order_combo.setCurrentIndex(0 if params.get("randomize", True) else 1)
        elif self.method_combo.currentIndex() == 1:
            self.t_levels_combo.setCurrentIndex(0 if meta.get("levels", 2) == 2 else 1)
            self.t_noise_levels_combo.setCurrentIndex(0 if meta.get("noise_level_count", 2) in (0, 2) else 1)
            for combo, key in ((self.t_inner_combo, "inner_label"), (self.t_outer_combo, "outer_label")):
                index = next((i for i in range(combo.count()) if combo.itemText(i).startswith(meta.get(key, "无"))), 0)
                combo.setCurrentIndex(index)
            self.t_repeat_spin.setValue(meta.get("replicates", 1))
            self.t_snr_combo.setCurrentText(params.get("snr_mode", "按各响应目标特征自动"))
            self.t_seed_spin.setValue(params.get("seed", 789))
            self.t_order_combo.setCurrentIndex(0 if params.get("randomize", True) else 1)

    def _select_method(self, method):
        if "筛选" in method:
            self.method_combo.setCurrentIndex(0)
        elif "田口" in method:
            self.method_combo.setCurrentIndex(1)
        else:
            key = "RSM" if "响应曲面" in method else "Kriging" if "Kriging" in method else "SVR" if "SVR" in method else "ANN"
            self.model_combo.setCurrentIndex(self.MODEL_KEYS.index(key))
            self.method_combo.setCurrentIndex(2)

    def _on_selection_changed(self, *_args):
        model = self.method_combo.currentIndex() == 2
        self.model_label.setVisible(model)
        self.model_combo.setVisible(model)
        self.model_stack.setCurrentIndex(self.model_combo.currentIndex())
        self.dynamic_params_widget.setCurrentIndex(self.method_combo.currentIndex())
        self._configuration_changed()

    def _fit_dynamic_params(self):
        editor = self.model_stack.currentWidget()
        self.model_stack.setFixedHeight(editor.sizeHint().height() + 2)
        current = self.dynamic_params_widget.currentWidget()
        self.dynamic_params_widget.setFixedHeight(current.sizeHint().height() + 2)

    def _configuration_changed(self, *_args):
        self._fit_dynamic_params()
        if self._applied_state != self._draft_state():
            self.config_status.setText("配置已修改，尚未生成试验方案" if not self.project_data.doe_matrix else "配置已修改，尚未重新生成方案；现有试验数据仍属于原方案")
        else:
            self.config_status.setText("当前配置已生成试验方案")
        self._preview_timer.start()

    def _draft_state(self):
        widget = self.dynamic_params_widget.currentWidget()
        if self.method_combo.currentIndex() == 2:
            widget = self.model_stack.currentWidget()
        controls = ([c.currentText() for c in widget.findChildren(QComboBox)],
                    [c.text() for c in widget.findChildren(QAbstractSpinBox)])
        bounds = getattr(widget, "bounds_table", None)
        ranges = [[bounds.item(i, j).text() for j in (1, 2)] for i in range(bounds.rowCount())] if bounds else []
        return self._selected_method(), repr(self.project_data.factors), repr(self.project_data.responses), controls, ranges

    def _design_factors(self):
        return [f for f in self.project_data.factors if f.name and f.source == "设计" and not f.is_fixed]

    def _noise_factors(self):
        return [f for f in self.project_data.factors if f.name and f.source == "环境" and not f.is_fixed]

    def update_info_display(self):
        definition = repr(self.project_data.factors)
        if definition != self._definition:
            for editor in self.model_editors.values():
                editor.set_factors(self._design_factors())
            self._definition = definition
        self._configuration_changed()

    @staticmethod
    def _reset_combo(combo, items):
        previous = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        if previous in items:
            combo.setCurrentText(previous)
        combo.blockSignals(False)

    def _on_taguchi_levels(self, *_args):
        inner = ["L4 (2^3)", "L8 (2^7)", "L12 (2^11)", "L16 (2^15)"] if self.t_levels_combo.currentIndex() == 0 else ["L9 (3^4)", "L27 (3^13)"]
        outer = ["L4 (2^3)", "L8 (2^7)", "L12 (2^11)", "L16 (2^15)"] if self.t_noise_levels_combo.currentIndex() == 0 else ["L9 (3^4)", "L27 (3^13)"]
        self._reset_combo(self.t_inner_combo, ["自动推荐", *inner])
        self._reset_combo(self.t_outer_combo, ["无（仅内表）", "自动推荐", *outer])

    def _resolve_oa(self, label, k, levels):
        if label.startswith("无") or k == 0:
            return "无"
        if label != "自动推荐":
            return label.replace(" (", "(")
        from backend.engines import doe
        for candidate in (["L4", "L8", "L12", "L16"] if levels == 2 else ["L9", "L27"]):
            try:
                doe.taguchi_arrays(candidate, k)
                return candidate
            except ValueError:
                pass
        raise ValueError("因子数量超过当前正交表的容量")

    def _build_plan(self, preview=False):
        if not preview and self.method_combo.currentIndex() != 2:
            commit_numeric_inputs(self.dynamic_params_widget.currentWidget())
        method = self._selected_method()
        if "筛选" in method:
            return design_service.screening_plan(self.project_data, method,
                ("full", "half", "quarter", "pb")[self.screen_kind_combo.currentIndex()],
                self.f_seed_spin.value(), self.f_center_spin.value(), self.f_repeat_spin.value(),
                self.f_order_combo.currentText() == "随机", self.f_topn_spin.value())
        if "田口" in method:
            levels = 2 if self.t_levels_combo.currentIndex() == 0 else 3
            noise_levels = 2 if self.t_noise_levels_combo.currentIndex() == 0 else 3
            return design_service.taguchi_plan(self.project_data, method,
                self._resolve_oa(self.t_inner_combo.currentText(), len(self._design_factors()), levels),
                self._resolve_oa(self.t_outer_combo.currentText(), len(self._noise_factors()), noise_levels),
                levels, self.t_seed_spin.value(), self.t_repeat_spin.value(),
                self.t_order_combo.currentText() == "随机", self.t_snr_combo.currentText())
        editor = self.model_stack.currentWidget()
        return design_service.model_plan(self.project_data, method,
            editor.collect_config(commit=not preview), preview=preview)

    def _refresh_preview(self):
        try:
            plan = self._build_plan(preview=True)
            meta = plan.params.get("meta", {})
            self.preview_label.setText(rich_text(f"预计试验次数：{meta.get('total_runs', len(plan.rows))} 次\n"
                f"{meta.get('bounds_note', '')}"))
        except (ValueError, TypeError) as exc:
            self.preview_label.setText(f"当前配置不可生成：{exc}")

    def _generate_by_method(self, method=None):
        if method is not None:
            self._select_method(method)
        plan = self._build_plan()
        design_service.commit_plan(self.project_data, plan)
        self._applied_state = deepcopy(self._draft_state())
        self.update_info_display()
        return plan

    def on_generate_clicked(self):
        service = ProjectService.for_project(self.project_data)
        try:
            plan = self._generate_by_method()
        except Exception as exc:
            service.record_operation("方案生成", "失败", message=str(exc))
            Notice.warning(self, "无法生成方案", str(exc))
            return
        service.record_operation("方案生成", message=f"生成 {len(plan.rows)} 行 DOE")
        Notice.information(self, "方案已生成", f"已生成 {plan.method}，共 {len(plan.rows)} 次试验。\n请进入【数据管理】填入或导入响应结果。")
