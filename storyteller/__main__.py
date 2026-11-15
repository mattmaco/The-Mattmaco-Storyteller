"""Command line: ``python -m storyteller serve`` and ``python -m storyteller script <pdf>``."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
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


def serve(port: int, open_browser: bool) -> None:
    import uvicorn

    from storyteller.server import create_app

    server = uvicorn.Server(uvicorn.Config(create_app(), host=HOST, port=port, log_level="info"))
    if open_browser:
        threading.Thread(
            target=_open_when_up, args=(server, f"http://{HOST}:{port}/"), daemon=True
        ).start()
    server.run()


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
    p_script = sub.add_parser("script", help="print the spoken text of every sentence")
    p_script.add_argument("pdf")
    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(args.port if args.port is not None else _default_port(), not args.no_browser)
        return 0
    return script(args.pdf)


if __name__ == "__main__":
    sys.exit(main())
