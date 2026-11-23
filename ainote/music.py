"""Audio analysis and musical decisions, independent of GUI/output hardware."""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
# 1回の打撃を表す。timeは鳴らす時刻、velocityは打音の強さ。
class Hit:
    time: float  # seconds on the accompaniment timeline
    velocity: float = 0.7

@dataclass(frozen=True)
class Analysis:
    bpm: float
    offset: float
    confidence: float


# ファイル再生用に、伴奏から一定テンポと拍の基準位置を推定する。
def estimate(audio, rate):
    """Offline constant-tempo estimate (80–160 BPM); not a live beat tracker."""
    mono = np.asarray(audio[:rate * 90]).mean(axis=1)
    step = max(1, rate // 11025)
    mono = mono[::step]
    sr = rate / step
    hop, window = 256, 1024
    if len(mono) < window * 4 or np.max(np.abs(mono)) < 1e-5:
        raise ValueError('音源が短すぎるか無音です。手動BPMを使用してください。')
    frames = np.lib.stride_tricks.sliding_window_view(mono, window)[::hop]
    spectra = np.abs(np.fft.rfft(frames * np.hanning(window), axis=1))
    flux = np.maximum(np.diff(np.log1p(spectra), axis=0), 0).sum(axis=1)
    flux = np.maximum(flux - np.median(flux), 0)
    if flux.max() < 1e-8:
        raise ValueError('拍の特徴を検出できません。手動BPMを使用してください。')
    fps = sr / hop
    lo, hi = int(fps * 60 / 160), int(np.ceil(fps * 60 / 80))
    corr = np.correlate(flux, flux, mode='full')[len(flux)-1:]
    lags = np.arange(lo, min(hi + 1, len(corr)))
    lag = int(lags[np.argmax(corr[lags])])
    # Parabolic interpolation reduces the hop-size tempo quantization.
    delta = 0.0
    if 0 < lag < len(corr)-1:
        a, b, c = corr[lag-1:lag+2]
        den = a - 2*b + c
        if abs(den) > 1e-9:
            delta = float(np.clip(0.5*(a-c)/den, -.5, .5))
    period = (lag + delta) / fps
    times = (np.arange(len(flux)) * hop + hop + window/2) / sr
    phases = np.linspace(0, period, 120, endpoint=False)
    scores = [np.sum(flux * np.exp(-0.5 * (((times-p+period/2)%period-period/2)/.035)**2)) for p in phases]
    phase = float(phases[int(np.argmax(scores))])
    confidence = float(np.clip(corr[lag] / (corr[0] + 1e-12), 0, 1))
    return Analysis(float(np.clip(60/period, 80, 160)), phase, confidence)


# 指定された時間内で、盛り上げ度に応じて打つ時刻を並べる。
def hits_between(start, end, bpm, offset, excitement, interlude=False):
    """Half-open interval avoids double hits across audio buffers."""
    if excitement <= 0 or end <= start:
        return []
    level = min(3, (1 if excitement <= 33 else 2 if excitement <= 66 else 3) + int(interlude))
    beat = 60 / bpm
    stride = beat * 2 if level == 1 else beat if level == 2 else beat / 2
    first = max(0, int(np.ceil((start-offset)/stride - 1e-9)))
    result = []
    for i in range(first, int(np.ceil((end-offset)/stride - 1e-9))):
        t = offset + i*stride
        if start-1e-9 <= t < end-1e-9:
            result.append(Hit(t, .75 if level < 3 or i % 2 == 0 else .4))
    return result


def tambourine(rate):
    rng = np.random.default_rng(42)
    t = np.arange(int(rate * .18)) / rate
    noise = rng.normal(size=len(t))
    high = noise - np.roll(noise, 1)
    rings = sum(np.sin(2*np.pi*f*t) for f in (3100, 4270, 5610, 6970)) / 4
    sample = (.28*high + .28*rings)*np.exp(-t*28)
    sample[:100] *= np.linspace(0, 1, min(100, len(sample)))
    return sample.astype('float32')


def demo(rate=48000, duration=32, bpm=120):
    """Original synthetic practice accompaniment; no bundled copyrighted song."""
    data = np.zeros((int(rate*duration), 2), dtype='float32')
    for index, time in enumerate(np.arange(0, duration, 60/bpm)):
        t = np.arange(int(rate*.18))/rate
        kick = .26*np.sin(2*np.pi*(65*t + 30*(1-np.exp(-t*30))/30))*np.exp(-t*22)
        if index % 2:
            kick += np.random.default_rng(index).normal(0, .06, len(t))*np.exp(-t*40)
        pos = round(time*rate)
        n = min(len(kick), len(data)-pos)
        data[pos:pos+n] += kick[:n, None]
    return data, rate


def beat_indicator(timestamp, bpm, phase, beat_index=0, scale=1.0, offset=0):
    """Four-beat visualization; ordinal survives phase anchor replacement.

    This is an inferred beat counter, not recognized musical downbeat position.
    """
    return int(np.floor(beat_index*scale + (timestamp-phase-offset)*bpm*scale/60 + 1e-7)) % 4
