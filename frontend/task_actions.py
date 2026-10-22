"""Native, application-wide task menus and the task-file lifecycle."""
from pathlib import Path
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from backend.domain.models import ProjectData
from backend.services import task_storage
from frontend.notifications import Notice


class TaskActions:
    def __init__(self, window):
        self.window = window
        self.path = None
        self.saved_fingerprint = task_storage.fingerprint(window.project_data)
        bar = window.menuBar()
        bar.setNativeMenuBar(False)
        menu = bar.addMenu('文件')
        self.actions = {}
        for title, shortcut, slot in (
                ('保存', QKeySequence.StandardKey.Save, self.save),
                ('另存为', QKeySequence.StandardKey.SaveAs, self.save_as),
                ('读取', QKeySequence.StandardKey.Open, self.open)):
            action = QAction(title, window)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
            menu.addAction(action)
            self.actions[title] = action
        bar.addAction('教程', self.tutorial)
        bar.addAction('设置工作目录', window.choose_working_directory)
        self.bind_welcome()

    def bind_welcome(self):
        for title, slot in (('读取已有任务', self.open), ('新建任务', self.new), ('教程', self.tutorial)):
            button = self.window.welcome_page.action_buttons[title]
            button.setToolTip('')
            button.setAccessibleDescription(title)
            button.clicked.connect(slot)

    def busy(self):
        if getattr(self.window.page_OPT, '_worker', None) is not None:
            Notice.warning(self.window, '计算进行中', '请等待计算结束后保存或切换任务。')
            return True
        return False

    def save(self, *_args, save_as=False):
        if self.busy():
            return False
        path = self.path
        if save_as or path is None:
            default = str(path) if path else self.window.workspace.file_path('未命名任务.rodas')
            path, _ = QFileDialog.getSaveFileName(self.window, '保存任务', default, 'RODAS 任务 (*.rodas)')
            if not path:
                return False
            if not path.lower().endswith('.rodas'):
                path += '.rodas'
        try:
            digest = task_storage.save_task(self.window.project_data, path)
        except Exception as exc:
            Notice.warning(self.window, '任务保存失败', str(exc))
            return False
        self.path = Path(path).resolve()
        self.saved_fingerprint = digest
        self._title()
        Notice.information(self.window, '任务已保存', f'{self.path}\n仅保存已提交数据，不包含输入草稿。')
        return True

    def save_as(self, *_args):
        return self.save(save_as=True)

    def confirm_leave(self, force=False):
        if self.busy():
            return False
        try:
            dirty = task_storage.fingerprint(self.window.project_data) != self.saved_fingerprint
        except ValueError:
            dirty = True
        if not force and not dirty:
            return True
        choice = QMessageBox.question(self.window, '保存任务',
            '是否保存当前任务？\n仅保存已提交数据；尚未提交的输入不会写入任务文件。',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return choice == QMessageBox.StandardButton.Discard

    def open(self, *_args):
        if self.busy():
            return False
        path, _ = QFileDialog.getOpenFileName(self.window, '读取任务', self.window.workspace.directory,
                                             'RODAS 任务 (*.rodas)')
        if not path:
            return False
        try:
            project = task_storage.load_task(path)
        except ValueError as exc:
            Notice.warning(self.window, '任务读取失败', str(exc))
            return False
        if not self.confirm_leave():
            return False
        try:
            target = Path(path).resolve()
            if target == self.path:
                project = task_storage.load_task(path)
            self._replace(project, target)
        except Exception as exc:
            Notice.warning(self.window, '任务读取失败', str(exc))
            return False
        Notice.information(self.window, '任务已读取', str(self.path))
        return True

    def new(self, *_args):
        if self.confirm_leave():
            self._replace(ProjectData(), None)

    def _replace(self, project, path):
        window = self.window
        old = window.stacked_widget
        attributes = ('project_data', 'stacked_widget', 'page_MOD', 'page_CFG', 'page_DM',
                      'page_OPT', 'page_REP', 'welcome_page', 'welcome_index')
        previous = {name: getattr(window, name) for name in attributes}
        try:
            window.project_data = project
            stack = window._build_main_workspace()
            window.page_OPT.controller.restore_results()
        except Exception:
            if window.stacked_widget is not old:
                window.stacked_widget.deleteLater()
            for name, value in previous.items():
                setattr(window, name, value)
            raise
        window.workspace_splitter.replaceWidget(0, stack)
        old.hide()
        old.deleteLater()
        self.path = path
        self.saved_fingerprint = task_storage.fingerprint(project)
        self.bind_welcome()
        window._clear_messages()
        window.show_welcome()
        stack.show()
        self._title()

    def _title(self):
        from frontend.pages.welcome_page import CHINESE_NAME
        label = (self.path.name + ' · ') if self.path else ''
        self.window.setWindowTitle(label + 'RODAS · ' + CHINESE_NAME)

    def tutorial(self, *_args):
        QMessageBox.information(self.window, '教程',
            '1. 在业务建模中定义响应与因子，点击“保存业务模型数据”。\n'
            '2. 在方案配置中选择主线与参数，生成试验方案。\n'
            '3. 在数据管理中填写或导入响应，保存并检查完整度。\n'
            '4. 在设计优化中执行分析或优化，查看模型诊断与设计结果。\n'
            '5. 在分析报告中预览、导出结果。\n\n'
            '文件 → 保存：将已提交任务和训练模型保存为 .rodas 文件。\n'
            '文件 → 读取：恢复任务和模型，保持当前工作目录不变。')
