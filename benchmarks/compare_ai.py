"""Past-window prediction, never scoring retrospective AI beats as live hits."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import time
import numpy as np
from ainote.ai_tracking import get_predictor, infer_beats, clock_from_beats, infer_clock
from ainote.tracking import AubioTracker
from ainote.music import hits_between
from benchmarks.compare_trackers import fixture


def score(predictions, target):
    p=np.asarray(predictions);used=set();errors=[]
    for beat in target:
        if len(p):
            index=int(np.argmin(abs(p-beat)))
            if index not in used and abs(p[index]-beat)<=.07:
                used.add(index); errors.append(abs(p[index]-beat)*1000)
    precision=len(used)/max(1,len(p));recall=len(used)/max(1,len(target))
    return {'f1_70ms':round(2*precision*recall/max(1e-9,precision+recall),3),
            'mean_matched_ms':round(float(np.mean(errors)),1) if errors else None,
            'predictions':len(p), 'reference':len(target)}


def run(audio, rate, bpm, backend):
    duration=len(audio)/rate
    target=np.arange(0,duration,60/bpm);target=target[target>=8]
    if backend=='aubio':
        tracker=AubioTracker(rate);events=[];last=-100;first=None;times=[]
        for pos in range(0,len(audio)-512,512):
            now=pos/rate;before=time.perf_counter();state=tracker.feed(audio[pos:pos+512],now);times.append(time.perf_counter()-before)
            if state.locked:
                if first is None:first=now
                for hit in hits_between(now,now+512/rate,state.bpm,state.phase,50):
                    if hit.time-last>.15:
                        if hit.time>=8:events.append(hit.time)
                        last=hit.time
        first=first
    else:
        for name in ('small0','small1') if backend == 'ensemble' else (backend,):
            get_predictor(name)
        # Warm-up excluded from steady-state measurements, reported separately.
        before=time.perf_counter();infer_clock(audio[:rate*4],rate,0,4,backend)
        warm=time.perf_counter()-before
        events=[];times=[];first=None;state=None;last=-100;updates=[]
        for end in np.arange(4,duration,1):
            start=max(0,end-8)
            before=time.perf_counter()
            state=infer_clock(audio[int(start*rate):int(end*rate)],rate,start,end,backend,state)
            cost=time.perf_counter()-before;times.append(cost)
            updates.append((end+cost, state))
        # While new inference runs, the last published clock still plays.
        cursor=0; published=None;fallback=AubioTracker(rate)
        for frame in range(0, len(audio)-512, 512):
            now=frame/rate
            basic=fallback.feed(audio[frame:frame+512],now) if backend == "ensemble" else None
            while cursor<len(updates) and updates[cursor][0]<=now:
                published=updates[cursor][1]; cursor+=1
            chosen=published
            if chosen is None or not chosen.locked or now-chosen.updated>=2.5:
                chosen=basic
            if chosen is None or not chosen.locked:continue
            if first is None:first=now
            for hit in hits_between(now,now+512/rate,chosen.bpm,chosen.phase,50):
                if hit.time-last>.15:
                    if hit.time>=8:events.append(hit.time)
                    last=hit.time
    result=score(events,target)
    result.update(backend=backend, first_lock_s=round(first,3) if first else None,
                  computation_ms=round(sum(times)*1000,1),
                  inference_p95_ms=round(float(np.percentile(times,95))*1000,1))
    if backend!='aubio':result['warmup_s']=round(warm,3)
    return result

if __name__=='__main__':
    results=[]
    for bpm,condition in ((90,'clean'),(120,'clean'),(150,'clean'),(90,'room'),(120,'room'),(150,'room')):
        audio,rate=fixture(bpm,condition,duration=24)
        for backend in ('aubio','small0','small1','ensemble'):
            result=run(audio,rate,bpm,backend);result.update(bpm=bpm,condition=condition)
            results.append(result);print(json.dumps(result),flush=True)
            Path('docs/ai-benchmark-results.json').write_text(json.dumps(results,indent=2))
