"""Local, calibrated visual transition detector. No game/process access."""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class Detection:
    state: str
    box: tuple
    score: float


def overlap(a, b):
    x, y = max(a[0], b[0]), max(a[1], b[1])
    w = max(0, min(a[0]+a[2], b[0]+b[2])-x)
    h = max(0, min(a[1]+a[3], b[1]+b[3])-y)
    intersection = w*h
    return intersection / max(1, min(a[2]*a[3], b[2]*b[3]))


class Matcher:
    def __init__(self, samples, threshold=0.86):
        self.threshold = threshold
        self.templates = []
        for state, sample in samples:
            gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
            for scale in (0.65, 0.8, 1.0, 1.2, 1.45):
                w, h = round(gray.shape[1]*scale), round(gray.shape[0]*scale)
                if min(w, h) >= 12:
                    self.templates.append((state, cv2.resize(gray, (w, h))))

    def detect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        found = []
        for state, sample in self.templates:
            h, w = sample.shape
            if h > gray.shape[0] or w > gray.shape[1]:
                continue
            result = cv2.matchTemplate(gray, sample, cv2.TM_CCOEFF_NORMED)
            for _ in range(6):
                _, score, _, (x, y) = cv2.minMaxLoc(result)
                if score < self.threshold:
                    break
                found.append(Detection(state, (x, y, w, h), score))
                result[max(0,y-h//2):y+h//2+1, max(0,x-w//2):x+w//2+1] = -1
        kept = []
        for d in sorted(found, key=lambda d: d.score, reverse=True):
            if not any(overlap(d.box, k.box) > .45 for k in kept):
                kept.append(d)
        return kept[:12]


class TransitionTracker:
    """Two closed frames then two open frames; never count open-only objects."""
    def __init__(self):
        self.tracks = []

    def update(self, detections, now):
        self.tracks = [t for t in self.tracks if now-t['seen'] < 3]
        used = set()
        count = 0
        for d in detections:
            choices = [(overlap(t['box'], d.box), i, t)
                       for i, t in enumerate(self.tracks) if i not in used]
            choices = [c for c in choices if c[0] > .25]
            if choices:
                _, idx, t = max(choices, key=lambda c: c[0])
            else:
                t = dict(box=d.box, seen=now, closed=0, opened=0,
                         last_closed=-999, counted=False, open_first=d.state=='open')
                self.tracks.append(t)
                idx = len(self.tracks)-1
            used.add(idx)
            if now-t['seen'] > .7:
                t['opened'] = 0
                t['closed'] = 0
            t['box'], t['seen'] = d.box, now
            if d.state == 'closed':
                t['closed'] += 1
                t['opened'] = 0
                t['last_closed'] = now
            else:
                t['opened'] += 1
                if (not t['counted'] and not t['open_first'] and t['closed'] >= 2
                        and t['opened'] >= 2 and now-t['last_closed'] < 1.6):
                    count += 1
                    t['counted'] = True
        return count


def shrink(frame):
    scale = min(1., 960 / frame.shape[1])
    return cv2.resize(frame, (round(frame.shape[1]*scale), round(frame.shape[0]*scale)))
