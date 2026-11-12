from pathlib import Path
import ctypes
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from xp_detector import ChestXPReader,NotificationGate,is_chest_label,is_xp_amount,chest_award,SCREENSHOT_ROI
from xp_detector import scan_interval


class XPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader=ChestXPReader()
        cls.image=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures'/'chest_xp.png',np.uint8),cv2.IMREAD_COLOR)

    def test_supplied_screenshot_and_duplicate_frames(self):
        text,matched=self.reader.read_notification(self.image)
        self.assertTrue(matched,text)
        gate=NotificationGate()
        self.assertEqual(sum(gate.update(matched,i*.25) for i in range(30)),1)
        for stamp in (8,8.4,8.8): gate.update(False,stamp)
        self.assertFalse(gate.update(matched,9))
        self.assertTrue(gate.update(matched,9.25))

    def test_amount_alone_never_counts(self):
        image=self.image.copy(); image[60:95,145:245]=image[100,100]
        text,matched=self.reader.read_notification(image)
        self.assertFalse(matched,text)

    def test_label_without_xp_never_counts(self):
        image=self.image.copy(); image[20:64,60:225]=image[100,100]
        text,matched=self.reader.read_notification(image)
        self.assertFalse(matched,text)

    def test_other_rewards_and_quests_rejected(self):
        for value in ('УБИЙСТВО','ЯЩИК С ПАТРОНАМИ','Обыщите сундуки','СУНДУКОВ','открыть сундук','CHESTS','ELIMINATION'):
            self.assertFalse(is_chest_label(value),value)
        for value in ('СУНДУК','CYHДYK','сүндук','CHEST','SEARCHED CHEST'):
            self.assertTrue(is_chest_label(value),value)
        for value in ('+600оп','+ 100 ОП','+1 200 XP','+250 опыта'):
            self.assertTrue(is_xp_amount(value),value)
        for value in ('600 ОП','-600 ОП','+600','+600 ОП за убийство'):
            self.assertFalse(is_xp_amount(value),value)

    def test_wrong_spatial_pair_rejected(self):
        amount=dict(text='+600ОП',center=10,height=20,left=0,right=100)
        label=dict(text='СУНДУК',center=40,height=20,left=60,right=110)
        self.assertTrue(chest_award([amount,label]))
        self.assertFalse(chest_award([amount,dict(label,center=250)]))
        self.assertFalse(chest_award([amount,dict(label,left=400,right=450)]))

    def test_slow_ocr_does_not_rearm_visible_notice(self):
        gate=NotificationGate()
        self.assertFalse(gate.update(True,0))
        self.assertTrue(gate.update(True,2))
        self.assertFalse(gate.update(True,6))

    def test_fast_confirmation_preserves_two_read_rule(self):
        gate=NotificationGate()
        self.assertFalse(gate.update(True,0))
        self.assertLess(scan_interval(gate),.1)
        self.assertTrue(gate.update(True,.09))
        self.assertGreaterEqual(scan_interval(gate),.25)
        self.assertFalse(gate.update(True,.39))
        gate.update(False,.7); gate.update(False,1.4)
        self.assertFalse(gate.update(True,1.5))
        self.assertTrue(gate.update(True,1.59))

    def test_screenshot_roi(self):
        self.assertEqual([round(SCREENSHOT_ROI[i]*(1919 if i%2==0 else 1079)) for i in range(4)],[1170,280,300,130])

    def test_plain_f2_f3_bindings(self):
        import xp_app
        calls=[]
        with patch.object(xp_app.USER32,'RegisterHotKey',return_value=True) as register, patch.object(xp_app.USER32,'UnregisterHotKey',return_value=True):
            keys=xp_app.Keys({2:lambda:calls.append(1),3:lambda:calls.append(-1),6:lambda:None})
            self.assertEqual([call.args for call in register.call_args_list],[(None,2,0x4000,0x71),(None,3,0x4000,0x72),(None,6,0x4000,0x75)])
            message=xp_app.wintypes.MSG(); message.message=0x0312
            for key in (2,3):
                message.wParam=key; self.assertTrue(keys.nativeEventFilter(None,ctypes.addressof(message))[0])
            self.assertEqual(calls,[1,-1]); keys.close()


if __name__=='__main__': unittest.main()
