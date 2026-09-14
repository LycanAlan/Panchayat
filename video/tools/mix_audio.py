"""Mix the film's soundtrack: narration, music bed and effects.

Cue times come from the same word timings the animation uses (src/film/vo2.json), so the
whooshes, stamps and pops land on the same frames as the visuals. Mixing outside Remotion
avoids re-rendering every frame just to get audio. ffmpeg (the one Remotion bundles is a
minimal build) only decodes each input; the mix itself is numpy.

    python video/tools/mix_audio.py --voice public/vo-riya.mp3 --out out/soundtrack.wav
"""

import argparse
import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

VIDEO = Path(__file__).resolve().parents[1]
SR = 48000


def decode(path: Path) -> np.ndarray:
    """Any audio file -> float32 stereo array at 48 kHz."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "x.wav"
        cmd = ["npx", "remotion", "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
               "-ac", "2", "-ar", str(SR), "-c:a", "pcm_s16le", str(wav)]
        cwd = os.environ.get("REMOTION_DIR", str(VIDEO))
        subprocess.run(subprocess.list2cmdline(cmd), cwd=cwd, check=True, shell=True)
        with wave.open(str(wav)) as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return data.reshape(-1, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default=str(VIDEO / "public" / "vo-riya.mp3"))
    parser.add_argument("--timing", default=str(VIDEO / "src" / "film" / "vo2.json"))
    parser.add_argument("--public", default=str(VIDEO / "public"))
    parser.add_argument("--out", default=str(VIDEO / "out" / "soundtrack.wav"))
    args = parser.parse_args()

    timing = json.loads(Path(args.timing).read_text(encoding="utf-8"))
    public = Path(args.public).resolve()

    def start(i: int) -> float:
        return timing[min(i, len(timing) - 1)]["start"]

    def word(i: int, w: str, nth: int = 0) -> float:
        hits = [x["s"] for x in timing[i]["words"] if x["w"] == w]
        return hits[nth] if len(hits) > nth else timing[i]["start"]

    vo_end = timing[-1]["end"]
    end = vo_end + 5.5
    whoosh_at = (7, 8, 9, 10, 11, 12, 13, 16, 19, 28, 29, 30, 32, 33, 34, 35)
    cues = [(start(i) - 0.35, "whoosh.wav", 0.35) for i in whoosh_at]
    cues += [(t, "stamp.wav", 0.5) for t in (word(6, "CLOSED"), word(7, "RESOLVED"), word(27, "COMES") + 0.1,
                                             word(32, "RESOLVED"), word(32, "DISPUTE"), word(34, "CLOSE"))]
    cues += [(t - 0.15, "pop.wav", 0.3) for t in (word(0, "HOSPITAL"), word(1, "POWER"), word(2, "SCHOLARSHIP"),
                                                  word(3, "BANK"), word(4, "POTHOLE"), word(4, "TAP"))]

    n = int(end * SR)
    mix = np.zeros((n, 2), dtype=np.float32)

    def add(clip: np.ndarray, at: float, gain: np.ndarray | float) -> None:
        a = max(0, int(at * SR))
        b = min(n, a + len(clip))
        if b > a:
            mix[a:b] += clip[: b - a] * (gain if np.isscalar(gain) else gain[: b - a, None])

    voice = Path(args.voice)
    add(decode(voice if voice.is_absolute() else Path(os.environ.get("REMOTION_DIR", str(VIDEO))) / voice), 0, 1.0)

    music = decode(public / "audio" / "music_bed.mp3")[:n]
    t = np.arange(len(music)) / SR
    gain = 0.22 * np.minimum(1, t / 2.5) * np.clip((end - t) / 4, 0, 1) * np.where(t > vo_end, 1.6, 1.0)
    add(music, 0, gain.astype(np.float32))

    sounds = {name: decode(public / "audio" / name) for name in {c[1] for c in cues}}
    for at, name, vol in cues:
        add(sounds[name], at, vol)

    peak = float(np.max(np.abs(mix)))
    if peak > 0.98:
        mix *= 0.98 / peak
    out = Path(args.out)
    os.makedirs(out.parent, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    print("wrote", out, f"{end:.1f}s", "peak", round(peak, 3))


if __name__ == "__main__":
    main()
