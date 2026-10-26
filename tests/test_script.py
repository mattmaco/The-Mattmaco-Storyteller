import re
from pathlib import Path

import pytest

from storyteller.extract import extract
from storyteller.model import Block, Document, OutlineEntry, SpokenWord, Table, Word
from storyteller.speech import ScriptOptions, build_script
from storyteller.speech.sentences import split_long, split_sentences
from storyteller.speech.tables import linearise_table

NOISE = re.compile(r"Page \d|\(P\d|deck, slides|★")


def _words(text: str, page: int = 0, y: float = 100.0) -> list[Word]:
    return [Word(t, page, (10.0 * i, y, 10.0 * i + 8, y + 10)) for i, t in enumerate(text.split())]


def _texts(group: list[Word]) -> str:
    return " ".join(w.text for w in group)


@pytest.fixture(scope="module")
def mini_doc():
    return extract(Path(__file__).parent / "fixtures" / "studypack_mini.pdf")


@pytest.fixture(scope="module")
def mini_script(mini_doc):
    return build_script(mini_doc, "mini", ScriptOptions())


@pytest.fixture(scope="module")
def real_doc():
    path = Path(__file__).parent / "fixtures" / "local" / "biol2040.pdf"
    if not path.exists():
        pytest.skip("real pack not present")
    return extract(path)


# --- sentence splitting -----------------------------------------------------


def test_split_basic():
    groups = split_sentences(_words("Hello there. Next one."))
    assert [_texts(g) for g in groups] == ["Hello there.", "Next one."]


def test_no_split_abbrev():
    groups = split_sentences(_words("See Fig. 7 and e.g. this. Done."))
    assert [_texts(g) for g in groups] == ["See Fig. 7 and e.g. this.", "Done."]


def test_no_split_decimal():
    groups = split_sentences(_words("p = 0.6 here. Ok."))
    assert [_texts(g) for g in groups] == ["p = 0.6 here.", "Ok."]


def test_no_split_initial_or_parenthesis():
    assert len(split_sentences(_words("Named by J. Smith today."))) == 1
    assert len(split_sentences(_words("A claim (see above. It holds) stands. Next."))) == 2


def test_no_split_after_list_numbers():
    groups = split_sentences(_words("1. Q1. What is it? At time t. 2. No mutation. Ends at 2. Then"))
    assert [_texts(g) for g in groups] == [
        "1. Q1. What is it?", "At time t.", "2. No mutation.", "Ends at 2.", "Then",
    ]


def test_split_after_closing_quote():
    groups = split_sentences(_words('He said "stop." Then left.'))
    assert [_texts(g) for g in groups] == ['He said "stop."', "Then left."]


def test_split_long():
    items = [f"item{n:03d}," for n in range(100)]
    spoken = [SpokenWord(t, i) for i, t in enumerate(items)]
    original = " ".join(items)
    assert len(original) > 700
    parts = split_long(spoken)
    assert len(parts) > 1
    assert all(len(" ".join(w.text for w in p)) <= 300 for p in parts)
    assert " ".join(" ".join(w.text for w in p) for p in parts) == original


def test_split_long_prefers_punctuation_and_hard_splits():
    words = ["word"] * 40 + ["end;"] + ["word"] * 40
    parts = split_long([SpokenWord(t, i) for i, t in enumerate(words)], limit=250)
    assert parts[0][-1].text == "end;"
    plain = ["abcdefghi"] * 80  # no punctuation at all
    parts = split_long([SpokenWord(t, i) for i, t in enumerate(plain)])
    assert all(len(" ".join(w.text for w in p)) <= 300 for p in parts)
    assert sum(len(p) for p in parts) == 80


# --- tables ----------------------------------------------------------------


