"""Replace PercussionOutput to add an Arduino scheduler without changing music rules."""
from typing import Protocol
import numpy as np
from .music import Hit, tambourine

# 演奏側が出力先に求める操作。打撃の予約、音声区間の生成、停止を定める。
class PercussionOutput(Protocol):
    def schedule(self, hit: Hit): ...
    def render(self, start_frame: int, frames: int) -> np.ndarray: ...
    def stop(self): ...

# 現在の出力先。予約された打撃を、PCで再生するタンバリンの音に変える。
class PCOutput:
    def __init__(self, rate):
        self.rate = rate
        self.sample = tambourine(rate)
        self.pending = []

    def schedule(self, hit):
        self.pending.append((round(hit.time*self.rate), hit.velocity))

    # 今回再生する区間に重なる打音だけを混ぜ、残りは次回へ持ち越す。
    def render(self, start_frame, frames):
        data = np.zeros(frames, dtype='float32')
        keep = []
        for position, velocity in self.pending:
            a, b = max(start_frame, position), min(start_frame+frames, position+len(self.sample))
            if a < b:
                data[a-start_frame:b-start_frame] += self.sample[a-position:b-position]*velocity
            if position+len(self.sample) > start_frame+frames:
                keep.append((position, velocity))
        self.pending = keep
        return data

    def stop(self):
        self.pending.clear()
