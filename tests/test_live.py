import unittest
from types import SimpleNamespace
import numpy as np
from ainote.music import demo, beat_indicator
from ainote.live import Tracker, LiveEngine, BeatState
from ainote.output import PCOutput

class LiveTests(unittest.TestCase):
    def test_beat_animation_survives_anchor_update(self):
        # Every observed beat used to reset the UI to dot zero.
        dots = []
        for ordinal in range(8):
            anchor = 5 + ordinal*.5
            dots.append(beat_indicator(anchor+.01, 120, anchor, ordinal))
        self.assertEqual(dots, [0, 1, 2, 3, 0, 1, 2, 3])
        self.assertEqual(beat_indicator(5.25, 120, 5, 0, 2), 1)

    def test_fast_provisional_start_and_all_dots(self):
        audio, rate = demo(duration=8, bpm=120)
        tracker = Tracker(rate)
        first = None
        dots = set()
        provisional = False
        for pos in range(0, len(audio)-512, 512):
            state = tracker.feed(audio[pos:pos+512, 0], pos/rate)
            if state.locked:
                if first is None: first = pos/rate
                provisional |= state.provisional
                dots.add(beat_indicator(pos/rate, state.bpm, state.phase, state.beat_index))
        self.assertIsNotNone(first)
        self.assertLess(first, 3)
        self.assertTrue(provisional)
        self.assertEqual(dots, {0, 1, 2, 3})

    def test_stream_tempo_and_silence(self):
        for bpm in (90, 120, 150):
            audio, rate = demo(duration=12, bpm=bpm)
            tracker = Tracker(rate)
            for pos in range(0, len(audio)-512, 512):
                state = tracker.feed(audio[pos:pos+512, 0], pos/rate)
            self.assertTrue(state.locked, (bpm, state))
            self.assertLess(abs(state.bpm-bpm), 2, state)
            for pos in range(len(audio), len(audio)+rate*2, 512):
                state = tracker.feed(np.zeros(512), pos/rate)
            self.assertFalse(state.locked)

    def test_reported_eleven_percent_can_lock_with_rhythm(self):
        # Regression: an aubio raw confidence of .124 displays as 11%,
        # and was permanently excluded by the previous > .5 threshold.
        class Detector:
            def __init__(self): self.frame = -1
            def __call__(self, block):
                self.frame += 1
                return [int(self.frame % 43 == 0)]
            def get_bpm(self): return 130.0
            def get_confidence(self): return .124
            def get_last_s(self): return self.frame*512/48000
        tracker = Tracker(48000)
        tracker.detector = Detector()
        for i in range(500):
            amplitude = .03 if i % 43 < 8 else .004
            t = (np.arange(512)+i*512)/48000
            state = tracker.feed((amplitude*np.sin(2*np.pi*330*t)).astype('float32'), i*512/48000)
        self.assertAlmostEqual(state.confidence, .11, places=2)
        self.assertTrue(state.locked, state)
        self.assertGreaterEqual(state.beat_count, 3)

    def test_waiting_reason_distinguishes_silence(self):
        tracker = Tracker(48000)
        state = tracker.feed(np.zeros(512, dtype='float32'), 0)
        self.assertFalse(state.locked)
        self.assertIn('無音', state.reason)

    def test_noise_and_tone_do_not_lock(self):
        for kind in ('noise', 'tone'):
            tracker = Tracker(48000)
            rng = np.random.default_rng(7)
            for i in range(2000):
                t = (np.arange(512)+i*512)/48000
                block = rng.normal(0, .003, 512) if kind == 'noise' else .03*np.sin(2*np.pi*440*t)
                state = tracker.feed(block.astype('float32'), i*512/48000)
                self.assertFalse(state.locked, (kind, state))

    def test_low_level_and_nonzero_origin(self):
        audio, rate = demo(duration=20, bpm=120)
        tracker = Tracker(rate)
        for p in range(0, len(audio)-512, 512):
            state = tracker.feed(audio[p:p+512, 0]*.01, 10+p/rate)
        self.assertTrue(state.locked)
        self.assertGreater(state.phase, 10)
        self.assertLess(abs(state.bpm-120), 2)

    def test_live_callback_mutes_unlocked_and_stale(self):
        engine = LiveEngine()
        engine.rate = 48000
        engine.output = PCOutput(48000)
        engine.active = True
        output = np.empty((512, 2), dtype='float32')
        timing = SimpleNamespace(inputBufferAdcTime=0, outputBufferDacTime=.03)
        for state in (BeatState(), BeatState(120, 0, .8, .1, -2, True)):
            engine.state = state
            engine._live_callback(np.zeros((512, 1)), output, 512, timing, None)
            self.assertFalse(np.any(output))
        engine.stop()

if __name__ == '__main__':
    unittest.main()
