"""方案配置页面：实验设计类型选择、参数细化与代理模型设置入口。"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QGroupBox, QTextEdit, QSpinBox,
    QDoubleSpinBox, QMessageBox, QStackedWidget, QSizePolicy
)

import doe_engine as engine
from models import ProjectData
from services import design_service
from services.project_service import ProjectService
from pages.surrogate_dialogs import SurrogateDialog, MODEL_TITLES
from pages import configuration_panels


class ConfigurationPage(QWidget):
    def __init__(self, project_data: ProjectData):
        super().__init__()
        self.project_data = project_data
        from copy import deepcopy
        self.surrogate_config = deepcopy(project_data.surrogate_config)
        self.init_ui()

    # ------------------------------------------------------------------ 布局
    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.info_group = QGroupBox("当前业务模型配置")
        self.info_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(3)
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setMinimumHeight(34)
        self.info_label.setProperty("role", "muted")
        info_layout.addWidget(self.info_label)
        self.info_group.setLayout(info_layout)
        main_layout.addWidget(self.info_group)

        design_group = QGroupBox("方案与设计方法选择")
        design_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        design_layout = QVBoxLayout()
        design_layout.setContentsMargins(12, 10, 12, 10)
        design_layout.setSpacing(8)
        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("设计方法"))
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "两水平筛选设计（全因子/部分析因/PB）",
            "响应曲面设计（CCD/Box-Behnken）",
            "田口稳健设计（内表×外表）",
            "代理模型建模 · Kriging",
            "代理模型建模 · SVR",
            "代理模型建模 · BP 神经网络",
        ])
        method_row.addWidget(self.method_combo, 1)
        design_layout.addLayout(method_row)

        self.dynamic_params_widget = QStackedWidget()
        self.dynamic_params_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.screening_widget = self._build_screening_widget()
        self.rsm_widget = self._build_rsm_widget()
        self.taguchi_widget = self._build_taguchi_widget()
        self.surrogate_widget = self._build_surrogate_widget()

        for w in (self.screening_widget, self.rsm_widget,
                  self.taguchi_widget, self.surrogate_widget):
            w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.dynamic_params_widget.addWidget(w)
        design_layout.addWidget(self.dynamic_params_widget)

        self.preview_label = QLabel("尚未估算试验次数")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("color:#1d4ed8;font-weight:bold;")
        design_layout.addWidget(self.preview_label)

        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        self.desc_text.setMinimumHeight(65)
        self.desc_text.setMaximumHeight(90)
        self.desc_text.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        design_layout.addWidget(self.desc_text)

        design_group.setLayout(design_layout)
        main_layout.addWidget(design_group)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.refresh_btn = QPushButton("刷新问题定义")
        self.refresh_btn.clicked.connect(self.update_info_display)
        self.gen_btn = QPushButton("生成试验方案")
        self.gen_btn.setMinimumWidth(150)
        from ui_theme import primary
        primary(self.gen_btn)
        self.gen_btn.clicked.connect(self.on_generate_clicked)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.gen_btn)
        main_layout.addLayout(btn_layout)
        main_layout.addStretch(1)

        self.setLayout(main_layout)
        self._connect_preview_signals()
        self._on_taguchi_levels(self.t_levels_combo.currentText())
        self.method_combo.currentTextChanged.connect(self._on_method_changed)
        self.dynamic_params_widget.currentChanged.connect(
            lambda _index: self._fit_dynamic_params())
        self.update_info_display()
        self._on_method_changed(self.method_combo.currentText())

    def _fit_dynamic_params(self):
        """让堆叠容器只占当前参数页需要的高度。"""
        current = self.dynamic_params_widget.currentWidget()
        if current is None:
            return
        current.adjustSize()
        height = max(current.sizeHint().height(), current.minimumSizeHint().height())
        self.dynamic_params_widget.setFixedHeight(height + 2)

    # ------------------------------------------------------------- 控件构建
    def _build_screening_widget(self):
        return configuration_panels.screening(self)

    def _build_rsm_widget(self):
        return configuration_panels.response_surface(self)

    def _build_taguchi_widget(self):
        return configuration_panels.taguchi(self)

    def _build_surrogate_widget(self):
        return configuration_panels.surrogate(self)

    # ------------------------------------------------------------- 联动刷新
    def _connect_preview_signals(self):
        for box in (self.method_combo, self.screen_kind_combo, self.rsm_type_combo,
                    self.rsm_alpha_combo, self.t_levels_combo, self.t_inner_combo,
                    self.t_outer_combo, self.t_snr_combo):
            box.currentTextChanged.connect(self._refresh_preview)
        for spin in (self.f_topn_spin, self.f_center_spin, self.f_repeat_spin,
                     self.rsm_center_spin, self.rsm_repeat_spin, self.rsm_alpha_spin):
            spin.valueChanged.connect(self._refresh_preview)
        self.t_noise_levels_combo.currentTextChanged.connect(self._refresh_preview)
        self.t_repeat_spin.valueChanged.connect(self._refresh_preview)

    def _on_method_changed(self, text):
        if "筛选" in text:
            self.dynamic_params_widget.setCurrentWidget(self.screening_widget)
        elif "响应曲面" in text:
            self.dynamic_params_widget.setCurrentWidget(self.rsm_widget)
        elif "田口" in text:
            self.dynamic_params_widget.setCurrentWidget(self.taguchi_widget)
        else:
            self.dynamic_params_widget.setCurrentWidget(self.surrogate_widget)
        self._fit_dynamic_params()
        self._update_surrogate_labels(text)
        self._set_description(text)
        self._refresh_preview()

    def _set_description(self, method):
        if "筛选" in method:
            desc = ("筛选设计遵循“效应稀疏 + 效应等级”原则，用尽量少的试验识别活跃主效应。"
                    "本模块支持全因子、1/2 与 1/4 部分析因以及 Plackett-Burman；"
                    "输出包含试验结构、主效应排序、设计诊断（正交性/分辨率/混杂说明）。")
        elif "响应曲面" in method:
            desc = ("二阶响应曲面模型（含平方项与两两交互）由 CCD 或 Box-Behnken 支撑。"
                    "CCD 可旋转 α、面心 α 或自定义 α；BBD 将每个因子控制在 3 个水平，避免顶点极端工况。"
                    "后续在【设计优化】拟合二次模型并给出优选设置。")
        elif "田口" in method:
            desc = ("田口稳健设计以正交表安排控制因子（内表）与噪声因子（外表），"
                    "通过内×外叉积试验估计均值与波动，并按信噪比（S/N）挑选稳健水平组合。"
                    "未固定的环境因子作为噪声因子；内外表可分别选择 2/3 水平并设置重复次数。"
                    "无外表且无重复时只分析均值；望目采用相对目标中点的均方偏差损失 S/N，候选水平须做确认试验。")
        elif "代理模型" in method:
            desc = ("代理模型面向高成本仿真黑盒：先按试验设计生成样本点（响应留空，"
                    "在【数据管理】填入或导入结果），再由所选模型训练并评估。"
                    "三种模型均可通过独立窗口设置试验设计与模型参数。")
        self.desc_text.setPlainText(desc)

    def _on_rsm_type(self, text):
        self.rsm_alpha_combo.setEnabled("CCD" in text)
        self.rsm_alpha_spin.setEnabled("CCD" in text and self.rsm_alpha_combo.currentText().startswith("用户"))
        if "BBD" in text:
            self.rsm_center_spin.setValue(3)

    def _on_alpha_mode(self, text):
        self.rsm_alpha_spin.setEnabled("CCD" in self.rsm_type_combo.currentText() and text.startswith("用户"))

    def _on_taguchi_levels(self, text):
        levels = self.t_levels_combo.currentText()
        inner_items = {
            "2 水平": ["自动推荐", "L4 (2^3)", "L8 (2^7)", "L12 (2^11)", "L16 (2^15)"],
            "3 水平": ["自动推荐", "L9 (3^4)", "L27 (3^13)"],
        }
        outer_items = {
            "2 水平": ["无（仅内表）", "自动推荐", "L4 (2^3)", "L8 (2^7)", "L12 (2^11)", "L16 (2^15)"],
            "3 水平": ["无（仅内表）", "自动推荐", "L9 (3^4)", "L27 (3^13)"],
        }
        self._reset_combo(self.t_inner_combo, inner_items[levels])
        self._reset_combo(self.t_outer_combo, outer_items[self.t_noise_levels_combo.currentText()])

    @staticmethod
    def _reset_combo(combo, items):
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        if current in items:
            combo.setCurrentText(current)
        combo.blockSignals(False)

    # ------------------------------------------------------------- 因子/预览
    def _design_factors(self):
        """仅设计因子进入经典 DOE/代理抽样；环境因子仅用于田口外表。"""
        return [f for f in self.project_data.factors
                if f.name and f.source == "设计" and not f.is_fixed]

    def _noise_factors(self):
        return [f for f in self.project_data.factors if f.name and f.source == "环境" and not f.is_fixed]

    def _k(self):
        return len(self._design_factors())

    def _screen_kind_key(self):
        text = self.screen_kind_combo.currentText()
        if "1/2" in text:
            return "half"
        if "1/4" in text:
            return "quarter"
        if "Plackett" in text:
            return "pb"
        return "full"

    def _refresh_preview(self):
        method = self.method_combo.currentText()
        k = self._k()
        if "代理模型" not in method and k == 0:
            self.preview_label.setText("尚未在【业务建模】中配置设计因子，无法估算试验次数")
            return
        if "代理模型" in method and k == 0:
            self.preview_label.setText("代理模型抽样需要至少 1 个设计因子")
            return
        try:
            if "筛选" in method:
                rows, meta = engine.build_screening(
                    engine.simple_factors(self._design_factors()),
                    self._screen_kind_key(), seed=0,
                    centers=self.f_center_spin.value(),
                    replicates=self.f_repeat_spin.value(), randomize=False)
                n = meta["total_runs"]
                extra = f"（k={k}，{meta['kind']}，中心点 {self.f_center_spin.value()}）"
            elif "响应曲面" in method:
                rsm_type = "BBD" if "BBD" in self.rsm_type_combo.currentText() else "CCD"
                alpha = 0.0
                if rsm_type == "CCD":
                    alpha = {"可旋转": engine.rotatable_alpha(k), "位于表面": 1.0}.get(
                        self.rsm_alpha_combo.currentText().split("（")[0],
                        self.rsm_alpha_spin.value())
                rows, meta = engine.build_response_surface(
                    engine.simple_factors(self._design_factors()), rsm_type,
                    "face" if "位于表面" in self.rsm_alpha_combo.currentText()
                    else ("rotatable" if "可旋转" in self.rsm_alpha_combo.currentText() else "custom"),
                    self.rsm_alpha_spin.value(), centers=self.rsm_center_spin.value(),
                    replicates=self.rsm_repeat_spin.value(), randomize=False)
                n = meta["total_runs"]
                extra = f"（k={k}，{meta['design']}，中心点 {self.rsm_center_spin.value()}）\n{meta['bounds_note']}"
            elif "田口" in method:
                ctl = engine.simple_factors(self._design_factors())
                noise = engine.simple_factors(self._noise_factors())
                levels = 2 if "2 水平" in self.t_levels_combo.currentText() else 3
                inner = self._resolve_oa(self.t_inner_combo.currentText(), len(ctl), levels)
                if noise:
                    outer = self._resolve_oa(self.t_outer_combo.currentText(), len(noise), 2 if "2" in self.t_noise_levels_combo.currentText() else 3)
                    if outer == "无":
                        raise ValueError("存在未固定噪声因子，请选择外表；仅内表请先固定噪声因子")
                else:
                    outer = "无"
                rows, meta = engine.build_taguchi(ctl, noise, inner, outer, levels, seed=0, replicates=self.t_repeat_spin.value())
                n = meta["total_runs"]
                extra = (f"（k={len(ctl)} 控制+{len(noise)} 噪声，内表 {meta['inner_label']}"
                         f"×外表 {meta['outer_label']}）")
            else:
                n = (self.surrogate_config.get("sample_count")
                     if self.surrogate_config else 50)
                extra = f"（k={k}，LHS/空间填充样本点）"
            self.preview_label.setText(f"预计试验次数：{n} 次 {extra}")
        except Exception as exc:
            self.preview_label.setText(f"试验次数估算不可用：{exc}")

    def _resolve_oa(self, label, k, levels):
        """把“自动推荐”解析为具体正交表标签。"""
        if label.startswith("无"):
            return "无"
        if label != "自动推荐":
            return label.replace(" (", "(")
        if k <= 0:
            return "无"
        if levels == 2:
            for cand in ("L4", "L8", "L12", "L16"):
                try:
                    engine.taguchi_arrays(cand, k)
                    return cand
                except ValueError:
                    continue
            raise ValueError("两水平因子数量超过 L16 容量（15）")
        for cand in ("L9", "L27"):
            try:
                engine.taguchi_arrays(cand, k)
                return cand
            except ValueError:
                continue
        raise ValueError("三水平因子数量超过 L27 容量（13）")

    def _update_surrogate_labels(self, method):
        if "代理模型" not in method:
            return
        key = "Kriging" if "Kriging" in method else ("SVR" if "SVR" in method else "ANN")
        k = self._k()
        self.surrogate_info_label.setText(
            f"代理模型：{MODEL_TITLES[key]} ｜ 输入变量 {k} 个（设计因子）"
            f" ｜ 输出变量 {len(self.project_data.responses)} 个（响应）")
        if self.surrogate_config and self.surrogate_config.get("model") == key:
            self.surrogate_status.setText(
                f"已保存：样本 {self.surrogate_config.get('sample_count')} 点，"
                f"{self.surrogate_config.get('doe_method')}")
        else:
            self.surrogate_status.setText("尚未设置该模型的参数")

    # ------------------------------------------------------------- 数据刷新
    def update_info_display(self):
        k = len(self._design_factors())
        noise = len(self._noise_factors())
        info = (
            f"设计因子：{k} 个 ｜ 环境（噪声）因子：{noise} 个 ｜ "
            f"响应/目标：{len(self.project_data.responses)} 个\n"
            f"当前设计方案：{self.project_data.design_method or '尚未生成'}"
        )
        self.info_label.setText(info)
        self._on_method_changed(self.method_combo.currentText())

    # ------------------------------------------------------------- 代理设置
    def _open_surrogate_dialog(self):
        method = self.method_combo.currentText()
        key = "Kriging" if "Kriging" in method else ("SVR" if "SVR" in method else "ANN")
        factors = self._design_factors()
        if not factors:
            Notice.warning(self, "缺少因子",
                                "当前没有可用的设计因子。请先在【业务建模】添加设计因子并保存。")
            return
        dialog = SurrogateDialog(key, factors, self, config=self.surrogate_config)
        if dialog.exec() == SurrogateDialog.DialogCode.Accepted:
            self.surrogate_config = dialog.collect_config()
            self._update_surrogate_labels(method)
            self._refresh_preview()
            Notice.information(
                self, "设置已保存",
                "代理模型与试验设计参数已保存，点击下方【生成试验方案】即可生成样本点（响应列留空，"
                "随后在【数据管理】填入或导入响应结果）。")

    # ------------------------------------------------------------- 生成方案
    def on_generate_clicked(self):
        method = self.method_combo.currentText()
        service = ProjectService.for_project(self.project_data)
        try:
            self._generate_by_method(method)
        except ValueError as exc:
            service.record_operation("方案生成", "失败", message=str(exc))
            Notice.warning(self, "无法生成方案", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            service.record_operation("方案生成", "失败", message=str(exc))
            Notice.critical(self, "生成失败", f"发生未预期错误：{exc}")
            return
        service.record_operation(
            "方案生成", message=f"生成 {len(self.project_data.doe_matrix)} 行 DOE")
        self.info_label.setText(
            f"设计因子：{self._k()} 个 ｜ 环境因子：{len(self._noise_factors())} 个 ｜ "
            f"响应：{len(self.project_data.responses)} 个\n当前设计方案：{method}"
            f"（{len(self.project_data.doe_matrix)} 次试验）")
        Notice.information(
            self, "方案已生成",
            f"已生成 {method} 试验方案，共 {len(self.project_data.doe_matrix)} 次试验。\n"
            "请进入【数据管理】查看 DOE 矩阵并填入/导入响应结果。")

    def _generate_by_method(self, method):
        if "筛选" in method:
            plan = design_service.screening_plan(
                self.project_data, method, self._screen_kind_key(),
                self.f_seed_spin.value(), self.f_center_spin.value(),
                self.f_repeat_spin.value(),
                self.f_order_combo.currentText() == "随机",
                self.f_topn_spin.value())
        elif "响应曲面" in method:
            rsm_type = (
                "BBD" if "BBD" in self.rsm_type_combo.currentText() else "CCD")
            alpha_text = self.rsm_alpha_combo.currentText()
            if "位于表面" in alpha_text:
                alpha_mode, alpha_value = "face", 1.0
            elif "可旋转" in alpha_text:
                alpha_mode, alpha_value = "rotatable", 0.0
            else:
                alpha_mode, alpha_value = "custom", self.rsm_alpha_spin.value()
            plan = design_service.response_surface_plan(
                self.project_data, method, rsm_type, alpha_mode, alpha_value,
                self.rsm_center_spin.value(), self.rsm_repeat_spin.value(),
                self.rsm_seed_spin.value(),
                self.rsm_order_combo.currentText() == "随机")
        elif "田口" in method:
            levels = 2 if "2 水平" in self.t_levels_combo.currentText() else 3
            inner = self._resolve_oa(
                self.t_inner_combo.currentText(), self._k(), levels)
            noise_count = len(self._noise_factors())
            noise_levels = (
                2 if "2" in self.t_noise_levels_combo.currentText() else 3)
            outer = self._resolve_oa(
                self.t_outer_combo.currentText(), noise_count, noise_levels)
            plan = design_service.taguchi_plan(
                self.project_data, method, inner, outer, levels,
                self.t_seed_spin.value(), self.t_repeat_spin.value(),
                self.t_order_combo.currentText() == "随机",
                self.t_snr_combo.currentText())
        else:
            plan = design_service.surrogate_plan(
                self.project_data, method, self.surrogate_config,
                self.f_seed_spin.value())
        design_service.commit_plan(self.project_data, plan)
        return plan

    # ------------------------------------------------------------- 后端结果
from notifications import Notice
