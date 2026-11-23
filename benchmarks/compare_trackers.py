"""Deterministic, causal synthetic comparison; not a real-room music benchmark."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importlib.util
import json
import time
import numpy as np
import aubio
from ainote.tracking import AubioTracker
from ainote.music import demo

legacy_spec = importlib.util.spec_from_file_location('ainote.legacy_live', Path(__file__).resolve().parents[1]/'benchmarks/legacy_baseline.py')
legacy = importlib.util.module_from_spec(legacy_spec)
sys.modules[legacy_spec.name] = legacy
legacy_spec.loader.exec_module(legacy)


def fixture(bpm, condition, duration=30, rate=48000):
    audio, _ = demo(rate=rate, duration=duration, bpm=bpm)
    x = audio[:, 0].copy()
    rng = np.random.default_rng(173)
    t = np.arange(len(x))/rate
    if condition != 'clean':
        # Added sustained harmony, syncopated bright notes, room echoes, noise.
        melody = .018*np.sin(2*np.pi*330*t) + .012*np.sin(2*np.pi*494*t)
        for onset in np.arange(.25, duration-.2, 60/bpm):
            a = int(onset*rate)
            tt = np.arange(int(.12*rate))/rate
            melody[a:a+len(tt)] += .06*np.sin(2*np.pi*1300*tt)*np.exp(-tt*35)
        x += melody
        x = x - np.convolve(x, np.ones(241)/241, 'same')
        for delay, weight in ((.043,.35),(.097,.2),(.157,.12)):
            d = int(delay*rate)
            x[d:] += weight*x[:-d].copy()
        x += rng.normal(0, .003, len(x))
        x *= .15 if condition == 'quiet_room' else 1
    return x.astype('float32'), rate


def evaluate(kind, audio, rate, bpm):
    if kind == 'legacy':
        tracker = legacy.Tracker(rate)
    elif kind == 'aubio_adapter':
        tracker = AubioTracker(rate)
    else:
        tracker = aubio.tempo('default', 2048, 512, rate)
        tracker.set_silence(-60)
    estimates, predictions, elapsed = [], [], []
    first = None
    last_emit = -1
    for start in range(0, len(audio)-512, 512):
        block = audio[start:start+512]
        stamp = start/rate
        before = time.perf_counter()
        if kind in ('legacy', 'aubio_adapter'):
            state = tracker.feed(block, stamp)
            valid = state.locked
            tempo, phase = state.bpm, state.phase
        else:
            detected = bool(tracker(block)[0])
            tempo = tracker.get_bpm()
            valid = tempo > 0 and tracker.get_confidence() > 0
            phase = tracker.get_last_s()
        elapsed.append(time.perf_counter()-before)
        if valid:
            if first is None: first = stamp
            if stamp >= 8:
                estimates.append(tempo)
                period = 60/tempo
                upcoming = phase + np.ceil((stamp-phase)/period)*period
                if stamp <= upcoming < stamp+512/rate and upcoming-last_emit>.15:
                    predictions.append(upcoming)
                    last_emit=upcoming
    target = np.arange(8, len(audio)/rate, 60/bpm)
    # Ground truth is anchored at time zero, not at the scoring-window boundary.
    target = np.arange(0, len(audio)/rate, 60/bpm)
    target = target[target>=8]
    pred = np.asarray(predictions)
    used=set(); matched=0; errors=[]
    for beat in target:
        if len(pred):
            j=int(np.argmin(abs(pred-beat)))
            if j not in used and abs(pred[j]-beat)<=.07:
                matched+=1; used.add(j); errors.append(abs(pred[j]-beat)*1000)
    precision=matched/max(1,len(pred)); recall=matched/max(1,len(target))
    return {'backend':kind,'bpm':bpm,'tempo_mae':round(float(np.mean(np.abs(np.asarray(estimates)-bpm))),2) if estimates else None,
            'first_lock_s':round(first,2) if first is not None else None,
            'beat_f1_70ms':round(2*precision*recall/max(1e-9,precision+recall),3),
            'matched_error_ms':round(float(np.mean(errors)),1) if errors else None,
            'cpu_ms':round(sum(elapsed)*1000,1), 'p95_block_ms':round(float(np.percentile(elapsed,95))*1000,3),
            'predicted_hits':len(pred), 'reference_hits':len(target)}

if __name__=='__main__':
    results=[]
    for bpm in (90,120,150):
        for condition in ('clean','room','quiet_room'):
            audio, rate=fixture(bpm,condition)
            for kind in ('legacy','aubio','aubio_adapter'):
                row=evaluate(kind,audio,rate,bpm);row['condition']=condition
                results.append(row)
                print(json.dumps(row),flush=True)
    Path('docs/benchmark-results.json').write_text(json.dumps(results,indent=2))
