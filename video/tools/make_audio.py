"""Royalty-free music bed and sound effects, synthesized from scratch.

A warm, slow chord bed: reflective (Bm9 - Gmaj7 - D/F# - A6) for the problem, opening
to a hopeful progression (Dmaj9 - Aadd9 - Bm7 - Gmaj7) from 'Meet Panchayat' on, with
soft felt-piano plucks. Plus a paper whoosh, a rubber-stamp thud and a card pop.
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
ROOT = Path(__file__).resolve().parents[1] / "public"
OUT = ROOT / "audio"
OUT.mkdir(parents=True, exist_ok=True)
timing = json.load(open(Path(__file__).resolve().parents[1] / "src" / "film" / "vo2.json", encoding="utf-8"))
meet_at = timing[16]["start"]
build_at = timing[13]["start"]
total = timing[-1]["end"] + 7.5
rng = np.random.default_rng(7)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def write(path, data):
    data = np.clip(data, -1, 1)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    pcm = (data * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def one_pole_lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.zeros_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


# ---------------------------------------------------------------- music bed
SAD = [[47, 54, 57, 61, 62], [43, 50, 54, 57, 59], [42, 50, 54, 57, 62], [45, 52, 54, 57, 61]]
HOPE = [[50, 57, 61, 64, 66], [45, 52, 57, 59, 64], [47, 54, 57, 62, 66], [43, 50, 54, 59, 62]]
BAR = 4.0
n = int(total * SR)
t = np.arange(n) / SR
left = np.zeros(n)
right = np.zeros(n)

bar_count = int(np.ceil(total / BAR))
for b in range(bar_count):
    start = b * BAR
    chord = (HOPE if start >= meet_at - 0.5 else SAD)[b % 4]
    s0 = int(start * SR)
    s1 = min(n, int((start + BAR + 1.5) * SR))
    seg = t[s0:s1] - start
    env = np.minimum(1, seg / 1.2) * np.clip((BAR + 1.5 - seg) / 1.5, 0, 1)
    for k, note in enumerate(chord):
        f = midi(note)
        pan = 0.5 + 0.35 * np.sin(k * 1.7)
        tone = (np.sin(2 * np.pi * f * seg) + 0.35 * np.sin(2 * np.pi * f * 1.003 * seg)
                + 0.12 * np.sin(2 * np.pi * 2 * f * seg))
        amp = (0.05 if k == 0 else 0.028) * env
        left[s0:s1] += tone * amp * (1 - pan)
        right[s0:s1] += tone * amp * pan

    if start >= build_at - 0.5:
        density = 8 if start >= meet_at - 0.5 else 4
        arp = chord[1:] + chord[2:][::-1]
        for q in range(density):
            at = start + q * BAR / density
            p0 = int(at * SR)
            dur = int(1.6 * SR)
            p1 = min(n, p0 + dur)
            if p0 >= n:
                break
            seg2 = (np.arange(p1 - p0)) / SR
            f = midi(arp[q % len(arp)] + 12)
            pl = (np.sin(2 * np.pi * f * seg2) * np.exp(-seg2 * 3.2)
                  + 0.25 * np.sin(2 * np.pi * 2 * f * seg2) * np.exp(-seg2 * 6))
            pan = 0.3 + 0.4 * ((q * 37) % 7) / 6
            gain = 0.03 if density == 8 else 0.024
            left[p0:p1] += pl * gain * (1 - pan)
            right[p0:p1] += pl * gain * pan

bed = np.stack([left, right], axis=1)
# soft room: a few decaying echoes
for delay, g in [(0.083, 0.35), (0.19, 0.22), (0.31, 0.14)]:
    d = int(delay * SR)
    bed[d:] += bed[:-d] * g * np.array([0.7, 1.0])
bed /= np.max(np.abs(bed)) + 1e-9
bed *= 0.55
write(OUT / "music_bed.wav", bed)

# ---------------------------------------------------------------- whoosh
d = int(0.7 * SR)
tt = np.arange(d) / SR
noise = rng.standard_normal(d)
sweep = one_pole_lowpass(noise, 900) * np.sin(np.pi * tt / 0.7) ** 2
sweep += one_pole_lowpass(noise, 2400) * np.sin(np.pi * np.clip(tt / 0.5, 0, 1)) ** 4 * 0.4
sweep /= np.max(np.abs(sweep))
write(OUT / "whoosh.wav", np.stack([sweep * np.linspace(1, 0.4, d), sweep * np.linspace(0.4, 1, d)], axis=1) * 0.8)

# ---------------------------------------------------------------- stamp
d = int(0.5 * SR)
tt = np.arange(d) / SR
thud = (np.sin(2 * np.pi * 85 * tt) * np.exp(-tt * 18)
        + 0.6 * one_pole_lowpass(rng.standard_normal(d), 1800) * np.exp(-tt * 40))
thud /= np.max(np.abs(thud))
write(OUT / "stamp.wav", thud * 0.9)

# ---------------------------------------------------------------- pop
d = int(0.25 * SR)
tt = np.arange(d) / SR
pop = np.sin(2 * np.pi * (520 + 380 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 28) * 0.7
write(OUT / "pop.wav", pop)
print("music", round(total, 1), "s ->", OUT)
sys.exit(0)
