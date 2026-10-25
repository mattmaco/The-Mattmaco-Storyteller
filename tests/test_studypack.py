import re
from pathlib import Path

import pymupdf
import pytest

from storyteller.extract.studypack import is_studypack, studypack_blocks


def _text(block):
    return " ".join(w.text for w in block.words)


@pytest.fixture
def mini_blocks(mini_pdf):
    with pymupdf.open(mini_pdf) as doc:
        return studypack_blocks(doc)


@pytest.fixture(scope="module")
def real_blocks():
    path = Path(__file__).parent / "fixtures" / "local" / "biol2040.pdf"
    if not path.exists():
        pytest.skip("real pack not present")
    with pymupdf.open(path) as doc:
        return studypack_blocks(doc)


def test_detects_studypack(mini_pdf):
    with pymupdf.open(mini_pdf) as doc:
        assert is_studypack(doc)


def test_no_footer_or_page_numbers(mini_blocks):
    assert mini_blocks
    for b in mini_blocks:
        assert not re.search(r"Page \d+ of \d+", _text(b))
        assert "study notes" not in _text(b)


def test_no_cites(mini_blocks):
    assert not any(re.search(r"\(P\d", _text(b)) for b in mini_blocks)


def test_source_line_dropped(mini_blocks):
    assert not any("deck, slides" in _text(b) for b in mini_blocks)


def test_chain_tags_become_leads(mini_blocks):
    entry = [b for b in mini_blocks if b.lead == "Entry:"]
    assert entry and entry[0].box_kind == "chain" and entry[0].role == "body"
    assert _text(entry[0]).startswith("Parents contribute")
    assert any(b.lead == "Route:" for b in mini_blocks)
    assert not any(_text(b) in ("Entry", "Route") for b in mini_blocks)


def test_badge_becomes_lead(mini_blocks):
    stated = [b for b in mini_blocks if b.lead == "Stated:"]
    assert stated and _text(stated[0]).startswith("A population is in balance")
    assert not any(_text(b) == "Stated" for b in mini_blocks)


def test_chunk_heading(mini_blocks):
    heads = [b for b in mini_blocks if b.role == "heading2"]
    assert len(heads) == 1
    assert heads[0].lead == "Chunk 1."
    assert _text(heads[0]) == "Hardy-Weinberg basics"
    assert heads[0].flagged


def test_flag_dropped(mini_blocks):
    for b in mini_blocks:
        assert "★" not in _text(b)
        assert "Likely tested" not in _text(b)


def test_banner_heading1(mini_blocks):
    h1 = [b for b in mini_blocks if b.role == "heading1"]
    assert h1 and all(_text(b) == "Lecture 1: Test lecture" for b in h1)
    assert mini_blocks[0].role == "heading1"


def test_subheading_heading3(mini_blocks):
    h3 = [_text(b) for b in mini_blocks if b.role == "heading3"]
    assert "The principle" in h3 and "Worked example" in h3


def test_box_kinds(mini_blocks):
    kinds = {b.box_kind for b in mini_blocks if b.box_kind}
    assert kinds >= {"chain", "kit", "traps", "analogy"}
    labels = {_text(b): b.box_kind for b in mini_blocks if b.role == "box_label"}
    assert labels["Chain: one generation"] == "chain"
    assert labels["Reasoning kit"] == "kit"
    assert labels["Traps"] == "traps"
    assert labels["Analogy: shuffled deck"] == "analogy"


def test_wrapped_paragraph_one_block(mini_blocks):
    hits = [b for b in mini_blocks if "evolution has carried" in _text(b)]
    assert len(hits) == 1
    assert _text(hits[0]).startswith("Over many generations")
    assert _text(hits[0]).endswith("where it began.")


def test_cite_gap_collapsed(mini_blocks):
    text = " ".join(_text(b) for b in mini_blocks)
    assert "q² = 1. Allele" in text
    assert " ." not in text
    assert ".." not in text


def test_reading_order_and_ids(mini_blocks):
    texts = [_text(b) for b in mini_blocks if b.page == 0]
    assert texts.index("Hardy-Weinberg basics") < texts.index("The principle")
    assert all(re.fullmatch(r"b\d{3}_\d{3}", b.id) for b in mini_blocks)
    assert len({b.id for b in mini_blocks}) == len(mini_blocks)


def test_tables_skipped(mini_blocks):
    assert not any("Q1: Is p stable?" in _text(b) for b in mini_blocks)


def test_real_pack_detected(real_pack):
    with pymupdf.open(real_pack) as doc:
        assert is_studypack(doc)


def test_real_pack_no_noise(real_blocks):
    assert len(real_blocks) > 300
    for b in real_blocks:
        t = _text(b)
        assert not re.search(r"Page \d+ of 56", t)
        assert not re.search(r"\(P\d \d", t)
        assert not re.search(r"\((Lk|SS) \d", t)
        assert not re.search(r"\bdeck,? slides?\b", t)
        assert "Likely tested" not in t


def test_real_pack_structure(real_blocks):
    heads = [b for b in real_blocks if b.role == "heading2"]
    assert [b.lead for b in heads] == [f"Chunk {n}." for n in range(1, 36)]
    assert sum(b.flagged for b in heads) == 19  # the 19 "★ Likely tested" chunk titles
    for h in heads:  # native order lists the chunk header last; it must be read first
        before = [b for b in real_blocks if b.page == h.page and b.id < h.id]
        assert all(b.role == "heading1" for b in before), h.id
    assert sum(1 for b in real_blocks if b.lead and b.box_kind == "chain") >= 20
    kinds = {b.box_kind for b in real_blocks if b.box_kind}
    assert kinds >= {"chain", "kit", "traps", "key", "analogy"}


def test_plain_pdf_not_studypack():
    doc = pymupdf.open()
    for n in range(4):
        page = doc.new_page()
        page.insert_text((72, 100), "An ordinary report paragraph.", fontsize=11)
        page.insert_text((72, 770), f"Page {n + 1} of 4", fontsize=8)
    assert not is_studypack(doc)
