import unittest
import numpy as np
from ainote.ai_tracking import clock_from_beats, consensus_clock, get_predictor
from ainote.tracking import BeatState

class AITests(unittest.TestCase):
    def test_consensus_accepts_alignment_and_rejects_disagreement(self):
        a=BeatState(120,7.5,.8,.1,8,True)
        b=BeatState(121,7.52,.8,.1,8,True)
        self.assertTrue(consensus_clock(a,b,8).locked)
        self.assertFalse(consensus_clock(a,BeatState(60,7.5,.8,.1,8,True),8).locked)
        self.assertFalse(consensus_clock(a,BeatState(120,7.75,.8,.1,8,True),8).locked)
        self.assertFalse(consensus_clock(a,BeatState(),8).locked)

    def test_octave_ambiguity_requires_recent_aligned_previous_clock(self):
        slow=BeatState(83.333,11.5,.8,.1,12,True)
        fast=BeatState(166.667,11.5,.8,.1,12,True)
        previous=BeatState(166.667,10.78,.8,.1,11,True)
        result=consensus_clock(slow,fast,12,previous)
        self.assertTrue(result.locked)
        self.assertAlmostEqual(result.bpm,166.667)
        self.assertFalse(consensus_clock(slow,fast,12).locked)
        self.assertFalse(consensus_clock(slow,fast,20,previous).locked)
        offbeat=BeatState(83.333,11.62,.8,.1,12,True)
        self.assertFalse(consensus_clock(offbeat,fast,12,previous).locked)

    def test_arbitrary_checkpoint_not_accepted(self):
        with self.assertRaises(ValueError):get_predictor('/tmp/untrusted.ckpt')

    def test_past_beats_project_clock_and_keep_ordinal(self):
        before=BeatState(120,10,1,.1,10,True,beat_index=8)
        state=clock_from_beats(np.arange(0,8,.5),8,16,before)
        self.assertTrue(state.locked)
        self.assertEqual(state.bpm,120)
        self.assertEqual(state.phase,15.5)
        self.assertEqual(state.beat_index,19)

    def test_no_clock_from_silence_or_unstable_beats(self):
        self.assertFalse(clock_from_beats([],0,8).locked)
        self.assertFalse(clock_from_beats([.5,.8,1.6,2,3,3.2],0,8).locked)

    def test_exclude_right_edge_and_do_not_extrapolate_ancient_beats(self):
        self.assertFalse(clock_from_beats([.5,1,1.5,2],0,8).locked)
        s=clock_from_beats([.5,1,1.5,2,2.49],0,2.5)
        self.assertTrue(s.locked)
        self.assertEqual(s.phase,2)

if __name__=='__main__':unittest.main()