def test_linearise_table():
    table = Table(
        header=[_words("Question"), _words("Answer"), _words("Why")],
        rows=[[_words("Q1"), _words("f[A1] = p"), _words("sums to one")]],
    )
    out = linearise_table(table)
    assert [" ".join(tokens) for tokens, _ in out] == [
        "Table, 1 row: Question, Answer, Why.",
        "Question: Q1. Answer: f[A1] = p. Why: sums to one.",
    ]
    assert [w.text for w in out[0][1]] == ["Question", "Answer", "Why"]
    assert [w.text for w in out[1][1]] == ["Q1", "f[A1]", "=", "p", "sums", "to", "one"]


def test_linearise_table_plural_and_empty_cells():
    table = Table(
        header=[_words("Term"), _words("Meaning")],
        rows=[[_words("p"), []], [_words("q"), _words("other allele?")]],
    )
    out = linearise_table(table)
    assert " ".join(out[0][0]) == "Table, 2 rows: Term, Meaning."
    assert " ".join(out[1][0]) == "Term: p."
    assert " ".join(out[2][0]) == "Term: q. Meaning: other allele?"


# --- build_script on the mini pack -----------------------------------------


def test_mini_script_noise_free(mini_script):
    assert mini_script.sentences
    for s in mini_script.sentences:
        assert not NOISE.search(s.spoken_text), s.spoken_text


def test_mini_script_leads(mini_script):
    texts = [s.spoken_text for s in mini_script.sentences]
    assert any(t.startswith("Entry:") for t in texts)
    assert any(t.startswith("Chunk 1.") for t in texts)
    entry = next(s for s in mini_script.sentences if s.spoken_text.startswith("Entry:"))
    assert entry.spoken[0].word_index == 0


def test_mini_script_formula(mini_script):
    assert any(
        "p squared plus 2 p q plus q squared equals 1" in s.spoken_text for s in mini_script.sentences
    )


def test_mini_script_table(mini_script):
    table = [s for s in mini_script.sentences if s.kind == "table"]
    assert table[0].spoken_text == "Table, 2 rows: Question, Answer, Why."
    assert table[1].spoken_text.startswith("Question: Q1: Is p stable?")


def test_spoken_words_map_to_display(mini_script):
    for s in mini_script.sentences:
        assert s.display
        idx = [w.word_index for w in s.spoken]
        assert idx == sorted(idx)
        assert all(0 <= i < len(s.display) for i in idx)


def test_ids_sequential(mini_script):
    assert [s.id for s in mini_script.sentences] == [
        f"s{n:05d}" for n in range(len(mini_script.sentences))
    ]


def test_no_empty_sentences():
    blocks = [
        Block("b000_000", "body", _words("★ – ★"), 0),
        Block("b000_001", "body", _words("Real words here."), 0),
        Block("b000_002", "body", _words("★"), 0, lead="Stated:"),
    ]
    doc = Document("studypack", 1, blocks, [], "t")
    script = build_script(doc, "p", ScriptOptions(read_badges=False))
    assert [s.spoken_text for s in script.sentences] == ["Real words here."]
    assert all(s.spoken_text.strip() for s in script.sentences)


def test_punctuation_only_word_keeps_boundary():
    blocks = [Block("b000_000", "body", _words("First part ★. Second part."), 0)]
    script = build_script(Document("studypack", 1, blocks, [], "t"), "p", ScriptOptions())
    assert [s.spoken_text for s in script.sentences] == ["First part.", "Second part."]
    assert len(script.sentences[0].display) == 3


def test_badges_follow_read_badges():
    blocks = [Block("b000_000", "body", _words("It holds."), 0, lead="Stated:")]
    doc = Document("studypack", 1, blocks, [], "t")
    assert build_script(doc, "p", ScriptOptions()).sentences[0].spoken_text == "Stated: It holds."
    off = build_script(doc, "p", ScriptOptions(read_badges=False))
    assert off.sentences[0].spoken_text == "It holds."


def test_read_flags(mini_doc):
    on = build_script(mini_doc, "mini", ScriptOptions(read_flags=True)).sentences
    i = next(n for n, s in enumerate(on) if s.spoken_text.startswith("Chunk 1."))
    assert on[i + 1].spoken_text == "Likely tested."
    off = build_script(mini_doc, "mini", ScriptOptions()).sentences
    assert not any(s.spoken_text == "Likely tested." for s in off)


