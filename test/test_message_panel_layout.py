import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from frontend.main_window import MainWindow


class MessagePanelLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font = Path("C:/Windows/Fonts/msyh.ttc")
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.settle_layout()

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def settle_layout(self):
        for _ in range(4):
            self.app.processEvents()

    def assert_message_panel_contained(self):
        self.settle_layout()
        panel = self.window.message_panel
        splitter = self.window.workspace_splitter
        self.assertTrue(panel.isVisible())
        self.assertTrue(splitter.rect().contains(panel.geometry()))
        self.assertGreater(panel.height(), 0)
        self.assertGreaterEqual(self.window.stacked_widget.height(), 200)

    def test_splitter_limits_and_page_switches(self):
        for width, height in ((1440, 940), (1050, 700)):
            self.window.resize(width, height)
            self.settle_layout()
            for page in range(5):
                with self.subTest(size=(width, height), page=page):
                    self.window.switch_page(page)
                    self.settle_layout()
                    splitter = self.window.workspace_splitter
                    positions = (0, splitter.height() // 2, splitter.height())
                    for position in positions:
                        splitter.moveSplitter(position, 1)
                        self.assert_message_panel_contained()

    def test_fold_and_return_from_welcome(self):
        self.window.switch_page(0)
        self.settle_layout()
        self.window._post_message("成功", "测试", "拖动后消息仍可查看")
        for _ in range(2):
            self.window.fold_messages.click()
            self.assertFalse(self.window.message_view.isVisible())
            self.assert_message_panel_contained()
            self.window.fold_messages.click()
            self.assertTrue(self.window.message_view.isVisible())
            self.assert_message_panel_contained()
            self.assertIn("拖动后消息仍可查看", self.window.message_view.toPlainText())
            self.window.show_welcome()
            self.settle_layout()
            self.assertFalse(self.window.message_panel.isVisible())
            self.window.switch_page(3)
            self.assert_message_panel_contained()


if __name__ == "__main__":
    unittest.main()
