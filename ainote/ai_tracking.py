"""Local Beat This! inference and bounded, past-window live adaptation.

Official code and weights: MIT, CPJKU; docs/licenses/beat-this-MIT.txt.
No arbitrary checkpoints, network inference, or recording persistence.
"""
from pathlib import Path
from dataclasses import replace
from collections import deque
import hashlib
import json
import queue
import threading
import time
import numpy as np
from .tracking import AubioTracker, BeatState
from .bass_tracking import BassTracker, fuse_bass

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAMES = ('small0', 'small1')
_MODELS = {}
_MODEL_LOCK = threading.Lock()


# 学習済みの重みをPC内のファイルから読み、次の推論でも使えるように保持する。
def get_predictor(name):
    if name not in MODEL_NAMES:
        raise ValueError('未対応のAIモデルです')
    with _MODEL_LOCK:
        if name not in _MODELS:
            import torch
            from beat_this.inference import Audio2Beats
            torch.set_num_threads(2)
            path = ROOT/'models'/f'beat-this-{name}.ckpt'
            manifest = json.loads((ROOT/'models/manifest.json').read_text())
            expected = manifest[name]['sha256']
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('モデルのチェックサムが一致しません。再取得してください。')
            # Local path: upstream uses torch.load(weights_only=True), not a
            # network URL or unrestricted pickle checkpoint from the user.
            _MODELS[name] = Audio2Beats(checkpoint_path=str(path), device='cpu', dbn=False)
        return _MODELS[name]


# 入力音声を整え、モデルから拍と小節頭の時刻を受け取る。
def infer_beats(audio, rate, name='small0'):
    predictor = get_predictor(name)
    mono = np.asarray(audio, dtype='float32')
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    if not len(mono) or not np.isfinite(mono).all():
        raise ValueError('解析できる音声がありません')
    # Model input level normalization, capped to avoid extreme noise gain.
    rms = float(np.sqrt(np.mean(mono**2)))
    mono = np.clip(mono*min(10, .08/max(rms, .008)), -1, 1)
    with _MODEL_LOCK:
        beats, downbeats = predictor(mono, rate)
    return np.asarray(beats), np.asarray(downbeats)


# 拍の時刻から、拍の間隔（BPM）と次の拍を予測する基準時刻を求める。
def clock_from_beats(beats, start, end, previous=None, name='small0'):
    """Use only beats inside received audio, excluding unreliable right edge."""
    valid = np.asarray(beats)
    valid = valid[(valid >= .15) & (valid <= end-start-.2)] + start
    if len(valid) < 4:
        return BeatState(updated=end, reason='AI：拍の候補を確認中')
    recent = valid[-6:]
    intervals = np.diff(recent)
    period = float(np.median(intervals))
    variation = float(np.std(intervals)/max(period, 1e-6))
    if not .286 <= period <= 1.09 or variation > .16 or end-recent[-1] > period*2:
        return BeatState(updated=end, reason='AI：拍間隔が不安定')
    # Robust slope across several beats reduces 20-ms model-frame rounding
    # error; a median of adjacent intervals alone can jump by several BPM.
    slopes=[(recent[j]-recent[i])/(j-i) for i in range(len(recent)) for j in range(i+1,len(recent))]
    period=float(np.median(slopes))
    intercept=float(np.median(recent-np.arange(len(recent))*period))
    bpm, phase = 60/period, intercept+(len(recent)-1)*period
    ordinal = 0
    if previous is not None and previous.locked:
        ordinal = previous.beat_index + max(0, round((phase-previous.phase)*previous.bpm/60))
    return BeatState(bpm, phase, max(0, 1-variation/.16), 0, end, True,
                     f'AI {name}：受信済み音声から拍を予測', len(valid), ordinal)


# 2モデルのテンポと拍位置を照らし合わせ、演奏に使う候補を決める。
def consensus_clock(first, second, end, previous=None):
    """Accept AI only when independently trained checkpoints agree."""
    if not first.locked or not second.locked:
        return BeatState(updated=end, reason='AI：2モデルの確定待ち')
    if abs(first.bpm-second.bpm)/first.bpm > .06:
        # Octave ambiguity is common in recorded music. Resolve it only with
        # a recent, already agreed clock; never guess an initial metrical level.
        slow, fast = sorted((first, second), key=lambda state: state.bpm)
        usable = (previous is not None and previous.locked
                  and 0 <= end-previous.updated <= 8)
        if usable and abs(fast.bpm/slow.bpm-2) <= .06:
            period = 60/fast.bpm
            error = (slow.phase-fast.phase+period/2)%period-period/2
            chosen = min((slow, fast), key=lambda state: abs(state.bpm-previous.bpm))
            old_period = 60/previous.bpm
            old_error = (chosen.phase-previous.phase+old_period/2)%old_period-old_period/2
            if (abs(error) <= .035 and abs(chosen.bpm-previous.bpm) <= 3
                    and abs(old_error) <= .06):
                return replace(chosen, confidence=min(first.confidence, second.confidence),
                               reason='AI 半分・倍の候補：確定済みテンポを維持')
        return BeatState(updated=end, reason='AI：テンポ候補が不一致')
    period = 60/((first.bpm+second.bpm)/2)
    phase_error = (first.phase-second.phase+period/2)%period-period/2
    if abs(phase_error) > .035:
        return BeatState(updated=end, reason='AI：拍位置が不一致')
    return replace(second, bpm=(first.bpm+second.bpm)/2,
                   phase=second.phase+phase_error/2,
                   confidence=min(first.confidence, second.confidence),
                   reason='AI 2モデル一致：拍を予測')


