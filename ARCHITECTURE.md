# RAMS v0.2 结构说明

v0.2 采用四层结构，保持现有算法与界面行为不变：

- core/：纯计算。DOE、代理模型、响应模型、统计与优化均可脱离 PyQt6 调用。
- services/：业务流程。负责生成方案、准备模型、组织统计分析，以及统一修改 ProjectData。
- pages/：Qt 界面。页面收集输入、调用 service、显示结果；复杂页面拆为面板、控制器、绘图和文本模块。
- file_io.py：CSV、JSON、HTML 与 PDF 的实际读写适配。
- 根目录兼容模块：doe_engine.py、optimizer_engine.py、design_analysis.py、workbench_analysis.py 保留旧导入路径，内部转发到 core/。

## 项目数据写入规则

所有页面对项目状态的修改都经过 services.project_service.ProjectService：

- update_definition：更新因子与响应；
- commit_design：一次提交设计方法、参数、DOE 矩阵和初始结果；
- update_responses / replace_dataset：提交试验响应或外部数据；
- publish_results：发布分析结果，并可校验计算开始时的输入签名；
- update_workbench / clear_workbench：维护工作台结果；
- 输入变化会统一清除失效结果和模型缓存。

ProjectData 中原有的 analysis_signature、ensure_results_current 和
record_operation 暂时保留为兼容入口，并委托给 ProjectService。

## 页面拆分

- configuration_page.py：方案配置控制器；
- configuration_panels.py：方案参数控件；
- optimization_page.py：优化页面与公开兼容方法；
- optimization_controller.py：页面流程协调；
- optimization_panels.py：优化页签和控件；
- optimization_plots.py：绘图；
- result_text.py：结果文本格式化；
- qt_tasks.py：Qt 后台任务适配；
- table_widgets.py：可复用表格控件。

## 兼容与验证

重构保留 v0.1 的公开模块路径，以减少一次性迁移风险。长期代码应优先直接调用
core/ 与 services/。现有测试继续放在 test/，一次性脚本和日志放在 temp/。
