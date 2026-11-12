"""A focused engineering launchpad with a scalable, illustrative design space."""
from math import ceil, exp
from pathlib import Path

from PyQt6.QtCore import Qt, QPointF, QRectF, QSize, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QFontMetricsF, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSizePolicy, QStackedWidget,
)
from backend.domain.models import TASK_TYPES
from frontend.terminology import tooltip

CHINESE_NAME = '面向飞行器结构的鲁棒优化设计平台'
ENGLISH_NAME = 'Robust Optimal Design of Aerospace Structures'
LOGO_PATH = Path(__file__).resolve().parents[2] / 'assets' / 'branding' / 'rodas-logo.png'

WELCOME_STYLE = """
QWidget#welcomePage { background:#f3f6fa; }
QWidget#welcomeContent { background:transparent; }
QWidget#welcomeHero { background:#ffffff; border:1px solid #dfe7f0; border-radius:18px; }
QLabel#welcomeEyebrow { color:#53748d; font-size:13px; font-weight:600; }
QLabel#welcomeVersion { color:#416680; background:#edf5fa; border:1px solid #dceaf3; border-radius:10px; padding:3px 10px; font-size:11px; }
QLabel#welcomeTitle { color:#18344f; font-weight:600; }
QLabel#welcomeTagline { color:#6b7f92; font-size:14px; }
QLabel#welcomeCapability { color:#41657e; background:#f2f7fb; border:1px solid #e3edf4; border-radius:4px; padding:5px 10px; font-size:12px; }
QLabel#welcomeSectionTitle { color:#243f58; font-weight:600; font-size:17px; }
QLabel#welcomeSectionNote, QLabel#welcomeFooter { color:#7a8e9f; font-size:12px; }
QPushButton#welcomeAction { background:white; border:1px solid #dce5ef; border-radius:12px; padding:0; min-height:120px; }
QPushButton#welcomeAction:hover { background:#f8fcff; border-color:#71a8c7; }
QPushButton#welcomeAction:focus { border:2px solid #238db6; }
QPushButton#welcomeAction:pressed { background:#eaf4fa; }
QPushButton#welcomeAction[primaryAction="true"] { background:#123e65; border-color:#123e65; }
QPushButton#welcomeAction[primaryAction="true"]:hover { background:#194c76; border-color:#3c8cb4; }
QPushButton#welcomeAction[primaryAction="true"]:focus { border:2px solid #23b4cd; }
QPushButton#welcomeAction[primaryAction="true"]:pressed { background:#0e3355; }
QLabel#welcomeActionLabel { font-size:17px; font-weight:600; color:#213f59; }
QLabel#welcomeActionHint { font-size:12px; color:#7a8c9d; }
QLabel#welcomeActionArrow { color:#8ca4b9; font-size:18px; }
QPushButton[primaryAction="true"] QLabel#welcomeActionLabel { color:#fff; }
QPushButton[primaryAction="true"] QLabel#welcomeActionHint { color:#a8c9df; }
QPushButton[primaryAction="true"] QLabel#welcomeActionArrow { color:#86cede; }
QWidget#welcomeTaskOptions { background:#123e65; border:1px solid #3e83a9; border-radius:12px; }
QLabel#welcomeTaskCaption { color:#a8c9df; font-size:12px; }
QPushButton#welcomeTaskChoice { color:#fff; background:transparent; text-align:left; border:1px solid transparent; border-radius:6px; padding:6px 10px; min-height:24px; }
QPushButton#welcomeTaskChoice:hover, QPushButton#welcomeTaskChoice:focus { background:#225879; border-color:#5696b5; color:white; }
"""


