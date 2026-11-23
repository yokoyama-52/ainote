"""One audio clock mixes accompaniment and percussion, avoiding UI-timer drift."""
from dataclasses import dataclass
from collections import deque
import time
import numpy as np
import sounddevice as sd
from .arduino import ArduinoPlayback
from .music import hits_between
from .output import PCOutput
from .devices import output_channels

@dataclass(frozen=True)
class Controls:
    bpm: float = 120
    offset: float = 0
    excitement: int = 50
    interlude: bool = False
    music_volume: float = .7
    percussion_volume: float = .5

class Engine:
    def __init__(self, output_factory=PCOutput):
        self.output_factory = output_factory
        self.stream = None
        self.position = 0
        self.controls = Controls()
        self.error = ''
        self.finished = False
        self.active = False
        self.output = None
        self.arduino = None
        self.visual_hits = deque(maxlen=64)

    def start(self, audio, rate, output_device=None, arduino_port=None):
        self.stop()
        self.audio, self.rate = audio, rate
        self.position, self.finished, self.error = 0, False, ''
        self.output = self.output_factory(rate)
        try:
            self.stream = sd.OutputStream(device=output_device, samplerate=rate, channels=output_channels(output_device), dtype='float32',
                                          blocksize=512, callback=self._callback)
            if arduino_port:
                self.arduino = ArduinoPlayback(arduino_port)
            self.active = True
            self.stream.start()
        except Exception:
            self.stop()
            raise

    # 音声機器から求められた短い区間ごとに、伴奏とタンバリンの音を混ぜる。
    def _callback(self, outdata, frames, timing, status):
        outdata.fill(0)
        if status:
            self.error = str(status)
        if not self.active:
            raise sd.CallbackStop
        start = self.position
        if start >= len(self.audio):
            self.finished = True
            self.active = False
            raise sd.CallbackStop
        c = self.controls
        end = min(start+frames, len(self.audio))
        for hit in hits_between(start/self.rate, end/self.rate, c.bpm, c.offset, c.excitement, c.interlude):
            self.schedule_hit(hit, start, timing)
        music = self.audio[start:end]
        if outdata.shape[1] == 1:music = music.mean(axis=1, keepdims=True)
        outdata[:end-start] = music * c.music_volume
        outdata += self.output.render(start, frames)[:, None] * c.percussion_volume
        np.clip(outdata, -1, 1, out=outdata)
        self.position += frames

    def schedule_hit(self, hit, start, timing):
        # One event source for both output paths and the UI. No Qt calls or waits
        # in the audio callback. PortAudio timestamps are relative to its clock.
        latency = max(0.0, float(timing.outputBufferDacTime-getattr(timing, 'currentTime', timing.outputBufferDacTime))) if timing is not None else 0.0
        delay = latency + hit.time - start/self.rate
        self.visual_hits.append((time.monotonic() + max(0.0, delay), hit.velocity))
        if self.arduino is None:
            self.output.schedule(hit)
            return
        # 出力バッファの先頭時刻に、バッファ内での打撃位置を足す。
        delay = timing.outputBufferDacTime - timing.currentTime
        self.arduino.schedule(delay + hit.time - start / self.rate)

    def stop(self):
        self.active = False
        if self.arduino is not None:
            self.arduino.stop()
        if self.stream is not None:
            self.stream.abort()
            self.stream.close()
            self.stream = None
        self.arduino = None
        if self.output is not None:
            self.output.stop()
        self.visual_hits.clear()
