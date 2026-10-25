"""Study-pack detection, span role classification and Block assembly.

Rules come from the "Study-pack template facts" measured on the real pack:
colours, bold/size relations and filled rects identify every element, so
footers, cites, flags and source lines never reach the listening script,
while chain tags and badges become spoken leads ("Entry:", "Stated:").
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

import pymupdf

from storyteller.extract.pdfwords import RawSpan, join_lines, read_spans, read_spans_with_chars, span_words
from storyteller.model import BBox, Block, Table, Word

BODY = 0x1F2933
CITE_COLOURS = {0x5C6774, 0x55606C}
TEAL = 0x0F6B6B
BANNER_FILL = 0x0E6A6A
FLAG = 0x9B1C1C
WHITE = 0xFFFFFF

LABEL_KINDS = {
    0x0F6B6B: "chain",
    0x1D5A8E: "figure",
    0x4A5562: "note",
    0x8A4A00: "analogy",
    0x9B1C1C: "key",
    0x14602F: "kit",
}
NOTE_PREFIXES = (
    ("What the slides don’t say", "gap"),
    ("What the slides don't say", "gap"),
    ("Background", "background"),
    ("Reading aid", "reading_aid"),
)

FOOTER_PAGE_RE = re.compile(r"^Page \d+ of \d+$")
SOURCE_LINE_RE = re.compile(r"\bdeck,? slides?\b")
INLINE_CITE_RE = re.compile(r"\s*\((?:P\d|Lk|SS) \d[^()]*\)")  # a cite printed in a label's own colour
FLAG_RE = re.compile(r"^(★\s*)?(Likely tested)?$")
EXAM_PILL = "Past exam question"  # chunk-header pill in the flag colour: dropped, but not "Likely tested"
FLAG_PILL_MAX_SIZE = 8.5  # pills are small; a key-box label in the flag colour is 9pt
BADGES = {"Stated", "Follows"}
PUNCT_START = tuple(".,;:?!)")

CONTINUED_BOX_TOP = 60  # an unlabelled box starting above this y continues the previous page's box
BOX_RUNS_OFF_MARGIN = 60  # a box ending this close to the page bottom may continue overleaf

JUMP_BACK = 30  # a block starting this far above its predecessor is out of native order

DROPPED = {"footer", "cite", "flag", "table"}
TEXT_ROLES = {"banner", "heading2", "heading3", "box_label", "body"}
BLOCK_ROLE = {"banner": "heading1"}


@dataclass
class Box:
    rect: BBox
    kind: str


@dataclass
class PageContext:
    page_height: float
    body_median: float
    boxes: list[Box] = field(default_factory=list)
    table_rects: list[BBox] = field(default_factory=list)
    tag_rects: list[BBox] = field(default_factory=list)
    banner_rects: list[BBox] = field(default_factory=list)


# ---------------------------------------------------------------- geometry


def _centre(b: BBox) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _inside(b: BBox, rect: BBox, tol: float = 1.0) -> bool:
    cx, cy = _centre(b)
    return rect[0] - tol <= cx <= rect[2] + tol and rect[1] - tol <= cy <= rect[3] + tol


def _area(r: BBox) -> float:
    return (r[2] - r[0]) * (r[3] - r[1])


def _union(boxes) -> BBox:
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _rgb_int(fill) -> int:
    r, g, b = (max(0, min(255, round(c * 255))) for c in fill[:3])
    return (r << 16) | (g << 8) | b


def _close(a: int, b: int, tol: int = 3) -> bool:
    return all(abs(((a >> s) & 255) - ((b >> s) & 255)) <= tol for s in (16, 8, 0))


# ---------------------------------------------------------------- detection


def is_studypack(doc: pymupdf.Document) -> bool:
    footer_pages: set[int] = set()
    body = cites = 0
    for pno, page in enumerate(doc):
        h = page.rect.height
        for s in read_spans(page, pno):
            if s.bbox[1] > h - 40 and FOOTER_PAGE_RE.match(s.text.strip()):
                footer_pages.add(pno)
            if s.color == BODY:
                body += 1
            elif s.color in CITE_COLOURS:
                cites += 1
        if len(footer_pages) >= 3 and body >= 20 and cites >= 5:
            return True
    return False


# ---------------------------------------------------------------- page context


def _body_median(spans: list[RawSpan]) -> float:
    # Weighted by length so the many one-char subscript spans don't drag it down.
    sizes = [s.size for s in spans if s.color == BODY and not s.bold for _ in range(len(s.text.strip()))]
    return statistics.median(sizes) if sizes else 9.5


def _box_kind(label: RawSpan, line_text: str) -> str | None:
    kind = LABEL_KINDS.get(label.color)
    if kind == "note":
        for prefix, sub in NOTE_PREFIXES:
            if line_text.startswith(prefix):
                return sub
    return kind


def page_context(
    page: pymupdf.Page, spans: list[RawSpan], table_rects: list[BBox], carry_kind: str | None = None
) -> PageContext:
    """Boxes, tag rects and body size of one page.

    `carry_kind` is the kind of a box still open at the bottom of the previous
    page: an unlabelled box at the top of this page continues it.
    """
    filled: list[tuple[BBox, int]] = []
    for d in page.get_drawings():
        if d.get("fill") is None:
            continue
        r = d["rect"]
        filled.append(((r.x0, r.y0, r.x1, r.y1), _rgb_int(d["fill"])))

    # Wider teal rects are header cells of tables find_tables() misses, never step tags.
    tag_rects = [r for r, c in filled if r[2] - r[0] < (40 if _close(c, TEAL) else 120)]
    banner_rects = [r for r, c in filled if r[2] - r[0] > 300 and _close(c, BANNER_FILL)]
    boxes: list[Box] = []
    for rect, colour in filled:
        if rect[2] - rect[0] <= 300 or rect[3] - rect[1] < 6 or _close(colour, BANNER_FILL):
            continue
        if any(_inside(rect, t) for t in table_rects):
            continue
        contained = [s for s in spans if _inside(s.bbox, rect, tol=0)]
        if not contained:
            continue
        label = contained[0]
        if label.bold and label.color in LABEL_KINDS:
            line_text = "".join(s.text for s in contained if (s.block_no, s.line_no) == (label.block_no, label.line_no))
            kind = _box_kind(label, line_text.strip())
        elif carry_kind and rect[1] < CONTINUED_BOX_TOP:
            kind = carry_kind
        else:
            continue
        boxes.append(Box(rect, kind))
        if kind == "kit":
            for s in contained[1:]:
                if s.bold and s.text.strip() == "Traps":
                    boxes.append(Box((rect[0], s.bbox[1] - 1, rect[2], rect[3]), "traps"))
                    break

    return PageContext(
        page_height=page.rect.height,
        body_median=_body_median(spans),
        boxes=boxes,
        table_rects=list(table_rects),
        tag_rects=tag_rects,
        banner_rects=banner_rects,
    )


def open_box_kind(ctx: PageContext) -> str | None:
    """Kind of the box running off the bottom of this page, if any."""
    bottom = [b for b in ctx.boxes if b.rect[3] > ctx.page_height - BOX_RUNS_OFF_MARGIN]
    return min(bottom, key=lambda b: _area(b.rect)).kind if bottom else None


def _box_at(b: BBox, ctx: PageContext) -> Box | None:
    hits = [box for box in ctx.boxes if _inside(b, box.rect, tol=0)]
    return min(hits, key=lambda box: _area(box.rect)) if hits else None


# ---------------------------------------------------------------- classification


def classify_span(span: RawSpan, ctx: PageContext) -> str:
    text = span.text.strip()
    if span.bbox[1] > ctx.page_height - 40:
        return "footer"
    if any(_inside(span.bbox, r, tol=2) for r in ctx.table_rects):
        return "table"
    if span.color in CITE_COLOURS:
        return "cite"
    if span.color == FLAG and (FLAG_RE.match(text) or (text == EXAM_PILL and span.size < FLAG_PILL_MAX_SIZE)):
        return "flag"
    if text in BADGES and span.bold and span.size < 8.5:
        return "badge"
    if span.color == WHITE and span.bold:
        if text.isdigit() and span.size >= 12:
            return "chunk_number"
        # Table header rows share the banner's fill; the banner's text is larger than body text.
        if span.size >= 1.05 * ctx.body_median and any(_inside(span.bbox, r) for r in ctx.banner_rects):
            return "banner"
        word_like = any(c.isalpha() for c in text) or text.isdigit()  # not a "#" header cell
        if word_like and len(text.split()) <= 3 and any(_inside(span.bbox, r) for r in ctx.tag_rects):
            return "tag"
    box = _box_at(span.bbox, ctx)
    if box is not None and span.bold and span.color in LABEL_KINDS:
        return "box_label"
    if span.color == BODY and span.bold and span.size >= 1.35 * ctx.body_median:
        return "heading2"
    if span.color == TEAL and span.bold and span.size >= 1.05 * ctx.body_median and box is None:
        return "heading3"
    return "body"


# ---------------------------------------------------------------- assembly


def _line_words(parts: list[tuple[RawSpan, list, bool]]) -> list[Word]:
    """Words of one line from (span, chars, gap_before) parts.

    Adjacent spans that touch (a subscript, a bold run inside a word) join into
    one word; a dropped span or a visible gap between them separates words.
    """
    chars: list[dict] = []
    prev: RawSpan | None = None
    for span, span_chars, gap_before in parts:
        if prev is not None:
            visible_gap = span.bbox[0] - prev.bbox[2] > 0.25 * min(span.size, prev.size)
            if gap_before or visible_gap:
                chars.append({"c": " ", "bbox": span.bbox})
        chars.extend(span_chars)
        prev = span
    return span_words(parts[0][0], chars) if parts else []


def _strip_inline_cites(chars: list) -> list[tuple[list, bool]]:
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


def _collapse_punct(words: list[Word]) -> list[Word]:
    out: list[Word] = []
    for w in words:
        if out and w.text.startswith(PUNCT_START):
            prev = out[-1]
            text = w.text[1:] if w.text.startswith(".") and prev.text.endswith(".") else w.text  # no ".."
            out[-1] = Word(prev.text + text, prev.page, _union([prev.bbox, w.bbox]))
        else:
            out.append(w)
    return out


@dataclass
class _Group:
    role: str
    block_no: int
    lines: list[list[Word]]
    lead: str | None = None


@dataclass
class _Pending:
    """Reading state carried across lines and pages."""

    box_kind: str | None = None  # box left open at the bottom of the previous page
    lead: list[str] = field(default_factory=list)  # tag/badge words waiting for a body block
    lead_open: bool = False  # True while consecutive tag spans extend one lead
    chunk_number: str | None = None


def _page_groups(page: pymupdf.Page, pno: int, pending: _Pending, table_rects: list[BBox]):
    """Text groups of one page in native order, plus its context, flag and chunk-number spans."""
    pairs = read_spans_with_chars(page, pno)
    ctx = page_context(page, [s for s, _ in pairs], table_rects, carry_kind=pending.box_kind)
    pending.box_kind = open_box_kind(ctx)

    lines: dict[tuple[int, int], list[tuple[RawSpan, list]]] = {}
    for s, chars in pairs:
        lines.setdefault((s.block_no, s.line_no), []).append((s, chars))

    groups: list[_Group] = []
    flags: list[BBox] = []
    numbers: list[tuple[str, BBox]] = []
    for (block_no, _), line in lines.items():
        line_text = "".join(s.text for s, _ in line)
        source_line = bool(SOURCE_LINE_RE.search(line_text))
        line_role: str | None = None
        parts: list[tuple[RawSpan, list, bool]] = []
        gap = False
        for s, chars in line:
            role = classify_span(s, ctx)
            if role == "body" and source_line and s.color != BODY:
                role = "source"
            if role == "tag" and s.text.strip().isdigit():
                pass  # a numbered step circle: native order puts it after its text, and the text carries (a), (b)…
            elif role in ("tag", "badge"):
                if not pending.lead_open:
                    pending.lead = []
                pending.lead.append(s.text.strip())
                pending.lead_open = True
            elif role == "chunk_number":
                numbers.append((s.text.strip(), s.bbox))
            elif role == "flag":
                if FLAG_RE.match(s.text.strip()):  # only "★ Likely tested" sets flagged
                    flags.append(s.bbox)
            elif role in TEXT_ROLES:
                pending.lead_open = False
                line_role = line_role or role
                for seg, cut_before in _strip_inline_cites(chars):
                    parts.append((s, seg, gap or cut_before))
                    gap = False
                gap = False
                continue
            gap = True  # footer, cite, table, source line, tag, number: a word break
        words = _line_words(parts)
        if not words:
            continue
        if line_role != "body":
            pending.lead = []  # a heading or box label came first: the lead belonged to nothing here
        cur = groups[-1] if groups else None
        # A tag or badge starts a new body block, even mid-PyMuPDF-block ("4. Follows ...").
        lead_here = line_role == "body" and bool(pending.lead)
        if cur is None or cur.role != line_role or cur.block_no != block_no or lead_here:
            cur = _Group(line_role, block_no, [])
            groups.append(cur)
        if lead_here:
            cur.lead = " ".join(pending.lead) + ":"
            pending.lead = []
        cur.lines.append(words)
    return groups, ctx, flags, numbers


def _restore_y_order(blocks: list[Block], bboxes: dict[int, BBox]) -> list[Block]:
    """Put back blocks that native order lists out of place.

    Chromium writes positioned elements (the chunk header, some step lists)
    after the page's flow, so they come last in native order. A block that
    jumps back up the page over the block before it (and overlaps it
    horizontally, so it is not a side-by-side column) is moved to its y
    position, together with the blocks that follow on from it.
    """
    top = lambda b: bboxes[id(b)][1]  # noqa: E731
    out: list[Block] = []
    cursor: int | None = None  # insertion point while moving a run of displaced blocks
    for b in blocks:
        if cursor is not None:
            if top(b) >= top(out[cursor - 1]) - 5 and (cursor == len(out) or top(b) <= top(out[cursor])):
                out.insert(cursor, b)
                cursor += 1
                continue
            cursor = None
        displaced = (b.role == "heading2" or _overlaps_x(bboxes[id(b)], bboxes[id(out[-1])])) if out else False
        if out and top(b) < top(out[-1]) - JUMP_BACK and displaced:
            cursor = next((i for i, o in enumerate(out) if top(o) > top(b)), len(out))
            out.insert(cursor, b)
            cursor += 1
            continue
        out.append(b)
    return out


def _overlaps_x(a: BBox, b: BBox) -> bool:
    return min(a[2], b[2]) - max(a[0], b[0]) > 0


def _continues(prev: Block | None, g: _Group, words: list[Word]) -> bool:
    """True when a body group is the wrapped tail of the previous body block's sentence."""
    if prev is None or prev.role != "body" or g.role != "body" or g.lead is not None:
        return False
    prev_text = " ".join(w.text for w in prev.words)
    if prev_text.count("(") > prev_text.count(")"):
        return True  # "(chunk" … "6)"
    first = words[0].text[:1]
    return (first.islower() or first == "(") and not prev_text.endswith((".", "?", "!", ":"))


