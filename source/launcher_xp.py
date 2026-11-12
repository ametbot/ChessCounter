import ctypes
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def self_test(report,native_capture=False):
    os.environ['QT_QPA_PLATFORM']='windows' if native_capture else 'offscreen'
    with tempfile.TemporaryDirectory(prefix='ChestXP-test-') as temporary:
        os.environ['CHEST_COUNTER_DATA']=temporary
        import xp_app as app
        from PySide6.QtCore import QAbstractNativeEventFilter
        from PySide6.QtGui import QFontDatabase
        import unittest
        import test_xp
        class TestKeys(QAbstractNativeEventFilter):
            def __init__(self,callbacks): super().__init__(); self.registered=list(callbacks)
            def nativeEventFilter(self,kind,message): return False,0
            def close(self): pass
        original_keys=app.Keys; app.Keys=TestKeys
        application=app.QApplication([]); application.setStyle('Fusion'); application.setStyleSheet(app.STYLE)
        for name in ('segoeui.ttf','segoeuib.ttf'): QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name))
        window=app.MainWindow()
        assert not window.windowIcon().isNull() and not window.logo_label.pixmap().isNull()
        assert window.roi==list(app.SCREENSHOT_ROI)
        window.start_number.setValue(83); window.apply_number(); window.adjust(1)
        assert window.count==84 and window.overlay.count==84
        window.adjust(-1); assert window.count==83
        window.on_event(window.epoch); assert window.count==83
        assert json.loads((app.DATA/'settings.json').read_text())['count']==83
        assert not hasattr(window,'device') and not hasattr(window,'record_button')
        epoch=window.epoch
        for percent in (60,140,85):
            window.overlay_size.setValue(percent)
            assert window.overlay.width()==round(236*percent/100)
            assert window.overlay.height()==round(82*percent/100)
            assert window.epoch==epoch
        assert json.loads((app.DATA/'settings.json').read_text())['overlay_scale']==85
        window.show(); application.processEvents()
        assert not window.grab().isNull()
        if native_capture:
            from ctypes import wintypes
            from PySide6.QtCore import QEventLoop,QTimer
            import mss
            import numpy as np
            from PIL import Image
            # Check the actual native window, including resize and hide/show paths.
            get_affinity=app.USER32.GetWindowDisplayAffinity
            get_affinity.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
            get_affinity.restype=wintypes.BOOL
            for size in (60,140,85):
                window.show_overlay.setChecked(False)
                window.overlay_size.setValue(size)
                window.show_overlay.setChecked(True)
                application.processEvents()
                affinity=wintypes.DWORD()
                assert get_affinity(int(window.overlay.winId()),ctypes.byref(affinity)),ctypes.get_last_error()
                assert affinity.value==0,f'Overlay excluded from capture: {affinity.value}'
            settle=QEventLoop(); QTimer.singleShot(350,settle.quit); settle.exec()
            screen=window.screen(); geometry=screen.geometry()
            with mss.mss() as capture:
                monitor=capture.monitors[window.monitor.currentData()]
                ratio=monitor['width']/geometry.width()
                region=dict(left=monitor['left']+round((window.overlay.x()-geometry.x())*ratio),
                    top=monitor['top']+round((window.overlay.y()-geometry.y())*ratio),
                    width=round(window.overlay.width()*ratio),height=round(window.overlay.height()*ratio))
                pixels=np.array(capture.grab(region))
            # The warm accent and light count must exist in a desktop capture.
            gold=(pixels[:,:,2]>180)&(pixels[:,:,1]>90)&(pixels[:,:,1]<220)&(pixels[:,:,0]<140)
            light=(pixels[:,:,2]>210)&(pixels[:,:,1]>210)&(pixels[:,:,0]>180)
            assert gold.sum()>10 and light.sum()>20,'Overlay missing from desktop capture'
            Image.fromarray(pixels[:,:,[2,1,0]]).save(str(report.with_name(report.stem+'-capture.png')))
        if os.environ.get('CHEST_COUNTER_TEST_IMAGE'):
            image_path=Path(os.environ['CHEST_COUNTER_TEST_IMAGE'])
            window.grab().save(str(image_path))
            for size in (60,85,140):
                window.overlay_size.setValue(size)
                window.overlay.grab().save(str(image_path.with_name(f'overlay-{size}.png')))
            window.overlay_size.setValue(85)
        window.close(); app.Keys=original_keys
        output=io.StringIO()
        result=unittest.TextTestRunner(stream=output,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_xp))
        assert result.wasSuccessful(),output.getvalue()
        report.write_text(json.dumps({'ok':True,'tests':result.testsRun,'details':output.getvalue(),
            'ui':'Qt rendering, count persistence, screenshot ROI default, no sound controls passed',
            'native_capture':'WDA_NONE after resize/hide/show; overlay pixels in desktop capture' if native_capture else 'Not tested (offscreen)',
            'scope':'Supplied screenshot and logic verified. Live Fortnite sequence and Discord call not tested.'},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    test_mode=len(sys.argv)>=3 and sys.argv[1] in ('--self-test','--capture-test')
    try:
        if test_mode: self_test(Path(sys.argv[2]),native_capture=sys.argv[1]=='--capture-test')
        else:
            import xp_app
            xp_app.main()
    except Exception:
        error=traceback.format_exc()
        if test_mode: Path(sys.argv[2]).write_text(json.dumps({'ok':False,'error':error},ensure_ascii=False,indent=2),encoding='utf-8')
        else:
            folder=Path(os.environ.get('LOCALAPPDATA','.'))/'ChestCounter'; folder.mkdir(parents=True,exist_ok=True)
            (folder/'error.log').write_text(error,encoding='utf-8')
            ctypes.windll.user32.MessageBoxW(None,'Ошибка запуска. Подробности: '+str(folder/'error.log'),'Chest Counter XP',0x10)
        sys.exit(1)
