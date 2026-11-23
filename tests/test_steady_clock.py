import unittest
import numpy as np
from ainote.steady_clock import SteadyClock
from ainote.tracking import BeatState
from ainote.music import hits_between, beat_indicator


def observation(now, bpm=120, phase=None, locked=True):
    phase = np.floor(now*2)/2 if phase is None else phase
    return BeatState(bpm,float(phase),.7,.02,now,locked,'AI一致',int(now*2)+1,int(now*2))

class SteadyClockTests(unittest.TestCase):
    def test_bpm_jitter_does_not_reset_grid_or_stop(self):
        c=SteadyClock();events=[];dots=set()
        for frame in range(6000):
            now=frame*.01
            bpm=(120,122,119,121,118)[int(now)%5]
            s=c.update(observation(now,bpm),now,.02)
            self.assertEqual(s.bpm,120)
            self.assertTrue(s.locked)
            events.extend(h.time for h in hits_between(now,now+.01,s.bpm,s.phase,50))
            dots.add(beat_indicator(now,s.bpm,s.phase,s.beat_index))
        self.assertEqual(dots,{0,1,2,3})
        self.assertTrue(np.allclose(np.diff(events),.5,atol=1e-6))

    def test_short_dropout_holds_then_expires(self):
        c=SteadyClock();c.update(observation(0),0,.02)
        for now in (1,3,5,7.9):
            state=c.update(BeatState(updated=now),now,.02)
            self.assertTrue(state.locked)
            self.assertEqual(state.bpm,120)
        self.assertFalse(c.update(BeatState(updated=8.1),8.1,.02).locked)

    def test_silence_stops_and_rescan_clears_tempo(self):
        c=SteadyClock();c.update(observation(0),0,.02)
        self.assertTrue(c.update(BeatState(),1,0).locked)
        self.assertFalse(c.update(BeatState(),2.1,0).locked)
        c.reset()
        self.assertEqual(c.update(observation(3,135),3,.02).bpm,135)

    def test_half_double_errors_do_not_change_clock(self):
        c=SteadyClock();c.update(observation(0),0,.02)
        for i in range(1,30):
            s=c.update(observation(i,60 if i%2 else 240),i,.02)
            self.assertEqual(s.bpm,120)

    def test_real_tempo_change_requires_persistence_and_keeps_position(self):
        c=SteadyClock();c.update(observation(0),0,.02)
        for i in range(1,7):
            s=c.update(observation(i,128),i,.02)
            self.assertEqual(s.bpm,120)
        s=c.update(observation(7,128),7,.02)
        self.assertEqual(s.bpm,128)
        self.assertAlmostEqual(c.position,14)

    def test_initial_provisional_half_tempo_can_be_corrected(self):
        from dataclasses import replace
        c=SteadyClock()
        early=replace(observation(0,60),provisional=True)
        self.assertEqual(c.update(early,0,.02).bpm,60)
        for now in (1,2,3):
            state=c.update(observation(now,120),now,.02)
        self.assertEqual(state.bpm,120)
        self.assertTrue(c.established)
        self.assertFalse(state.provisional)
        for now in (4,5,6):
            self.assertEqual(c.update(observation(now,60),now,.02).bpm,120)

    def test_fractional_bpm_is_preserved(self):
        c=SteadyClock()
        self.assertEqual(c.update(observation(0,120.1),0,.02).bpm,120.1)

    def test_consistent_phase_offset_converges_without_jumps(self):
        c=SteadyClock(); c.update(observation(0),0,.02)
        positions=[]
        for frame in range(1,2001):
            now=frame*.01
            # A new anchor once per beat, 100 ms behind initial grid.
            anchor=np.floor((now-.1)*2)/2+.1
            state=c.update(observation(now,120,anchor),now,.02)
            positions.append(c.position)
        error=((20-.1)*2-c.position+.5)%1-.5
        self.assertLess(abs(error),.015)
        self.assertTrue(np.all((np.diff(positions)>.0195)&(np.diff(positions)<.0205)))

    def test_fractional_tempo_does_not_accumulate_rounding_drift(self):
        c=SteadyClock();bpm=166.6666667
        for frame in range(6001):
            now=frame*.01
            phase=np.floor(now*bpm/60)*60/bpm
            c.update(observation(now,bpm,phase),now,.02)
        self.assertAlmostEqual(c.position,60*bpm/60,places=7)

    def test_half_beat_outlier_is_not_followed(self):
        c=SteadyClock();c.update(observation(0),0,.02)
        for frame in range(1,1001):
            now=frame*.01
            c.update(observation(now,120,np.floor(now*2)/2+.25),now,.02)
        self.assertAlmostEqual(c.position,20)

    def test_repeated_copy_is_not_three_phase_observations(self):
        c=SteadyClock();c.update(observation(0),0,.02)
        for frame in range(1,101):
            now=frame*.01
            c.update(BeatState(120,.1,.7,.02,now,True,'AI一致',1,0),now,.02)
        self.assertEqual(len(c.phase_samples),2)
        self.assertAlmostEqual(c.position,2)

if __name__=='__main__':unittest.main()
