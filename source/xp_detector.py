"""Chest-only XP award detection calibrated against the supplied screenshot."""
import re
import cv2
from signals_engine import XPReader

# Supplied screenshot: 1919 x 1079. Covers the award with room for its animation.
SCREENSHOT_ROI = [1170/1919, 280/1079, 300/1919, 130/1079]
TRANSLATION = str.maketrans({'c':'с','y':'у','h':'н','k':'к','o':'о','p':'р',
    'x':'х','t':'т','a':'а','e':'е','m':'м','b':'в','ү':'у','ё':'е'})


def normalize(text):
    return text.casefold().translate(TRANSLATION).strip()


def is_chest_label(text):
    raw=text.casefold().strip()
    if raw in ('chest','searched chest','rare chest','treasure chest'):
        return True
    return normalize(text) in ('сундук','обыскан сундук','открыт сундук','редкий сундук','сундук с сокровищами')


def is_xp_amount(text):
    text=normalize(text).replace('−','-')
    return bool(re.fullmatch(r'\+\s*\d[\d\s,.]*\s*(?:оп\.?|опыта|опыт|хр)',text))


def group_lines(entries):
    rows=[]
    for text,score,box in sorted(entries,key=lambda e:min(float(p[1]) for p in e[2])):
        if score<.60:
            continue
        left=min(float(p[0]) for p in box); right=max(float(p[0]) for p in box)
        top=min(float(p[1]) for p in box); bottom=max(float(p[1]) for p in box)
        center=(top+bottom)/2
        target=next((row for row in rows if abs(row['center']-center)<max(bottom-top,row['height'])*.55),None)
        if target is None:
            target=dict(center=center,height=bottom-top,left=left,right=right,items=[])
            rows.append(target)
        target['items'].append((left,text)); target['left']=min(target['left'],left); target['right']=max(target['right'],right)
    for row in rows:
        row['text']=' '.join(t for _,t in sorted(row['items']))
    return rows


def chest_award(rows):
    for label in rows:
        if not is_chest_label(label['text']): continue
        for amount in rows:
            if not is_xp_amount(amount['text']): continue
            height=max(label['height'],amount['height'],1)
            vertical=label['center']-amount['center']
            horizontal=max(label['left']-amount['right'],amount['left']-label['right'],0)
            if 0<vertical<height*4 and horizontal<height*1.5:
                return True
    return False


class ChestXPReader(XPReader):
    def __init__(self):
        super().__init__()
        # Detect text on a bounded image, but retain enlarged source pixels for
        # character recognition. Single-thread sessions avoid competing worker
        # pools/spinning while the game is running.
        cv2.setNumThreads(1)
        self.engine.cfg.Det.limit_side_len=480
        self.engine.cfg.Det.limit_type='max'
        self.engine.cfg.EngineConfig.onnxruntime.intra_op_num_threads=1
        self.engine.cfg.EngineConfig.onnxruntime.inter_op_num_threads=1

    def warm_up(self):
        self.engine._load_det_model()
        self.engine._load_rec_model()

    def read_notification(self,frame):
        # Enlarging the small italic notification and removing its purple outline
        # improves Cyrillic recognition; keep original frame for the UI preview.
        scale=min(3.,1440/max(frame.shape[:2]))
        enlarged=cv2.resize(frame,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
        gray=cv2.cvtColor(enlarged,cv2.COLOR_BGR2GRAY)
        gray=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
        result=self.engine(gray)
        rows=group_lines(zip(result.txts or (),result.scores if result.scores is not None else (),result.boxes if result.boxes is not None else ()))
        text=' | '.join(row['text'] for row in rows)
        return text,chest_award(rows)


class NotificationGate:
    def __init__(self):
        self.latched=False; self.hits=0; self.misses=0; self.absent_since=None

    def update(self,present,now):
        if present:
            self.absent_since=None; self.misses=0; self.hits+=1
            if self.hits>=2 and not self.latched:
                self.latched=True
                return True
        else:
            self.hits=0; self.misses+=1
            if self.absent_since is None: self.absent_since=now
            if self.misses>=2 and now-self.absent_since>=.65: self.latched=False
        return False


def scan_interval(gate):
    # Confirm a new candidate promptly; scan confirmed notifications less often.
    if gate.latched: return .30
    if gate.hits: return .08
    return .16
