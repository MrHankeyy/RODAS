from PyQt6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QTextEdit, QComboBox, QSplitter, QMainWindow,
    QApplication, QScrollArea, QFileDialog, QStatusBar)
from PyQt6.QtCore import Qt
from frontend.pages.modeling_page import ModelingPage
from frontend.pages.configuration_page import ConfigurationPage
from frontend.pages.data_management_page import DataManagementPage
from frontend.pages.optimization_page import OptimizationPage
from frontend.pages.analysis_page import AnalysisPage
from backend.domain.models import ProjectData
from frontend.theme import install_theme, polish_tables
from frontend.pages.welcome_page import WelcomePage, CHINESE_NAME, brand_icon
from frontend.workspace import Workspace, DirectoryButton


class MainWindow(QMainWindow):
    PAGE_INFO = [
        ("业务建模", "定义响应目标、性能约束与输入因子，建立分析问题。"),
        ("方案配置", "选择试验设计方法，设置采样与模型参数，生成试验方案。"),
        ("数据管理", "导入、编辑试验数据，检查完整度并查看描述统计。"),
        ("设计优化", "运行当前方案分析，在分类工作区查看模型诊断与设计结果。"),
        ("分析报告", "预览本次计算结果，填写编制信息并导出报告。"),
    ]

    def __init__(self, workspace=None):
        super().__init__()
        self.project_data = ProjectData()
        self.workspace = workspace if workspace is not None else Workspace(parent=self)
        self.setWindowTitle('RODAS · ' + CHINESE_NAME)
        self.resize(1440, 940)
        self.setMinimumSize(1050, 700)
        self.setWindowIcon(brand_icon())
        install_theme(QApplication.instance())
        self._build_ui()
        self.show_welcome()

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_module_navigation_bar())
        heading = QWidget()
        self.module_heading = heading
        heading.setObjectName("pageHeading")
        header = QHBoxLayout(heading)
        header.setContentsMargins(22, 12, 22, 12)
        text = QVBoxLayout()
        text.setSpacing(3)
        self.page_title = QLabel(self.PAGE_INFO[0][0])
        self.page_title.setProperty("role", "heading")
        self.page_title.setToolTip(self.PAGE_INFO[0][1])
        text.addWidget(self.page_title)
        header.addLayout(text, 1)
        self.step_label = QLabel("工作流程  1 / 5")
        self.step_label.setProperty("role", "badge")
        header.addWidget(self.step_label)
        root.addWidget(heading)
        self.workspace_splitter = QSplitter(Qt.Orientation.Vertical)
        self.workspace_splitter.addWidget(self._build_main_workspace())
        self.message_panel = self._build_message_panel()
        self.workspace_splitter.addWidget(self.message_panel)
        self.workspace_splitter.setCollapsible(0, False)
        self.workspace_splitter.setCollapsible(1, False)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)
        self.workspace_splitter.setSizes([700, 100])
        root.addWidget(self.workspace_splitter, 1)
        self.setCentralWidget(central)
        self._build_directory_status()
        polish_tables(self)

    def _build_module_navigation_bar(self):
        widget = QWidget()
        widget.setObjectName("appChrome")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(22, 0, 16, 0)
        layout.setSpacing(0)
        self.brand_button = QPushButton('开始')
        self.brand_button.setObjectName('brand')
        self.brand_button.setIcon(brand_icon())
        self.brand_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.brand_button.setToolTip('返回开始界面（Alt+0）')
        self.brand_button.setShortcut('Alt+0')
        self.brand_button.clicked.connect(self.show_welcome)
        layout.addWidget(self.brand_button)
        self.btns_switch = []
        for i, (title, _) in enumerate(self.PAGE_INFO):
            button = QPushButton(title)
            button.setProperty("workflow", True)
            button.setProperty("active", i == 0)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"{title}（Alt+{i+1}）\n{self.PAGE_INFO[i][1]}")
            button.setShortcut(f"Alt+{i+1}")
            button.clicked.connect(lambda checked=False, index=i: self.on_switch_module(self.PAGE_INFO[index][0], index))
            self.btns_switch.append(button)
            layout.addWidget(button, 1)
        self.btn_switch_MOD, self.btn_switch_CFG, self.btn_switch_DM, self.btn_switch_OPT, self.btn_switch_REP = self.btns_switch
        return widget

    def _build_main_workspace(self):
        self.stacked_widget = QStackedWidget()
        self.page_MOD = ModelingPage(self.project_data)
        self.page_CFG = ConfigurationPage(self.project_data)
        self.page_DM = DataManagementPage(self.project_data)
        self.page_OPT = OptimizationPage(self.project_data)
        self.page_REP = AnalysisPage(self.project_data)
        self.page_OPT.optimization_finished.connect(self.page_REP.run_analysis)
        self.page_OPT.overview.data_requested.connect(lambda: self.switch_page(2))
        self.page_MOD.model_saved.connect(self.page_CFG.update_info_display)
        for page in (self.page_MOD, self.page_CFG, self.page_DM, self.page_OPT, self.page_REP):
            page.setMinimumWidth(1000)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.stacked_widget.addWidget(scroll)
        # Keep existing module indices 0..4 stable for navigation and integrations.
        self.welcome_page = WelcomePage()
        self.welcome_page.directory_requested.connect(self.choose_working_directory)
        self.welcome_index = self.stacked_widget.addWidget(self.welcome_page)
        return self.stacked_widget

    def _build_directory_status(self):
        status = QStatusBar(self)
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)
        self.directory_button = DirectoryButton()
        self.directory_button.clicked.connect(self.choose_working_directory)
        status.addWidget(self.directory_button, 1)
        self.workspace.directory_changed.connect(self.directory_button.update_directory)
        self.directory_button.update_directory(self.workspace.directory)

    def choose_working_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, '设置工作目录', self.workspace.directory)
        if not directory:
            return
        try:
            self.workspace.set_directory(directory)
        except (OSError, ValueError) as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, '工作目录设置失败', str(exc))

    def _refresh_navigation(self, active_index):
        for index, button in enumerate(self.btns_switch):
            button.setProperty('active', index == active_index)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        self.brand_button.setProperty('active', active_index is None)
        self.brand_button.style().unpolish(self.brand_button)
        self.brand_button.style().polish(self.brand_button)
        self.brand_button.update()

    def show_welcome(self):
        if self.stacked_widget.currentIndex() == 0:
            self.page_MOD.sync_to_project_data()
        self.stacked_widget.setCurrentIndex(self.welcome_index)
        self.module_heading.hide()
        self.message_panel.hide()
        self._refresh_navigation(None)

    def _build_message_panel(self):
        from frontend.notifications import bus
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 6, 16, 8)
        layout.setSpacing(4)
        bar = QHBoxLayout()
        title = QLabel("运行消息")
        title.setProperty("role", "muted")
        bar.addWidget(title)
        self.message_filter = QComboBox()
        self.message_filter.addItems(["全部", "成功", "进度", "提醒", "错误"])
        self.message_filter.setFixedWidth(94)
        bar.addWidget(self.message_filter)
        bar.addStretch()
        self.message_count = QLabel("0 条消息")
        self.message_count.setProperty("role", "muted")
        bar.addWidget(self.message_count)
        clear = QPushButton("清空")
        bar.addWidget(clear)
        self.fold_messages = QPushButton("收起")
        self.fold_messages.setCheckable(True)
        self.fold_messages.clicked.connect(self._toggle_messages)
        bar.addWidget(self.fold_messages)
        layout.addLayout(bar)
        self.message_view = QTextEdit()
        self.message_view.setReadOnly(True)
        self.message_view.setMinimumHeight(45)
        self.message_view.document().setMaximumBlockCount(500)
        layout.addWidget(self.message_view)
        self._messages = []
        clear.clicked.connect(self._clear_messages)
        self.message_filter.currentTextChanged.connect(self._render_messages)
        bus.posted.connect(self._post_message)
        self._post_message("进度", "工作区已就绪", "定义问题 → 配置试验 → 回填响应 → 分析优化 → 导出结果")
        return widget

    def _toggle_messages(self, collapsed):
        self.message_view.setVisible(not collapsed)
        self.fold_messages.setText("展开" if collapsed else "收起")
        sizes = self.workspace_splitter.sizes()
        self.workspace_splitter.setSizes([sum(sizes) - (45 if collapsed else 100), 45 if collapsed else 100])

    def _post_message(self, level, title, message):
        from datetime import datetime
        self._messages.append((datetime.now().strftime("%H:%M:%S"), level, title, message))
        self._messages = self._messages[-500:]
        self._render_messages()

    def _clear_messages(self):
        self._messages.clear()
        self._render_messages()

    def _render_messages(self, *_args):
        from html import escape
        selected = self.message_filter.currentText()
        self.message_count.setText(f"{len(self._messages)} 条消息")
        colors = {"成功":"#168064", "进度":"#2563eb", "提醒":"#ad6800", "错误":"#c73545"}
        self.message_view.setHtml("<br>".join(
            f'<span style="color:{colors[level]}">{time} · {level} · {escape(title)}</span>　{escape(message).replace(chr(10), "<br>")}'
            for time, level, title, message in self._messages if selected == "全部" or level == selected))
        self.message_view.verticalScrollBar().setValue(self.message_view.verticalScrollBar().maximum())

    def on_test_click(self, name):
        print(f"已点击：{name}")

    def on_switch_module(self, module_name, index):
        self.switch_page(index)

    def switch_page(self, index: int):
        if not 0 <= index < len(self.PAGE_INFO):
            raise ValueError('未知的功能模块索引。')
        if index != 0 and self.stacked_widget.currentIndex() == 0:
            self.page_MOD.sync_to_project_data()
        self.stacked_widget.setCurrentIndex(index)
        self.module_heading.show()
        self.message_panel.show()
        self._refresh_navigation(index)
        title, description = self.PAGE_INFO[index]
        self.page_title.setText(title)
        self.page_title.setToolTip(description)
        self.step_label.setText(f"工作流程  {index + 1} / 5")

    def closeEvent(self, event):
        if getattr(self.page_OPT, "_worker", None) is not None:
            from frontend.notifications import Notice
            Notice.warning(self, "计算进行中", "请等待当前计算结束后关闭窗口。")
            event.ignore()
            return
        super().closeEvent(event)
