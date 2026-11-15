"""Voice backends. `get_backend()` picks one from env STORYTELLER_VOICE (kokoro | stub)."""

from __future__ import annotations

import os
import threading

from .base import SynthResult, VoiceBackend, align_words

__all__ = ["PREVIEW_VOICES", "SynthResult", "VoiceBackend", "align_words", "get_backend"]

# Voices offered in settings. Setup downloads all of them so switching voice works offline.
PREVIEW_VOICES = ("af_heart", "af_bella", "af_nicole", "am_michael", "bf_emma", "bm_george")

_backend: VoiceBackend | None = None
_backend_name: str | None = None
_lock = threading.Lock()


def get_backend() -> VoiceBackend:
    """Cached singleton. Re-created only if STORYTELLER_VOICE changes."""
    global _backend, _backend_name
    name = os.environ.get("STORYTELLER_VOICE", "kokoro").strip().lower() or "kokoro"
    with _lock:
        if _backend is None or _backend_name != name:
            if name == "stub":
                from .stub import StubVoice

                _backend = StubVoice()
            elif name == "kokoro":
                from .kokoro_backend import KokoroVoice

                _backend = KokoroVoice()
            else:
                raise ValueError(f"unknown STORYTELLER_VOICE {name!r} (expected kokoro or stub)")
            _backend_name = name
        return _backend
