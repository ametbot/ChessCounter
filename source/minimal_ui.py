from pathlib import Path
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPainter,QColor,QPen,QFont,QFontMetricsF,QLinearGradient
from PySide6.QtWidgets import QWidget

STYLE='''
QWidget { background:#101114; color:#f1f0ed; font-family:'Segoe UI'; font-size:13px; }
QLabel { background:transparent; }
QLabel#muted { color:#a1a3ad; }
QLabel#title { font-size:24px; font-weight:600; }
QLabel#eyebrow { color:#a6a3a0; font-size:10px; font-weight:600; letter-spacing:1px; }
QLabel#badge { color:#ffb853; background:#332719; border:1px solid #624422; border-radius:6px; padding:5px 9px; font-size:10px; font-weight:700; }
QLabel#status { color:#b7b5af; padding:0 2px; }
QFrame#card { background:#191b20; border:1px solid #2b2e35; border-radius:14px; }
QFrame#counterCard { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #35281d,stop:0.65 #211e1b,stop:1 #1b1c20); border:1px solid #664727; border-radius:16px; }
QPushButton { background:#26282e; border:1px solid #3b3d46; border-radius:9px; padding:9px 12px; font-weight:600; }
QPushButton:hover { background:#343139; border-color:#b27c38; }
QPushButton:pressed { background:#433423; }
QPushButton:focus { border-color:#ffb853; }
QPushButton#primary { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff9d29,stop:1 #ffc65e); color:#241708; font-weight:700; border:1px solid #ffc569; padding:13px; }
QPushButton#primary:hover { background:#ffcb76; }
QPushButton#primary:pressed { background:#ed9b30; }
QPushButton:disabled { color:#666971; }
QSpinBox,QComboBox { background:#121419; border:1px solid #373a43; border-radius:7px; padding:5px 9px; min-height:24px; selection-background-color:#795023; }
QComboBox { border-radius:11px; padding:6px 34px 6px 12px; }
QComboBox:hover { border-color:#886335; }
QComboBox::drop-down { subcontrol-origin:padding; subcontrol-position:top right; width:30px; border:none; background:transparent; }
QComboBox::down-arrow { image:url("__CHEVRON__"); width:12px; height:8px; }
QComboBox QAbstractItemView { background:#1c1e24; color:#f1f0ed; border:1px solid #55432c; padding:6px; outline:0; selection-background-color:#624622; selection-color:#fff4dc; }
QSpinBox:focus,QComboBox:focus { border-color:#ffb853; }
QCheckBox { spacing:8px; background:transparent; }
QSlider { background:transparent; }
QCheckBox::indicator { width:16px; height:16px; border-radius:5px; border:1px solid #555963; background:#14161b; }
QCheckBox::indicator:checked { background:#ffb44d; border:3px solid #705128; }
QCheckBox::indicator:hover { border-color:#ffb853; }
QScrollArea { border:none; }
QScrollBar:vertical { width:7px; background:transparent; }
QScrollBar::handle:vertical { background:#393c43; border-radius:3px; min-height:30px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QSlider::groove:horizontal { height:4px; background:#33363c; border-radius:2px; }
QSlider::sub-page:horizontal { background:#f6ac48; border-radius:2px; }
QSlider::handle:horizontal { background:#ffcf83; width:14px; margin:-5px 0; border-radius:7px; }
QToolButton { color:#a4a7ae; background:transparent; border:none; padding:8px 0; text-align:left; }
QToolButton:hover { color:white; }
'''.replace('__CHEVRON__',(Path(__file__).resolve().parent/'assets'/'chevron-down.svg').as_posix())


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None,Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.Tool|Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle('Chest Counter · Оверлей')
        self.count=0
        self.scale_percent=85
        self.set_scale(85)

    def set_scale(self,percent):
        self.scale_percent=max(60,min(140,int(percent)))
        self.setFixedSize(round(236*self.scale_percent/100),round(82*self.scale_percent/100))
        self.update()

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.width()/236,self.height()/82)
        gradient=QLinearGradient(0,0,236,82)
        gradient.setColorAt(0,QColor(37,29,21,246)); gradient.setColorAt(1,QColor(16,18,23,246))
        p.setPen(QPen(QColor(255,183,77,115),1)); p.setBrush(gradient)
        p.drawRoundedRect(QRectF(.5,.5,235,81),12,12)
        p.setPen(Qt.NoPen); p.setBrush(QColor('#ffb44d')); p.drawRoundedRect(QRectF(16,16,3,12),1.5,1.5)
        font=QFont('Segoe UI'); font.setPixelSize(14); p.setFont(font); p.setPen(QColor('#b8bbc2'))
        p.drawText(QRectF(26,11,195,22),Qt.AlignLeft|Qt.AlignVCenter,'Открыто сундуков')
        text=f'{self.count:,}'.replace(',',' ')
        font.setPixelSize(32); font.setWeight(QFont.DemiBold)
        while QFontMetricsF(font).horizontalAdvance(text)>203 and font.pixelSize()>18:
            font.setPixelSize(font.pixelSize()-1)
        p.setFont(font); p.setPen(QColor('#fff4dc'))
        p.drawText(QRectF(16,32,204,42),Qt.AlignLeft|Qt.AlignVCenter,text)
