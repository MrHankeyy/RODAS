# 基于不确定性量化的复杂工程结构鲁棒优化设计平台

版本：1.0。

鲁棒优化设计与分析桌面软件，支持田口设计、响应曲面设计，以及 Kriging、SVR、ANN 代理模型方案。

## 运行环境

已验证环境：Windows、Python 3.14.2、PyQt6。安装环境与启动：

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe main.py
```

`requirements.txt` 列出直接依赖；`requirements.lock.txt` 固定本次验证使用的运行环境。

## 生成桌面程序

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File build.ps1
```

生成目录为 `dist/基于不确定性量化的复杂工程结构鲁棒优化设计平台/`，运行 `基于不确定性量化的复杂工程结构鲁棒优化设计平台.exe`。分发时必须保留整个目录。
构建过程需要较多磁盘空间；首次构建时间较长。软件未配置数字签名或安装向导。

## 源代码结构

- `backend/`：领域数据、试验设计、模型训练、优化、统计分析与报告。
- `frontend/`：窗口、交互、图表及后台计算任务。
- `assets/`：主题与品牌资源。
- `docs/`：架构、使用说明与已知问题。
- `main.py`：程序入口。

本文件夹为当前维护的正式源码；上级目录的 `RODAS_v1.0_源代码提交包.zip` 为此前生成的提交快照，后续源码修改不自动同步该压缩包。提交包排除本地虚拟环境、Git 元数据和构建产物。

最终测试与过程材料保存在上级目录 `历史存档_RODAS_v1.0_最终核验_20261112.zip` 中。解压后可使用源目录的虚拟环境，在核验目录执行：

```powershell
D:\work\RODAS\code\RODAS_v1.0\.venv\Scripts\python.exe -m unittest discover -s test -p test_*.py
```

该材料保留源码镜像、适配当前入口的测试和完整日志。原始开发验证归档用于历史对照，包含已移除旧接口的测试，不作为最终版直接执行入口。
详见 [最终核验说明](docs/整理与验证说明.md) 与 [SVR 精度限制](docs/bugs/BUG-002.md)。

请另行保存实际工程文件与试验数据。开发虚拟环境、Git 元数据及打包中间文件不属于提交源代码。

当前界面、窗口标题与报告统一使用上述全称。新版任务文件扩展名为 `.设计任务`；旧任务可通过读取对话框的“所有文件”选项打开。

界面图形标识沿用原 R 图案并显示 ROD，软件中文全称不变。后续修改默认只更新源码，不自动备份或重新生成提交压缩包；需要提交时再手动生成。
