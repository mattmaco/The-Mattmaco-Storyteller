import pytest

from storyteller.extract import extract
from storyteller.speech.pronounce import apply_pronunciations
from storyteller.speech.symbols import Rules, speak_word

# Every symbol found in the real pack.
PACK_SYMBOLS = list("–’²“”−ω×★÷µ≈½̄′Δ√…Σ≠α") + ["á", "¼"]


@pytest.mark.parametrize(
    "word, expected",
    [
        ("p²", ["p", "squared"]),
        ("q²", ["q", "squared"]),
        ("2pq", ["2", "p", "q"]),
        ("p′", ["p", "prime"]),
        ("w̄", ["w", "bar"]),
        ("ω", ["omega"]),
        ("Δp", ["delta", "p"]),
        ("½", ["one", "half"]),
        ("dN/dS", ["d", "N", "over", "d", "S"]),
        ("f[A1]", ["frequency", "of", "A1"]),
        ("A1A2", ["A", "1", "A", "2"]),
        ("2–7", ["2", "to", "7"]),
        ("≈", ["approximately"]),
        ("★", []),
        ("genotypes.", ["genotypes."]),
        ("p².", ["p", "squared."]),
        ("(genotypes),", ["genotypes,"]),
        ("“hello,”", ["hello,"]),
        ("dN/dS.", ["d", "N", "over", "d", "S."]),
        ("this–that", ["this,", "that"]),
        ("–", []),
        ("f[A1A1]", ["frequency", "of", "A", "1", "A", "1"]),
        ("f[A1A1],", ["frequency", "of", "A", "1", "A", "1,"]),
        ("(0.755)²", ["0.755", "squared"]),
        ("2(0.6)(0.4)", ["2", "times", "0.6", "times", "0.4"]),
        ("(p+q)²", ["p", "plus", "q", "squared"]),
        ("(see", ["see"]),
        ("that)", ["that"]),
        ("(foo).", ["foo."]),
        ("foo.),", ["foo.,"]),
        ("—", []),
        ("a—b", ["a,", "b"]),
        ("+", ["plus"]),
        ("=", ["equals"]),
        ("5µm", ["5", "mu", "m"]),
        ("α-helix", ["alpha-helix"]),
        ("don’t", ["don't"]),
    ],
)
def test_speak_word(word, expected):
    assert speak_word(word, Rules.load()) == expected


def test_unknown_symbol_named():
    rules = Rules.load()
    assert speak_word("⊕", rules) == ["circled", "plus"]
    assert "⊕" in rules.unknown


def test_every_real_pack_symbol_has_rule():
    rules = Rules.load()
    for sym in PACK_SYMBOLS:
        speak_word(f"x{sym}1", rules)
        speak_word(sym, rules)
    assert rules.unknown == set()


def test_pronunciation_override():
    out = apply_pronunciations(["the", "Fisherian", "model"], {"Fisherian": "fisher-ee-an"})
    assert out == ["the", "fisher-ee-an", "model"]
    assert apply_pronunciations(["fisherian."], {"Fisherian": "fisher-ee-an"}) == ["fisher-ee-an."]
    phon = "[Fisherian](/fˈɪʃɚɹiən/)"
    assert apply_pronunciations(["Fisherian"], {"fisherian": phon}) == [phon]


def test_real_pack_has_no_unknown_symbols(real_pack):
    doc = extract(real_pack)
    rules = Rules.load()
    for block in doc.blocks:
        words = list(block.words)
        if block.table:
            words += [w for cell in block.table.header for w in cell]
            words += [w for row in block.table.rows for cell in row for w in cell]
        for w in words:
            speak_word(w.text, rules)
    assert rules.unknown == set()


def test_real_pack_tokens_have_no_brackets(real_pack):
    doc = extract(real_pack)
    rules = Rules.load()
    bad = set()
    for block in doc.blocks:
        words = list(block.words)
        if block.table:
            words += [w for cell in block.table.header for w in cell]
            words += [w for row in block.table.rows for cell in row for w in cell]
        for w in words:
            for tok in speak_word(w.text, rules):
                if any(c in tok for c in "()[]"):
                    bad.add(tok)
    assert bad == set()
