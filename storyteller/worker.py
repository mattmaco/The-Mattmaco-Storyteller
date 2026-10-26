"""Background clip renderer. The clip endpoint renders on demand; this thread renders ahead."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from storyteller.library import Library
from storyteller.model import Script, Sentence
from storyteller.settings import Settings

__all__ = ["RenderWorker"]

log = logging.getLogger(__name__)


class RenderWorker:
    """One render lock shared by the thread and ``render_now``.

    The thread holds the lock for one clip at a time and steps aside while any
    ``render_now`` call is waiting, so a click is never queued behind more than
    the clip being synthesised.
    """

    def __init__(self, library: Library, backend) -> None:
        self.library = library
        self.backend = backend
        self.failed: set[tuple[str, str]] = set()
        self._render_lock = threading.Lock()
        self._cond = threading.Condition()
        self._urgent = 0  # render_now calls waiting for the lock
        self._focus: tuple[str, str] | None = None
        self._focus_gen = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._scripts: dict[str, tuple[int, Script]] = {}
        self._scripts_lock = threading.Lock()

    # ---- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="storyteller-render", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 30.0) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout)
            self._thread = None

    # ---- scripts -----------------------------------------------------------

    def script(self, pack_id: str) -> Script:
        """The pack's script, re-read only when script.json changes."""
        path = self.library.pdf_path(pack_id).with_name("script.json")  # KeyError for unknown packs
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = -1
        with self._scripts_lock:
            cached = self._scripts.get(pack_id)
            if cached and cached[0] == stamp:
                return cached[1]
        script = self.library.script(pack_id)
        with self._scripts_lock:
            self._scripts[pack_id] = (stamp, script)
        return script

    def sentence(self, pack_id: str, sentence_id: str) -> Sentence:
        """Raises KeyError for an unknown pack or sentence."""
        for s in self.script(pack_id).sentences:
            if s.id == sentence_id:
                return s
        raise KeyError(sentence_id)

    # ---- rendering ---------------------------------------------------------

    def _cached(self, path: Path) -> bool:
        return path.exists() and self.library.load_clip_meta(path) is not None

    def _render(self, pack_id: str, sentence: Sentence, voice: str) -> Path:
        """Synthesise one clip unless present. The caller holds ``_render_lock``."""
        path = self.library.clip_path(pack_id, sentence, voice)
        if self._cached(path):
            return path
        try:
            result = self.backend.synth([w.text for w in sentence.spoken], voice)
            self.library.save_clip(path, result)
        except Exception:
            self.failed.add((pack_id, sentence.id))
            raise
        self.failed.discard((pack_id, sentence.id))
        return path

    def render_now(self, pack_id: str, sentence_id: str) -> Path:
        """Render one clip synchronously (or return the cached one). Raises on failure."""
        sentence = self.sentence(pack_id, sentence_id)
        voice = Settings.load().voice
        path = self.library.clip_path(pack_id, sentence, voice)
        if self._cached(path):
            return path
        with self._cond:
            self._urgent += 1
        try:
            with self._render_lock:
                return self._render(pack_id, sentence, voice)
        finally:
            with self._cond:
                self._urgent -= 1
                self._cond.notify_all()

    def focus(self, pack_id: str, sentence_id: str) -> None:
        """Render from this sentence to the pack end, then from the start."""
        self.sentence(pack_id, sentence_id)
        with self._cond:
            self._focus = (pack_id, sentence_id)
            self._focus_gen += 1
            self._cond.notify_all()

    def status(self, pack_id: str) -> dict[str, int]:
        sentences = self.script(pack_id).sentences
        voice = Settings.load().voice
        names = set()
        if sentences:
            folder = self.library.clip_path(pack_id, sentences[0], voice).parent
            try:
                names = {n for n in os.listdir(folder) if n.endswith(".wav")}
            except OSError:
                pass
        rendered = sum(1 for s in sentences if self.library.clip_path(pack_id, s, voice).name in names)
        return {"rendered": rendered, "total": len(sentences)}

    # ---- thread ------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._cond:
                while self._focus is None and not self._stop.is_set():
                    self._cond.wait()
                if self._stop.is_set():
                    return
                target, gen = self._focus, self._focus_gen
            try:
                self._render_from(target, gen)
            except Exception:  # never let the thread die
                log.exception("render pass failed")
                with self._cond:
                    if self._focus_gen == gen:
                        self._focus = None
            with self._cond:
                if self._focus_gen == gen:
                    self._focus = None  # pass finished; idle until the next focus

    def _render_from(self, target: tuple[str, str], gen: int) -> None:
        pack_id, sentence_id = target
        sentences = self.script(pack_id).sentences
        start = next((i for i, s in enumerate(sentences) if s.id == sentence_id), 0)
        voice = Settings.load().voice
        for sentence in sentences[start:] + sentences[:start]:
            if self._stop.is_set() or self._focus_gen != gen:
                return
            if (pack_id, sentence.id) in self.failed:
                continue
            if self._cached(self.library.clip_path(pack_id, sentence, voice)):
                continue
            with self._cond:  # yield to any click waiting for the lock
                while self._urgent and not self._stop.is_set():
                    self._cond.wait(0.05)
            with self._render_lock:
                if self._stop.is_set() or self._focus_gen != gen:
                    return
                try:
                    self._render(pack_id, sentence, voice)
                except Exception:
                    log.warning("render failed for %s/%s", pack_id, sentence.id, exc_info=True)
