"""Table regions and cell words, plus the document outline.

`page.find_tables()` locates tables reliably, but its `extract()` text is
garbled by ligatures and lost spaces. Cell words are therefore rebuilt from
the page's own chars: a char belongs to the cell its centre lies in, so a
span that crosses cells splits correctly.
"""
from __future__ import annotations

import pymupdf

from storyteller.extract.studypack import CITE_COLOURS, _strip_inline_cites
from storyteller.extract.pdfwords import RawSpan, join_lines, read_spans_with_chars, span_words
from storyteller.model import BBox, OutlineEntry, Table, Word

LINE_TOLERANCE = 0.5  # fraction of a span's height within which two segments share a line


def _in_cell(bbox, cell: BBox) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return cell[0] <= cx <= cell[2] and cell[1] <= cy <= cell[3]


def _cell_words(pairs: list[tuple[RawSpan, list]], cell: BBox) -> list[Word]:
    """Words of the chars centred in `cell`, cites dropped, in reading order."""
    segments: list[tuple[RawSpan, list]] = []
    for span, chars in pairs:
        if span.color in CITE_COLOURS or not _overlaps(span.bbox, cell):
            continue
        inside = [ch for ch in chars if _in_cell(ch["bbox"], cell)]
        for seg, cut_before in _strip_inline_cites(inside):  # a cite printed in body colour
            if cut_before:
                seg = [{"c": " ", "bbox": seg[0]["bbox"]}, *seg]
            segments.append((span, seg))
    if not segments:
        return []

    segments.sort(key=lambda s: (s[0].bbox[1] + s[0].bbox[3]) / 2)
    lines: list[list[tuple[RawSpan, list]]] = []
    for seg in segments:
        mid = (seg[0].bbox[1] + seg[0].bbox[3]) / 2
        last = lines[-1][0][0].bbox if lines else None
        if last is not None and abs(mid - (last[1] + last[3]) / 2) <= LINE_TOLERANCE * (last[3] - last[1]):
            lines[-1].append(seg)
        else:
            lines.append([seg])

    line_words: list[list[Word]] = []
    for line in lines:
        line.sort(key=lambda s: s[0].bbox[0])
        chars: list[dict] = []
        prev: RawSpan | None = None
        for span, span_chars in line:
            if prev is not None and span.bbox[0] - prev.bbox[2] > 0.25 * min(span.size, prev.size):
                chars.append({"c": " ", "bbox": span.bbox})
            chars.extend(span_chars)
            prev = span
        line_words.append(span_words(line[0][0], chars))
    return join_lines(line_words)


def _overlaps(a: BBox, b: BBox) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def find_tables(
    page: pymupdf.Page, page_no: int, spans: list[tuple[RawSpan, list]] | None = None
) -> list[tuple[BBox, Table]]:
    """Tables of one page as (region, Table); row 0 is the header.

    `spans` are the page's (RawSpan, chars) pairs from `read_spans_with_chars`;
    pass them to avoid reading the page twice. A cell with no text is `[]`.
    """
    found = page.find_tables().tables
    if not found:
        return []
    pairs = spans if spans is not None else read_spans_with_chars(page, page_no)
    out: list[tuple[BBox, Table]] = []
    for t in found:
        grid: list[list[list[Word]]] = []
        for row in t.rows:
            grid.append([_cell_words(pairs, tuple(c)) if c is not None else [] for c in row.cells])
        if not grid:
            continue
        out.append((tuple(t.bbox), Table(header=grid[0], rows=grid[1:])))
    return out


def build_outline(doc: pymupdf.Document) -> list[OutlineEntry]:
    entries: list[OutlineEntry] = []
    for level, title, page, dest in doc.get_toc(simple=False):
        point = dest.get("to") if isinstance(dest, dict) else None
        y = float(point.y) if point is not None else 0.0
        entries.append(OutlineEntry(level=level, title=title, page=max(page - 1, 0), y=y))
    return entries
