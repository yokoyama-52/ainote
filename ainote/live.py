"""Streaming rhythm estimation and full-duplex audio; analysis never blocks audio."""
from dataclasses import dataclass
from collections import deque
import queue
import threading
import numpy as np
import sounddevice as sd
from .arduino import ArduinoPlayback
from .engine import Engine
from .music import hits_between
from .steady_clock import SteadyClock
from .devices import output_channels

from .tracking import BeatState, AubioTracker

Tracker = AubioTracker

class LiveEngine(Engine):
    def __init__(self):
        super().__init__()
        self.state = BeatState()
        self.input_level = 0
        self.dropped = 0
        self.tempo_scale = 1.0
        self.backend = "ensemble"
        self.bass_support = False
        self.worker = None
        self.shutdown = threading.Event()
        self.buffers = queue.Queue(maxsize=24)

    # 画面で選んだ方式に応じて、拍を推定する処理を選ぶ。
    def _make_tracker(self):
        if self.backend == 'aubio':
            return Tracker(self.rate)
        from .ai_tracking import HybridTracker
        return HybridTracker(self.rate, model=self.backend, bass_support=self.bass_support)

    def start_live(self, input_device=None, output_device=None, arduino_port=None):
        self.stop()
        info = sd.query_devices(input_device, 'input')
        self.rate = int(info['default_samplerate'])
        self.tracker = self._make_tracker()
        self.state = BeatState()
        self.steady_clock = SteadyClock()
        self.position, self.error, self.finished, self.dropped = 0, '', False, 0
        self.buffers = queue.Queue(maxsize=24)
        self.output = self.output_factory(self.rate)
        self.last_hit = -100
        self.shutdown = threading.Event()
        try:
            self.stream = sd.Stream(device=(input_device, output_device), samplerate=self.rate,
                channels=(1, output_channels(output_device)), dtype='float32', blocksize=512, callback=self._live_callback)
            self.worker = threading.Thread(target=self._analyze, args=(self.shutdown,), daemon=True)
            if arduino_port:
                self.arduino = ArduinoPlayback(arduino_port)
            self.active = True
            self.worker.start()
            self.stream.start()
        except Exception:
            self.stop()
            raise

    # 入力音声を別スレッドで解析し、推定した拍を演奏に使える状態へ整える。
    def _analyze(self, stop_event):
        last = None
        buffers, tracker = self.buffers, self.tracker
        try:
            while not stop_event.is_set():
                try:
                    frame, data = buffers.get(timeout=.1)
                except queue.Empty:
                    continue
                try:
                    if last is not None and frame-last != 512:
                        if hasattr(tracker, 'close'):
                            tracker.close()
                        if stop_event.is_set():
                            break
                        tracker = self._make_tracker()
                        self.tracker = tracker
                        self.steady_clock.reset()
                    result = tracker.feed(data, frame/self.rate)
                    result = self.steady_clock.update(result, frame/self.rate, float(np.sqrt(np.mean(data**2))))
                    if not stop_event.is_set():
                        self.state = result
                    last = frame
                except Exception as exc:
                    if not stop_event.is_set():
                        self.state = BeatState()
                        self.error = f'拍解析を停止しました: {exc}'
                        stop_event.set()
        finally:
            if hasattr(tracker, 'close'):
                tracker.close()

    # 音声機器との窓口。入力を解析側へ渡し、今回の出力区間に入る打音を鳴らす。
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
        output_bpm = state.bpm*self.tempo_scale
        excitement = min(c.excitement, 33) if state.provisional else c.excitement
        if state.locked and 0 <= start/self.rate-state.updated < .8:
            for hit in hits_between(start/self.rate, (start+frames)/self.rate,
                                    output_bpm, shifted, excitement, c.interlude and not state.provisional):
                # A phase correction must not cause two nearly adjacent strikes.
                minimum = min(.18, 60/output_bpm/2*.7)
                if hit.time-getattr(self, 'last_hit', -100) >= minimum:
                    self.schedule_hit(hit, start, timing)
                    self.last_hit = hit.time
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
                self.worker.join(timeout=5)
                self.worker = None
            elif hasattr(self, 'tracker') and hasattr(self.tracker, 'close'):
                self.tracker.close()
        self.state = BeatState()
