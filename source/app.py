import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import time
import traceback

import cv2
import mss
import numpy as np
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QRect, QAbstractNativeEventFilter, QLockFile
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QFrame, QMessageBox, QScrollArea)
from detector import Matcher, TransitionTracker, shrink

DATA = Path(os.environ.get('CHEST_COUNTER_DATA', str(Path(os.environ.get('LOCALAPPDATA', '.')) / 'ChestCounter')))
DATA.mkdir(parents=True, exist_ok=True)
USER32 = ctypes.WinDLL('user32', use_last_error=True)
USER32.GetForegroundWindow.restype = wintypes.HWND
USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
USER32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
USER32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]


def foreground_game():
    title = ctypes.create_unicode_buffer(512)
    USER32.GetWindowTextW(USER32.GetForegroundWindow(), title, 512)
    return 'fortnite' in title.value.casefold()


def qimage(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888).copy()


def exclude_capture(widget):
    # Only OUR OWN windows; no handles from the game are modified.
    USER32.SetWindowDisplayAffinity(int(widget.winId()), 0x11)


class Worker(QThread):
    counted = Signal(int)
    status = Signal(str)
    preview = Signal(QImage)
    failed = Signal(str)

    def __init__(self, monitor, samples, threshold, game_only):
        super().__init__()
        self.monitor, self.samples = monitor, samples
        self.threshold, self.game_only = threshold, game_only

    def run(self):
        try:
            matcher = Matcher(self.samples, self.threshold)
            tracker = TransitionTracker()
            last_status, last_preview = '', 0
            with mss.mss() as capture:
                monitor = capture.monitors[self.monitor]
                while not self.isInterruptionRequested():
                    started = time.monotonic()
                    if self.game_only and not foreground_game():
                        tracker = TransitionTracker()
                        status = 'Ожидаю окно Fortnite'
                    else:
                        frame = shrink(np.asarray(capture.grab(monitor))[:, :, :3])
                        detections = matcher.detect(frame)
                        increment = tracker.update(detections, started)
                        if increment:
                            self.counted.emit(increment)
                        status = f'Распознавание • объектов: {len(detections)}'
                        if started-last_preview > .5:
                            for d in detections:
                                x,y,w,h = d.box
                                color = (110,220,80) if d.state == 'open' else (30,185,255)
                                cv2.rectangle(frame, (x,y), (x+w,y+h), color, 2)
                                cv2.putText(frame, f'{d.state} {d.score:.2f}', (x,max(15,y-5)), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
                            self.preview.emit(qimage(frame))
                            last_preview = started
                    if status != last_status:
                        self.status.emit(status)
                        last_status = status
                    self.msleep(max(10, round((.16-(time.monotonic()-started))*1000)))
        except Exception as error:
            self.failed.emit(f'Не удалось захватить экран: {error}')


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(248, 110)
        self.count, self.status = 0, 'РУЧНОЙ РЕЖИМ'

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(16,23,35,230)); p.setPen(QPen(QColor('#344358'),1))
        p.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),16,16)
        p.setPen(QColor('#b5c6dd')); p.setFont(QFont('Segoe UI',9,QFont.Bold))
        p.drawText(18,25,'ОТКРЫТО СУНДУКОВ')
        p.setPen(QColor('#ffffff')); p.setFont(QFont('Segoe UI',27,QFont.Bold))
        p.drawText(17,70,f'{self.count:,}'.replace(',',' '))
        p.setPen(QColor('#69ddbc')); p.setFont(QFont('Segoe UI',8))
        p.drawText(18,94,self.status)


