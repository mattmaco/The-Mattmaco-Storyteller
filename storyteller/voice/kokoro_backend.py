"""Kokoro-82M backend. kokoro/torch are imported lazily so the voice extra is optional."""

from __future__ import annotations

import numpy as np

from .base import SAMPLE_RATE, SynthResult, align_words, check_request


class KokoroVoice:
    def __init__(self, device: str | None = None):
        import torch  # noqa: F401  (lazy: only needed when Kokoro is actually used)

        self._torch = torch
        self.notice: str | None = None
        self._pipelines: dict[str, object] = {}
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            try:
                torch.zeros(1, device="cuda")
            except Exception:
                device = "cpu"
                self.notice = "GPU unavailable, using CPU"
        self.device = device

    def _pipeline(self, lang: str):
        pipe = self._pipelines.get(lang)
        if pipe is None:
            from kokoro import KPipeline

            try:
                pipe = KPipeline(lang_code=lang, device=self.device)
            except Exception:
                if self.device != "cuda":
                    raise
                self.device = "cpu"
                self.notice = "GPU unavailable, using CPU"
                pipe = KPipeline(lang_code=lang, device="cpu")
            self._pipelines[lang] = pipe
        return pipe

    def synth(self, words: list[str], voice: str) -> SynthResult:
        text = check_request(words, voice)
        pipeline = self._pipeline(voice[0])
        chunks: list[np.ndarray] = []
        tokens: list[tuple[str, float | None, float | None]] = []
        offset = 0.0
        for result in pipeline(text, voice=voice, speed=1.0, split_pattern=None):
            audio = result.audio
            if audio is None:
                continue
            audio = np.asarray(audio.detach().cpu() if hasattr(audio, "detach") else audio,
                               dtype=np.float32).reshape(-1)
            for tok in result.tokens or []:
                s, e = tok.start_ts, tok.end_ts
                tokens.append((
                    tok.text,
                    None if s is None else s + offset,
                    None if e is None else e + offset,
                ))
            chunks.append(audio)
            offset += len(audio) / SAMPLE_RATE
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return SynthResult(audio, SAMPLE_RATE, align_words(words, tokens, len(audio) / SAMPLE_RATE))
