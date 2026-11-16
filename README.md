# 基于不确定性量化的复杂工程结构鲁棒优化设计平台

版本：1.0。

面向复杂工程结构的鲁棒优化设计与分析桌面软件，支持田口设计、二次响应面，以及 Kriging、SVR、ANN 代理模型方案。

## 运行环境

运行环境为 Windows 和 PyQt6，当前代码兼容 Python 3.12。云端锁定环境为 Python 3.14.2，在源代码目录执行：

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe main.py
```

`requirements.txt` 列出直接依赖，`requirements.lock.txt` 固定云端 Python 3.14 环境的运行依赖版本。本机已有 Python 3.12 环境时，执行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` 更新依赖后运行。

## 使用流程

新建任务后，依次完成问题定义、试验配置、响应回填、模型验证或田口分析、结果核验与报告导出。页面中的输入应先提交，再保存整个任务。

任务文件使用 `.rodas` 扩展名，可恢复已提交的数据、模型和当前结果；读取旧任务时可选择“所有文件”。报告支持 PDF 和 HTML，导出报告不代替保存任务。

## 生成桌面程序

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File build.ps1
```

生成目录为 `dist/RODAS/`，运行其中的 `RODAS.exe`。目录包需保留完整目录，构建中间文件写入系统临时目录。两个构建入口共用 `packaging/RODAS.spec`，包含启动画面、当前品牌图标和 DLL 隔离处理。

安装向导使用 Inno Setup，执行 `powershell -ExecutionPolicy Bypass -File packaging/build_installer.ps1 -Rebuild` 可重新构建程序并生成安装包。名称与版本从 `backend/domain/application.py` 读取，构建说明见 [Windows 安装包说明](packaging/README.md)。

## 源代码结构

- `backend/`：领域数据、试验设计、模型训练、优化、统计分析与报告。
- `frontend/`：窗口、页面、图表及后台计算任务。
- `assets/`：正式品牌资源与界面图标。
- `docs/`：架构、分析功能说明与已知限制。
- `main.py`：桌面程序入口。
- `软件打包.spec`、`build.ps1`：桌面程序构建配置。
- `package_source.py`：源代码提交包生成工具。

窗口、界面及报告统一使用软件中文全称；图形标识为 R 图案与 ROD 字样，英文为 Robust Optimal Design。

## 源代码提交

执行 `python package_source.py` 可生成源代码提交包，包含程序、资源、依赖清单、构建配置和使用文档，并附文件校验清单。提交包是生成时的快照；源代码更新后需重新生成。该工具不包含 `.venv`、`.git`、缓存和桌面构建产物。

功能与适用范围见 [文档索引](docs/README.md)，模型精度限制见 [SVR 参数搜索说明](docs/bugs/BUG-002.md)。
