import sys

from PyQt6.QtCore import QLibraryInfo, QTranslator
from PyQt6.QtWidgets import QApplication

from backend.domain.application import APPLICATION_NAME, APPLICATION_VERSION

def _splash_status(message):
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.update_text(message)
    except Exception:
        pass


def _splash_close():
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.close()
    except Exception:
        pass


def install_chinese_qt_text(app):
    translator = QTranslator(app)
    if translator.load(
        "qtbase_zh_CN", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    ):
        app.installTranslator(translator)
    return translator


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APPLICATION_NAME)
    app.setApplicationDisplayName(APPLICATION_NAME)
    app.setApplicationVersion(APPLICATION_VERSION)
    install_chinese_qt_text(app)
    _splash_status('正在加载分析与绘图组件…')

    from frontend.main_window import MainWindow

    _splash_status('正在构建工作台…')
    window = MainWindow()
    window.showMaximized()

    app.processEvents()
    _splash_close()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
