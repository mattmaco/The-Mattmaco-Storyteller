"""Best-effort extraction for any PDF, plus the top-level `extract()`."""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from pathlib import Path

import pymupdf

from storyteller.extract.common import collapse_punct
from storyteller.extract.pdfwords import RawSpan, join_lines, read_spans_with_chars, span_words
from storyteller.extract.studypack import is_studypack, studypack_blocks
from storyteller.extract.tables import build_outline, find_tables
from storyteller.model import BBox, Block, Document, OutlineEntry, Table, Word

CITE_RES = [
    re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]"),
    re.compile(r"\([A-Z][A-Za-z]+(?: et al\.)?,? \d{4}[a-z]?\)"),
]
EDGE_FRACTION = 0.08  # top/bottom band searched for running headers and footers
MIN_WORDS = 20
HEADING2_RATIO = 1.25
HEADING3_RATIO = 1.1


class NoTextLayerError(Exception):
    """The PDF has (almost) no extractable text, e.g. a scan."""


def _norm(text: str) -> str:
    return re.sub(r"\d", "#", " ".join(text.split()))


def _union(boxes) -> BBox:
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _centre_in(bbox: BBox, rect: BBox) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]


class _Line:
    def __init__(self) -> None:
        self.parts: list[tuple[RawSpan, list]] = []

    @property
    def text(self) -> str:
        return " ".join("".join(ch["c"] for ch in chars).strip() for _, chars in self.parts)

    @property
    def bbox(self) -> BBox:
        return _union(s.bbox for s, _ in self.parts)

    def words(self) -> list[Word]:
        return [w for s, chars in self.parts for w in span_words(s, chars)]


def _page_lines(pairs: list[tuple[RawSpan, list]], tables: list[BBox]) -> dict[int, list[_Line]]:
    """Lines grouped by PyMuPDF block (in sorted order), table text left out."""
    blocks: dict[int, dict[int, _Line]] = defaultdict(dict)
    for span, chars in pairs:
        if any(_centre_in(span.bbox, r) for r in tables):
            continue
        blocks[span.block_no].setdefault(span.line_no, _Line()).parts.append((span, chars))
    return {b: [lines[n] for n in sorted(lines)] for b, lines in blocks.items()}


