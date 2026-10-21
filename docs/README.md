# RAMS v0.2 项目文档

本目录位于 `RAMS_version_0_2/docs/`，集中保存本版本的架构、使用、验证和 BUG 文档。

## 目录

| 位置 | 内容 |
|---|---|
| `bugs/` | 未解决的 BUG 记录及截图；新问题依次编号，已修复记录删除后不复用其编号 |
| `bugs/assets/` | BUG 对应的截图与附件 |
| 本目录下的 Markdown 文件 | 架构说明、功能使用、测试验证与问题诊断文档 |
| `references/` | 试验设计等项目参考资料 |
| `improvement/` | 逐项改进需求、设计确认、LOGO 附件与实施验证记录 |

## 常用入口

- [架构说明](D:/Study/Poject_Software/software/RAMS_version_0_2/docs/ARCHITECTURE.md)
- [经典 DOE 验证与使用说明](D:/Study/Poject_Software/software/RAMS_version_0_2/docs/经典DOE验证与使用说明.md)
- [优化工作台分析功能说明](D:/Study/Poject_Software/software/RAMS_version_0_2/docs/优化工作台分析功能说明.md)
- [报告模块需求映射与使用说明](D:/Study/Poject_Software/software/RAMS_version_0_2/docs/报告模块需求映射与使用说明.md)
- [手动测试问题诊断](D:/Study/Poject_Software/software/RAMS_version_0_2/docs/手动测试问题诊断.md)
- [试验设计参考指南](D:/Study/Poject_Software/software/RAMS_version_0_2/docs/references/design-of-experiments-guide-zh.pdf)
- [Demo 1：悬臂梁响应曲面优化](D:/Study/Poject_Software/software/demos/demo_1/README.md)
- [Demo 2：悬臂梁两水平筛选设计](D:/Study/Poject_Software/software/demos/demo_2/README.md)
- [Demo 3：悬臂梁田口稳健性分析](D:/Study/Poject_Software/software/demos/demo_3/README.md)

## 放置约定

- 架构、使用及验证文档直接放在本目录；BUG 放在 `bugs/`，参考资料放在 `references/`。
- BUG 记录包含版本与环境、复现步骤、实际和预期表现、截图、处理状态与验收结果。
- BUG 修复并验证通过后，删除对应记录及不再使用的专属截图、附件；未修复的问题保留。
- `AGENTS.md` 保留在代码目录，供开发工具发现；`requirements.txt` 保留原位用于安装依赖。
- 示例位于与版本目录同级的 `software/demos/`，各示例保留操作说明、CSV、视频与导出报告，便于整套复现。
- 长期测试代码和测试数据放在 `test/`，临时调试脚本放在 `temp/`，程序生成结果放在 `output/`。
- 除非另有说明，本版本文档中的代码路径和命令以 `RAMS_version_0_2/` 为基准，不以 `docs/` 为基准。
