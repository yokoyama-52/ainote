import unittest
import queue
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
from ainote.live import LiveEngine
from ainote.tracking import BeatState

class CaptureOutput:
    def __init__(self):self.hits=[]
    def schedule(self,hit):self.hits.append(hit.time)
    def render(self,start,frames):return np.zeros(frames,dtype='float32')
    def stop(self):pass

class LiveTimingTests(unittest.TestCase):
    def collect(self,offset):
        e=LiveEngine();e.rate=48000;e.output=CaptureOutput();e.active=True
        e.buffers=queue.Queue()
        e.controls=replace(e.controls,offset=offset)
        timing=SimpleNamespace(inputBufferAdcTime=0,outputBufferDacTime=.02)
        for _ in range(100):
            e.state=BeatState(120,0,.8,.02,e.position/e.rate,True)
            e._live_callback(np.zeros((512,1),dtype='float32'),np.empty((512,2),dtype='float32'),512,timing,None)
        return np.asarray(e.output.hits)

    def test_negative_correction_advances_sound_without_changing_tempo(self):
        normal=self.collect(0);early=self.collect(-.03)
        self.assertGreaterEqual(len(normal),2)
        self.assertTrue(np.allclose(early-normal,-.03))
        self.assertTrue(np.allclose(np.diff(normal),np.diff(early)))

if __name__=='__main__':unittest.main()
