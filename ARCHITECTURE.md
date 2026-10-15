# RAMS v0.2 结构说明

v0.2 使用两个顶层生产代码包，目录名直接表达技术职责：

- `backend/core/`：纯计算。DOE、代理模型、响应模型、统计与优化均可脱离 PyQt6 调用。
- `backend/domain/`：因子、响应和 `ProjectData` 等领域数据结构。
- `backend/services/`：业务流程。负责生成方案、准备模型、组织统计分析，以及统一修改 `ProjectData`。
- `backend/engines/`：面向业务层和界面的稳定算法门面。
- `backend/infrastructure/`：CSV、JSON、HTML 与 PDF 等文件读写适配。
- `backend/reporting/`：报告内容构建与渲染。
- `frontend/`：PyQt6 窗口、页面、主题和通知适配；页面位于 `frontend/pages/`。
- `main.py`：唯一的桌面程序启动入口。

`frontend` 可以调用 `backend`；`backend` 不导入 `frontend`。长期测试位于 `test/`，
一次性调试脚本位于 `temp/`，生成结果位于 `output/`。当前不创建 `poc/`。

## 项目数据写入规则

所有页面对项目状态的修改都经过 `backend.services.project_service.ProjectService`：

- `update_definition`：更新因子与响应；
- `commit_design`：一次提交设计方法、参数、DOE 矩阵和初始结果；
- `update_responses` / `replace_dataset`：提交试验响应或外部数据；
- `publish_results`：发布分析结果，并可校验计算开始时的输入签名；
- `update_workbench` / `clear_workbench`：维护工作台结果；
- 输入变化会统一清除失效结果和模型缓存。

`ProjectData` 只保存领域数据，不导入业务服务。输入签名、结果失效和操作通知都通过
`ProjectService` 的公开方法完成。

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

生产代码和长期测试统一使用 `backend.*` 与 `frontend.*` 包路径。算法实现保留在
`backend.core`，界面通过 `backend.engines` 和 `backend.services` 调用计算与业务流程。
