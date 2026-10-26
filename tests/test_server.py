import subprocess
import sys
import threading
import time
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from storyteller.library import Library
from storyteller.server import create_app
from storyteller.voice import get_backend

ROOT = Path(__file__).parent.parent
NO_TEXT = (
    "This PDF has no text layer (it looks scanned). Storyteller can't read it yet."
)


def _worker_threads():
    return [t for t in threading.enumerate() if t.name == "storyteller-render" and t.is_alive()]


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c
    assert not _worker_threads()


def _upload(client, path: Path):
    with open(path, "rb") as f:
        return client.post("/api/packs", files={"file": (path.name, f, "application/pdf")})


@pytest.fixture
def pack(client, mini_pdf):
    r = _upload(client, mini_pdf)
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_and_list(client, pack, mini_pdf):
    assert pack["filename"] == "studypack_mini.pdf"
    assert pack["total"] > 0
    assert [p["id"] for p in client.get("/api/packs").json()] == [pack["id"]]
    pdf = client.get(f"/api/packs/{pack['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf.content == mini_pdf.read_bytes()


def test_upload_scanned_422(client, tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.set_rect(pix.irect, (200, 200, 200))
    page.insert_image(page.rect, pixmap=pix)
    scanned = tmp_path / "scan.pdf"
    doc.save(scanned)
    r = _upload(client, scanned)
    assert r.status_code == 422
    assert r.json() == {"error": "no_text_layer", "message": NO_TEXT}


def test_upload_garbage_400(client, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    assert _upload(client, bad).status_code == 400


def test_script_endpoint(client, pack):
    script = client.get(f"/api/packs/{pack['id']}/script").json()
    ids = [s["id"] for s in script["sentences"]]
    assert ids == [f"s{n:05d}" for n in range(len(ids))] and ids


def test_unknown_pack_and_sentence_404(client, pack):
    assert client.get("/api/packs/0123456789abcdef/script").status_code == 404
    assert client.get("/api/packs/..%2f..%2fetc/script").status_code == 404
    assert client.get(f"/api/packs/{pack['id']}/clip/s99999").status_code == 404
    assert client.get(f"/api/packs/{pack['id']}/audio/bad%2Fvoice/{'0' * 16}.wav").status_code == 404
    assert client.get(f"/api/packs/{pack['id']}/audio/stub/..%2f..%2fsource.wav").status_code == 404
    assert client.post(f"/api/packs/{pack['id']}/focus", json={"sentence_id": "nope"}).status_code == 404
    assert client.put(f"/api/packs/{pack['id']}/position", json={"sentence_id": "nope"}).status_code == 404


def test_clip_renders_on_demand(client, pack):
    script = client.get(f"/api/packs/{pack['id']}/script").json()
    sentence = script["sentences"][1]
    r = client.get(f"/api/packs/{pack['id']}/clip/{sentence['id']}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["words"]) == len(sentence["spoken"])
    assert body["duration"] > 0
    assert body["url"].startswith(f"/api/packs/{pack['id']}/audio/af_heart/")
    audio = client.get(body["url"])
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert audio.content[:4] == b"RIFF"


def test_clip_uses_current_voice(client, pack):
    client.put("/api/settings", json={"voice": "am_michael"})
    body = client.get(f"/api/packs/{pack['id']}/clip/s00000").json()
    assert "/audio/am_michael/" in body["url"]


def test_focus_then_status_progresses(client, pack):
    assert client.post(f"/api/packs/{pack['id']}/focus", json={"sentence_id": "s00002"}).status_code == 204
    deadline = time.time() + 5
    status = {}
    while time.time() < deadline:
        status = client.get("/api/status").json()
        if status["packs"][pack["id"]]["rendered"] > 0:
            break
        time.sleep(0.05)
    assert status["packs"][pack["id"]]["rendered"] > 0
    assert status["packs"][pack["id"]]["total"] == pack["total"]
    assert status["device"] == "stub"
    assert status["notice"] is None


def test_worker_renders_everything_and_wraps(client, pack):
    client.post(f"/api/packs/{pack['id']}/focus", json={"sentence_id": "s00003"})
    deadline = time.time() + 20
    while time.time() < deadline:
        st = client.get("/api/status").json()["packs"][pack["id"]]
        if st["rendered"] == st["total"]:
            break
        time.sleep(0.05)
    assert st["rendered"] == st["total"]


class FlakyBackend:
    def __init__(self, inner, bad_text):
        self.inner, self.bad_text = inner, bad_text
        self.device, self.notice = inner.device, inner.notice

    def synth(self, words, voice):
        if " ".join(words) == self.bad_text:
            raise RuntimeError("boom")
        return self.inner.synth(words, voice)


def test_failed_sentence_returns_500_and_worker_survives(mini_pdf):
    library = Library()
    info = library.add_pdf(mini_pdf.read_bytes(), mini_pdf.name)
    sentences = library.script(info.id).sentences
    bad = sentences[0]
    backend = FlakyBackend(get_backend(), bad.spoken_text)
    app = create_app(library, backend)
    with TestClient(app) as c:
        r = c.get(f"/api/packs/{info.id}/clip/{bad.id}")
        assert r.status_code == 500
        assert r.json() == {"error": "synth_failed"}
        assert c.get(f"/api/packs/{info.id}/clip/{sentences[1].id}").status_code == 200
        assert library.clip_path(info.id, bad, 'af_heart') in app.state.worker.failed
        # the worker skips failed sentences (every sentence with the same text) and renders the rest
        n_bad = sum(1 for s in sentences if s.spoken_text == bad.spoken_text)
        c.post(f"/api/packs/{info.id}/focus", json={"sentence_id": bad.id})
        deadline = time.time() + 20
        while time.time() < deadline:
            st = c.get("/api/status").json()["packs"][info.id]
            if st["rendered"] >= st["total"] - n_bad:
                break
            time.sleep(0.05)
        assert st["rendered"] >= st["total"] - n_bad
        assert c.get(f"/api/packs/{info.id}/clip/{bad.id}").status_code == 500  # explicit retry still tries
    assert not _worker_threads()


def test_same_clip_never_synthesised_twice(mini_pdf):
    library = Library()
    info = library.add_pdf(mini_pdf.read_bytes(), mini_pdf.name)
    sid = library.script(info.id).sentences[0].id
    inner = get_backend()
    calls = []

    class Slow:
        device, notice = inner.device, inner.notice

        def synth(self, words, voice):
            calls.append(words)
            time.sleep(0.2)
            return inner.synth(words, voice)

    app = create_app(library, Slow())
    with TestClient(app) as c:
        results = []
        ts = [
            threading.Thread(target=lambda: results.append(c.get(f"/api/packs/{info.id}/clip/{sid}").status_code))
            for _ in range(4)
        ]
        [t.start() for t in ts]
        [t.join() for t in ts]
    assert results == [200] * 4
    assert len(calls) == 1


def test_position_persists(client, pack):
    assert client.put(f"/api/packs/{pack['id']}/position", json={"sentence_id": "s00004"}).status_code == 204
    assert client.get("/api/packs").json()[0]["position"] == "s00004"


def test_skip_rejected_for_study_packs(client, pack):
    r = client.post(f"/api/packs/{pack['id']}/skip", json={"pattern": "x"})
    assert r.status_code == 400


def test_skip_on_besteffort_pack(client, plain_pdf):
    info = _upload(client, plain_pdf).json()
    before = client.get(f"/api/packs/{info['id']}/script").json()
    first = before["sentences"][0]["spoken"][0]["text"]
    r = client.post(f"/api/packs/{info['id']}/skip", json={"pattern": f"^{first}"})
    assert r.status_code == 200
    assert len(r.json()["sentences"]) <= len(before["sentences"])
    assert client.post(f"/api/packs/{info['id']}/skip", json={"pattern": "("}).status_code == 400


def test_settings_partial_update(client):
    base = client.get("/api/settings").json()
    assert base["voice"] == "af_heart"
    r = client.put("/api/settings", json={"speed": 1.25})
    assert r.status_code == 200
    assert r.json()["speed"] == 1.25 and r.json()["voice"] == "af_heart"
    r = client.put("/api/settings", json={"pauses": {"block": 700}})
    assert r.json()["pauses"] == {"sentence": 250, "block": 700, "section": 1000}
    assert client.get("/api/settings").json()["speed"] == 1.25


@pytest.mark.parametrize(
    "bad",
    [
        {"nonsense": 1},
        {"speed": 5},
        {"speed": "fast"},
        {"speed": True},
        {"voice": "../x"},
        {"pauses": {"nope": 1}},
        {"highlight_word": "yes"},
    ],
)
def test_settings_invalid_400(client, bad):
    assert client.put("/api/settings", json=bad).status_code == 400
    assert client.get("/api/settings").json()["speed"] == 1.0


def test_pages_served(client, pack):
    assert client.get("/read/0123456789abcdef").status_code == 404
    assert client.get("/read/..%2fx").status_code == 404
    for url in ("/", "/web/library.html", f"/read/{pack['id']}"):
        r = client.get(url)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_cli_script_output():
    out = subprocess.run(
        [sys.executable, "-m", "storyteller", "script", str(ROOT / "tests/fixtures/studypack_mini.pdf")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    lines = out.splitlines()
    assert all(ln.split("\t")[0].startswith("s") and "\t" in ln for ln in lines)
    assert "Entry:" in out
    assert "Page 1 of 3" not in out


def test_cli_serve_binds_loopback(monkeypatch):
    import uvicorn

    from storyteller import __main__ as cli

    seen = {}

    class FakeServer:
        started = False

        def __init__(self, config):
            seen["config"] = config

        def run(self):
            seen["ran"] = True

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setenv("STORYTELLER_PORT", "9123")
    cli.main(["serve", "--no-browser"])
    assert seen["ran"] and seen["config"].host == "127.0.0.1" and seen["config"].port == 9123
    cli.main(["serve", "--no-browser", "--port", "9555"])
    assert seen["config"].port == 9555


def test_concurrent_dict_puts_do_not_lose_updates(client):
    keys = ["sentence", "block", "section"]
    def put(k):
        for i in range(20):
            assert client.put("/api/settings", json={"pauses": {k: 100 + i}}).status_code == 200
    ts = [threading.Thread(target=put, args=(k,)) for k in keys]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert client.get("/api/settings").json()["pauses"] == {k: 119 for k in keys}


def test_pronunciations_replace_on_put(client):
    client.put("/api/settings", json={"pronunciations": {"a": "b", "c": "d"}})
    r = client.put("/api/settings", json={"pronunciations": {"c": "d"}})
    assert r.json()["pronunciations"] == {"c": "d"}
    assert client.get("/api/settings").json()["pronunciations"] == {"c": "d"}


def test_worker_follows_voice_change(mini_pdf):
    library = Library()
    info = library.add_pdf(mini_pdf.read_bytes(), mini_pdf.name)
    app = create_app(library)
    with TestClient(app) as c:
        c.put("/api/settings", json={"voice": "bf_emma"})
        c.post(f"/api/packs/{info.id}/focus", json={"sentence_id": "s00000"})
        deadline = time.time() + 10
        while time.time() < deadline and c.get("/api/status").json()["packs"][info.id]["rendered"] == 0:
            time.sleep(0.05)
        assert c.get("/api/status").json()["packs"][info.id]["rendered"] > 0
    assert any((library.pdf_path(info.id).parent / "clips" / "bf_emma").glob("*.wav"))
