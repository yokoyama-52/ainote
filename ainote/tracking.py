"""aubio adapter: causal beat observations -> stable, timestamped beat clock.

Uses aubio 0.4.9 (GPL-3.0-or-later). See THIRD_PARTY_NOTICES.md.
"""
from dataclasses import dataclass
from collections import deque
import numpy as np
import aubio

@dataclass(frozen=True)
# 拍の推定結果をまとめる。BPMは速さ、phaseは拍の基準時刻を表す。
class BeatState:
    bpm: float = 120
    phase: float = 0
    confidence: float = 0
    level: float = 0
    updated: float = -100
    locked: bool = False
    reason: str = "拍の検出待ち"
    beat_count: int = 0
    beat_index: int = 0
    provisional: bool = False

# 短い音声ブロックを順に受け取り、aubioで拍とテンポを推定する。
class AubioTracker:
    name = 'aubio 0.4.9 / causal tempo + phase tracking'

    def __init__(self, rate, block=512):
        self.rate, self.block = rate, block
        self._reset_detector()
        self.origin = None
        self.last_sound = -100
        self.last_beat = -100
        self.level_smooth = .02
        self.anchors = deque(maxlen=5)
        self.levels = deque(maxlen=max(8, int(rate/block*2)))
        self.beat_count = 0
        self.onsets = deque(maxlen=6)
        self.state = BeatState()
        self.silent_reset = False

    def _reset_detector(self):
        self.detector = aubio.tempo('default', 2048, self.block, self.rate)
        self.detector.set_silence(-60)
        self.detector.set_threshold(.3)
        self.onset_detector = aubio.onset('specflux', 2048, self.block, self.rate)
        self.onset_detector.set_silence(-60)
        self.onset_detector.set_threshold(.3)
        self.onset_detector.set_minioi_s(.14)

    def feed(self, data, timestamp):
        mono = np.asarray(data, dtype='float32').reshape(-1)
        if len(mono) != self.block or not np.isfinite(mono).all():
            raise ValueError('音声ブロックが不正です')
        if self.origin is None:
            self.origin = timestamp
        level = float(np.sqrt(np.mean(mono**2)))
        self.level_smooth = .98*self.level_smooth + .02*level
        self.levels.append(level)
        if level > .0003:
            self.last_sound = timestamp
        if timestamp-self.last_sound > 1.1:
            if not self.silent_reset:
                self._reset_detector()
                self.anchors.clear()
                self.onsets.clear()
                self.beat_count = 0
                self.levels.clear()
                self.silent_reset = True
                self.origin = None
            self.state = BeatState(level=level, updated=timestamp, reason="入力音が小さいか無音です。入力機器・マイク権限を確認してください")
            return self.state
        if self.silent_reset:
            self.origin = timestamp
            self.silent_reset = False
        gain = min(20.0, .04/max(self.level_smooth, .002))
        normalized_audio = np.clip(mono*gain, -1, 1).astype('float32')
        detected = bool(self.detector(normalized_audio)[0])
        onset = bool(self.onset_detector(normalized_audio)[0])
        if onset:
            self.onsets.append(self.origin + float(self.onset_detector.get_last_s()))
        tempo = float(self.detector.get_bpm())
        raw_confidence = float(self.detector.get_confidence())
        previous = self.state
        bpm, phase = previous.bpm, previous.phase
        beat_index = previous.beat_index
        if detected and 55 <= tempo <= 210:
            observed = self.origin + float(self.detector.get_last_s())
            self.anchors.append(observed)
            self.beat_count += 1
            self.last_beat = timestamp
            intervals = np.diff(self.anchors)
            if len(intervals) >= 2:
                multiples = np.maximum(1, np.rint(intervals/(60/tempo)))
                refined = 60/float(np.median(intervals/multiples))
                if abs(refined-tempo)/tempo < .1:
                    tempo = refined
            if previous.locked and abs(tempo-bpm)/bpm < .12:
                bpm += .2*(tempo-bpm)
                period = 60/bpm
                predicted = phase + round((observed-phase)/period)*period
                # Follow a stable beat clock instead of replacing the phase grid.
                phase = predicted + float(np.clip(observed-predicted, -.06, .06))*.35
            else:
                bpm, phase = tempo, observed
        if detected and phase != previous.phase:
            beat_index += max(0, round((phase-previous.phase)*previous.bpm/60)) if previous.beat_count or previous.provisional else 0
        intervals = np.diff(self.anchors)
        normalized = intervals/np.maximum(1, np.rint(intervals/(60/max(bpm, 1))))
        stable = len(intervals) >= 2 and np.std(normalized)/max(np.mean(normalized), 1e-6) < .12
        # aubio confidence is not calibrated across songs. The former raw > .5
        # gate meant a UI reading of 11% could never start. Low confidence may
        # be accepted when rhythmic dynamics independently reject steady noise.
        if len(self.levels) >= 8:
            low, high = np.percentile(self.levels, [10, 90])
            dynamics = float(high/max(low, 1e-6))
        else:
            dynamics = 1.0
        evidence = raw_confidence > .5 or (raw_confidence > .08 and dynamics > 1.35)
        locked = bool(stable and evidence and timestamp-self.last_sound < 1.1)
        provisional = False
        # Short regular-onset evidence can start a sparse provisional clock
        # before aubio's longer tempo inference converges. Never use time alone.
        if not locked and len(self.onsets) >= 4:
            recent = np.asarray(self.onsets)[-4:]
            spacings = np.diff(recent)
            period = float(np.median(spacings))
            regular = .286 <= period <= 1.09 and np.std(spacings)/max(period, 1e-6) < .08
            fresh = timestamp-recent[-1] < min(1.1, period*1.8)
            if regular and fresh and dynamics > 1.35:
                bpm, phase = 60/period, float(recent[-1])
                beat_index = previous.beat_index + max(0, round((phase-previous.phase)*previous.bpm/60)) if previous.locked else 0
                locked, provisional = True, True
        if locked:
            reason = "仮追従：規則的な発音に控えめに合わせています" if provisional else "拍に追従中"
        elif len(intervals) < 2:
            reason = "テンポ候補を検出中：複数の拍を待っています"
        elif not stable:
            reason = "拍間隔が不安定です。伴奏を明瞭に入力してください"
        else:
            reason = "拍の根拠が弱い状態です。音量・入力機器・周囲の雑音を確認してください"
        # aubio's confidence is not a probability; normalize only for UI display.
        confidence = raw_confidence/(1+raw_confidence) if raw_confidence>0 else 0
        self.state = BeatState(bpm, phase, confidence, level, timestamp, locked, reason, self.beat_count, beat_index, provisional)
        return self.state
