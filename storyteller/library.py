"""Pack library: PDFs, cached listening scripts, reading positions, rendered clips."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

from storyteller.extract import extract
from storyteller.model import Script, Sentence
from storyteller.settings import Settings, atomic_write, home
from storyteller.speech import build_script
from storyteller.speech.symbols import Rules
from storyteller.voice.base import SynthResult

__all__ = ["Library", "PackInfo"]

_ID = re.compile(r"[0-9a-f]{16}\Z")
_VOICE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_LOCK = threading.RLock()  # guards every meta.json / script.json / skip.json / settings write


@dataclass
class PackInfo:
    id: str
    title: str
    filename: str
    page_count: int
    position: str | None
    rendered: int
    total: int
    added: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _clip_key(sentence: Sentence) -> str:
    return hashlib.sha1(sentence.spoken_text.encode("utf-8")).hexdigest()[:16]


class Library:
    """Packs under ``$STORYTELLER_HOME/packs/<id>/``; safe to call from several threads."""

    def __init__(self) -> None:
        # pack id -> (script.json mtime_ns, clip keys of its sentences)
        self._keys: dict[str, tuple[int, list[str]]] = {}

    # ---- paths -------------------------------------------------------------

    @staticmethod
    def _packs() -> Path:
        return home() / "packs"

    def _dir(self, pack_id: str) -> Path:
        if not isinstance(pack_id, str) or not _ID.match(pack_id):
            raise KeyError(pack_id)
        d = self._packs() / pack_id
        if not (d / "meta.json").exists():
            raise KeyError(pack_id)
        return d

    def pdf_path(self, pack_id: str) -> Path:
        return self._dir(pack_id) / "source.pdf"

    # ---- adding ------------------------------------------------------------

    def add_pdf(self, data: bytes, filename: str) -> PackInfo:
        pack_id = hashlib.sha256(data).hexdigest()[:16]
        final = self._packs() / pack_id
        if (final / "meta.json").exists():
            return self._info(pack_id)
        packs = self._packs()
        packs.mkdir(parents=True, exist_ok=True)
        tmp = packs / f".tmp-{uuid.uuid4().hex}"
        try:
            tmp.mkdir()
            (tmp / "source.pdf").write_bytes(data)
            script = self._build(tmp / "source.pdf", pack_id, [])
            now = _now()
            atomic_write(tmp / "script.json", json.dumps(script.to_dict()))
            atomic_write(
                tmp / "meta.json",
                json.dumps(
                    {
                        "id": pack_id,
                        "title": script.title or Path(filename).stem,
                        "filename": filename,
                        "page_count": script.page_count,
                        "position": None,
                        "added": now,
                        "last_opened": now,
                    }
                ),
            )
            with _LOCK:
                if not (final / "meta.json").exists():
                    if final.exists():  # stale partial directory
                        shutil.rmtree(final)
                    os.rename(tmp, final)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return self._info(pack_id)

    def _build(self, pdf: Path, pack_id: str, skip: list[str]) -> Script:
        doc = extract(pdf, skip_patterns=skip or None)
        rules = Rules.load()
        script = build_script(doc, pack_id, Settings.load().script_options(), rules)
        if rules.unknown:
            with _LOCK:
                settings = Settings.load()
                merged = sorted(set(settings.unknown_symbols) | set(rules.unknown))
                if merged != settings.unknown_symbols:
                    settings.unknown_symbols = merged
                    settings.save()
        return script

    # ---- listing -----------------------------------------------------------

    def _meta(self, pack_id: str) -> dict:
        meta = _read_json(self._packs() / pack_id / "meta.json")
        if not isinstance(meta, dict):
            raise KeyError(pack_id)
        return meta

    def _clip_keys(self, pack_id: str) -> list[str]:
        path = self._packs() / pack_id / "script.json"
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return []
        cached = self._keys.get(pack_id)
        if cached and cached[0] == stamp:
            return cached[1]
        script = self._load_script(pack_id)
        keys = [_clip_key(s) for s in script.sentences] if script else []
        self._keys[pack_id] = (stamp, keys)
        return keys

    def _info(self, pack_id: str) -> PackInfo:
        meta = self._meta(pack_id)
        keys = self._clip_keys(pack_id)
        voice = Settings.load().voice
        clips = self._packs() / pack_id / "clips" / voice
        try:
            have = {p[:-4] for p in os.listdir(clips) if p.endswith(".wav")}
        except OSError:
            have = set()
        return PackInfo(
            id=pack_id,
            title=meta.get("title", ""),
            filename=meta.get("filename", ""),
            page_count=meta.get("page_count", 0),
            position=meta.get("position"),
            rendered=sum(1 for k in keys if k in have),
            total=len(keys),
            added=meta.get("added", ""),
        )

    def list(self) -> list[PackInfo]:
        packs = self._packs()
        if not packs.exists():
            return []
        found: list[tuple[str, PackInfo]] = []
        for d in packs.iterdir():
            if not _ID.match(d.name):
                continue
            try:
                meta = self._meta(d.name)
                found.append((max(meta.get("last_opened", ""), meta.get("added", "")), self._info(d.name)))
            except KeyError:
                continue
        found.sort(key=lambda item: item[0], reverse=True)
        return [info for _, info in found]

    # ---- script ------------------------------------------------------------

    def _load_script(self, pack_id: str) -> Script | None:
        data = _read_json(self._packs() / pack_id / "script.json")
        if not isinstance(data, dict):
            return None
        try:
            return Script.from_dict(data)
        except (KeyError, TypeError, ValueError):
            return None

    def script(self, pack_id: str) -> Script:
        self._dir(pack_id)
        return self._load_script(pack_id) or self.rebuild_script(pack_id)

    def _skip_patterns(self, pack_id: str) -> list[str]:
        skip = _read_json(self._packs() / pack_id / "skip.json", [])
        return [p for p in skip if isinstance(p, str)] if isinstance(skip, list) else []

    def rebuild_script(self, pack_id: str) -> Script:
        d = self._dir(pack_id)
        script = self._build(d / "source.pdf", pack_id, self._skip_patterns(pack_id))
        with _LOCK:
            atomic_write(d / "script.json", json.dumps(script.to_dict()))
            meta = self._meta(pack_id)
            if meta.get("position") not in {s.id for s in script.sentences}:
                meta["position"] = None
            meta["page_count"] = script.page_count
            atomic_write(d / "meta.json", json.dumps(meta))
        return script

    def add_skip_pattern(self, pack_id: str, regex: str) -> None:
        d = self._dir(pack_id)
        try:
            re.compile(regex)
        except re.error as e:
            raise ValueError(f"invalid skip pattern: {e}") from e
        with _LOCK:
            patterns = self._skip_patterns(pack_id)
            if regex not in patterns:
                patterns.append(regex)
                atomic_write(d / "skip.json", json.dumps(patterns))
        self.rebuild_script(pack_id)

    # ---- position ----------------------------------------------------------

    def set_position(self, pack_id: str, sentence_id: str) -> None:
        d = self._dir(pack_id)
        with _LOCK:
            meta = self._meta(pack_id)
            meta["position"] = sentence_id
            meta["last_opened"] = _now()
            atomic_write(d / "meta.json", json.dumps(meta))

    # ---- clips -------------------------------------------------------------

    def clip_path(self, pack_id: str, sentence: Sentence, voice: str) -> Path:
        if not _VOICE.match(voice):
            raise ValueError(f"invalid voice name: {voice!r}")
        return self._dir(pack_id) / "clips" / voice / f"{_clip_key(sentence)}.wav"

    def save_clip(self, path: Path, result: SynthResult) -> None:
        """Write sibling .json first, then the WAV, so a WAV on disk is always complete."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        audio = np.clip(np.asarray(result.audio, dtype=np.float32), -1.0, 1.0)
        meta = {
            "duration": len(audio) / result.sample_rate,
            "words": [[float(s), float(e)] for s, e in result.word_times],
        }
        atomic_write(path.with_suffix(".json"), json.dumps(meta))
        tmp = path.with_name(f"{path.stem}.{uuid.uuid4().hex}.tmp")
        try:
            sf.write(tmp, audio, result.sample_rate, subtype="PCM_16", format="WAV")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def load_clip_meta(self, path: Path) -> dict | None:
        meta = _read_json(Path(path).with_suffix(".json"))
        return meta if isinstance(meta, dict) else None
