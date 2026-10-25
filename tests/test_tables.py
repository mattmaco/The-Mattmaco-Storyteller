import re
from pathlib import Path

import pymupdf
import pytest

from storyteller.extract.studypack import studypack_blocks
from storyteller.extract.tables import build_outline, find_tables


def _cell(words):
    return " ".join(w.text for w in words)


def test_mini_table(mini_pdf):
    with pymupdf.open(mini_pdf) as doc:
        found = [t for n, p in enumerate(doc) for t in find_tables(p, n)]
    assert len(found) == 1
    rect, table = found[0]
    assert [_cell(c) for c in table.header] == ["Question", "Answer", "Why"]
    assert len(table.rows) == 2
    assert all(len(r) == 3 for r in table.rows)
    assert _cell(table.rows[0][0]) == "Q1: Is p stable?"
    for w in table.header:
        for word in w:
            assert word.page == 0 and rect[0] <= word.bbox[0] and word.bbox[2] <= rect[2]


def test_table_block_position(mini_pdf):
    with pymupdf.open(mini_pdf) as doc:
        blocks = studypack_blocks(doc)
    page0 = [b for b in blocks if b.page == 0]
    idx = [i for i, b in enumerate(page0) if b.role == "table"]
    assert len(idx) == 1 and page0[idx[0]].table is not None
    above = [b for b in page0[: idx[0]]]
    assert above and above[-1].role != "table"
    ids = [b.id for b in blocks]
    assert len(ids) == len(set(ids))
    # below the "Quick check" heading above it, and above the next page's blocks
    y0 = min(w.bbox[1] for w in page0[idx[0]].words)
    assert min(w.bbox[1] for w in above[-1].words) < y0
    assert above[-1].role == "heading3"
    assert blocks[blocks.index(page0[idx[0]]) + 1].page == 1


def test_tables_by_page_is_not_recomputed(mini_pdf):
    with pymupdf.open(mini_pdf) as doc:
        tables = {n: find_tables(p, n) for n, p in enumerate(doc)}
        blocks = studypack_blocks(doc, tables_by_page=tables)
    assert sum(b.role == "table" for b in blocks) == 1


def test_outline_mini(mini_pdf):
    with pymupdf.open(mini_pdf) as doc:
        outline = build_outline(doc)
    assert [(o.level, o.title) for o in outline] == [
        (1, "Lecture 1: Test lecture"),
        (2, "1 Hardy-Weinberg basics"),
    ]
    assert outline[1].page == 0 and outline[1].y == 36.0


@pytest.fixture(scope="module")
def real_doc():
    path = Path(__file__).parent / "fixtures" / "local" / "biol2040.pdf"
    if not path.exists():
        pytest.skip("real pack not present")
    with pymupdf.open(path) as doc:
        yield doc


def test_real_pack_tables(real_doc):
    found = find_tables(real_doc[4], 4)
    assert len(found) == 2
    assert [_cell(c) for c in found[0][1].header] == ["Question", "Answer", "Why"]
    for _, table in found:
        for cell in table.header + [c for r in table.rows for c in r]:
            assert not re.search(r"Questoi|Anwer|Qustion", _cell(cell))


def test_real_pack_chunk_map_not_a_table_block(real_doc):
    blocks = studypack_blocks(real_doc)
    assert not any(b.role == "table" and b.page == 0 for b in blocks)
    assert any(b.role == "table" for b in blocks)
    ids = [b.id for b in blocks]
    assert len(ids) == len(set(ids))


def test_real_outline_has_35_chunks(real_doc):
    outline = build_outline(real_doc)
    chunks = [o for o in outline if o.level == 2 and o.title[:1].isdigit()]
    assert len(chunks) == 35
