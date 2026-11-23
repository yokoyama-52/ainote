"""A persistent musical clock, independent of noisy detector observations."""
from collections import deque
from dataclasses import replace
import math
import statistics
from .tracking import BeatState

class SteadyClock:
    DEAD_BAND = 3.0           # BPM: treat small changes as measurement noise
    CHANGE_WAIT = 6.0         # seconds of consistent new tempo before adoption
    HOLD_SECONDS = 8.0        # continue through short recognition gaps with sound
    SILENCE_SECONDS = 2.0     # actual missing audio must still stop playback
    PHASE_SLEW = .04          # beats per second, no discontinuous phase jumps

    def __init__(self):
        self.reset()

    def reset(self):
        self.bpm = None
        self.position = 0.0
        self.last_time = None
        self.last_sound = -100.0
        self.last_valid = -100.0
        self.observation_key = None
        self.change_samples = deque(maxlen=12)
        self.change_since = None
        self.phase_error = 0.0
        self.phase_samples = deque(maxlen=3)
        self.fine_tempos = deque(maxlen=5)
        self.last_fine_time = None
        self.reference = BeatState()
        self.established = False
        self.promotion_samples = deque(maxlen=8)
        self.promotion_since = None

    # 新しい推定を受け取り、BPMや打音の位置が急に飛ばないよう調整する。
    def update(self, observation, now, level):
        if self.last_time is not None and now < self.last_time:
            self.reset()
        dt = 0 if self.last_time is None else now-self.last_time
        self.last_time = now
        if level > .0003:
            self.last_sound = now
        audible = now-self.last_sound < self.SILENCE_SECONDS
        if not audible:
            self.bpm = None
            self.established = False
            self.promotion_samples.clear()
            self.promotion_since = None
            self.change_samples.clear()
            self.change_since = None
            self.observation_key = None
            self.phase_samples.clear()
            self.fine_tempos.clear()
            self.last_fine_time = None
            self.phase_error = 0
            return BeatState(level=level, updated=now, reason='無音のため停止。音楽が戻ると再認識します')
        valid = (observation.locked and 0 <= now-observation.updated < 2.5
                 and math.isfinite(observation.bpm) and 40 <= observation.bpm <= 240)
        if self.bpm is not None:
            # Integrate time continuously; changing the nominal BPM never
            # reinterprets all elapsed song time or teleports the beat grid.
            correction = max(-self.PHASE_SLEW*dt, min(self.PHASE_SLEW*dt, self.phase_error))
            self.position += dt*self.bpm/60 + correction
            self.phase_error -= correction
        if valid:
            self.last_valid = now
            self.reference = observation
            if self.bpm is None:
                self.bpm = float(observation.bpm)
                self.established = not observation.provisional
                self.position = observation.beat_index + (now-observation.phase)*observation.bpm/60
            # AI and aubio may publish the same observation every audio block.
            # Count only new anchors, not repeat copies, toward tempo changes.
            key = (round(observation.phase, 5), observation.beat_count,
                   observation.provisional, observation.reason.split(':')[0])
            if key != self.observation_key:
                self.observation_key = key
                # Do not permanently freeze a half-tempo guess made during
                # provisional onset tracking. Promote only repeated confirmed
                # observations; established tempo keeps the normal dead band.
                if not self.established and not observation.provisional:
                    if self.promotion_samples and abs(observation.bpm-statistics.median(self.promotion_samples)) > 2:
                        self.promotion_samples.clear()
                        self.promotion_since = None
                    self.promotion_samples.append(observation.bpm)
                    if self.promotion_since is None:self.promotion_since=now
                    if now-self.promotion_since >= 2 and len(self.promotion_samples) >= 3:
                        self.bpm = float(statistics.median(self.promotion_samples))
                        fraction = ((now-observation.phase)*self.bpm/60)%1
                        self.position = math.floor(self.position)+fraction
                        self.phase_error = 0
                        self.established = True
                        self.change_samples.clear()
                        self.change_since = None
                difference = observation.bpm-self.bpm
                if abs(difference) <= self.DEAD_BAND:
                    self.change_samples.clear()
                    self.change_since = None
                elif .8 < observation.bpm/self.bpm < 1.25:
                    if self.change_samples and abs(observation.bpm-statistics.median(self.change_samples)) > 2:
                        self.change_samples.clear()
                        self.change_since = None
                    self.change_samples.append(observation.bpm)
                    if self.change_since is None:self.change_since=now
                    if now-self.change_since >= self.CHANGE_WAIT and len(self.change_samples) >= 4:
                        self.bpm = float(statistics.median(self.change_samples))
                        self.change_samples.clear()
                        self.change_since = None
                else:
                    # Half/double-tempo flips and one-off large errors are not
                    # automatically accepted. User can rescan or use tempo scale.
                    self.change_samples.clear()
                    self.change_since = None
                # Match metrical level before using a confirmed observation
                # for phase; half/double readings must not switch the clock BPM.
                matched_bpm = min((observation.bpm/2, observation.bpm, observation.bpm*2),
                                  key=lambda value: abs(value-self.bpm))
                compatible = abs(matched_bpm-self.bpm) <= self.DEAD_BAND
                if compatible and not observation.provisional:
                    self.fine_tempos.append(matched_bpm)
                    elapsed = 0 if self.last_fine_time is None else min(2, now-self.last_fine_time)
                    self.last_fine_time = now
                    # A narrow, persistent cluster can refine the fractional BPM;
                    # broad measurement jitter cannot pull the tempo around.
                    if len(self.fine_tempos) == 5 and max(self.fine_tempos)-min(self.fine_tempos) <= 1:
                        target = statistics.median(self.fine_tempos)
                        self.bpm += max(-.1*elapsed, min(.1*elapsed, (target-self.bpm)*.2))
                    observed_position = (now-observation.phase)*self.bpm/60
                    error = (observed_position-self.position+.5)%1-.5
                    self.phase_samples.append(error)
                    # Require three independent anchors that agree on the shift.
                    # Reject half-beat source changes and isolated false detections.
                    if abs(error) <= .10:
                        self.phase_error = error
                    elif len(self.phase_samples) == 3:
                        spread = max(self.phase_samples)-min(self.phase_samples)
                        median = statistics.median(self.phase_samples)
                        if spread <= .08 and abs(median) <= .30:
                            self.phase_error = median
                else:
                    self.phase_samples.clear()
                    self.fine_tempos.clear()
                    self.last_fine_time = None
        if self.bpm is None:
            return replace(observation, locked=False, level=level, updated=now)
        age = now-self.last_valid
        if age > self.HOLD_SECONDS:
            self.bpm = None
            self.phase_samples.clear()
            self.fine_tempos.clear()
            self.last_fine_time = None
            self.phase_error = 0
            return BeatState(level=level, updated=now, reason='認識が長く途切れたため再確認中')
        ordinal = math.floor(self.position)
        phase = now-(self.position-ordinal)*60/self.bpm
        holding = not valid
        reason = (f'テンポ固定 {self.bpm:.0f} BPM：認識を再確認しながら継続（残り{max(0,self.HOLD_SECONDS-age):.0f}秒）'
                  if holding else f'テンポ固定 {self.bpm:.0f} BPM / {observation.reason}')
        return replace(self.reference, bpm=self.bpm, phase=phase, beat_index=ordinal,
                       level=level, updated=now, locked=True, reason=reason)