def test_pause_values(mini_doc, mini_script):
    roles = {b.id: b.role for b in mini_doc.blocks}
    sents = mini_script.sentences
    for n, s in enumerate(sents):
        last_in_block = n + 1 == len(sents) or sents[n + 1].block_id != s.block_id
        if roles[s.block_id].startswith("heading"):
            assert s.pause_after_ms == 1000
            assert s.kind == "heading"
        elif last_in_block:
            assert s.pause_after_ms == 600
        else:
            assert s.pause_after_ms == 250
    assert any(s.pause_after_ms == 250 for s in sents)


def test_custom_pauses(mini_doc):
    opts = ScriptOptions(pauses={"sentence": 100, "block": 200, "section": 300})
    assert {s.pause_after_ms for s in build_script(mini_doc, "m", opts).sentences} == {100, 200, 300}


def test_skip_box_kind(mini_doc):
    analogy = {b.id for b in mini_doc.blocks if b.box_kind == "analogy"}
    assert analogy
    opts = ScriptOptions()
    opts.read_boxes["analogy"] = False
    script = build_script(mini_doc, "mini", opts)
    assert not any(s.block_id in analogy for s in script.sentences)
    assert ScriptOptions().read_boxes["analogy"] is True  # defaults not shared


def test_outline_sentence_ids(mini_script):
    ids = {s.id for s in mini_script.sentences}
    assert mini_script.outline
    for entry in mini_script.outline:
        assert entry.sentence_id in ids
    chunk = next(e for e in mini_script.outline if e.level == 2)
    first = next(s for s in mini_script.sentences if s.id == chunk.sentence_id)
    assert first.display[0].page == chunk.page


def test_outline_respects_position():
    blocks = [
        Block("b000_000", "body", _words("Top text.", y=50), 0),
        Block("b000_001", "heading2", _words("Later", y=300), 0),
        Block("b001_000", "body", _words("Next page.", page=1, y=50), 1),
    ]
    outline = [OutlineEntry(2, "Later", 0, 300.0), OutlineEntry(2, "P2", 1, 40.0)]
    script = build_script(Document("studypack", 2, blocks, outline, "t"), "p", ScriptOptions())
    assert [e.sentence_id for e in script.outline] == ["s00001", "s00002"]


def test_pronunciations_applied():
    blocks = [Block("b000_000", "body", _words("Allele drift."), 0)]
    opts = ScriptOptions(pronunciations={"allele": "uh-leel"})
    assert build_script(Document("studypack", 1, blocks, [], "t"), "p", opts).sentences[
        0
    ].spoken_text == "uh-leel drift."


def test_long_sentence_split_into_sentences():
    text = " ".join(f"item{n:03d}," for n in range(80)) + " end."
    blocks = [Block("b000_000", "body", _words(text), 0)]
    script = build_script(Document("studypack", 1, blocks, [], "t"), "p", ScriptOptions())
    assert len(script.sentences) > 1
    assert all(len(s.spoken_text) <= 300 for s in script.sentences)
    shown = [w.text for s in script.sentences for w in s.display]
    assert shown == text.split()
    for s in script.sentences:
        assert all(s.display[w.word_index].text.startswith(w.text[:4]) for w in s.spoken)
    assert [s.pause_after_ms for s in script.sentences][-1] == 600


# --- real pack ---------------------------------------------------------------


def test_real_pack_script(real_doc):
    script = build_script(real_doc, "biol2040", ScriptOptions())
    assert len(script.sentences) > 500
    for s in script.sentences:
        assert s.spoken_text.strip()
        assert len(s.spoken_text) <= 300
        assert not NOISE.search(s.spoken_text), s.spoken_text
    ids = {s.id for s in script.sentences}
    chunks = [e for e in script.outline if e.level == 2 and re.match(r"\d+\. ", e.title)]
    assert len(chunks) == 35
    assert all(e.sentence_id in ids for e in script.outline)