def _near_y(a: BBox, b: BBox, gap: float = 6.0) -> bool:
    """Same visual line, or the next one when a long chunk title wraps the flag below it."""
    return min(a[3], b[3]) - max(a[1], b[1]) > -gap


def _overlaps_y(a: BBox, b: BBox) -> bool:
    return min(a[3], b[3]) - max(a[1], b[1]) > 0


def table_rects_of(page: pymupdf.Page) -> list[BBox]:
    return [tuple(t.bbox) for t in page.find_tables().tables]


def _chunk_map_rect(doc: pymupdf.Document, table_rects: list[BBox]) -> BBox | None:
    """The page-0 table that lists the chunks (≥ 3 level-2 outline titles inside it)."""
    titles = [re.sub(r"^\d+\s+", "", t[1]).strip()[:24] for t in doc.get_toc() if t[0] == 2]
    for rect in table_rects:
        text = " ".join(doc[0].get_text("text", clip=pymupdf.Rect(rect)).split())
        if sum(1 for t in titles if t and t in text) >= 3:
            return rect
    return None


def _drop_chunk_map_heading(blocks: list[Block], bboxes: dict[int, BBox], rect: BBox) -> list[Block]:
    """Drop the heading whose next content is the chunk-map table (the outline replaces both)."""
    above = [b for b in blocks if bboxes[id(b)][3] <= rect[1] + 2]
    if not above:
        return blocks
    last = max(above, key=lambda b: bboxes[id(b)][3])
    if last.role.startswith("heading") and rect[1] - bboxes[id(last)][3] < 30:
        return [b for b in blocks if b is not last]
    return blocks


