#!/usr/bin/env python3
"""Generate an original ~16s music bed (chords+arp+soft kick) — no samples,
no licensing. Output: assets/music/licensed/t1p-bed-01.wav (or --out)."""
import sys, wave
from pathlib import Path
import numpy as np

def main(out="assets/music/licensed/t1p-bed-01.wav", seed=1):
    rng = np.random.default_rng(seed)
    sr, dur = 44100, 16.0
    t = np.linspace(0, dur, int(sr*dur), endpoint=False)
    mix = np.zeros_like(t)
    def note(freq, start, length, amp):
        n0, n1 = int(start*sr), int(min(dur, start+length)*sr)
        tt = t[n0:n1]-start
        env = np.minimum(tt/0.12, 1)*np.exp(-tt/(length*0.9))
        mix[n0:n1] += amp*env*(np.sin(2*np.pi*freq*tt)+0.4*np.sin(4*np.pi*freq*tt)+0.15*np.sin(6*np.pi*freq*tt))
    chords = [(174.61,220.0,261.63),(130.81,164.81,196.0),(146.83,174.61,220.0),(116.54,146.83,174.61)]
    for rep in range(2):
        for ci, ch in enumerate(chords):
            for f in ch:
                note(f, rep*8+ci*2, 2.2, 0.10); note(f*2, rep*8+ci*2, 2.2, 0.035)
    arp = [523.25, 659.25, 783.99, 659.25]
    for b in range(int(dur/0.5)):
        note(arp[b % 4]*(1 if (b//4)%2==0 else 0.75), b*0.5+0.02, 0.35, 0.05)
    for k in np.arange(0, dur, 0.6):
        n0 = int(k*sr); n1 = min(len(mix), n0+int(0.12*sr)); tt = t[n0:n1]-k
        mix[n0:n1] += 0.28*np.exp(-tt/0.05)*np.sin(2*np.pi*(60+40*np.exp(-tt/0.02))*tt)
    f0 = int((dur-2.5)*sr)
    fade = np.ones_like(mix); fade[f0:] = np.linspace(1, 0, len(mix)-f0)
    mix = np.tanh(mix*fade*1.2)
    pcm = (mix/np.max(np.abs(mix))*0.85*32767).astype(np.int16)
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    w = wave.open(str(out), "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(pcm.tobytes()); w.close()
    print(out)

if __name__ == "__main__":
    main(*sys.argv[1:])
