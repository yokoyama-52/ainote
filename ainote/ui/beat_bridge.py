"""Drain bounded audio-clock events on the GUI thread, then deliver a Qt signal."""
import time
from PySide6.QtCore import QObject, Signal, Slot


class BeatBridge(QObject):
    # Emit as soon as the audio thread calculates the deadline so the character
    # can descend before the Arduino command is due.
    scheduled = Signal(float, float)
    beat = Signal(float)

    @Slot(object)
    def poll(self, engine):
        now = time.monotonic()
        latest = None
        while engine.visual_hits and engine.visual_hits[0][0] <= now + .30:
            due, strength = engine.visual_hits.popleft()
            if engine.active and now-due < .12:
                self.scheduled.emit(due, strength)
            if due > now:
                continue
            if now-due < .12:
                latest = strength
        if latest is not None and engine.active:
            self.beat.emit(latest)
