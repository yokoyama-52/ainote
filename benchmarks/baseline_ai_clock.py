"""Pre-bass/robust-fit decoder snapshot for reproducible comparison."""
import numpy as np
from ainote.tracking import BeatState

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
    bpm, phase = 60/period, float(recent[-1])
    ordinal = 0
    if previous is not None and previous.locked:
        ordinal = previous.beat_index + max(0, round((phase-previous.phase)*previous.bpm/60))
    return BeatState(bpm, phase, max(0, 1-variation/.16), 0, end, True,
                     f'AI {name}：受信済み音声から拍を予測', len(valid), ordinal)