def brand_pixmap():
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
        self.setMaximumWidth(580)
        self.setFixedHeight(116)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        ratio = self.devicePixelRatioF()
        pixmap = self._artwork.scaled(
            QSize(max(1, self.width() - 24), self.height()) * ratio,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        pixmap.setDevicePixelRatio(ratio)
        self.setPixmap(pixmap)
        self.display_width_changed.emit(round(pixmap.deviceIndependentSize().width()))


class ResponseSurface(QWidget):
    """Decorative geometry, never presented as an actual optimization result."""
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName('响应面与采样点示意图')
        self.setToolTip('工程设计空间示意图，用于表现结构参数、试验采样与稳健寻优；不代表当前任务的计算结果。')

    @staticmethod
    def _point(x, y):
        z = .84 * exp(-2.1 * ((x - .12)**2 + (y + .1)**2))
        z -= .32 * exp(-3 * ((x + .5)**2 + (y - .5)**2))
        z += .06 * x
        return QPointF(302 + (x - y) * 116, 244 + (x + y) * 51 - z * 115)

    @staticmethod
    def _line(painter, points, color, width=1):
        painter.setPen(QPen(QColor(color), width))
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.drawPath(path)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 0, -1, -1)
        background = QLinearGradient(rect.topLeft(), rect.bottomRight())
        background.setColorAt(0, QColor('#f6fafc'))
        background.setColorAt(1, QColor('#e8f3f9'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 12, 12)
        painter.save()
        scale = min(self.width() / 600, self.height() / 410)
        painter.translate((self.width() - 600 * scale) / 2,
                          (self.height() - 410 * scale) / 2)
        painter.scale(scale, scale)
        # A sparse drafting grid gives the scene scale without competing with controls.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#cbdfea'))
        for x in range(36, 580, 24):
            for y in range(36, 390, 24):
                painter.drawEllipse(QPointF(x, y), .7, .7)
        glow = QRadialGradient(QPointF(302, 210), 220)
        glow.setColorAt(0, QColor(178, 221, 238, 150))
        glow.setColorAt(1, QColor(225, 242, 249, 0))
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(302, 210), 245, 170)
        painter.translate(0, -40)
        painter.setPen(QPen(QColor('#d2e5f0'), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(76, 159, 447, 179))
        painter.drawEllipse(QRectF(55, 146, 489, 205))
        # Filled strips under the wireframe provide a quiet sense of volume.
        for j in range(22):
            y0, y1 = -1 + j / 11, -1 + (j + 1) / 11
            polygon = QPolygonF([self._point(-1 + k / 20, y0) for k in range(41)] +
                                [self._point(-1 + k / 20, y1) for k in reversed(range(41))])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(131, 198, 220, 18 + j * 2))
            painter.drawPolygon(polygon)
        for axis in range(2):
            for j in range(23):
                fixed = -1 + j / 11
                points = [self._point(-1 + k / 28, fixed) if axis else
                          self._point(fixed, -1 + k / 28) for k in range(57)]
                self._line(painter, points, '#73b1cc' if j % 3 == 0 else '#acd2e3', 1 if j % 3 == 0 else .65)
        samples = [(-.75, -.4), (-.55, .55), (.45, -.65), (.7, .25), (.15, .6), (-.1, -.15)]
        for x, y in samples:
            point = self._point(x, y)
            painter.setPen(QPen(QColor('#ffffff'), 1.8))
            painter.setBrush(QColor('#1d87ac'))
            painter.drawEllipse(point, 4.2, 4.2)
        target = self._point(.18, -.1)
        painter.setPen(QPen(QColor('#198da7'), 1))
        painter.setBrush(QColor(36, 166, 185, 25))
        painter.drawEllipse(target, 18, 18)
        painter.drawEllipse(target, 11, 11)
        painter.setBrush(QColor('#1a9ba9'))
        painter.setPen(QPen(QColor('#fff'), 2))
        painter.drawEllipse(target, 5, 5)
        painter.restore()
        caption_font = QFont(self.font())
        caption_font.setPixelSize(round(12 * max(1, min(1.55, self.width() / 600))))
        painter.setFont(caption_font)
        painter.setPen(QColor('#7e9aaf'))
        painter.drawText(QRectF(24, self.height() - 42, self.width() - 48, 24),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         '响应面与采样点')



