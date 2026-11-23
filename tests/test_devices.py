import unittest
from unittest.mock import patch,Mock
import numpy as np
from ainote.devices import discover,output_channels
from ainote.engine import Engine,Controls
from ainote.output import PCOutput

class DeviceTests(unittest.TestCase):
    def test_mono_headphones_included_and_input_only_excluded(self):
        devices=[dict(name='Mic',max_input_channels=1,max_output_channels=0),
                 dict(name='Mono headset',max_input_channels=1,max_output_channels=1),
                 dict(name='USB headphones',max_input_channels=0,max_output_channels=2)]
        with patch('ainote.devices.sd.query_devices',return_value=devices):
            inputs,outputs=discover()
        self.assertEqual(outputs,[(1,'Mono headset'),(2,'USB headphones')])
        self.assertEqual(inputs,[(0,'Mic'),(1,'Mono headset')])

    def test_refresh_reinitializes_before_query(self):
        events=[]
        with patch('ainote.devices.sd._terminate',side_effect=lambda:events.append('terminate')), \
             patch('ainote.devices.sd._initialize',side_effect=lambda:events.append('initialize')), \
             patch('ainote.devices.sd.query_devices',side_effect=lambda:events.append('query') or []):
            discover(True)
        self.assertEqual(events,['terminate','initialize','query'])

    def test_mono_output_mix(self):
        e=Engine();e.audio=np.tile([.2,.4],(1024,1)).astype('float32');e.rate=48000
        e.active=True;e.output=PCOutput(48000);e.controls=Controls(excitement=0,music_volume=1)
        output=np.empty((512,1),dtype='float32');e._callback(output,512,None,None)
        self.assertTrue(np.allclose(output,.3))
        with patch('ainote.devices.sd.query_devices',return_value={'max_output_channels':1}):
            self.assertEqual(output_channels(3),1)

if __name__=='__main__':unittest.main()
