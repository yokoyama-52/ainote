import unittest
import numpy as np
from ainote.music import hits_between, demo, estimate, Hit
from ainote.output import PCOutput
from ainote.engine import Engine, Controls

class CoreTests(unittest.TestCase):
    def test_boundaries_and_silence(self):
        whole = hits_between(0, 4, 120, 0, 50)
        split = hits_between(0, 1, 120, 0, 50) + hits_between(1, 4, 120, 0, 50)
        self.assertEqual(whole, split)
        self.assertEqual(len(whole), 8)
        self.assertEqual(hits_between(0, 4, 120, 0, 0, True), [])
        self.assertEqual(len(hits_between(0, 4, 120, 0, 20)), 4)
        self.assertEqual(len(hits_between(0, 4, 120, 0, 20, True)), 8)

    def test_render_cross_buffer_and_stop(self):
        output = PCOutput(48000)
        output.schedule(Hit(.01))
        a = output.render(0, 512)
        b = output.render(512, 512)
        self.assertTrue(np.any(a))
        self.assertTrue(np.any(b))
        output.stop()
        self.assertFalse(np.any(output.render(1024, 512)))

    def test_estimate_clicks(self):
        for bpm in (90, 120, 150):
            audio, sr = demo(duration=20, bpm=bpm)
            analysis = estimate(audio, sr)
            self.assertLess(abs(analysis.bpm-bpm), 2)
        with self.assertRaises(ValueError):
            estimate(np.zeros((48000, 2)), 48000)

    def test_audio_callback_clock_and_mix(self):
        engine = Engine()
        engine.audio, engine.rate = demo(duration=2)
        engine.output = PCOutput(engine.rate)
        engine.active = True
        engine.controls = Controls()
        out = np.empty((512, 2), dtype='float32')
        for _ in range(100):
            engine._callback(out, 512, None, None)
            self.assertTrue(np.isfinite(out).all())
            self.assertLessEqual(np.abs(out).max(), 1)
        self.assertEqual(engine.position, 51200)
        engine.stop()
        self.assertEqual(engine.output.pending, [])

if __name__ == '__main__':
    unittest.main()
