"""Word-level timestamps for the voiceover, so every animation beat lands on its word.

ElevenLabs' transcription returns text without timings, and pause detection
cannot tell a paragraph break from a breath. This force-aligns the known
narration against the audio with wav2vec2 (CTC), which is exact and local.

    python video/tools/align_voiceover.py

Reads video/narration.txt (one sentence per line) and video/public/voiceover.mp3,
writes video/src/vo_timing.json. Needs torch + transformers (~360 MB model on
first run) and uses the ffmpeg bundled with Remotion, so run `npm ci` in video/
first.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

VIDEO = Path(__file__).resolve().parents[1]
MODEL = "facebook/wav2vec2-base-960h"
SAMPLE_RATE = 16_000


def load_audio(mp3: Path) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "vo.wav"
        subprocess.run(
            ["npx", "remotion", "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(mp3), "-ac", "1", "-ar", str(SAMPLE_RATE), str(wav)],
            cwd=VIDEO, check=True, shell=True,
        )
        with wave.open(str(wav)) as w:
            frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768


def align(tokens: list[int], blank: int, emission: torch.Tensor) -> list[tuple[int, int]]:
    """Viterbi path through the CTC trellis: (token index, frame) pairs."""
    frames, n = emission.size(0), len(tokens)
    trellis = torch.full((frames + 1, n + 1), -float("inf"))
    trellis[:, 0] = 0
    trellis[1:, 0] = torch.cumsum(emission[:, blank], 0)
    for t in range(frames):
        trellis[t + 1, 1:] = torch.maximum(trellis[t, 1:] + emission[t, blank],
                                           trellis[t, :-1] + emission[t, tokens])
    path, t, j = [], frames, n
    while j > 0 and t > 0:
        stay = trellis[t - 1, j] + emission[t - 1, blank]
        change = trellis[t - 1, j - 1] + emission[t - 1, tokens[j - 1]]
        if change > stay:
            path.append((j - 1, t - 1))
            j -= 1
        t -= 1
    return path[::-1]


def main() -> None:
    sentences = [s.strip() for s in (VIDEO / "narration.txt").read_text(encoding="utf-8").splitlines() if s.strip()]
    audio = load_audio(VIDEO / "public" / "voiceover.mp3")

    processor = Wav2Vec2Processor.from_pretrained(MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    with torch.inference_mode():
        values = processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_values
        emission = torch.log_softmax(model(values).logits, dim=-1)[0]

    vocab = processor.tokenizer.get_vocab()
    words, owner = [], []
    for si, sentence in enumerate(sentences):
        for raw in sentence.split():
            word = re.sub(r"[^A-Z']", "", raw.upper())
            if word:
                words.append(word)
                owner.append(si)
    tokens = [vocab[c] for c in "|".join(words)]
    path = align(tokens, vocab["<pad>"], emission)

    seconds_per_frame = len(audio) / SAMPLE_RATE / emission.size(0)
    spans: dict[int, list[int]] = {}
    for token, frame in path:
        spans.setdefault(token, [frame, frame])[1] = frame

    timed, cursor = [], 0
    for word in words:
        hits = [spans[k] for k in range(cursor, cursor + len(word)) if k in spans]
        timed.append((round(hits[0][0] * seconds_per_frame, 2), round((hits[-1][1] + 1) * seconds_per_frame, 2)))
        cursor += len(word) + 1

    out = []
    for si, sentence in enumerate(sentences):
        ws = [(words[i], timed[i]) for i in range(len(words)) if owner[i] == si]
        out.append({"i": si, "start": ws[0][1][0], "end": ws[-1][1][1], "text": sentence,
                    "words": [{"w": w, "s": s, "e": e} for w, (s, e) in ws]})
        print(f"{si:2d} {ws[0][1][0]:6.2f}-{ws[-1][1][1]:6.2f}  {sentence}")

    (VIDEO / "src" / "vo_timing.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
