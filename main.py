"""RODAS application entry point.

The heavy UI import is deliberately deferred into main() so the bootloader
splash screen can report progress while matplotlib / numpy / pandas load.
"""
import sys

from PyQt6.QtCore import QLibraryInfo, QTranslator
from PyQt6.QtWidgets import QApplication


def _splash_status(message):
    """Update the bootloader splash text; a no-op when running from source."""
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.update_text(message)
    except Exception:
        pass


def _splash_close():
    """Dismiss the splash once the real window is on screen."""
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.close()
    except Exception:
        pass


def install_chinese_qt_text(app):
    """让 Qt 自带的确定/取消、另存等标准按钮显示中文。"""
    translator = QTranslator(app)
    if translator.load('qtbase_zh_CN', QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    return translator


def main():
    app = QApplication(sys.argv)
    install_chinese_qt_text(app)
    _splash_status('正在加载分析与绘图组件…')

    from frontend.main_window import MainWindow

    _splash_status('正在构建工作台…')
    window = MainWindow()
    window.showMaximized()

    # Let Qt paint the main window before the always-on-top splash goes away.
    app.processEvents()
    _splash_close()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