class NewTaskCard(QStackedWidget):
    task_requested = pyqtSignal(str)

    def __init__(self, cover):
        super().__init__()
        self.cover = cover
        self.addWidget(cover)
        self.options = QWidget()
        self.options.setObjectName('welcomeTaskOptions')
        layout = QVBoxLayout(self.options)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        caption = QLabel('选择分析任务')
        caption.setObjectName('welcomeTaskCaption')
        layout.addWidget(caption)
        self.buttons = {}
        term_keys = {'robust': 'task_robust', 'taguchi': 'taguchi_design'}
        for key, title in TASK_TYPES.items():
            button = QPushButton(title)
            button.setToolTip(tooltip(term_keys[key]))
            button.setAccessibleDescription(tooltip(term_keys[key]))
            button.setObjectName('welcomeTaskChoice')
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, kind=key: self.task_requested.emit(kind))
            layout.addWidget(button)
            self.buttons[key] = button
        self.addWidget(self.options)
        cover.clicked.connect(self.open_choices)
        self.setAccessibleName('新建任务，选择分析主线')

    def open_choices(self):
        self.setCurrentWidget(self.options)
        self.buttons['robust'].setFocus(Qt.FocusReason.TabFocusReason)

    def enterEvent(self, event):
        self.setCurrentWidget(self.options)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setCurrentWidget(self.cover)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self.setCurrentWidget(self.cover)
        super().hideEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.setCurrentWidget(self.cover)
            self.cover.setFocus()
            event.accept()
        else:
            super().keyPressEvent(event)


