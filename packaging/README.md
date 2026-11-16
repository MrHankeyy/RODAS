# Windows程序打包

当前为正式窗口版（`console=False`），由 PyInstaller 目录模式打包，再用 Inno Setup 6 制作安装向导。启动阶段带 PyInstaller 官方 Splash 启动画面，覆盖「点击快捷方式 → 主窗口就绪」之间的反馈空窗期。

## 构建命令

推荐统一用一键脚本（会自动清 PATH、清缓存、编译安装包）：

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1 -Rebuild
```

只想重建目录包时，在 RODAS 项目根目录执行：

```powershell
$env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notlike '*Anaconda*' }) -join ';'
..\RODAS-build-env\Scripts\python.exe -m PyInstaller --clean -y --distpath .\dist --workpath .\build .\packaging\RODAS.spec
```

> `-y` 不能省：`--clean` 只清 PyInstaller 的缓存与 `build/`，**不清空已有的 `dist/RODAS`**，否则最后一步会报 `output directory is not empty`。
> 清 PATH 也不能省：否则 PyInstaller 会沿 PATH 抓到 `D:\Anaconda\Library\bin` 的 ICU 73.1，与 Qt6 期望的系统 ICU 符号名不匹配，导致启动即崩溃（错误 127）。

构建环境使用 Python 3.12 64 位及 PyInstaller 6.22.3。重新创建环境时：

```powershell
..\RODAS-build-env\Scripts\python.exe -m pip install -r .\packaging\requirements-build.txt
```

预期产物：

```text
dist/
  RODAS/
    RODAS.exe
    _internal/
      assets/
      demos/
      tcl86t.dll, tk86t.dll, _tcl_data/, _tk_data/   # 启动画面依赖
      ...运行依赖...
  RODAS-Setup-V1.0.exe
```

## 启动画面（Splash）

| 项 | 说明 |
|---|---|
| 素材 | `packaging/RODAS-splash.png`，720×340，复刻欢迎页元素（R Logo + RODAS 字标、中文主标题、副标语、右侧线框响应曲面、版本号、进度槽） |
| 生成脚本 | `packaging/make_splash.py`，从 `assets/branding/brand-wordmark.png` 取图，Pillow 绘制，响应曲面数学定义与 `welcome_page.py` 一致 |
| 重新生成 | `..\RODAS-build-env\Scripts\python.exe packaging\make_splash.py`（改品牌图或版本号后执行） |
| 打包接入 | `RODAS.spec` 的 `Splash(...)`。onedir 模式必须把 **splash 传给 `EXE`**、**`splash.binaries` 传给 `COLLECT`** |
| 生命周期 | bootloader 启动即显示 → `main.py` 分阶段 `pyi_splash.update_text()` 更新底部状态文字 → 主窗口 `showMaximized()` 后 `processEvents()` 再 `pyi_splash.close()` 自动关闭 |

实测时间线（窗口枚举 + 抓屏）：

| 事件 | 时刻 |
|---|---|
| 启动画面出现 | 0.22 s |
| 主窗口出现 | 3.97 s |
| 启动画面消失 | 4.02 s |
| 覆盖空窗期 | 约 3.75 s（冷启动负载高时可达 5.5 s） |

开启启动画面的额外开销约 **+0.3~0.4 秒**（关闭时 3.84 s / 开启时 4.11–4.23 s），换来全程有反馈。Tcl/Tk 跑在独立线程，主线程导入 matplotlib 期间画面依然可刷新、状态文字可更新。

**关闭方式**

- 主窗口绘制完成后**自动关闭**，不会挡住软件；无需手动操作，也不会残留进程。
- 要彻底不显示：设置环境变量 `PYINSTALLER_SUPPRESS_SPLASH_SCREEN=1`（已实测 0 个启动画面窗口）。
- Tk 启动画面是无边框窗口，**没有可点击的 × 按钮**，因此不支持「启动过程中手动关掉」。若确实需要随时可 × 的交互窗口，需改为独立轻量启动器进程方案（多打一个 exe、快捷方式指向启动器、用窗口探测或命名事件通知关闭）。

**两个必须注意的坑**

1. `text_font` 不能含空格。PyInstaller 把字体名原样写进 `font create myFont -family ...`，填 `Microsoft YaHei` 会让 Tcl 解析出多余参数并抛错，脚本在贴图/设置窗口尺寸之前就中断，屏幕上只剩一个 216×239 的默认 Tk 窗口。已改用 Windows 自带的 **`SimHei`**（无空格、支持中文）。
2. 图片里不能出现纯洋红 `#ff00ff`，该色在 Windows 上被用作透明色。生成脚本已校验不含有此颜色。

## 其它打包约定