def _running_edges(page_lines: list[list[_Line]], heights: list[float]) -> set[str]:
    """Normalised texts seen in the top or bottom band on at least half of the pages."""
    pages_seen: dict[str, set[int]] = defaultdict(set)
    for pno, (lines, h) in enumerate(zip(page_lines, heights)):
        for line in lines:
            _, y0, _, y1 = line.bbox
            if y1 <= h * EDGE_FRACTION or y0 >= h * (1 - EDGE_FRACTION):
                pages_seen[_norm(line.text)].add(pno)
    need = max(2, -(-len(page_lines) // 2))
    return {t for t, seen in pages_seen.items() if t and len(seen) >= need}


def _strip_cites(words: list[Word]) -> list[Word]:
    """Remove cite text from a block's words, cutting across word boundaries."""
    text = " ".join(w.text for w in words)
    mask = [False] * len(text)
    for rx in CITE_RES:
        for m in rx.finditer(text):
            mask[m.start() : m.end()] = [True] * (m.end() - m.start())
    if not any(mask):
        return words
    out: list[Word] = []
    pos = 0
    for w in words:
        kept = "".join(c for c, gone in zip(w.text, mask[pos : pos + len(w.text)]) if not gone)
        pos += len(w.text) + 1
        if kept:
            out.append(Word(kept, w.page, w.bbox))
    return out


def _reading_order(items: list[tuple[BBox, Block]], page_width: float) -> list[Block]:
    """Top-to-bottom order, except that a two-column page reads left column then right.

    A page counts as two-column when at least two blocks sit wholly left of the page
    middle and at least two wholly right of it. Blocks straddling the middle (titles,
    full-width tables) stay in place and split the page into independent bands.
    """
    mid = page_width / 2
    items = sorted(items, key=lambda it: it[0][1])
    left = [it for it in items if it[0][2] <= mid + 5]
    right = [it for it in items if it[0][0] >= mid - 5]
    if len(left) < 2 or len(right) < 2:
        return [b for _, b in items]
    out: list[Block] = []
    band_l: list[Block] = []
    band_r: list[Block] = []

    def flush() -> None:
        out.extend(band_l + band_r)
        band_l.clear()
        band_r.clear()

    for box, b in items:
        if box[2] <= mid + 5:
            band_l.append(b)
        elif box[0] >= mid - 5:
            band_r.append(b)
        else:
            flush()
            out.append(b)
    flush()
    return out


def _role(sizes: list[tuple[float, bool, int]], body: float) -> str:
    """Role of a block from its (size, bold, nchars) spans against the document body size."""
    total = sum(n for _, _, n in sizes) or 1
    size = sum(s * n for s, _, n in sizes) / total
    bold = all(b for _, b, _ in sizes)
    if size >= HEADING2_RATIO * body:
        return "heading2"
    if bold and size >= HEADING3_RATIO * body:
        return "heading3"
    return "body"


def besteffort_blocks(doc: pymupdf.Document, skip_patterns: list[str] | None = None) -> list[Block]:
    skips = [re.compile(p) for p in (skip_patterns or [])]
    pairs_by_page: list[list[tuple[RawSpan, list]]] = []
    tables_by_page: list[list[tuple[BBox, Table]]] = []
    for pno, page in enumerate(doc):
        pairs = read_spans_with_chars(page, pno, sort=True)
        pairs_by_page.append(pairs)
        tables_by_page.append(find_tables(page, pno, pairs))
    lines_by_page = [
        _page_lines(pairs, [r for r, _ in tables]) for pairs, tables in zip(pairs_by_page, tables_by_page)
    ]
    flat = [[ln for b in sorted(blocks) for ln in blocks[b]] for blocks in lines_by_page]
    edges = _running_edges(flat, [p.rect.height for p in doc])

    sizes = [s.size for pairs in pairs_by_page for s, chars in pairs for c in chars if not c["c"].isspace()]
    body = statistics.median(sizes) if sizes else 0.0

    blocks: list[Block] = []
    for pno, page in enumerate(doc):
        h = page.rect.height
        made: list[tuple[BBox, Block]] = []
        for _, lines in sorted(lines_by_page[pno].items()):
            kept = [
                ln for ln in lines
                if not (_norm(ln.text) in edges and (ln.bbox[3] <= h * EDGE_FRACTION or ln.bbox[1] >= h * (1 - EDGE_FRACTION)))
            ]
            if not kept:
                continue
            words = collapse_punct(_strip_cites(join_lines([ln.words() for ln in kept])))
            if not words or any(rx.search(" ".join(w.text for w in words)) for rx in skips):
                continue
            spans = [(s.size, s.bold, sum(1 for c in chars if not c["c"].isspace())) for ln in kept for s, chars in ln.parts]
            made.append((_union(ln.bbox for ln in kept), Block("", _role(spans, body), words, pno)))
        for rect, table in tables_by_page[pno]:
            cells = list(table.header) + [c for row in table.rows for c in row]
            words = [w for c in cells for w in c]
            if words:
                made.append((rect, Block("", "table", words, pno, table=table)))
        for n, b in enumerate(_reading_order(made, page.rect.width)):
            b.id = f"b{pno:03d}_{n:03d}"
            blocks.append(b)
    return blocks


def _heading_outline(blocks: list[Block]) -> list[OutlineEntry]:
    return [
        OutlineEntry(level=2, title=" ".join(w.text for w in b.words), page=b.page, y=min(w.bbox[1] for w in b.words))
        for b in blocks
        if b.role == "heading2"
    ]


def extract(path: str | Path, skip_patterns: list[str] | None = None) -> Document:
    """Open a PDF and return its Document; study packs get the dedicated profile."""
    path = Path(path)
    with pymupdf.open(path) as doc:
        if sum(len(page.get_text("words")) for page in doc) < MIN_WORDS:
            raise NoTextLayerError(f"{path.name} has no text layer (scanned PDF?)")
        title = (doc.metadata or {}).get("title", "").strip() or path.stem
        if is_studypack(doc):
            profile, blocks = "studypack", studypack_blocks(doc)
        else:
            profile, blocks = "besteffort", besteffort_blocks(doc, skip_patterns)
        outline = build_outline(doc) or _heading_outline(blocks)
        return Document(profile, doc.page_count, blocks, outline, title)
