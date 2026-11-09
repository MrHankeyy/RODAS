import sys
from PyQt6.QtCore import QLibraryInfo, QTranslator
from PyQt6.QtWidgets import QApplication
from frontend.main_window import MainWindow


def install_chinese_qt_text(app):
    """让 Qt 自带的确定/取消、另存等标准按钮显示中文。"""
    translator = QTranslator(app)
    if translator.load('qtbase_zh_CN', QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    return translator


def main():
    app = QApplication(sys.argv)
    install_chinese_qt_text(app)
    window = MainWindow()
    window.showMaximized()  
    sys.exit(app.exec()) 


if __name__ == "__main__":
    main()