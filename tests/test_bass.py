import unittest
import numpy as np
from ainote.bass_tracking import BassTracker,fuse_bass
from ainote.tracking import BeatState
from ainote.ai_tracking import clock_from_beats

class BassTests(unittest.TestCase):
    def test_filter_keeps_kick_and_suppresses_highs(self):
        levels=[]
        for hz in (70,1000):
            tracker=BassTracker(48000);energies=[]
            for i in range(100):
                t=(np.arange(512)+512*i)/48000
                y=tracker.filter((.1*np.sin(2*np.pi*hz*t)).astype('float32'))
                if i>20:energies.append(np.mean(y*y))
            levels.append(np.sqrt(np.mean(energies)))
        self.assertGreater(levels[0],.05)
        self.assertLess(levels[1]/levels[0],.05)

    def test_low_band_does_not_force_half_tempo_or_start_alone(self):
        bass=BeatState(60,4,.9,.1,4,True,'bass')
        primary=BeatState(120,4,.7,.1,4,True,'AI')
        self.assertEqual(fuse_bass(primary,bass,4),primary)
        self.assertFalse(fuse_bass(BeatState(),bass,4).locked)

    def test_only_agreement_can_refine_and_stale_bass_ignored(self):
        primary=BeatState(120,4,.7,.1,4,True,'AI')
        bass=BeatState(121,4.02,.8,.1,4,True,'bass')
        result=fuse_bass(primary,bass,4)
        self.assertIn('低音一致',result.reason)
        self.assertLess(abs(result.phase-primary.phase),.01)
        self.assertEqual(fuse_bass(primary,bass,5),primary)

    def test_steady_low_tone_and_noise_do_not_create_bass_clock(self):
        for noise in (False,True):
            tracker=BassTracker(48000);rng=np.random.default_rng(9)
            for i in range(900):
                t=(np.arange(512)+i*512)/48000
                x=rng.normal(0,.01,512) if noise else .1*np.sin(2*np.pi*70*t)
                state=tracker.feed(x.astype('float32'),i*512/48000)
                self.assertFalse(state.locked,state)
            self.assertLessEqual(len(tracker.history),int(np.ceil(5*48000/512)))

    def test_robust_fit_reduces_model_frame_quantization_error(self):
        bpm=123
        beats=np.round((np.arange(9)*60/bpm)/.02)*.02
        state=clock_from_beats(beats,0,4.2)
        self.assertTrue(state.locked)
        self.assertLess(abs(state.bpm-bpm),1)

if __name__=='__main__':unittest.main()
