"""Voice backend protocol, shared request guard, and word-time alignment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import numpy as np

SAMPLE_RATE = 24000
MAX_SPOKEN_CHARS = 300


@dataclass
class SynthResult:
    audio: np.ndarray  # float32 mono
    sample_rate: int
    word_times: list[tuple[float, float]]  # one (start, end) seconds per requested word


class VoiceBackend(Protocol):
    device: str
    notice: str | None

    def synth(self, words: list[str], voice: str) -> SynthResult: ...


def check_request(words: list[str], voice: str) -> str:
    """Shared guard for every backend. Returns the joined spoken text."""
    text = " ".join(words)
    if not text.strip():
        raise ValueError("refusing to synthesise empty text")
    if len(text) > MAX_SPOKEN_CHARS:
        raise ValueError(f"spoken text is {len(text)} chars; limit is {MAX_SPOKEN_CHARS}")
    return text


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.lower())


def _proportional(words: list[str], duration: float) -> list[tuple[float, float]]:
    weights = [max(len(w), 1) for w in words]
    total = sum(weights)
    out: list[tuple[float, float]] = []
    acc = 0
    for w in weights:
        out.append((duration * acc / total, duration * (acc + w) / total))
        acc += w
    return out


def _match(
    words: list[str], tokens: list[tuple[str, float | None, float | None]]
) -> list[tuple[float, float]] | None:
    kept = [(_norm(t), s, e) for t, s, e in tokens]
    kept = [k for k in kept if k[0]]
    if any(s is None or e is None for _, s, e in kept):
        return None
    out: list[tuple[float, float]] = []
    i = 0
    prev_end = 0.0
    for word in words:
        target = _norm(word)
        if not target:  # pure punctuation: zero-length at the previous end
            out.append((prev_end, prev_end))
            continue
        joined = ""
        first = i
        while i < len(kept) and len(joined) < len(target):
            joined += kept[i][0]
            i += 1
            if not target.startswith(joined):
                return None
        if joined != target:
            return None
        start, end = kept[first][1], kept[i - 1][2]
        out.append((start, end))  # type: ignore[arg-type]
        prev_end = end  # type: ignore[assignment]
    if i != len(kept):
        return None
    return out


def align_words(
    words: list[str],
    tokens: list[tuple[str, float | None, float | None]],
    duration: float,
) -> list[tuple[float, float]]:
    """One (start, end) per word, monotonic and within [0, duration]."""
    if not words:
        return []
    times = _match(words, tokens)
    if times is None:
        times = _proportional(words, duration)
    out: list[tuple[float, float]] = []
    prev_start = 0.0
    for s, e in times:
        s = min(max(s, prev_start), duration)
        e = min(max(e, s), duration)
        out.append((s, e))
        prev_start = s
    return out
