"""Original raster strokes, animated with one bounded, interruptible envelope."""
import math
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QRectF, QSize, Slot
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget, QSizePolicy


class CharacterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName('音楽に合わせて動く手描きの顔')
        self.sprite = QPixmap(str(Path(__file__).resolve().parents[1] / 'assets' / 'character.png'))
        if self.sprite.isNull():
            raise RuntimeError('キャラクター画像を読み込めませんでした。')
        # Bounds in the original 1024px drawing. Never trace or replace the strokes.
        self.parts = [(226, 313, 99, 313), (712, 308, 87, 314), (359, 674, 354, 108)]
        self.playing = False
        self.started = time.monotonic()
        self.beat_at = -100.0
        self.amplitude = 0.0
        self.impacts = []
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def sizeHint(self):
        return QSize(430, 270)

    def set_playing(self, playing):
        self.playing = playing
        if not playing:
            self.beat_at = -100.0
            self.impacts.clear()
        self.update()

    @Slot(float)
    def beat(self, strength):
        """Compatibility entry point for an immediate, already-due hit."""
        self.schedule_beat(time.monotonic(), strength)

    @Slot(float, float)
    def schedule_beat(self, due, strength):
        if not self.playing:
            return
        # Keep nearby hits so one rebound can blend into the next descent.
        self.amplitude = 8.0 + 4.0 * max(0.0, min(1.0, strength))
        self.beat_at = due
        self.impacts = [(at, level) for at, level in self.impacts if at > due-.5]
        self.impacts.append((due, self.amplitude))
        self.impacts.sort()
        self.update()

    @staticmethod
    def _impact_offset(now, due, amplitude):
        """Sink to the command deadline, then make a damped upward rebound."""
        until = due-now
        if 0 < until <= .10:
            phase = 1-until/.10
            return amplitude * .5 * (1-math.cos(math.pi*phase))
        elapsed = now-due
        if 0 <= elapsed <= .42:
            return amplitude * math.exp(-10*elapsed) * math.cos(2*math.pi*elapsed/.20)
        return 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        now = time.monotonic()
        self.impacts = [(due, level) for due, level in self.impacts if due > now-.5]
        landing = sum(self._impact_offset(now, due, level) for due, level in self.impacts) if self.playing else 0.0
        sway = math.sin((now-self.started) * 2*math.pi / 5.5)
        side = min(self.width()*.82, self.height()*1.65, 520)
        scale = side/1024
        painter.translate(self.width()/2 + (1 if self.playing else 3)*sway,
                          self.height()/2 + landing)
        painter.rotate((.35 if self.playing else 1.25)*sway)
        # Centre the ink, rather than the large white margins of the source.
        painter.scale(scale, scale)
        painter.translate(-512, -545)
        for index, (x, y, w, h) in enumerate(self.parts):
            painter.save()
            painter.translate(x+w/2, y+h/2)
            compression = min(.10, max(-.06, landing/180))
            sy = 1 + compression*(.40 if index < 2 else -.26)
            painter.scale(1 - compression*.15, sy)
            painter.drawPixmap(QRectF(-w/2, -h/2, w, h), self.sprite, QRectF(x,y,w,h))
            painter.restore()
        painter.end()
