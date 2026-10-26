"""Download pdf.js (pdfjs-dist) into storyteller/web/vendor/pdfjs/ (stdlib only)."""
from __future__ import annotations

import io
import tarfile
import urllib.request
from pathlib import Path

VERSION = "4.10.38"
URL = f"https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-{VERSION}.tgz"
WANTED = {
    "package/build/pdf.mjs": "pdf.mjs",
    "package/build/pdf.worker.mjs": "pdf.worker.mjs",
    "package/LICENSE": "LICENSE",
}
DEST = Path(__file__).resolve().parent.parent / "storyteller" / "web" / "vendor" / "pdfjs"


def main() -> None:
    with urllib.request.urlopen(URL, timeout=120) as resp:
        data = resp.read()
    DEST.mkdir(parents=True, exist_ok=True)
    dest_root = DEST.resolve()
    found = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            target_name = WANTED.get(member.name)
            if target_name is None:
                continue
            if not member.isfile():
                raise SystemExit(f"unexpected non-file member {member.name}")
            target = (DEST / target_name).resolve()
            if target.parent != dest_root:  # path-traversal guard
                raise SystemExit(f"refusing to write outside {DEST}: {target}")
            src = tar.extractfile(member)
            assert src is not None
            target.write_bytes(src.read())
            found.add(member.name)
    missing = set(WANTED) - found
    if missing:
        raise SystemExit(f"missing from archive: {sorted(missing)}")
    print(f"pdfjs-dist {VERSION} -> {DEST}")


if __name__ == "__main__":
    main()
