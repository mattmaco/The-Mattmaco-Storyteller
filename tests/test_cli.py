"""CLI behaviour the Windows launcher and installer rely on."""

import http.server
import json
import socket
import threading

import pytest

from storyteller import __main__ as cli


def _serve_once(handler_cls):
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class _StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"device": "cpu", "notice": None, "packs": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _OtherHandler(_StatusHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_probe_free_port():
    assert cli.probe(_free_port()) == "free"


def test_probe_detects_running_storyteller():
    srv = _serve_once(_StatusHandler)
    try:
        assert cli.probe(srv.server_address[1]) == "storyteller"
    finally:
        srv.shutdown()


def test_probe_detects_other_app():
    srv = _serve_once(_OtherHandler)
    try:
        assert cli.probe(srv.server_address[1]) == "other"
    finally:
        srv.shutdown()


def test_serve_reuses_running_instance(monkeypatch, capsys):
    srv = _serve_once(_StatusHandler)
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    try:
        port = srv.server_address[1]
        assert cli.main(["serve", "--port", str(port)]) == 0
    finally:
        srv.shutdown()
    assert opened == [f"http://127.0.0.1:{port}/"]
    assert "already running" in capsys.readouterr().out


def test_serve_reports_port_taken(capsys):
    srv = _serve_once(_OtherHandler)
    try:
        assert cli.main(["serve", "--no-browser", "--port", str(srv.server_address[1])]) == 1
    finally:
        srv.shutdown()
    err = capsys.readouterr().err
    assert "in use" in err and "STORYTELLER_PORT" in err


def test_setup_with_stub_voice(capsys):
    assert cli.main(["setup"]) == 0
    out = capsys.readouterr().out
    assert "Voice ready" in out


def test_setup_reports_voice_failure(monkeypatch, capsys):
    import storyteller.voice as voice

    def boom():
        raise OSError("no network")

    monkeypatch.setattr(voice, "get_backend", boom)
    assert cli.main(["setup"]) == 1
    assert "no network" in capsys.readouterr().err


def test_where_prints_data_dir(tmp_path, capsys):
    assert cli.main(["where"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path)


@pytest.mark.parametrize("argv", [["serve", "--no-browser"]])
def test_serve_prints_how_to_stop(monkeypatch, capsys, argv):
    import uvicorn

    class FakeServer:
        started = False

        def __init__(self, config):
            pass

        def run(self):
            pass

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setenv("STORYTELLER_PORT", str(_free_port()))
    assert cli.main(argv) == 0
    assert "Close this window" in capsys.readouterr().out


def test_setup_prefetches_every_preview_voice(monkeypatch, capsys):
    import storyteller.voice as voice

    seen = {}

    class Fake:
        device = "cuda"
        notice = None

        def prepare(self, voices):
            seen["voices"] = list(voices)

        def synth(self, words, name):
            seen["synth"] = name

    monkeypatch.setattr(voice, "get_backend", Fake)
    assert cli.main(["setup"]) == 0
    assert seen["voices"][0] == "af_heart" and set(voice.PREVIEW_VOICES) <= set(seen["voices"])
    assert seen["synth"] == "af_heart"
    assert "graphics card" in capsys.readouterr().out
