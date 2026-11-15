"""User settings and the app data directory."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass, field, fields
from pathlib import Path

import platformdirs
import re
import threading

from storyteller.speech import BOX_KINDS, ScriptOptions

__all__ = ["VOICE_RE", "SPEED_MAX", "SPEED_MIN", "Settings", "atomic_write", "home"]

SPEED_MIN = 0.75
SPEED_MAX = 2.0
VOICE_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_SETTINGS_LOCK = threading.RLock()
_MERGED_DICTS = ("pauses", "read_boxes")  # pronunciations replace wholesale


def home() -> Path:
    """App data directory; ``STORYTELLER_HOME`` overrides the platform default."""
    env = os.environ.get("STORYTELLER_HOME")
    return Path(env) if env else Path(platformdirs.user_data_dir("Storyteller", appauthor=False))


def atomic_write(path: Path, data: bytes | str) -> None:
    """Write ``data`` to ``path`` via a temp file in the same directory and ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _default_pauses() -> dict[str, int]:
    return {"sentence": 250, "block": 600, "section": 1000}


@dataclass
class Settings:
    speed: float = 1.0
    voice: str = "af_heart"
    pauses: dict[str, int] = field(default_factory=_default_pauses)
    read_boxes: dict[str, bool] = field(default_factory=lambda: {k: True for k in BOX_KINDS})
    read_badges: bool = True
    skip_flags: bool = True
    highlight_sentence: bool = True
    highlight_word: bool = True
    sentence_color: str = "#fff3b0"
    word_color: str = "#f2a900"
    pronunciations: dict[str, str] = field(default_factory=dict)
    unknown_symbols: list[str] = field(default_factory=list)

    @staticmethod
    def path() -> Path:
        return home() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        """Read settings.json, merged over defaults; missing or corrupt gives defaults."""
        path = cls.path()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return cls()
        except UnicodeDecodeError:
            raw = None
        try:
            if raw is None:
                raise ValueError("settings.json is not UTF-8")
            saved = json.loads(raw)
            if not isinstance(saved, dict):
                raise ValueError("settings.json is not an object")
        except ValueError:
            try:
                shutil.copyfile(path, path.with_name(path.name + ".bak"))
            except OSError:
                pass
            return cls()
        return cls._from_saved(saved)

    @classmethod
    def _from_saved(cls, saved: dict) -> "Settings":
        s = cls()
        for f in fields(cls):
            if f.name not in saved:
                continue
            value, current = saved[f.name], getattr(s, f.name)
            if f.name == "speed":
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    s.speed = min(SPEED_MAX, max(SPEED_MIN, float(value)))
            elif f.name == "pauses":
                if isinstance(value, dict):
                    for k in current:
                        v = value.get(k)
                        if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                            current[k] = v
            elif f.name == "read_boxes":
                if isinstance(value, dict):
                    for k in current:
                        if isinstance(value.get(k), bool):
                            current[k] = value[k]
            elif f.name == "pronunciations":
                if isinstance(value, dict) and all(
                    isinstance(k, str) and isinstance(v, str) for k, v in value.items()
                ):
                    s.pronunciations = dict(value)
            elif f.name == "unknown_symbols":
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    s.unknown_symbols = list(value)
            elif f.name == "voice":
                if isinstance(value, str) and VOICE_RE.match(value):
                    s.voice = value
            elif isinstance(value, type(current)):
                setattr(s, f.name, value)
        return s

    @classmethod
    def validate_partial(cls, partial: dict) -> None:
        """Raise ValueError if ``partial`` has unknown fields or values update() would drop."""
        current = cls.load()
        unknown = set(partial) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown settings: {sorted(unknown)}")
        for key, value in partial.items():
            if key in _MERGED_DICTS:
                if not isinstance(value, dict):
                    raise ValueError(f"{key} must be an object")
                value = {**getattr(current, key), **value}
            if isinstance(value, bool) != isinstance(getattr(current, key), bool):
                raise ValueError(f"invalid value for {key}")
            if getattr(cls._from_saved({key: value}), key) != value:
                raise ValueError(f"invalid value for {key}")

    @classmethod
    def update(cls, **partial) -> "Settings":
        """Load, apply ``partial`` field values, save; atomic against other updaters."""
        with _SETTINGS_LOCK:
            s = cls.load()
            names = {f.name for f in fields(cls)}
            unknown = set(partial) - names
            if unknown:
                raise ValueError(f"unknown settings: {sorted(unknown)}")
            merged = {**s.__dict__, **partial}
            for key in _MERGED_DICTS:  # partial dicts merge over the stored one
                if isinstance(partial.get(key), dict):
                    merged[key] = {**getattr(s, key), **partial[key]}
            s = cls._from_saved(merged)
            s.save()
            return s

    def save(self) -> None:
        atomic_write(self.path(), json.dumps(self.__dict__, indent=2, ensure_ascii=False))

    def script_options(self) -> ScriptOptions:
        return ScriptOptions(
            pauses=dict(self.pauses),
            read_boxes=dict(self.read_boxes),
            read_badges=self.read_badges,
            read_flags=not self.skip_flags,
            pronunciations=dict(self.pronunciations),
        )
