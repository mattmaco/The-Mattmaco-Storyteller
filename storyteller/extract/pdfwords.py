"""Spans, words and line joining straight from PyMuPDF's rawdict."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import pymupdf

from storyteller.model import BBox, Word


@dataclass
class RawSpan:
    text: str
    page: int  # 0-based
    bbox: BBox
    size: float
    color: int
    bold: bool
    block_no: int
    line_no: int


def _area(bbox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _union(boxes) -> BBox:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _keep_char(ch: dict) -> bool:
    c = ch["c"]
    # Whitespace only separates words; combining marks may have no advance of their own.
    return c.isspace() or unicodedata.combining(c) > 0 or _area(ch["bbox"]) > 0


def read_spans_with_chars(page: pymupdf.Page, page_no: int) -> list[tuple[RawSpan, list]]:
    """Each span paired with its (zero-area-filtered) rawdict chars, for span_words."""
    out: list[tuple[RawSpan, list]] = []
    data = page.get_text("rawdict", sort=False)
    for block_no, block in enumerate(data["blocks"]):
        if block.get("type") != 0:
            continue
        for line_no, line in enumerate(block["lines"]):
            for span in line["spans"]:
                chars = [ch for ch in span["chars"] if _keep_char(ch)]
                text = "".join(ch["c"] for ch in chars)
                if not text.strip():
                    continue
                font = span.get("font", "")
                raw = RawSpan(
                    text=text,
                    page=page_no,
                    bbox=_union([ch["bbox"] for ch in chars]),
                    size=float(span["size"]),
                    color=int(span["color"]),
                    bold="Bold" in font or bool(span["flags"] & 16),
                    block_no=block_no,
                    line_no=line_no,
                )
                out.append((raw, chars))
    return out


def read_spans(page: pymupdf.Page, page_no: int) -> list[RawSpan]:
    return [span for span, _ in read_spans_with_chars(page, page_no)]


def span_words(span: RawSpan, chars: list) -> list[Word]:
    """Split a span's chars on whitespace; each word's bbox is the union of its chars."""
    words: list[Word] = []
    cur: list[dict] = []

    def flush() -> None:
        if cur:
            solid = [ch["bbox"] for ch in cur if _area(ch["bbox"]) > 0] or [cur[0]["bbox"]]
            words.append(Word("".join(ch["c"] for ch in cur), span.page, _union(solid)))
            cur.clear()

    for ch in chars:
        if ch["c"].isspace():
            flush()
        else:
            cur.append(ch)
    flush()
    return words


def join_lines(lines: list[list[Word]]) -> list[Word]:
    """Concatenate lines of words, repairing words hyphenated across a line break."""
    out: list[Word] = []
    carry: Word | None = None  # a trailing "xxx-" word waiting for the next line's first word
    for line in lines:
        words = list(line)
        if carry is not None and words:
            nxt = words[0]
            before = carry.text[-2:-1]
            if nxt.text[:1].isalpha() and nxt.text[:1].islower() and before.isalpha() and before.islower():
                words[0] = Word(carry.text[:-1] + nxt.text, carry.page, carry.bbox)
            elif nxt.text[:1].isupper():
                words[0] = Word(carry.text + nxt.text, carry.page, carry.bbox)
            else:
                out.append(carry)
            carry = None
        elif carry is not None:
            continue  # empty line: keep waiting
        if words and words[-1].text.endswith("-") and len(words[-1].text) > 1:
            carry = words.pop()
        out.extend(words)
    if carry is not None:
        out.append(carry)
    return out
