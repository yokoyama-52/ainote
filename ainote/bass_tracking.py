"""Causal 30–150 Hz auxiliary rhythm evidence; never replaces AI input."""
from collections import deque
from dataclasses import replace
import numpy as np
import aubio
from .tracking import BeatState


def biquad(kind, frequency, rate):
    w=2*np.pi*frequency/rate; co=np.cos(w); alpha=np.sin(w)/(2*np.sqrt(.5))
    a0=1+alpha
    if kind=='low':b=np.array([(1-co)/2,1-co,(1-co)/2])
    else:b=np.array([(1+co)/2,-(1+co),(1+co)/2])
    filt=aubio.digital_filter(3)
    filt.set_biquad(*(b/a0), -2*co/a0, (1-alpha)/a0)
    return filt

class BassTracker:
    """Five-second rolling bass energy novelty + periodicity/phase tests."""
    def __init__(self, rate, block=512):
        self.rate,self.block=rate,block
        self.high=biquad('high',30,rate);self.low=biquad('low',150,rate)
        self.history=deque(maxlen=int(np.ceil(5*rate/block)))
        self.previous_energy=0
        self.last_analysis=-100
        self.state=BeatState(reason='低音：観測中')
        self.confirmations=0
        self.previous_bpm=None
        self.last_sound=-100

    def filter(self, data):
        return self.low(self.high(np.asarray(data,dtype='float32')))

    def feed(self, data, timestamp):
        x=np.asarray(data,dtype='float32')
        y=self.filter(x)
        level=float(np.sqrt(np.mean(x*x)))
        energy=float(np.sqrt(np.mean(y*y)))
        novelty=max(0,np.log(energy+1e-6)-np.log(self.previous_energy+1e-6))
        self.previous_energy=energy
        if level>.0003:self.last_sound=timestamp
        self.history.append((timestamp+self.block/(2*self.rate),energy,novelty,level))
        if timestamp-self.last_analysis < .25:return self.state
        self.last_analysis=timestamp
        points=np.asarray(self.history)
        if len(points)*self.block/self.rate < 3:
            return self.state
        energy_range=np.percentile(points[:,1],[10,90])
        dominance=np.sqrt(np.mean(points[:,1]**2))/max(1e-8,np.sqrt(np.mean(points[:,3]**2)))
        if energy_range[1]<.00015 or energy_range[1]/max(energy_range[0],1e-6)<2 or dominance<.10:
            self.confirmations=0
            self.state=BeatState(level=level,updated=timestamp,reason='低音：明瞭な拍なし')
            return self.state
        envelope=np.convolve(points[:,2], [.25,.5,.25], mode='same')
        envelope=np.maximum(envelope-np.median(envelope),0)
        fps=self.rate/self.block
        ac=np.correlate(envelope,envelope,'full')[len(envelope)-1:]
        lags=np.arange(int(np.ceil(fps*60/200)),int(np.floor(fps*60/60))+1)
        lag=int(lags[np.argmax(ac[lags])])
        a,b,c=ac[lag-1:lag+2];den=a-2*b+c
        frac=float(np.clip(.5*(a-c)/den,-.5,.5)) if abs(den)>1e-12 else 0
        period=(lag+frac)/fps;bpm=60/period
        confidence=float(np.clip(ac[lag]/(ac[0]+1e-12),0,1))
        contrast=ac[lag]/max(np.median(ac[lags]),1e-9)
        phases=np.arange(100)*period/100
        weights=np.exp((points[:,0]-timestamp)/2)
        votes=[np.sum(envelope*weights*np.exp(-.5*(((points[:,0]-p+period/2)%period-period/2)/.025)**2)) for p in phases]
        phase=float(phases[np.argmax(votes)])
        # Bandpass group delay and the RMS block midpoint are small but nonzero;
        # the benchmark measures phase at actual known input beat times.
        consistent=self.previous_bpm is not None and abs(bpm-self.previous_bpm)<3
        self.confirmations=self.confirmations+1 if consistent else 1
        self.previous_bpm=bpm
        locked=confidence>=.55 and contrast>=3 and self.confirmations>=3 and timestamp-self.last_sound<1.0
        self.state=BeatState(bpm,phase,confidence,level,timestamp,locked,
            '低音補助：5秒窓の周期が安定' if locked else '低音：周期を確認中',self.confirmations,0,True)
        return self.state


# 低音側の推定が主判定と合うときだけ、BPMと拍位置を少し補正する。
def fuse_bass(primary, bass, now):
    """Corroborate only: never force the AI onto a contradictory bass pulse."""
    if not bass.locked or not 0<=now-bass.updated<.8:return primary
    if not primary.locked:return primary
    if abs(primary.bpm-bass.bpm)>3:return primary
    period=60/primary.bpm
    error=(bass.phase-primary.phase+period/2)%period-period/2
    if abs(error)>.060:return primary
    return replace(primary,bpm=.8*primary.bpm+.2*bass.bpm,
                   phase=primary.phase+.25*error,reason=primary.reason+' / 低音一致')