class Selector(QWidget):
    selected = Signal(object)
    region_selected = Signal(object)
    cancelled = Signal()

    def __init__(self, frame, geometry, title, hint='выдели сундук мышью • Esc: отмена'):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.frame, self.picture, self.title = frame, QPixmap.fromImage(qimage(frame)), title
        self.hint = hint
        self.origin = self.end = None
        self.setGeometry(geometry)
        self.setCursor(Qt.CrossCursor)
        self.setAttribute(Qt.WA_DeleteOnClose)

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.picture)
        p.fillRect(self.rect(), QColor(0,0,0,70))
        p.fillRect(0,0,self.width(),65,QColor(14,21,33,240))
        p.setPen(QColor('white')); p.setFont(QFont('Segoe UI',12))
        p.drawText(22,38,self.title+' — '+self.hint)
        if self.origin is not None and self.end is not None:
            p.setPen(QPen(QColor('#69ddbc'),2))
            p.drawRect(QRect(self.origin,self.end).normalized())

    def mousePressEvent(self,event):
        if event.button() == Qt.LeftButton:
            self.origin = self.end = event.position().toPoint()

    def mouseMoveEvent(self,event):
        if self.origin is not None:
            self.end = event.position().toPoint(); self.update()

    def mouseReleaseEvent(self,event):
        if self.origin is None:
            return
        r = QRect(self.origin,event.position().toPoint()).normalized().intersected(self.rect())
        sx, sy = self.frame.shape[1]/self.width(), self.frame.shape[0]/self.height()
        if r.width() >= 24 and r.height() >= 24:
            crop = self.frame[round(r.top()*sy):round((r.bottom()+1)*sy),round(r.left()*sx):round((r.right()+1)*sx)].copy()
            self.region_selected.emit((r.left()/self.width(),r.top()/self.height(),r.width()/self.width(),r.height()/self.height()))
            self.selected.emit(crop)
            self.close()

    def keyPressEvent(self,event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit(); self.close()


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, callbacks):
        super().__init__()
        self.callbacks = callbacks
        self.registered = [i for i in callbacks if USER32.RegisterHotKey(None,i,0x4003,0x70+i)]

    def nativeEventFilter(self,event_type,message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam in self.callbacks:
            self.callbacks[msg.wParam]()
            return True, 0
        return False, 0

    def close(self):
        for i in self.registered:
            USER32.UnregisterHotKey(None,i)


STYLE = '''
QWidget { background: #101723; color: #e7edf7; font-family: 'Segoe UI'; font-size: 13px; }
QLabel { background: transparent; }
QLabel#muted { color: #a4b4c9; }
QFrame#card { background: #192334; border: 1px solid #2b3b50; border-radius: 14px; }
QPushButton { background: #26364c; border: 1px solid #3b506a; border-radius: 7px; padding: 9px 16px; }
QPushButton:hover { background: #344b69; }
QPushButton:disabled { color: #627084; background: #1c2737; }
QPushButton#primary { background: #65d7b7; color: #0c241e; font-weight: 700; border: none; }
QSpinBox, QDoubleSpinBox, QComboBox { background: #1c293c; border: 1px solid #40516a; border-radius: 5px; padding: 6px; min-height: 22px; }
QCheckBox { spacing: 8px; }
QScrollArea { border: none; }
'''


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Chest Counter — счётчик сундуков')
        self.resize(720,850)
        try:
            self.config = json.loads((DATA/'settings.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.config = {}
        self.count = max(0,min(999999999,int(self.config.get('count',0))))
        self.worker = None
        self.selector = None
        self.calibrating = False
        self.overlay = Overlay()
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); outer.addWidget(scroll)
        content = QWidget(); scroll.setWidget(content)
        layout = QVBoxLayout(content); layout.setContentsMargins(22,18,22,18); layout.setSpacing(15)
        title = QLabel('CHEST COUNTER'); title.setStyleSheet('font-size: 25px; font-weight: 800;')
        layout.addWidget(title)
        layout.addWidget(self.label('Открытия на экране • включая наблюдение','muted'))
        card = QFrame(); card.setObjectName('card'); row = QHBoxLayout(card)
        self.number = QLabel(); self.number.setStyleSheet('font-size: 44px; font-weight: 700;')
        row.addWidget(self.number,1)
        row.addWidget(self.button('−1',lambda:self.adjust(-1)))
        row.addWidget(self.button('+1',lambda:self.adjust(1)))
        layout.addWidget(card)
        row = QHBoxLayout(); row.addWidget(QLabel('Начать с / изменить число'))
        self.start_number = QSpinBox(); self.start_number.setRange(0,999999999); self.start_number.setValue(self.count)
        row.addWidget(self.start_number); row.addWidget(self.button('Применить',self.apply_number)); layout.addLayout(row)
        self.status_label = self.label('Пауза • ручная корректировка доступна','muted'); layout.addWidget(self.status_label)
        self.toggle_button = self.button('Запустить автоподсчёт',self.toggle); self.toggle_button.setObjectName('primary'); layout.addWidget(self.toggle_button)
        grid = QGridLayout()
        self.monitor = QComboBox()
        with mss.mss() as capture:
            for i,m in enumerate(capture.monitors[1:],1):
                self.monitor.addItem(f'Экран {i} · {m["width"]} × {m["height"]}',i)
        self.monitor.setCurrentIndex(min(self.monitor.count()-1,max(0,self.config.get('monitor',1)-1)))
        self.corner = QComboBox(); self.corner.addItems(['Справа сверху','Слева сверху'])
        self.corner.setCurrentIndex(self.config.get('corner',0))
        grid.addWidget(QLabel('Экран игры'),0,0); grid.addWidget(self.monitor,0,1)
        grid.addWidget(QLabel('Угол оверлея'),1,0); grid.addWidget(self.corner,1,1)
        self.threshold = QDoubleSpinBox(); self.threshold.setRange(.65,.99); self.threshold.setSingleStep(.01); self.threshold.setValue(self.config.get('threshold',.86))
        grid.addWidget(QLabel('Порог совпадения'),2,0); grid.addWidget(self.threshold,2,1)
        layout.addLayout(grid)
        row = QHBoxLayout()
        self.show_overlay = QCheckBox('Показывать оверлей'); self.show_overlay.setChecked(self.config.get('overlay',True)); row.addWidget(self.show_overlay)
        self.game_only = QCheckBox('Только активное окно Fortnite'); self.game_only.setChecked(self.config.get('game_only',True)); row.addWidget(self.game_only)
        layout.addLayout(row)
        layout.addWidget(self.label('НАСТРОЙКА РАСПОЗНАВАНИЯ · БЕТА','muted'))
        instructions = self.label('В игре наведи камеру на закрытый сундук и нажми Ctrl+Alt+F9.\nВыдели весь сундук, захватив минимум фона. Открой его, сохрани ракурс\nи нажми Ctrl+Alt+F10 — выдели открытый сундук целиком.\nМожно добавить до 6 образцов каждого состояния с разных ракурсов.','muted')
        instructions.setWordWrap(True); layout.addWidget(instructions)
        self.samples_label = QLabel(); layout.addWidget(self.samples_label)
        row = QHBoxLayout()
        row.addWidget(self.button('Закрытый (через 3 с)',lambda:self.calibrate('closed',3000)))
        row.addWidget(self.button('Открытый (через 3 с)',lambda:self.calibrate('open',3000)))
        row.addWidget(self.button('Очистить образцы',self.clear_samples)); layout.addLayout(row)
        self.preview_label = QLabel('Предпросмотр появится после запуска\nЖёлтая рамка — закрытый • зелёная — открытый')
        self.preview_label.setAlignment(Qt.AlignCenter); self.preview_label.setMinimumHeight(155)
        self.preview_label.setStyleSheet('background: #0b111c; color: #8b9db6; border-radius: 10px;')
        layout.addWidget(self.preview_label)
        footer = self.label('Ctrl+Alt+F6 — старт / пауза    F7 — +1    F8 — −1 (везде с Ctrl+Alt)\nОконный режим без рамки. Считаются только видимые переходы закрыт → открыт.\nПосле смены разрешения заново создай образцы. Возможны пропуски и ошибки.','muted')
        footer.setWordWrap(True); layout.addWidget(footer)
        self.hotkeys = Hotkeys({5:self.toggle,6:lambda:self.adjust(1),7:lambda:self.adjust(-1),8:lambda:self.calibrate('closed'),9:lambda:self.calibrate('open')})
        QApplication.instance().installNativeEventFilter(self.hotkeys)
        if len(self.hotkeys.registered) < 5:
            self.status_label.setText('Часть горячих клавиш занята другой программой; используй кнопки.')
        for control in (self.monitor,self.corner):
            control.currentIndexChanged.connect(self.settings_changed)
        self.show_overlay.toggled.connect(self.settings_changed)
        self.game_only.toggled.connect(self.settings_changed)
        self.threshold.valueChanged.connect(self.settings_changed)
        self.update_count(); self.refresh_samples(); self.place_overlay()

    def label(self,text,name=''):
        label = QLabel(text); label.setObjectName(name); return label

    def button(self,text,callback):
        b = QPushButton(text); b.clicked.connect(callback); return b

    def save(self):
        cfg = dict(count=self.count, monitor=self.monitor.currentData(),corner=self.corner.currentIndex(),
                   overlay=self.show_overlay.isChecked(),threshold=self.threshold.value(),game_only=self.game_only.isChecked())
        try:
            temp = DATA/'settings.tmp'; temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8'); temp.replace(DATA/'settings.json')
        except OSError as error:
            self.status_label.setText(f'Не удалось сохранить: {error}')

    def update_count(self):
        self.number.setText(f'{self.count:,}'.replace(',',' ')); self.overlay.count=self.count; self.overlay.update()

    def adjust(self,delta):
        self.count=max(0,min(999999999,self.count+delta)); self.update_count(); self.save()

    def apply_number(self):
        self.count=self.start_number.value(); self.update_count(); self.save()

    def screen(self):
        # Match MSS physical monitor coordinates against Qt screen geometries/DPI.
        with mss.mss() as capture:
            m = capture.monitors[self.monitor.currentData()]
        screens = QApplication.screens()
        return min(screens,key=lambda s: abs(s.geometry().x()-m['left'])+abs(s.geometry().y()-m['top']))

    def place_overlay(self):
        g=self.screen().availableGeometry()
        x=g.left()+20 if self.corner.currentIndex() else g.right()-self.overlay.width()-20
        self.overlay.move(x,g.top()+20)
        self.overlay.setVisible(self.show_overlay.isChecked() and not self.calibrating)
        exclude_capture(self.overlay)

    def settings_changed(self,*args):
        if self.worker:
            self.stop()
            self.status_label.setText('Настройки изменены • запусти автоподсчёт снова')
        self.save(); self.place_overlay()

    def load_samples(self):
        samples=[]
        for state in ('closed','open'):
            for path in sorted(DATA.glob(f'{state}_*.png')):
                sample=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_COLOR)
                if sample is not None:
                    samples.append((state,sample))
        return samples

    def refresh_samples(self):
        samples=self.load_samples()
        self.samples_label.setText(f'Образцы: закрытый — {sum(s=="closed" for s,_ in samples)}   /   открытый — {sum(s=="open" for s,_ in samples)}')

    def clear_samples(self):
        self.stop()
        for state in ('closed','open'):
            for path in DATA.glob(f'{state}_*.png'):
                path.unlink()
        self.refresh_samples()

    def toggle(self):
        if self.calibrating:
            return
        if self.worker:
            self.stop(); return
        samples=self.load_samples()
        if {state for state,_ in samples} != {'closed','open'}:
            QMessageBox.information(self,'Нужны два состояния','Сначала добавь образец закрытого и открытого сундука.\nРучной счётчик и оверлей уже работают.'); return
        self.worker=Worker(self.monitor.currentData(),samples,self.threshold.value(),self.game_only.isChecked())
        self.worker.counted.connect(self.adjust); self.worker.status.connect(self.worker_status)
        self.worker.preview.connect(self.show_preview); self.worker.failed.connect(self.worker_error)
        self.worker.start(); self.toggle_button.setText('Приостановить автоподсчёт')
        self.overlay.status='АВТО · БЕТА'; self.overlay.update()

    def worker_status(self,text):
        if self.worker:
            self.status_label.setText(text)
            self.overlay.status='ОЖИДАЮ FORTNITE' if text.startswith('Ожидаю') else 'АВТО · БЕТА'
            self.overlay.update()

    def show_preview(self,img):
        if self.worker:
            self.preview_label.setPixmap(QPixmap.fromImage(img).scaled(600,190,Qt.KeepAspectRatio,Qt.SmoothTransformation))

    def worker_error(self,text):
        self.stop(); self.status_label.setText(text)

    def stop(self):
        if self.worker:
            self.worker.requestInterruption(); self.worker.wait(); self.worker=None
        self.toggle_button.setText('Запустить автоподсчёт'); self.status_label.setText('Пауза • ручная корректировка доступна')
        self.overlay.status='РУЧНОЙ РЕЖИМ'; self.overlay.update()

    def calibrate(self,state,delay=200):
        if self.calibrating:
            return
        if len(list(DATA.glob(f'{state}_*.png'))) >= 6:
            QMessageBox.information(self,'Образцы','Достигнут лимит: 6 образцов этого состояния.'); return
        self.stop(); self.calibrating=True; self.hide(); self.overlay.hide()
        QTimer.singleShot(delay,lambda:self.capture_sample(state))

    def capture_sample(self,state):
        try:
            with mss.mss() as capture:
                frame=np.asarray(capture.grab(capture.monitors[self.monitor.currentData()]))[:,:,:3].copy()
            self.capture_scale=min(1.,960/frame.shape[1])
            self.selector=Selector(frame,self.screen().geometry(),'ЗАКРЫТЫЙ' if state=='closed' else 'ОТКРЫТЫЙ')
            self.selector.selected.connect(lambda crop:self.sample_selected(state,crop))
            self.selector.cancelled.connect(self.end_calibration)
            self.selector.show(); self.selector.activateWindow(); self.selector.setFocus()
        except Exception as error:
            self.end_calibration(); self.status_label.setText(f'Ошибка захвата: {error}')

    def sample_selected(self,state,crop):
        try:
            sample=cv2.resize(crop,(round(crop.shape[1]*self.capture_scale),round(crop.shape[0]*self.capture_scale)))
            if min(sample.shape[:2]) < 12 or np.std(cv2.cvtColor(sample,cv2.COLOR_BGR2GRAY)) < 8:
                raise ValueError('Образец слишком маленький или однотонный. Выдели сундук целиком.')
            ok,encoded=cv2.imencode('.png',sample)
            if not ok:
                raise ValueError('Не удалось сохранить образец')
            encoded.tofile(DATA/f'{state}_{time.time_ns()}.png')
            self.refresh_samples()
            self.end_calibration()
            self.status_label.setText('Образец сохранён • автоподсчёт на паузе')
        except Exception as error:
            self.end_calibration(); QMessageBox.warning(self,'Образец',str(error))

    def end_calibration(self):
        self.calibrating=False; self.show(); self.place_overlay()

    def closeEvent(self,event):
        self.stop(); self.save(); self.hotkeys.close(); self.overlay.close()
        if self.selector:
            try: self.selector.close()
            except RuntimeError: pass
        QApplication.instance().quit()


def main():
    app=QApplication(sys.argv); app.setStyle('Fusion'); app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    lock=QLockFile(str(DATA/'instance.lock'))
    if not lock.tryLock(0):
        QMessageBox.information(None,'Chest Counter','Приложение уже запущено. Найди его на панели задач.'); return
    window=MainWindow(); window.show()
    app.exec()


if __name__=='__main__':
    try:
        main()
    except Exception:
        (DATA/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        raise
