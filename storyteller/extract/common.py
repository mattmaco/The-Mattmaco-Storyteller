"""Helpers shared by the study-pack and table extractors."""
from __future__ import annotations

import re

from storyteller.model import BBox, Word

CITE_COLOURS = {0x5C6774, 0x55606C}  # slide cites
INLINE_CITE_RE = re.compile(r"\s*\((?:P\d|Lk|SS) \d[^()]*\)")  # a cite printed in a label's own colour
PUNCT_START = tuple(".,;:?!)")


def _union(boxes) -> BBox:
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def strip_inline_cites(chars: list) -> list[tuple[list, bool]]:
    """Split a span's chars around cite-shaped text; True marks a segment that follows a cut."""
    text = "".join(ch["c"] for ch in chars)
    segments: list[tuple[list, bool]] = []
    pos, cut = 0, False
    for m in INLINE_CITE_RE.finditer(text):
        if m.start() > pos:
            segments.append((chars[pos : m.start()], cut))
        pos, cut = m.end(), True
    if pos < len(chars):
        segments.append((chars[pos:], cut))
    return [(seg, c) for seg, c in segments if "".join(ch["c"] for ch in seg).strip()]


def collapse_punct(words: list[Word]) -> list[Word]:
    out: list[Word] = []
    for w in words:
        if out and w.text.startswith(PUNCT_START):
            prev = out[-1]
            text = w.text[1:] if w.text.startswith(".") and prev.text.endswith(".") else w.text  # no ".."
            out[-1] = Word(prev.text + text, prev.page, _union([prev.bbox, w.bbox]))
        else:
            out.append(w)
    return out
