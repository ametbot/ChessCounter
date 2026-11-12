"""Offline XP recognition, audio fingerprints and event deduplication."""
from pathlib import Path
import re
import wave
import cv2
import numpy as np

RATE = 16000


def chest_xp(text):
    text = text.casefold().replace('ё', 'е')
    cyrillic = text.translate(str.maketrans({'c':'с','y':'у','h':'н','k':'к','o':'о','p':'р','x':'х','t':'т','a':'а','e':'е','m':'м','b':'в'}))
    # Restrict detection to an award with a chest label, never arbitrary XP.
    chest = re.search(r'\bсундук\w*\b', cyrillic) or re.search(r'\bchest\b', text)
    award = re.search(r'\+\s*[\d\s,.]+', text)
    unit = re.search(r'(?:\bхр\b|\bоп\.?\b|опыт)', cyrillic) or re.search(r'\bxp\b', text)
    quest = re.search(r'обыщите|откройте', cyrillic) or re.search(r'search chests|open chests', text)
    return bool(chest and award and unit and not quest)


class PresenceGate:
    def __init__(self, absent_seconds=.8):
        self.latched = False
        self.hits = 0
        self.last_seen = -999.
        self.absent_seconds = absent_seconds

    def update(self, present, now):
        if present:
            if now-self.last_seen > self.absent_seconds:
                self.hits = 0
                self.latched = False
            self.last_seen = now
            self.hits += 1
            if self.hits >= 2 and not self.latched:
                self.latched = True
                return True
        else:
            self.hits = 0
            if now-self.last_seen >= self.absent_seconds:
                self.latched = False
        return False


class EventMerger:
    def __init__(self, cooldown=2.):
        self.cooldown = cooldown
        self.last = -999.

    def accept(self, now):
        if now-self.last < self.cooldown:
            return False
        self.last = now
        return True


class XPReader:
    def __init__(self):
        from rapidocr import RapidOCR, OCRVersion, ModelType, LangRec
        root = Path(__file__).resolve().parent/'models'
        det, rec = root/'ch_PP-OCRv4_det_mobile.onnx', root/'cyrillic_PP-OCRv5_rec_mobile.onnx'
        for path in (det, rec):
            if not path.is_file():
                raise FileNotFoundError(f'Нет модели OCR: {path.name}. Распакуй всю папку приложения.')
        self.engine = RapidOCR(params={
            'Global.use_cls': False, 'Global.log_level': 'error',
            'Det.ocr_version': OCRVersion.PPOCRV4, 'Det.model_type': ModelType.MOBILE,
            'Det.model_path': str(det), 'Det.limit_side_len': 480,
            'Rec.ocr_version': OCRVersion.PPOCRV5, 'Rec.model_type': ModelType.MOBILE,
            'Rec.lang_type': LangRec.CYRILLIC, 'Rec.model_path': str(rec),
            'EngineConfig.onnxruntime.intra_op_num_threads': 2,
            'EngineConfig.onnxruntime.inter_op_num_threads': 1,
        })

    def read(self, frame):
        result = self.engine(frame)
        texts = result.txts if result.txts is not None else []
        scores = result.scores if result.scores is not None else []
        return ' | '.join(t for t,s in zip(texts, scores) if s >= .65)


def resample(data, source_rate):
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 2:
        data = data.mean(axis=1)
    if source_rate == RATE:
        return data.copy()
    n = round(len(data)*RATE/source_rate)
    if n < 1:
        return np.empty(0, dtype=np.float32)
    return np.interp(np.arange(n)*source_rate/RATE, np.arange(len(data)), data).astype(np.float32)


def write_wav(path, data):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(RATE)
        wav.writeframes((np.clip(data, -1, 1)*32767).astype('<i2').tobytes())


def read_wav(path):
    with wave.open(str(path), 'rb') as wav:
        if wav.getsampwidth() != 2:
            raise ValueError('Нужен WAV PCM 16 бит.')
        samples = np.frombuffer(wav.readframes(wav.getnframes()), '<i2').astype(np.float32)/32768
        return resample(samples.reshape(-1,wav.getnchannels()), wav.getframerate())


def fingerprint(samples):
    samples = np.asarray(samples, np.float32)
    if len(samples) < 512:
        return np.zeros((40,0), np.float32)
    windows = np.lib.stride_tricks.sliding_window_view(samples, 512)[::160]
    spectrum = np.abs(np.fft.rfft(windows*np.hanning(512), axis=1))**2
    # Interpolate to exactly 40 bands even at low frequencies.
    centers = np.geomspace(2,240,40)
    bands = np.stack([spectrum[:,max(1,int(c*.88)):max(2,int(c*1.12)+1)].mean(axis=1) for c in centers], axis=1)
    features = np.log(bands+1e-8)
    features -= features.mean(axis=1, keepdims=True)
    features /= np.maximum(np.linalg.norm(features,axis=1,keepdims=True),1e-6)
    return np.ascontiguousarray(features.T,dtype=np.float32)


class AudioMatcher:
    def __init__(self, reference, threshold=.78):
        if not .2 <= len(reference)/RATE <= 3:
            raise ValueError('Выдели от 0,2 до 3 секунд звука открытия.')
        if float(np.sqrt(np.mean(reference**2))) < .001:
            raise ValueError('Образец слишком тихий. Запиши звук открытия ещё раз.')
        self.template = fingerprint(reference)
        self.threshold = threshold
        self.duration = len(reference)/RATE
        self.last_event = -999.

    def update(self, recent, now):
        if len(recent) < (self.template.shape[1]-1)*160+512:
            return False, 0.
        if np.sqrt(np.mean(recent**2)) < .0005:
            return False, 0.
        features = fingerprint(recent)
        score = float(cv2.minMaxLoc(cv2.matchTemplate(features,self.template,cv2.TM_CCOEFF_NORMED))[1])
        hit = score >= self.threshold and now-self.last_event >= max(1.2,self.duration+.5)
        if hit:
            self.last_event = now
        return hit, score
