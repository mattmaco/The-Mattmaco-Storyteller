"""Command line: ``python -m storyteller serve | setup | where | script <pdf>``."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _default_port() -> int:
    try:
        return int(os.environ.get("STORYTELLER_PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


def _open_when_up(server, url: str, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if getattr(server, "started", False):
            webbrowser.open(url)
            return
        time.sleep(0.1)


def probe(port: int) -> str:
    """What is listening on 127.0.0.1:port: ``"free"``, ``"storyteller"`` or ``"other"``."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/status", timeout=2) as resp:
            body = json.loads(resp.read())
        return "storyteller" if isinstance(body, dict) and "packs" in body else "other"
    except urllib.error.HTTPError:
        return "other"
    except (urllib.error.URLError, OSError, ValueError):
        pass
    # Nothing answered HTTP; something may still hold the port.
    import socket

    with socket.socket() as s:
        s.settimeout(1)
        return "other" if s.connect_ex((HOST, port)) == 0 else "free"


def serve(port: int, open_browser: bool) -> int:
    url = f"http://{HOST}:{port}/"
    found = probe(port)
    if found == "storyteller":
        # A second launch (double-clicked shortcut): reuse the running reader.
        print(f"Storyteller is already running at {url}")
        if open_browser:
            webbrowser.open(url)
        return 0
    if found == "other":
        print(
            f"Port {port} is in use by another program, so Storyteller can't start.\n"
            "Close that program, or set STORYTELLER_PORT to a free port (for example 8766) and try again.",
            file=sys.stderr,
        )
        return 1

    import uvicorn

    from storyteller.server import create_app

    server = uvicorn.Server(uvicorn.Config(create_app(), host=HOST, port=port, log_level="warning"))
    if open_browser:
        threading.Thread(target=_open_when_up, args=(server, url), daemon=True).start()
    print(f"Storyteller is running at {url}")
    print("Close this window to stop it.")
    server.run()
    return 0


def setup() -> int:
    """Download the voice model (first run) and say which device it uses."""
    from storyteller import voice
    from storyteller.settings import Settings

    name = Settings.load().voice
    print("Loading the voice. The first time, this downloads about 350 MB...")
    try:
        backend = voice.get_backend()
        prepare = getattr(backend, "prepare", None)
        if prepare is not None:
            prepare(dict.fromkeys((name, *voice.PREVIEW_VOICES)))
        backend.synth(["Ready."], name)
    except Exception as e:  # report any failure in plain words; the installer stops on exit 1
        print(f"The voice could not be set up: {e}", file=sys.stderr)
        print("Check your internet connection, then run install.bat again.", file=sys.stderr)
        return 1
    device = getattr(backend, "device", "cpu")
    where = "the graphics card (fast)" if device == "cuda" else "the processor"
    print(f"Voice ready. It runs on {where}.")
    notice = getattr(backend, "notice", None)
    if notice:
        print(f"Note: {notice}.")
    return 0


def script(pdf: str) -> int:
    from pathlib import Path

    from storyteller.extract import NoTextLayerError, extract
    from storyteller.settings import Settings
    from storyteller.speech import build_script
    from storyteller.speech.symbols import Rules

    try:
        doc = extract(Path(pdf))
    except NoTextLayerError:
        print("This PDF has no text layer (it looks scanned). Storyteller can't read it yet.", file=sys.stderr)
        return 1
    result = build_script(doc, "cli", Settings().script_options(), Rules.load())
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8")
    for s in result.sentences:
        print(f"{s.id}\t{s.spoken_text}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="storyteller")
    sub = parser.add_subparsers(dest="command", required=True)
    p_serve = sub.add_parser("serve", help="start the reader on 127.0.0.1")
    p_serve.add_argument("--port", type=int, default=None, help="default: $STORYTELLER_PORT or 8765")
    p_serve.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    sub.add_parser("setup", help="download the voice model and check it works")
    sub.add_parser("where", help="print the folder where packs and settings are kept")
    p_script = sub.add_parser("script", help="print the spoken text of every sentence")
    p_script.add_argument("pdf")
    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(args.port if args.port is not None else _default_port(), not args.no_browser)
    if args.command == "setup":
        return setup()
    if args.command == "where":
        from storyteller.settings import home

        print(home())
        return 0
    return script(args.pdf)


if __name__ == "__main__":
    sys.exit(main())
