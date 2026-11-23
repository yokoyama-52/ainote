"""Streaming rhythm estimation and full-duplex audio; analysis never blocks audio."""
from dataclasses import dataclass
from collections import deque
import queue
import threading
import numpy as np
import sounddevice as sd
from .engine import Engine
from .music import hits_between

@dataclass(frozen=True)
class BeatState:
    bpm: float = 120
    phase: float = 0
    confidence: float = 0
    level: float = 0
    updated: float = -100
    locked: bool = False

class Tracker:
    """Rolling spectral-flux autocorrelation, 80–160 BPM, no song identification."""
    def __init__(self, rate, block=512):
        self.rate, self.block = rate, block
        self.history = deque(maxlen=int(rate*8/block))
        self.previous = np.zeros(block//2+1)
        self.window = np.hanning(block)
        self.last_sound = -100
        self.last_analysis = -100
        self.state = BeatState()

    def feed(self, data, timestamp):
        mono = np.asarray(data).reshape(-1)
        level = float(np.sqrt(np.mean(mono**2)))
        spectrum = np.log1p(np.abs(np.fft.rfft(mono*self.window)))
        flux = float(np.maximum(spectrum-self.previous, 0).sum())
        self.previous = spectrum
        if level > .003:
            self.last_sound = timestamp
        self.history.append((timestamp, flux))
        if timestamp-self.last_sound > 1.1:
            self.state = BeatState(level=level, updated=timestamp)
            return self.state
        if timestamp-self.last_analysis < .25:
            return self.state
        self.last_analysis = timestamp
        points = np.asarray(self.history)
        if len(points) < self.rate/self.block*3:
            return self.state
        values = np.maximum(points[:, 1]-np.median(points[:, 1]), 0)
        values = np.convolve(values, [0.25, 0.5, 0.25], mode='same')
        corr = np.correlate(values, values, 'full')[len(values)-1:]
        fps = self.rate/self.block
        lags = np.arange(int(np.ceil(fps*60/160)), int(np.floor(fps*60/80))+1)
        lag = int(lags[np.argmax(corr[lags])])
        a,b,c = corr[lag-1:lag+2]
        den = a-2*b+c
        frac = float(np.clip(.5*(a-c)/den, -.5, .5)) if abs(den)>1e-9 else 0
        period = (lag+frac)/fps
        confidence = float(corr[lag]/(corr[0]+1e-12))
        # Recent onsets vote for phase; newest music has more influence.
        phases = np.arange(100)*period/100
        ages = np.exp((points[:, 0]-timestamp)/3)
        scores = [np.sum(values*ages*np.exp(-.5*(((points[:,0]-p+period/2)%period-period/2)/.025)**2)) for p in phases]
        phase = float(phases[np.argmax(scores)])
        self.state = BeatState(60/period, phase, confidence, level, timestamp,
                               confidence >= .08 and corr[lag] > 2*np.median(corr[lags]) and timestamp-self.last_sound < .95)
        return self.state

class LiveEngine(Engine):
    def __init__(self):
        super().__init__()
        self.state = BeatState()
        self.input_level = 0
        self.dropped = 0
        self.worker = None
        self.shutdown = threading.Event()
        self.buffers = queue.Queue(maxsize=24)

    def start_live(self, input_device=None, output_device=None):
        self.stop()
        info = sd.query_devices(input_device, 'input')
        self.rate = int(info['default_samplerate'])
        self.tracker = Tracker(self.rate)
        self.state = BeatState()
        self.position, self.error, self.finished, self.dropped = 0, '', False, 0
        self.buffers = queue.Queue(maxsize=24)
        self.output = self.output_factory(self.rate)
        self.shutdown.clear()
        try:
            self.stream = sd.Stream(device=(input_device, output_device), samplerate=self.rate,
                channels=(1, 2), dtype='float32', blocksize=512, callback=self._live_callback)
            self.worker = threading.Thread(target=self._analyze, daemon=True)
            self.active = True
            self.worker.start()
            self.stream.start()
        except Exception:
            self.stop()
            raise

    def _analyze(self):
        last = None
        while not self.shutdown.is_set():
            try:
                frame, data = self.buffers.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                if last is not None and frame-last != 512:
                    self.tracker = Tracker(self.rate)
                self.state = self.tracker.feed(data, frame/self.rate)
                last = frame
            except Exception as exc:
                self.state = BeatState()
                self.error = f'拍解析を停止しました: {exc}'
                self.shutdown.set()

    def _live_callback(self, indata, outdata, frames, timing, status):
        outdata.fill(0)
        if not self.active:
            raise sd.CallbackStop
        if status:
            self.error = str(status)
        start = self.position
        self.input_level = float(np.sqrt(np.mean(indata**2)))
        try:
            self.buffers.put_nowait((start, indata[:, 0].copy()))
        except queue.Full:
            self.dropped += 1
            self.state = BeatState()
        state, c = self.state, self.controls
        # Input and DAC timestamps share PortAudio's clock. Project the learned
        # input beat into the future time of the outgoing buffer.
        lead = float(timing.outputBufferDacTime-timing.inputBufferAdcTime)
        shifted = state.phase-lead+c.offset
        if state.locked and 0 <= start/self.rate-state.updated < .8:
            for hit in hits_between(start/self.rate, (start+frames)/self.rate,
                                    state.bpm, shifted, c.excitement, c.interlude):
                self.output.schedule(hit)
        else:
            self.output.stop()
        outdata[:] = self.output.render(start, frames)[:, None]*c.percussion_volume
        np.clip(outdata, -1, 1, out=outdata)
        self.position += frames

    def stop(self):
        super().stop()
        if hasattr(self, 'shutdown'):
            self.shutdown.set()
            if self.worker is not None:
                self.worker.join(timeout=2)
                self.worker = None
        self.state = BeatState()
