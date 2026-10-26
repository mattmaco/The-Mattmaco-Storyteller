"""Silent voice backend: deterministic, instant, no dependencies."""

from __future__ import annotations

import numpy as np

from .base import SAMPLE_RATE, SynthResult, align_words, check_request

SECONDS_PER_CHAR = 0.06


class StubVoice:
    device = "stub"
    notice: str | None = None

    def synth(self, words: list[str], voice: str) -> SynthResult:
        text = check_request(words, voice)
        n = round(SECONDS_PER_CHAR * len(text) * SAMPLE_RATE)
        audio = np.zeros(n, dtype=np.float32)
        # No tokens -> proportional-by-length timing over the whole clip.
        return SynthResult(audio, SAMPLE_RATE, align_words(words, [], n / SAMPLE_RATE))
