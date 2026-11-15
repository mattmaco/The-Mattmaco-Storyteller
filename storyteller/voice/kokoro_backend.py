"""Kokoro-82M backend. kokoro/torch are imported lazily so the voice extra is optional."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np

from .base import SAMPLE_RATE, SynthResult, align_words, check_request

# espeak-ng keeps its data path in a fixed buffer (160 bytes, 230 on Windows) and silently falls
# back to a build-time path when the real one is longer, then exits the whole process. Leave room
# for the file names it appends.
_ESPEAK_PATH_LIMIT = (230 if os.name == "nt" else 160) - 40


def ensure_short_espeak_path() -> Path | None:
    """If the bundled espeak-ng data sits on too long a path, copy it under the app data folder
    and point espeak there. Returns the folder used, or None when the bundled path is fine."""
    try:
        import espeakng_loader
        import misaki.espeak  # noqa: F401  (sets the bundled path first; we override it below)
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
    except ImportError:  # a Kokoro setup without the espeak fallback: nothing to fix
        return None

    from storyteller.settings import home

    src = Path(espeakng_loader.get_data_path())
    if len(str(src.resolve())) <= _ESPEAK_PATH_LIMIT:
        return None
    dst = home() / "espeak-ng-data"
    if not (dst / "phontab").is_file() or (dst / "phontab").stat().st_size != (src / "phontab").stat().st_size:
        shutil.copytree(src, dst, dirs_exist_ok=True)
    if len(str(dst.resolve())) > _ESPEAK_PATH_LIMIT:
        raise RuntimeError(f"the voice data folder path is too long for espeak-ng: {dst}")
    EspeakWrapper.set_data_path(str(dst))
    return dst


class KokoroVoice:
    def __init__(self, device: str | None = None):
        import torch  # noqa: F401  (lazy: only needed when Kokoro is actually used)

        self._torch = torch
        ensure_short_espeak_path()
        self.notice: str | None = None
        self._pipelines: dict[str, object] = {}
        try:
            if device is None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cuda":
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
            except RuntimeError:  # CUDA failures only; network/weights errors propagate
                if self.device != "cuda":
                    raise
                self.device = "cpu"
                self.notice = "GPU unavailable, using CPU"
                self._pipelines.clear()  # others were built on cuda; rebuild lazily on cpu
                pipe = KPipeline(lang_code=lang, device="cpu")
            self._pipelines[lang] = pipe
        return pipe

    def prepare(self, voices) -> None:
        """Download (first run) and load the language models and voice files for ``voices``."""
        for voice in voices:
            self._pipeline(voice[0]).load_voice(voice)

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