class WelcomePage(QWidget):
    directory_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName('welcomePage')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(WELCOME_STYLE)
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(40, 28, 40, 28)
        self.root_layout.addStretch(2)
        self.content = QWidget()
        self.content.setObjectName('welcomeContent')
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(20)
        self.root_layout.addWidget(self.content, 0, Qt.AlignmentFlag.AlignHCenter)
        self.root_layout.addStretch(3)

        self.hero = QWidget()
        self.hero.setObjectName('welcomeHero')
        self.hero.setFixedHeight(360)
        self.hero_layout = QHBoxLayout(self.hero)
        self.hero_layout.setContentsMargins(38, 24, 20, 24)
        self.hero_layout.setSpacing(20)
        intro = QVBoxLayout()
        intro.setSpacing(12)
        intro.addStretch()
        header = QHBoxLayout()
        welcome = QLabel('欢迎使用 RODAS')
        welcome.setObjectName('welcomeEyebrow')
        header.addWidget(welcome)
        version = QLabel('V1.0')
        version.setObjectName('welcomeVersion')
        header.addWidget(version)
        header.addStretch()
        intro.addLayout(header)
        self.logo = BrandLogo()
        intro.addWidget(self.logo)
        self.title = QLabel(CHINESE_NAME)
        self.title.setObjectName('welcomeTitle')
        self.title.setWordWrap(False)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.logo.display_width_changed.connect(self._fit_title_to_logo)
        intro.addWidget(self.title)
        tagline = QLabel('从试验与数据出发，探索更稳健的结构设计。')
        tagline.setObjectName('welcomeTagline')
        intro.addWidget(tagline)
        capabilities = QHBoxLayout()
        capabilities.setSpacing(8)
        for title, key in [('试验设计', 'taguchi_design'), ('代理建模', 'task_robust'), ('鲁棒优化', 'task_robust')]:
            label = QLabel(title)
            label.setObjectName('welcomeCapability')
            label.setToolTip(tooltip(key))
            capabilities.addWidget(label)
        capabilities.addStretch()
        intro.addSpacing(4)
        intro.addLayout(capabilities)
        intro.addStretch()
        self.hero_layout.addLayout(intro, 6)
        self.surface = ResponseSurface()
        self.hero_layout.addWidget(self.surface, 5)
        self.content_layout.addWidget(self.hero)

        heading = QHBoxLayout()
        label = QLabel('开始工作')
        label.setObjectName('welcomeSectionTitle')
        heading.addWidget(label)
        heading.addStretch()
        hint = QLabel('选择任务入口，开始本次设计')
        hint.setObjectName('welcomeSectionNote')
        heading.addWidget(hint)
        self.content_layout.addLayout(heading)
        self.actions_widget = QWidget()
        actions = QGridLayout(self.actions_widget)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setHorizontalSpacing(16)
        self.action_buttons = {}
        icon_directory = LOGO_PATH.parent.parent / 'ui'
        entries = [
            ('读取已有任务', 'task-open.svg', '继续已有设计与分析'),
            ('新建任务', 'task-new.svg', '选择任务类型，建立设计问题'),
            ('设置工作目录', 'workspace-folder.svg', '设置本次任务的文件存放位置'),
        ]
        for column, (title, icon, subtitle) in enumerate(entries):
            button = QPushButton()
            button.setObjectName('welcomeAction')
            button.setProperty('primaryAction', title == '新建任务')
            button.setAccessibleName(title)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout = QVBoxLayout(button)
            layout.setContentsMargins(22, 18, 22, 18)
            layout.setSpacing(5)
            row = QHBoxLayout()
            mark = QLabel()
            pixmap = QIcon(str(icon_directory / icon)).pixmap(QSize(24, 24))
            if title == '新建任务':
                painter = QPainter(pixmap)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(pixmap.rect(), QColor('#90dbeb'))
                painter.end()
            mark.setPixmap(pixmap)
            row.addWidget(mark)
            row.addStretch()
            arrow = QLabel('↗')
            arrow.setObjectName('welcomeActionArrow')
            row.addWidget(arrow)
            layout.addLayout(row)
            layout.addStretch()
            label = QLabel(title)
            label.setObjectName('welcomeActionLabel')
            layout.addWidget(label)
            note = QLabel(subtitle)
            note.setObjectName('welcomeActionHint')
            layout.addWidget(note)
            for child in button.findChildren(QWidget):
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            if title == '设置工作目录':
                button.clicked.connect(self.directory_requested.emit)
            if title == '新建任务':
                self.new_task_card = NewTaskCard(button)
                actions.addWidget(self.new_task_card, 0, column)
            else:
                actions.addWidget(button, 0, column)
            actions.setColumnStretch(column, 1)
            self.action_buttons[title] = button
        self.content_layout.addWidget(self.actions_widget)
        footer = QHBoxLayout()
        for text in ('定义问题  →  设计试验  →  建模寻优  →  分析报告', 'RODAS  /  结构设计与稳健分析'):
            label = QLabel(text)
            label.setObjectName('welcomeFooter')
            footer.addWidget(label)
            footer.addStretch()
        self.content_layout.addLayout(footer)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 1200 or self.height() < 700
        horizontal_margin = 24 if compact else max(40, round(self.width() * .035))
        vertical_margin = 24 if compact else max(28, round(self.height() * .04))
        spacing = 16 if compact else max(20, round(self.height() * .022))
        card_height = 132 if compact else max(152, round(self.height() * .17))
        self.root_layout.setContentsMargins(horizontal_margin, vertical_margin,
                                           horizontal_margin, vertical_margin)
        self.content.setFixedWidth(max(0, self.width() - horizontal_margin * 2))
        self.content_layout.setSpacing(spacing)
        # Reserve the action row and captions before allocating the hero's height.
        available = self.height() - vertical_margin * 2 - card_height - spacing * 3 - 50
        self.hero.setFixedHeight(max(292, min(round(self.height() * .62), available)))
        self.hero_layout.setContentsMargins(28 if compact else horizontal_margin, 22,
                                           18 if compact else 26, 22)
        self.logo.setMaximumWidth(max(580, round(self.width() * .42)))
        self.logo.setFixedHeight(94 if compact else max(116, round(self.width() * .086)))
        self.actions_widget.setFixedHeight(card_height)
        font_scale = round(max(1, min(1.55, self.width() / 1440)), 2)
        if getattr(self, '_font_scale', None) != font_scale:
            self._font_scale = font_scale
            sizes = {'welcomeEyebrow': 13, 'welcomeVersion': 11, 'welcomeTagline': 14,
                     'welcomeCapability': 12, 'welcomeSectionTitle': 17,
                     'welcomeSectionNote': 12, 'welcomeFooter': 12,
                     'welcomeActionLabel': 17, 'welcomeActionHint': 12,
                     'welcomeActionArrow': 18, 'welcomeTaskCaption': 12}
            responsive = '\n'.join(f'QLabel#{name} {{ font-size:{round(size * font_scale)}px; }}'
                                   for name, size in sizes.items())
            responsive += f'\nQPushButton#welcomeTaskChoice {{ font-size:{round(13 * font_scale)}px; }}'
            self.setStyleSheet(WELCOME_STYLE + responsive)

    def _fit_title_to_logo(self, logo_width):
        font = QFont(self.title.font())
        font.setPixelSize(100)
        text_width = QFontMetricsF(font).horizontalAdvance(CHINESE_NAME)
        pixel_size = max(21, ceil(logo_width * 100 / max(1, text_width)))
        self.title.setStyleSheet(f'font-size:{pixel_size}px;')
