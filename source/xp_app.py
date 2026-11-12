import json
import sys
import time
import ctypes
from pathlib import Path
from ctypes import wintypes
import mss
import numpy as np
from PySide6.QtCore import Qt,QThread,QTimer,Signal,QLockFile,QAbstractNativeEventFilter
from PySide6.QtGui import QPixmap,QIcon
from PySide6.QtWidgets import (QApplication,QWidget,QLabel,QPushButton,QVBoxLayout,QHBoxLayout,
    QGridLayout,QSpinBox,QComboBox,QCheckBox,QFrame,QMessageBox,QScrollArea,QSlider,QToolButton)
from app import Selector,DATA,USER32,qimage,foreground_game
from minimal_ui import Overlay,STYLE
from xp_detector import SCREENSHOT_ROI,ChestXPReader,NotificationGate,scan_interval

LOGO_PATH=Path(__file__).resolve().parent/'assets'/'logo.png'


class Keys(QAbstractNativeEventFilter):
    def __init__(self,callbacks):
        super().__init__(); self.callbacks=callbacks
        # F2/F3/F6, no Ctrl or Alt. MOD_NOREPEAT prevents held-key repetition.
        self.registered=[key for key in callbacks if USER32.RegisterHotKey(None,key,0x4000,0x70+key-1)]

    def nativeEventFilter(self,kind,message):
        msg=wintypes.MSG.from_address(int(message))
        if msg.message==0x0312 and msg.wParam in self.callbacks:
            self.callbacks[msg.wParam](); return True,0
        return False,0

    def close(self):
        for key in self.registered: USER32.UnregisterHotKey(None,key)


class XPWorker(QThread):
    event=Signal()
    status=Signal(str)
    preview=Signal(object,str,bool)
    failed=Signal(str)

    def __init__(self,monitor,roi,game_only):
        super().__init__(); self.monitor=monitor; self.roi=roi; self.game_only=game_only
        self.preview_enabled=False

    def run(self):
        try:
            self.status.emit('Загружаю распознавание…')
            reader=ChestXPReader(); reader.warm_up(); gate=NotificationGate()
            last_status=''; last_preview=-999.
            with mss.mss() as capture:
                monitor=capture.monitors[self.monitor]; x,y,w,h=self.roi
                region=dict(left=monitor['left']+round(x*monitor['width']),top=monitor['top']+round(y*monitor['height']),
                    width=max(30,round(w*monitor['width'])),height=max(30,round(h*monitor['height'])))
                while not self.isInterruptionRequested():
                    started=time.monotonic()
                    if self.game_only and not foreground_game():
                        gate=NotificationGate(); status='Ожидаю активное окно Fortnite'; interval=.25
                    else:
                        frame=np.asarray(capture.grab(region))[:,:,:3].copy()
                        text,match=reader.read_notification(frame)
                        if gate.update(match,time.monotonic()): self.event.emit()
                        now=time.monotonic()
                        if self.preview_enabled and now-last_preview>=.5:
                            self.preview.emit(qimage(frame),text,match); last_preview=now
                        status='Вижу награду за сундук' if match else 'Ожидаю награду «СУНДУК»'
                        interval=scan_interval(gate)
                    if status!=last_status:
                        self.status.emit(status); last_status=status
                    self.msleep(max(8,int((interval-(time.monotonic()-started))*1000)))
        except Exception as e: self.failed.emit(str(e))


