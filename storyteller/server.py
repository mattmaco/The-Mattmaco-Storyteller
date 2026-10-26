"""FastAPI app: library, scripts, on-demand clips, settings and render status."""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from storyteller.extract import NoTextLayerError
from storyteller.library import Library
from storyteller.settings import VOICE_RE, Settings
from storyteller.voice import get_backend
from storyteller.worker import RenderWorker

__all__ = ["create_app"]

log = logging.getLogger(__name__)

WEB = Path(__file__).parent / "web"
NO_TEXT_MESSAGE = "This PDF has no text layer (it looks scanned). Storyteller can't read it yet."
_CLIP_NAME = re.compile(r"[0-9a-f]{16}\Z")


class SentenceRef(BaseModel):
    sentence_id: str


class SkipBody(BaseModel):
    pattern: str


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not found")


def _validate_settings(partial: dict) -> dict:
    """Return the values to store; raise ValueError for unknown fields or invalid values."""
    current = Settings.load()
    names = set(current.__dict__)
    unknown = set(partial) - names
    if unknown:
        raise ValueError(f"unknown settings: {sorted(unknown)}")
    out = {}
    for key, value in partial.items():
        if key in ("pauses", "read_boxes"):  # partial dicts merge into the stored one
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be an object")
            value = {**getattr(current, key), **value}
        if key == "speed" and isinstance(value, bool):
            raise ValueError("speed must be a number")
        # Settings drops values it cannot accept; anything that does not survive is invalid.
        if getattr(Settings._from_saved({key: value}), key) != value:
            raise ValueError(f"invalid value for {key}")
        out[key] = value
    return out


def create_app(library: Library | None = None, backend=None) -> FastAPI:
    library = library or Library()
    backend = backend or get_backend()
    worker = RenderWorker(library, backend)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title="Storyteller", lifespan=lifespan)
    app.state.library, app.state.worker, app.state.backend = library, worker, backend

    def sentence_or_404(pack_id: str, sentence_id: str):
        try:
            return worker.sentence(pack_id, sentence_id)
        except KeyError:
            raise _not_found() from None

    # ---- pages -------------------------------------------------------------

    def page(name: str) -> FileResponse:
        path = WEB / name
        if not path.is_file():
            raise _not_found()
        return FileResponse(path, media_type="text/html")

    @app.get("/", include_in_schema=False)
    def index():
        return page("library.html")

    @app.get("/read/{pack_id}", include_in_schema=False)
    def reader(pack_id: str):
        return page("reader.html")

    # ---- packs -------------------------------------------------------------

    @app.post("/api/packs")
    def add_pack(file: UploadFile = File(...)):
        data = file.file.read()
        try:
            return asdict(library.add_pdf(data, file.filename or "document.pdf"))
        except NoTextLayerError:
            return JSONResponse(
                {"error": "no_text_layer", "message": NO_TEXT_MESSAGE}, status_code=422
            )
        except (ValueError, RuntimeError):  # PyMuPDF's FileDataError is a RuntimeError
            log.warning("rejected upload %r", file.filename, exc_info=True)
            return JSONResponse(
                {"error": "invalid_pdf", "message": "That file could not be read as a PDF."},
                status_code=400,
            )

    @app.get("/api/packs")
    def list_packs():
        return [asdict(p) for p in library.list()]

    @app.get("/api/packs/{pack_id}/pdf")
    def pack_pdf(pack_id: str):
        try:
            return FileResponse(library.pdf_path(pack_id), media_type="application/pdf")
        except KeyError:
            raise _not_found() from None

    @app.get("/api/packs/{pack_id}/script")
    def pack_script(pack_id: str):
        try:
            return worker.script(pack_id).to_dict()
        except KeyError:
            raise _not_found() from None

    # ---- clips -------------------------------------------------------------

    @app.get("/api/packs/{pack_id}/clip/{sentence_id}")
    def clip(pack_id: str, sentence_id: str):
        sentence_or_404(pack_id, sentence_id)
        try:
            path = worker.render_now(pack_id, sentence_id)
        except KeyError:
            raise _not_found() from None
        except Exception:
            log.warning("synthesis failed for %s/%s", pack_id, sentence_id, exc_info=True)
            return JSONResponse({"error": "synth_failed"}, status_code=500)
        meta = library.load_clip_meta(path)
        if meta is None:
            return JSONResponse({"error": "synth_failed"}, status_code=500)
        return {
            "url": f"/api/packs/{pack_id}/audio/{path.parent.name}/{path.stem}.wav",
            "duration": meta["duration"],
            "words": meta["words"],
        }

    @app.get("/api/packs/{pack_id}/audio/{voice}/{name}.wav")
    def audio(pack_id: str, voice: str, name: str):
        if not VOICE_RE.match(voice) or not _CLIP_NAME.match(name):
            raise _not_found()
        try:
            folder = library.pdf_path(pack_id).parent / "clips" / voice
        except KeyError:
            raise _not_found() from None
        path = folder / f"{name}.wav"
        if not path.is_file():
            raise _not_found()
        return FileResponse(path, media_type="audio/wav")

    # ---- cursor, position, skip --------------------------------------------

    @app.post("/api/packs/{pack_id}/focus", status_code=204)
    def focus(pack_id: str, body: SentenceRef):
        sentence_or_404(pack_id, body.sentence_id)
        worker.focus(pack_id, body.sentence_id)
        return Response(status_code=204)

    @app.put("/api/packs/{pack_id}/position", status_code=204)
    def position(pack_id: str, body: SentenceRef):
        sentence_or_404(pack_id, body.sentence_id)
        library.set_position(pack_id, body.sentence_id)
        return Response(status_code=204)

    @app.post("/api/packs/{pack_id}/skip")
    def skip(pack_id: str, body: SkipBody):
        try:
            if worker.script(pack_id).profile == "studypack":
                return JSONResponse(
                    {"error": "not_supported", "message": "Skip patterns apply to best-effort packs only."},
                    status_code=400,
                )
            library.add_skip_pattern(pack_id, body.pattern)
            return worker.script(pack_id).to_dict()
        except KeyError:
            raise _not_found() from None
        except ValueError as e:
            return JSONResponse({"error": "invalid_pattern", "message": str(e)}, status_code=400)

    # ---- settings and status -----------------------------------------------

    @app.get("/api/settings")
    def get_settings():
        return Settings.load().__dict__

    @app.put("/api/settings")
    def put_settings(partial: dict):
        try:
            return Settings.update(**_validate_settings(partial)).__dict__
        except ValueError as e:
            return JSONResponse({"error": "invalid_settings", "message": str(e)}, status_code=400)

    @app.get("/api/status")
    def status():
        packs = {}
        for info in library.list():
            try:
                packs[info.id] = worker.status(info.id)
            except KeyError:
                continue
        return {"device": backend.device, "notice": backend.notice, "packs": packs}

    app.mount("/web", StaticFiles(directory=WEB), name="web")
    return app
