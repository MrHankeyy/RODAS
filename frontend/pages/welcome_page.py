"""RODAS start page: approved brand, four equal actions, no workflow clutter."""
from math import ceil, exp
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSizePolicy,
)

CHINESE_NAME = '面向飞行器结构的鲁棒性优化设计平台'
ENGLISH_NAME = 'Robust Optimal Design of Aerospace Structures'
LOGO_PATH = Path(__file__).resolve().parents[2] / 'assets' / 'branding' / 'rodas-logo.png'


def brand_pixmap():
    # Display the approved transparent artwork without its surrounding padding.
    return QPixmap(str(LOGO_PATH)).copy(90, 135, 1990, 430)


def brand_icon():
    return QIcon(brand_pixmap().copy(0, 0, 475, 410))


class BrandLogo(QLabel):
    display_width_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._artwork = brand_pixmap()
        self.setAccessibleName('RODAS — ' + ENGLISH_NAME)
        self.setMinimumWidth(300)
        self.setMaximumWidth(650)
        self.setFixedHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Leave room for the title's next whole-pixel font size below the logo.
        size = QSize(max(1, self.width() - 24), self.height())
        pixmap = self._artwork.scaled(
            size, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(pixmap)
        self.display_width_changed.emit(round(pixmap.deviceIndependentSize().width()))


class ResponseSurface(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(180, 200)
        self.setMaximumWidth(380)
        self.setAccessibleName('响应曲面与设计点示意图')

    @staticmethod
    def _point(x, y):
        z = .84 * exp(-2.3 * ((x - .15)**2 + (y + .1)**2))
        z -= .35 * exp(-3 * ((x + .5)**2 + (y - .5)**2))
        z += .08 * x
        return 190 + (x - y) * 82, 155 + (x + y) * 39 - z * 81

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / 380, self.height() / 280)
        painter.translate((self.width() - 380 * scale) / 2,
                          (self.height() - 280 * scale) / 2)
        painter.scale(scale, scale)
        for axis in range(2):
            for j in range(18):
                color = QColor('#168cb4')
                color.setAlphaF(.58 if j % 3 == 0 else .22)
                painter.setPen(QPen(color, .9))
                path = QPainterPath()
                fixed = -1 + 2 * j / 17
                for k in range(35):
                    t = -1 + 2 * k / 34
                    x, y = self._point(t, fixed) if axis else self._point(fixed, t)
                    if k:
                        path.lineTo(x, y)
                    else:
                        path.moveTo(x, y)
                painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#168cb4'))
        for x, y in [(-.7, -.3), (.1, -.1), (.7, .2), (-.2, .6), (.4, -.7)]:
            px, py = self._point(x, y)
            painter.drawEllipse(QRectF(px - 3.2, py - 3.2, 6.4, 6.4))


class WelcomePage(QWidget):
    directory_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName('welcomePage')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root = QVBoxLayout(self)
        root.setContentsMargins(44, 28, 44, 40)
        root.setSpacing(22)
        root.addStretch(1)
        hero = QHBoxLayout()
        hero.setSpacing(28)
        intro = QVBoxLayout()
        intro.setSpacing(14)
        welcome = QLabel('欢迎使用 RODAS   /   v0.2')
        welcome.setProperty('role', 'muted')
        intro.addWidget(welcome)
        self.logo = BrandLogo()
        intro.addWidget(self.logo)
        self.title = QLabel(CHINESE_NAME)
        self.title.setObjectName('welcomeTitle')
        self.title.setWordWrap(False)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.logo.display_width_changed.connect(self._fit_title_to_logo)
        intro.addWidget(self.title)
        tagline = QLabel('从试验与数据出发，探索更稳健的结构设计。')
        tagline.setProperty('role', 'muted')
        intro.addWidget(tagline)
        hero.addLayout(intro, 3)
        self.surface = ResponseSurface()
        hero.addWidget(self.surface, 2)
        root.addLayout(hero)
        root.addSpacing(20)
        start = QHBoxLayout()
        caption = QLabel('开始工作')
        caption.setProperty('role', 'muted')
        start.addWidget(caption)
        line = QWidget()
        line.setObjectName('welcomeDivider')
        line.setFixedHeight(1)
        start.addWidget(line, 1)
        root.addLayout(start)
        actions = QGridLayout()
        actions.setHorizontalSpacing(14)
        self.action_buttons = {}
        icon_directory = LOGO_PATH.parent.parent / 'ui'
        entries = [
            ('读取已有任务', 'task-open.svg'),
            ('新建任务', 'task-new.svg'),
            ('设置工作目录', 'workspace-folder.svg'),
            ('教程', 'tutorial.svg'),
        ]
        for column, (title, icon) in enumerate(entries):
            button = QPushButton()
            button.setObjectName('welcomeAction')
            button.setAccessibleName(title)
            button.setMinimumHeight(108)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout = QVBoxLayout(button)
            layout.setContentsMargins(18, 17, 18, 17)
            row = QHBoxLayout()
            mark = QLabel()
            mark.setPixmap(QIcon(str(icon_directory / icon)).pixmap(QSize(22, 22)))
            row.addWidget(mark)
            row.addStretch()
            arrow = QLabel('↗')
            arrow.setProperty('role', 'muted')
            row.addWidget(arrow)
            layout.addLayout(row)
            layout.addStretch()
            label = QLabel(title)
            label.setObjectName('welcomeActionLabel')
            layout.addWidget(label)
            # The complete button remains the click target, including child labels.
            for child in button.findChildren(QWidget):
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            if title == '设置工作目录':
                button.clicked.connect(self.directory_requested.emit)
            else:
                button.setToolTip('预留入口，后续接入任务与教程功能')
                button.setAccessibleDescription('预留入口，尚未接入功能')
            actions.addWidget(button, 0, column)
            actions.setColumnStretch(column, 1)
            self.action_buttons[title] = button
        root.addLayout(actions)
        root.addStretch(1)

    def _fit_title_to_logo(self, logo_width):
        font = QFont(self.title.font())
        font.setPixelSize(100)
        text_width = QFontMetricsF(font).horizontalAdvance(CHINESE_NAME)
        pixel_size = max(21, ceil(logo_width * 100 / max(1, text_width)))
        self.title.setStyleSheet(f'font-size:{pixel_size}px;')