def _table_block(rect: BBox, table: Table, pno: int) -> Block:
    cells = [c for c in table.header] + [c for row in table.rows for c in row]
    return Block("", "table", [w for c in cells for w in c], pno, table=table)


def _insert_by_y(page_blocks: list[Block], bboxes: dict[int, BBox], block: Block, rect: BBox) -> None:
    """Place a table block before the first block that starts below the table's top."""
    bboxes[id(block)] = rect
    at = next((i for i, b in enumerate(page_blocks) if bboxes[id(b)][1] >= rect[1]), len(page_blocks))
    page_blocks.insert(at, block)


def studypack_blocks(
    doc: pymupdf.Document,
    table_rects_by_page: dict[int, list[BBox]] | None = None,
    tables_by_page: dict[int, list[tuple[BBox, Table]]] | None = None,
) -> list[Block]:
    """Blocks of a study pack in reading order, tables included as `table` blocks.

    `find_tables()` runs once per page. A caller that already ran it passes
    `tables_by_page` (rects and Tables, which also yields table blocks) or just
    `table_rects_by_page` (table text is skipped and no table blocks are made).
    With neither, tables are found here.
    """
    from storyteller.extract.tables import find_tables

    blocks: list[Block] = []
    pending = _Pending()
    for pno, page in enumerate(doc):
        tables: list[tuple[BBox, Table]] = []
        if tables_by_page is not None:
            tables = tables_by_page.get(pno, [])
            table_rects = [r for r, _ in tables]
        elif table_rects_by_page is not None:
            table_rects = list(table_rects_by_page.get(pno, []))
        else:
            tables = find_tables(page, pno)
            table_rects = [r for r, _ in tables]
        groups, ctx, flags, numbers = _page_groups(page, pno, pending, table_rects)
        page_blocks: list[Block] = []
        for g in groups:
            words = _collapse_punct(join_lines(g.lines))
            prev = page_blocks[-1] if page_blocks else None
            if words and prev is not None and prev.role == g.role == "body" and words[0].text.startswith(PUNCT_START):
                # Punctuation stranded after a cite that opened a new PyMuPDF block ends the previous sentence.
                prev.words = _collapse_punct(prev.words + words[:1])
                words = words[1:]
            if words and _continues(prev, g, words):
                prev.words = prev.words + words  # a wrapped line PyMuPDF put in a block of its own
                continue
            if words:
                page_blocks.append(Block("", BLOCK_ROLE.get(g.role, g.role), words, pno, lead=g.lead))
        bboxes = {id(b): _union(w.bbox for w in b.words) for b in page_blocks}
        heads = [b for b in page_blocks if b.role == "heading2"]

        # A chunk number belongs to the heading on its visual line, else to the next heading.
        for digits, nb in numbers:
            same_line = [h for h in heads if h.lead is None and _overlaps_y(bboxes[id(h)], nb)]
            if same_line:
                same_line[0].lead = f"Chunk {digits}."
            else:
                pending.chunk_number = digits
        for h in heads:
            if h.lead is None and pending.chunk_number is not None:
                h.lead = f"Chunk {pending.chunk_number}."
                pending.chunk_number = None
            h.flagged = any(_near_y(bboxes[id(h)], fb) for fb in flags)

        page_blocks = _restore_y_order(page_blocks, bboxes)
        if pno == 0:
            chunk_map = _chunk_map_rect(doc, table_rects)
            if chunk_map is not None:
                page_blocks = _drop_chunk_map_heading(page_blocks, bboxes, chunk_map)
                tables = [(r, t) for r, t in tables if r != chunk_map]  # the outline replaces it
        for rect, table in tables:
            block = _table_block(rect, table, pno)
            if block.words:
                _insert_by_y(page_blocks, bboxes, block, rect)

        for n, b in enumerate(page_blocks):
            b.id = f"b{pno:03d}_{n:03d}"
            box = _box_at(bboxes[id(b)], ctx)
            b.box_kind = box.kind if box else None
        blocks.extend(page_blocks)
    return blocks