class MainWindow(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle('Chest Counter · Fast'); self.resize(600,790); self.setMinimumSize(520,600)
        self.setWindowIcon(QIcon(str(LOGO_PATH)))
        try: self.config=json.loads((DATA/'settings.json').read_text(encoding='utf-8'))
        except (OSError,ValueError): self.config={}
        self.count=max(0,min(999999999,int(self.config.get('count',0))))
        self.roi=self.config.get('xp_only_roi',list(SCREENSHOT_ROI))
        if not (isinstance(self.roi,list) and len(self.roi)==4 and all(isinstance(v,(int,float)) for v in self.roi)
            and 0<=self.roi[0]<1 and 0<=self.roi[1]<1 and self.roi[2]>0 and self.roi[3]>0
            and self.roi[0]+self.roi[2]<=1.001 and self.roi[1]+self.roi[3]<=1.001): self.roi=list(SCREENSHOT_ROI)
        self.worker=None; self.epoch=0; self.calibrating=False; self.closing=False; self.selector=None
        self.overlay=Overlay()
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); outer.addWidget(scroll)
        content=QWidget(); scroll.setWidget(content); layout=QVBoxLayout(content); layout.setContentsMargins(26,24,26,22); layout.setSpacing(16)
        heading=QHBoxLayout(); heading.setSpacing(15)
        self.logo_label=QLabel(); self.logo_label.setFixedSize(48,48)
        self.logo_label.setPixmap(QPixmap(str(LOGO_PATH)).scaled(48,48,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        self.logo_label.setAccessibleName('Логотип Chest Counter')
        heading.addWidget(self.logo_label)
        brand=QVBoxLayout(); brand.setSpacing(2)
        title=self.label('Chest Counter','title'); brand.addWidget(title)
        brand.addWidget(self.label('FORTNITE  /  СЧЁТЧИК СУНДУКОВ','eyebrow')); heading.addLayout(brand,1)
        badge=self.label('FAST','badge'); badge.setFixedHeight(26); badge.setAlignment(Qt.AlignCenter)
        heading.addWidget(badge); layout.addLayout(heading)
        card=QFrame(); card.setObjectName('counterCard'); card_layout=QVBoxLayout(card); card_layout.setContentsMargins(22,18,22,18)
        card_layout.addWidget(self.label('Открыто сундуков','muted')); row=QHBoxLayout(); card_layout.addLayout(row)
        self.number=QLabel(); self.number.setStyleSheet('font-size:48px;font-weight:600;color:#fff4dc;'); row.addWidget(self.number,1)
        card_layout.addWidget(self.label('F2  +1     ·     F3  −1','muted')); layout.addWidget(card)
        row=QHBoxLayout(); row.addWidget(self.label('Начальное число','muted'))
        self.start_number=QSpinBox(); self.start_number.setRange(0,999999999); self.start_number.setValue(self.count)
        row.addWidget(self.start_number); row.addWidget(self.button('Применить',self.apply_number)); layout.addLayout(row)
        self.status_label=self.label('На паузе','status'); self.status_label.setWordWrap(True)
        self.toggle_button=self.button('Начать подсчёт  ·  F6',self.toggle); self.toggle_button.setToolTip('Старт / пауза · F6'); self.toggle_button.setObjectName('primary'); layout.addWidget(self.toggle_button)
        layout.addWidget(self.status_label)
        settings=QFrame(); settings.setObjectName('card'); settings_layout=QVBoxLayout(settings); settings_layout.setContentsMargins(18,16,18,16); settings_layout.setSpacing(14)
        settings_layout.addWidget(self.label('ЭКРАН И ОВЕРЛЕЙ','eyebrow')); layout.addWidget(settings)
        grid=QGridLayout(); self.monitor=QComboBox()
        with mss.mss() as capture:
            for i,m in enumerate(capture.monitors[1:],1): self.monitor.addItem(f'Экран {i} · {m["width"]} × {m["height"]}',i)
        self.monitor.setCurrentIndex(max(0,min(self.monitor.count()-1,self.config.get('monitor',1)-1)))
        self.corner=QComboBox(); self.corner.addItems(['Справа сверху','Слева сверху']); self.corner.setCurrentIndex(self.config.get('corner',0))
        grid.addWidget(QLabel('Экран игры'),0,0); grid.addWidget(self.monitor,0,1)
        grid.addWidget(QLabel('Угол оверлея'),1,0); grid.addWidget(self.corner,1,1); grid.setVerticalSpacing(10); grid.setHorizontalSpacing(18); settings_layout.addLayout(grid)
        row=QHBoxLayout(); row.addWidget(self.label('Размер оверлея','muted'))
        self.overlay_size=QSlider(Qt.Horizontal); self.overlay_size.setRange(60,140); self.overlay_size.setSingleStep(5)
        self.overlay_size.setValue(max(60,min(140,int(self.config.get('overlay_scale',85)))))
        self.size_label=self.label(f'{self.overlay_size.value()}%','muted'); self.size_label.setFixedWidth(40)
        row.addWidget(self.overlay_size,1); row.addWidget(self.size_label); settings_layout.addLayout(row)
        self.overlay.set_scale(self.overlay_size.value())
        row=QHBoxLayout(); self.show_overlay=QCheckBox('Оверлей'); self.show_overlay.setChecked(self.config.get('overlay',True))
        self.game_only=QCheckBox('Только активное окно Fortnite'); self.game_only.setChecked(self.config.get('game_only',True))
        row.addWidget(self.show_overlay); row.addWidget(self.game_only); settings_layout.addLayout(row)
        capture_hint=self.label('Для Discord и записи выбери захват всего экрана.\nОверлей будет виден вместе с игрой.','muted'); capture_hint.setWordWrap(True); settings_layout.addWidget(capture_hint)
        self.details_button=QToolButton(); self.details_button.setText('Проверка распознавания'); self.details_button.setCheckable(True)
        self.details_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon); self.details_button.setArrowType(Qt.RightArrow); layout.addWidget(self.details_button)
        self.details=QWidget(); details_layout=QVBoxLayout(self.details); details_layout.setContentsMargins(0,0,0,0); self.details.hide(); layout.addWidget(self.details)
        self.details_button.toggled.connect(self.toggle_details)
        rule=self.label('Область XP настроена по твоему скриншоту.\nДля зачёта нужны сумма опыта и подпись «СУНДУК».','muted'); rule.setWordWrap(True); details_layout.addWidget(rule)
        self.preview_label=QLabel('Здесь появится область уведомления справа от центра'); self.preview_label.setAlignment(Qt.AlignCenter); self.preview_label.setMinimumHeight(160)
        self.preview_label.setStyleSheet('background:#101113;color:#93969e;border-radius:9px;'); self.preview_label.setWordWrap(True); details_layout.addWidget(self.preview_label)
        self.ocr_text=self.label('Прочитано: —','muted'); self.ocr_text.setWordWrap(True); details_layout.addWidget(self.ocr_text)
        row=QHBoxLayout(); row.addWidget(self.button('Сбросить область',self.reset_region)); row.addWidget(self.button('Выбрать область',self.select_region)); details_layout.addLayout(row)
        layout.addStretch(1)
        self.keys=Keys({2:lambda:self.adjust(1),3:lambda:self.adjust(-1),6:self.toggle})
        QApplication.instance().installNativeEventFilter(self.keys)
        missing=set((2,3,6))-set(self.keys.registered)
        if missing: self.status_label.setText('Клавиши заняты: '+', '.join(f'F{k}' for k in sorted(missing)))
        self.monitor.currentIndexChanged.connect(self.settings_changed)
        self.game_only.toggled.connect(self.settings_changed)
        self.corner.currentIndexChanged.connect(self.overlay_changed)
        self.show_overlay.toggled.connect(self.overlay_changed)
        self.overlay_size.valueChanged.connect(self.overlay_changed)
        self.update_count(); self.place_overlay()

    def label(self,text,name=''):
        result=QLabel(text); result.setObjectName(name); return result

    def button(self,text,callback):
        result=QPushButton(text); result.clicked.connect(callback); return result

    def save(self):
        self.config.update(count=self.count,monitor=self.monitor.currentData(),corner=self.corner.currentIndex(),
            overlay=self.show_overlay.isChecked(),game_only=self.game_only.isChecked(),xp_only_roi=list(self.roi),overlay_scale=self.overlay_size.value())
        try:
            temporary=DATA/'settings.tmp'; temporary.write_text(json.dumps(self.config,ensure_ascii=False,indent=2),encoding='utf-8'); temporary.replace(DATA/'settings.json')
        except OSError as e: self.status_label.setText('Ошибка сохранения: '+str(e))

    def update_count(self):
        self.number.setText(f'{self.count:,}'.replace(',',' ')); self.overlay.count=self.count; self.overlay.update()

    def adjust(self,delta):
        self.count=max(0,min(999999999,self.count+delta)); self.update_count(); self.save()

    def apply_number(self):
        self.count=self.start_number.value(); self.update_count(); self.save()

    def screen(self):
        with mss.mss() as capture: m=capture.monitors[self.monitor.currentData()]
        return min(QApplication.screens(),key=lambda s:abs(s.geometry().x()-m['left'])+abs(s.geometry().y()-m['top']))

    def place_overlay(self):
        g=self.screen().availableGeometry(); x=g.left()+20 if self.corner.currentIndex() else g.right()-self.overlay.width()-20
        # Keep the normal Windows capture policy: viewers should see the counter.
        self.overlay.move(x,g.top()+20); self.overlay.setVisible(self.show_overlay.isChecked() and not self.calibrating)

    def settings_changed(self,*args):
        if self.worker: self.stop()
        self.save(); self.place_overlay()

    def overlay_changed(self,*args):
        self.overlay.set_scale(self.overlay_size.value())
        self.size_label.setText(f'{self.overlay_size.value()}%')
        self.save(); self.place_overlay()

    def toggle_details(self,visible):
        self.details.setVisible(visible)
        self.details_button.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)
        if self.worker: self.worker.preview_enabled=visible

    def toggle(self):
        if self.calibrating or self.closing: return
        if self.worker: self.stop(); return
        self.epoch+=1; epoch=self.epoch
        self.worker=XPWorker(self.monitor.currentData(),self.roi,self.game_only.isChecked())
        self.worker.preview_enabled=self.details_button.isChecked()
        self.worker.event.connect(lambda e=epoch:self.on_event(e))
        self.worker.status.connect(lambda text,e=epoch:self.worker_status(text,e))
        self.worker.preview.connect(lambda img,text,matched,e=epoch:self.preview(img,text,matched,e))
        self.worker.failed.connect(lambda text,e=epoch:self.failed(text,e)); self.worker.start(QThread.LowPriority)
        self.toggle_button.setText('Приостановить  ·  F6')

    def on_event(self,epoch):
        if self.worker and epoch==self.epoch: self.adjust(1)

    def worker_status(self,text,epoch):
        if self.worker and epoch==self.epoch:
            self.status_label.setText(text)

    def preview(self,img,text,matched,epoch):
        if self.worker and epoch==self.epoch:
            self.preview_label.setPixmap(QPixmap.fromImage(img).scaled(480,160,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            self.ocr_text.setText(('✓ Сундук: ' if matched else 'Прочитано: ')+(text[:180] or '—'))

    def failed(self,text,epoch):
        if self.worker and epoch==self.epoch: self.stop(); self.status_label.setText('Ошибка: '+text)

    def stop(self):
        self.epoch+=1
        if self.worker: self.worker.requestInterruption(); self.worker.wait(); self.worker=None
        self.toggle_button.setText('Начать подсчёт  ·  F6'); self.status_label.setText('На паузе')

    def reset_region(self):
        self.stop(); self.roi=list(SCREENSHOT_ROI); self.save(); self.status_label.setText('Область восстановлена по твоему скриншоту')

    def select_region(self):
        if self.calibrating: return
        self.stop(); self.calibrating=True; self.hide(); self.overlay.hide(); QTimer.singleShot(3000,self.capture_region)

    def capture_region(self):
        if self.closing: return
        try:
            with mss.mss() as capture: frame=np.asarray(capture.grab(capture.monitors[self.monitor.currentData()]))[:,:,:3].copy()
            self.selector=Selector(frame,self.screen().geometry(),'ОБЛАСТЬ ОПЫТА','выдели сумму ОП и подпись СУНДУК • Esc: отмена')
            self.selector.region_selected.connect(self.region_chosen); self.selector.cancelled.connect(self.end_calibration)
            self.selector.show(); self.selector.activateWindow(); self.selector.setFocus()
        except Exception as e: self.end_calibration(); self.status_label.setText(str(e))

    def region_chosen(self,roi):
        self.roi=list(roi); self.save(); self.end_calibration()

    def end_calibration(self):
        self.calibrating=False; self.show(); self.place_overlay()

    def closeEvent(self,event):
        self.closing=True; self.stop(); self.save(); self.keys.close(); self.overlay.close()
        if self.selector:
            try: self.selector.close()
            except RuntimeError: pass
        QApplication.instance().quit()


def main():
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ChestCounter.XP.Desktop')
    application=QApplication(sys.argv); application.setStyle('Fusion'); application.setStyleSheet(STYLE); application.setQuitOnLastWindowClosed(False)
    application.setWindowIcon(QIcon(str(LOGO_PATH)))
    lock=QLockFile(str(DATA/'instance.lock'))
    if not lock.tryLock(0):
        QMessageBox.information(None,'Chest Counter','Закрой предыдущую версию счётчика перед запуском.'); return
    window=MainWindow(); window.show(); application.exec()
