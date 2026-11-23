import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication
from ainote.engine import Engine
from ainote.music import Hit
from ainote.output import PCOutput
from ainote.ui.beat_bridge import BeatBridge
from ainote.ui.character_widget import CharacterWidget


class CharacterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_same_hit_and_deadline_for_arduino_and_ui(self):
        engine = Engine()
        engine.rate = 48000
        engine.active = True
        engine.arduino = SimpleNamespace(schedule=lambda delay: delays.append(delay))
        delays = []
        timing = SimpleNamespace(outputBufferDacTime=10.05, currentTime=10)
        before = time.monotonic()
        engine.schedule_hit(Hit(1.01, .9), 48000, timing)
        due, strength = engine.visual_hits[0]
        self.assertAlmostEqual(delays[0], .06)
        self.assertAlmostEqual(due-before, delays[0], delta=.01)
        self.assertEqual(strength, .9)

    def test_bridge_discards_stale_and_coalesces_due_beats(self):
        engine = Engine()
        engine.active = True
        now = time.monotonic()
        engine.visual_hits.extend([(now-1, .1), (now-.04, .5), (now-.01, .8), (now+1, 1)])
        bridge = BeatBridge()
        values = []
        scheduled = []
        bridge.beat.connect(values.append)
        bridge.scheduled.connect(lambda due, strength: scheduled.append((due, strength)))
        bridge.poll(engine)
        self.assertEqual(values, [.8])
        self.assertEqual([strength for _, strength in scheduled], [.5, .8])
        self.assertEqual(len(engine.visual_hits), 1)
        engine.stop()
        self.assertFalse(engine.visual_hits)

    def test_pc_hit_delivered_without_second_detector(self):
        engine = Engine()
        engine.rate = 48000
        engine.output = PCOutput(engine.rate)
        hit = Hit(.01, .75)
        engine.schedule_hit(hit, 0, None)
        self.assertEqual(engine.output.pending[0], (480, .75))
        self.assertEqual(engine.visual_hits[0][1], .75)
        for i in range(100):
            engine.schedule_hit(Hit(.1+i*.01), 0, None)
        self.assertEqual(len(engine.visual_hits), 64)

    def test_animation_and_controls_survive_resize(self):
        from ainote.app import Window
        with patch('ainote.app.discover', return_value=([], [])), patch('ainote.app.usb_ports', return_value=[]):
            window = Window()
        window.show()
        for w,h in [(740,720),(640,480),(1000,850)]:
            window.resize(w,h)
            self.app.processEvents()
            self.assertEqual(window.size().height(), h)
            self.assertTrue(window.rect().contains(window.play.geometry().center()))
            self.assertTrue(window.rect().contains(window.stop_button.geometry().center()))
            self.assertGreater(window.character.height(), 0)
        window.character.set_playing(True)
        window.character.schedule_beat(time.monotonic() + .08, .9)
        window.character.schedule_beat(time.monotonic() + .20, .5)
        self.assertEqual(window.character.amplitude, 10)
        self.assertGreater(window.character._impact_offset(time.monotonic() + .20, window.character.beat_at, 10), 9.9)
        self.assertLess(window.character._impact_offset(time.monotonic() + .30, window.character.beat_at, 10), 0)
        window.character.set_playing(False)
        self.assertLess(window.character.beat_at, 0)
        window.resize(640,480)
        window.settings_toggle.setChecked(True)
        self.app.processEvents()
        self.assertEqual(window.height(), 480)
        self.assertTrue(window.arduino_port.isVisible())
        window.close()

if __name__ == '__main__':
    unittest.main()
