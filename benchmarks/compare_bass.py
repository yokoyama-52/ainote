"""Compare rolling windows and bass evidence without future-audio leakage."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from ainote.ai_tracking import infer_beats,clock_from_beats,consensus_clock,get_predictor
from ainote.bass_tracking import BassTracker,fuse_bass
from ainote.tracking import AubioTracker
from ainote.steady_clock import SteadyClock
from ainote.music import hits_between
from benchmarks.compare_trackers import fixture
from benchmarks.compare_ai import score
from benchmarks.baseline_ai_clock import clock_from_beats as old_clock


def evaluate(audio,rate,bpm,condition):
    duration=len(audio)/rate
    caches={};times={}
    for window in (5,8):
        caches[window]=[];times[window]=[]
        for end in np.arange(4,duration,1):
            start=max(0,end-window);predictions=[];before=time.perf_counter()
            for name in ('small0','small1'):
                beats,_=infer_beats(audio[int(start*rate):int(end*rate)],rate,name)
                predictions.append(beats)
            cost=time.perf_counter()-before
            caches[window].append((end+cost,start,end,predictions))
            times[window].append(cost)
    basic=AubioTracker(rate);bass=BassTracker(rate);observations=[];extra=0
    for frame in range(0,len(audio)-512,512):
        now=frame/rate;block=audio[frame:frame+512]
        fallback=basic.feed(block,now)
        before=time.perf_counter();low=bass.feed(block,now);extra+=time.perf_counter()-before
        observations.append((now,fallback,low,float(np.sqrt(np.mean(block**2)))))
    results=[]
    for label,window,decode,use_bass in (('before_8s',8,old_clock,False),('robust_5s',5,clock_from_beats,False),('robust_8s',8,clock_from_beats,False),('robust_8s_bass',8,clock_from_beats,True)):
        updates=[]
        for available,start,end,predictions in caches[window]:
            a,b=[decode(beats,start,end) for beats in predictions]
            updates.append((available,consensus_clock(a,b,end)))
        clock=SteadyClock();cursor=0;published=None;events=[];first=None;last=-100;agreements=0
        for now,fallback,low,level in observations:
            while cursor<len(updates) and updates[cursor][0]<=now:
                published=updates[cursor][1];cursor+=1
            use_ai=published is not None and published.locked and 0<=now-published.updated<2.5
            selected=published if use_ai else fallback
            if use_bass:
                merged=fuse_bass(selected,low,now)
                agreements+=int(merged.reason!=selected.reason);selected=merged
            state=clock.update(selected,now,level)
            if state.locked:
                if first is None:first=now
                for hit in hits_between(now,now+512/rate,state.bpm,state.phase,50):
                    if hit.time-last>.15:
                        if hit.time>=8:events.append(hit.time)
                        last=hit.time
        target=np.arange(0,duration,60/bpm);target=target[target>=8]
        result=score(events,target)
        result.update(variant=label,bpm=bpm,condition=condition,first_lock_s=round(first,3) if first is not None else None,
                      ai_p95_ms=round(float(np.percentile(times[window],95))*1000,1),
                      bass_cpu_ms=round(extra*1000,1) if use_bass else 0,bass_agreement_blocks=agreements)
        results.append(result);print(json.dumps(result),flush=True)
    return results

if __name__=='__main__':
    # Initial model construction/warm-up is excluded, same as previous comparison.
    for name in ('small0','small1'):get_predictor(name)
    all_results=[]
    for bpm in (90,120,150):
        for condition in ('clean','room'):
            x,r=fixture(bpm,condition,duration=24)
            all_results.extend(evaluate(x,r,bpm,condition))
            Path('docs/bass-benchmark-results.json').write_text(json.dumps(all_results,indent=2))
