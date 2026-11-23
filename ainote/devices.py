"""Stopped-stream device discovery for sounddevice 0.5.6 / PortAudio."""
import sounddevice as sd


def discover(reinitialize=False):
    # PortAudio may retain the device list from initialization. sounddevice
    # 0.5.6 has no public rescan API; isolate its pinned internal API here.
    # Caller must close ALL application streams first.
    if reinitialize:
        initialize=getattr(sd,'_initialize',None)
        terminate=getattr(sd,'_terminate',None)
        if not callable(initialize) or not callable(terminate):
            raise RuntimeError('この音声ライブラリでは再走査できません。アプリを再起動してください。')
        if getattr(sd,'_initialized',1)>0:terminate()
        initialize()
    devices=sd.query_devices()
    inputs=[(i,d['name']) for i,d in enumerate(devices) if d['max_input_channels']>=1]
    outputs=[(i,d['name']) for i,d in enumerate(devices) if d['max_output_channels']>=1]
    return inputs,outputs


def output_channels(device=None):
    count=int(sd.query_devices(device,'output')['max_output_channels'])
    if count<1:raise ValueError('選択した機器には音声出力がありません。')
    return min(2,count)
