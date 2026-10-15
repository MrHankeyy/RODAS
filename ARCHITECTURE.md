# RAMS v0.2 结构说明

生产代码统一放在 `rams/` 包中，仓库根目录只保留启动入口、项目配置、文档和资源：

- `rams/core/`：纯计算。DOE、代理模型、响应模型、统计与优化均可脱离 PyQt6 调用。
- `rams/domain/`：因子、响应和 `ProjectData` 等领域数据结构。
- `rams/services/`：业务流程。负责生成方案、准备模型、组织统计分析，以及统一修改 `ProjectData`。
- `rams/engines/`：面向业务层和 UI 的稳定算法门面，将分散的核心函数组合成原有调用接口。
- `rams/infrastructure/`：CSV、JSON、HTML 与 PDF 等文件读写适配。
- `rams/reporting/`：报告内容构建与渲染。
- `rams/ui/`：PyQt6 界面；页面位于 `rams/ui/pages/`。
- `main.py`：唯一的桌面程序启动入口。

## 项目数据写入规则

所有页面对项目状态的修改都经过 `rams.services.project_service.ProjectService`：

- `update_definition`：更新因子与响应；
- `commit_design`：一次提交设计方法、参数、DOE 矩阵和初始结果；
- `update_responses` / `replace_dataset`：提交试验响应或外部数据；
- `publish_results`：发布分析结果，并可校验计算开始时的输入签名；
- `update_workbench` / `clear_workbench`：维护工作台结果；
- 输入变化会统一清除失效结果和模型缓存。

`ProjectData` 只保存领域数据，不导入业务服务。输入签名、结果失效和操作通知都通过
`ProjectService` 的公开方法完成，页面和报告模块不再调用数据对象上的兼容方法。

## 页面拆分

- `configuration_page.py`：方案配置控制器；
- `configuration_panels.py`：方案参数控件；
- `optimization_page.py`：优化页面；
- `optimization_controller.py`：页面流程协调；
- `optimization_panels.py`：优化页签和控件；
- `optimization_plots.py`：绘图；
- `result_text.py`：结果文本格式化；
- `qt_tasks.py`：Qt 后台任务适配；
- `table_widgets.py`：可复用表格控件。

## 导入与验证

生产代码和长期测试统一使用 `rams.*` 包路径。算法实现保留在 `rams.core`，UI
通过 `rams.engines` 和 `rams.services` 调用。长期测试放在 `test/`，一次性脚本和
日志放在 `temp/`。