- `assets` 中的 Logo 与 SVG 资源显式收集；可执行程序图标由 `assets/branding/brand-icon.png` 生成到 `packaging/RODAS.ico`。
- 绘图固定为 QtAgg，并使用 PyQt6；显式收集 QtSvg，排除其他 Qt 绑定。其余科学计算依赖由 PyInstaller 及随附 hooks 分析收集。
- 本地工作区的 `../demos/demo_*` 中 CSV、任务文件及 Markdown 说明会收集到 `_internal/demos/`；不收集虚拟环境、Git 记录、测试、临时脚本或已有输出目录。
- 打开任务仍使用软件内的「文件→读取任务」。当前启动入口尚未增加任务文件参数处理，文件关联将在后续安装阶段单独处理。
- 验证 Logo、SVG 箭头、DEMO3 分析与 DEMO1 建模优化，并测试任务保存恢复、图表及 PDF 导出。窗口版下崩溃不再打印 traceback，排查问题时可临时改回 `console=True` 重新打包。
- 分发时不再需要整个 `dist/RODAS` 目录，只发 `dist/RODAS-Setup-V1.0.exe` 一个文件即可。

## 制作 Windows 安装包（Inno Setup 6）

前置：`dist/RODAS` 必须是已验证可启动的正式窗口版目录包；`RODAS.spec` 中 `console=False`。

本机编译器已安装在自定义路径 `D:\Software\Inno Setup 6\`（Inno Setup 6.7.3）。换机器时安装：

```powershell
winget install --id JRSoftware.InnoSetup -e -s winget -i
```

编译安装包（在项目根目录执行）：

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1
# 先重新 PyInstaller 打包再编译：
powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1 -Rebuild
# 编译器装在非标准位置时手动指定：
powershell -ExecutionPolicy Bypass -File .\packaging\build_installer.ps1 -IsccPath 'D:\Software\Inno Setup 6\ISCC.exe'
```

产物：`dist/RODAS-Setup-V1.0.exe`。LZMA2 压缩约 270 MB / 2183 个文件的目录包，成品约 76 MB，分发时只需这一个文件。

- **版本号是写死的**，不在源码里：`RODAS.iss` 的 `#define MyAppVersion "1.0"`（决定安装包元数据与输出文件名）、`build_installer.ps1` 末尾的产物检查路径、`make_splash.py` 里启动画面上的版本字样（已统一为 V1.0，改后需重新生成 PNG 并重跑 PyInstaller——splash 图嵌在 exe 里）。发新版本时这三处要手动同步。
- **中文安装界面**：`[Languages]` 使用 `packaging/ChineseSimplified.isl`（Inno Setup 6.3+ 官方语言文件，UTF-8 无 BOM，与 6.7.3 内置语言文件编码惯例一致；6.7.3 发行版的 `Languages/` 目录仍不自带，故随仓库携带）。`RODAS.iss` 本身必须保存为 **UTF-8 BOM**，中文文案才能被 ISCC 正确读取。
- **命名口径（2026-11-16 更新）**：中文名称统一为「基于不确定性量化的复杂工程结构鲁棒优化设计平台」，覆盖安装向导、快捷方式、卸载项、主窗口标题、欢迎页大标题（`frontend/pages/welcome_page.py` 的 `CHINESE_NAME`，标题字号自适应、无需手调）与启动画面主标题（字号 16）；**安装目录与安装包文件名用英文 `RODAS`**（`{commonpf64}\RODAS`、`RODAS-Setup-V1.0.exe`）；启动画面版本字样为 `RODAS · V1.0`。
- `RODAS.iss` 把整个 `dist/RODAS` 安装到 `{commonpf64}\RODAS`（`x64compatible`，需管理员权限），创建开始菜单项、可选桌面快捷方式、卸载项，卸载信息自动登记到「应用和功能」。`AppId` 与旧版 0.2 相同，覆盖安装/升级走同一卸载项。`RODAS.ico` 由 `brand-icon.png` 通过 Pillow 生成 16–256 六种尺寸。
- `build_installer.ps1` 按以下顺序定位 `ISCC.exe`：`-IsccPath` 参数 → 环境变量 `RODAS_ISCC` → PATH → 注册表卸载项的 `InstallLocation`（覆盖自定义安装路径）→ 常见默认路径（含 Inno Setup 7）。找不到时明确报错，不会静默跳过。`-Rebuild` 时若 `RODAS-splash.png` 缺失会自动调用 `make_splash.py` 重新生成。
- ~~脚本内界面文案暂用英文~~ 已改为全中文界面（2026-11-12）：`[Languages]` 指向随仓库的 `ChineseSimplified.isl`，`.iss` 为 UTF-8 BOM。
- `.rodas` 文件关联段落已写在 `RODAS.iss` 末尾（默认注释）。启用前必须先让 `main.py` 支持从 `sys.argv[1]` 读取任务文件路径，否则双击任务文件只会打开空界面。
- 程序导出文件均通过 `QFileDialog` 由用户选择路径，不写安装目录，因此装到 `Program Files` 不会遇到写权限问题。

## 合并后的构建入口

`build.ps1` 与 `软件打包.spec` 使用同一份 `packaging/RODAS.spec`，统一输出 `dist/RODAS/RODAS.exe`。`packaging/build_installer.ps1 -Rebuild` 进一步生成安装包。构建前重新生成启动图片和图标，安装包脚本从 `backend/domain/application.py` 读取中文名称和版本，保留原 AppId。源代码提交包包含 `packaging/`，可在解压后继续构建安装包。

云端依赖清单已更新，重建前需在所选构建环境安装当前 `requirements.txt`（或锁定环境对应的 `requirements.lock.txt`）。