def infer_clock(audio, rate, start, end, mode='ensemble', previous=None):
    if mode == 'ensemble':
        candidates=[]
        for name in MODEL_NAMES:
            beats,_ = infer_beats(audio, rate, name)
            candidates.append(clock_from_beats(beats,start,end,previous,name))
        return consensus_clock(*candidates,end,previous)
    beats,_ = infer_beats(audio, rate, mode)
    return clock_from_beats(beats,start,end,previous,mode)


# AIは別スレッドで動かし、結果を待つ間もaubioで拍を推定する。
class HybridTracker:
    """Aubio feeds cheaply; a latest-only worker handles heavier inference."""
    def __init__(self, rate, block=512, model='ensemble', bass_support=False):
        self.rate, self.block, self.model = rate, block, model
        self.fallback = AubioTracker(rate, block)
        self.bass = BassTracker(rate, block) if bass_support else None
        self.audio = deque(maxlen=int(np.ceil(rate*8/block)))
        self.mailbox = queue.Queue(maxsize=1)
        self.closed = threading.Event()
        self.result = BeatState()
        self.error = ''
        self.elapsed_ms = 0
        self.last_submit = -100
        self.last_sound = -100
        self.previous = BeatState()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def _run(self):
        try:
            for name in MODEL_NAMES if self.model == 'ensemble' else (self.model,):
                get_predictor(name)  # Load away from audio and GUI threads.
        except Exception as exc:
            self.error = f'AIを読み込めません。従来方式で継続: {exc}'
            return
        last_confirmed = None
        while not self.closed.is_set():
            try:
                audio, start, end = self.mailbox.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                before = time.perf_counter()
                candidate = infer_clock(audio, self.rate, start, end, self.model, last_confirmed)
                if candidate.locked:
                    last_confirmed = candidate
                self.elapsed_ms = (time.perf_counter()-before)*1000
                if not self.closed.is_set():
                    self.result = candidate
            except Exception as exc:
                self.error = f'AI解析に失敗。従来方式で継続: {exc}'
                self.result = BeatState()

    def feed(self, data, timestamp):
        fallback = self.fallback.feed(data, timestamp)
        bass = self.bass.feed(data, timestamp) if self.bass is not None else None
        level = fallback.level
        if level > .0003:
            self.last_sound = timestamp
        self.audio.append(np.array(data, dtype='float32', copy=True))
        end = timestamp + self.block/self.rate
        if len(self.audio)*self.block/self.rate >= 4 and timestamp-self.last_submit >= 1:
            self.last_submit = timestamp
            audio = np.concatenate(tuple(self.audio))
            snapshot = (audio, end-len(audio)/self.rate, end)
            if self.mailbox.full():
                try: self.mailbox.get_nowait()
                except queue.Empty: pass
            try: self.mailbox.put_nowait(snapshot)
            except queue.Full: pass
        candidate = self.result
        audible = timestamp-self.last_sound < 1.1
        if not audible:
            self.result = BeatState()
        use_ai = candidate.locked and 0 <= timestamp-candidate.updated < 2.5 and audible
        state = candidate if use_ai else fallback
        reason = (f'{state.reason} / AI計算 {self.elapsed_ms:.0f} ms' if use_ai else
                  f'{state.reason} / {candidate.reason if candidate.updated > -100 else "AIモデル準備中"}・従来方式で補助')
        if bass is not None:
            merged = fuse_bass(state, bass, timestamp)
            if merged.reason != state.reason:
                reason += " / 低音一致（5秒窓）"
            state = merged
        if self.error:
            reason = self.error
        ordinal = self.previous.beat_index
        if state.locked:
            if self.previous.locked:
                ordinal += max(0, round((state.phase-self.previous.phase)*self.previous.bpm/60))
            else:
                ordinal = 0
        self.previous = replace(state, level=level, updated=timestamp,
                                beat_index=ordinal, reason=reason)
        return self.previous

    def close(self):
        self.closed.set()
        self.worker.join(timeout=3)
