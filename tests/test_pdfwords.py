import pymupdf

from storyteller.extract.pdfwords import join_lines, read_spans, read_spans_with_chars, span_words
from storyteller.model import Word


def _w(text):
    return Word(text, 0, (0.0, 0.0, 1.0, 1.0))


def _texts(words):
    return [w.text for w in words]


def test_words_have_bboxes_on_page(mini_pdf):
    with pymupdf.open(mini_pdf) as doc:
        pairs = read_spans_with_chars(doc[0], 0)
        assert pairs
        words = [w for span, chars in pairs for w in span_words(span, chars)]
        assert [s.text for s in read_spans(doc[0], 0)] == [s.text for s, _ in pairs]
    assert words
    for w in words:
        x0, y0, x1, y1 = w.bbox
        assert x0 < x1 and y0 < y1
        assert 0 <= x0 and x1 <= 612 and 0 <= y0 and y1 <= 792
        assert w.page == 0
        assert w.text and not any(c.isspace() for c in w.text)


def test_no_whitespace_only_spans(mini_pdf):
    with pymupdf.open(mini_pdf) as doc:
        assert all(s.text.strip() for s in read_spans(doc[0], 0))


def test_combining_mark_stays_in_word():
    from storyteller.extract.pdfwords import RawSpan

    span = RawSpan("x̄ yz", 0, (0, 0, 40, 10), 9.0, 0, False, 0, 0)
    chars = [
        {"c": "x", "bbox": (0, 0, 5, 10)},
        {"c": "̄", "bbox": (0, 0, 5, 10)},
        {"c": " ", "bbox": (5, 0, 8, 10)},
        {"c": "y", "bbox": (8, 0, 13, 10)},
        {"c": "z", "bbox": (13, 0, 18, 10)},
    ]
    words = span_words(span, chars)
    assert _texts(words) == ["x̄", "yz"]
    assert words[1].bbox == (8, 0, 18, 10)


def test_join_lines_dehyphenates():
    assert _texts(join_lines([[_w("evolu-")], [_w("tion"), _w("acts")]])) == ["evolution", "acts"]


def test_join_lines_keeps_compound():
    assert _texts(join_lines([[_w("Hardy-")], [_w("Weinberg")]])) == ["Hardy-Weinberg"]


def test_join_lines_plain():
    assert _texts(join_lines([[_w("a"), _w("b")], [_w("c")]])) == ["a", "b", "c"]


def test_join_lines_no_merge_cases():
    assert _texts(join_lines([[_w("A-")], [_w("tion")]])) == ["A-", "tion"]
    assert _texts(join_lines([[_w("x-")], [_w("1")]])) == ["x-", "1"]
    assert _texts(join_lines([[], [_w("a")], []])) == ["a"]


def test_dehyphenated_keeps_first_bbox():
    first = Word("evolu-", 0, (1.0, 2.0, 3.0, 4.0))
    out = join_lines([[first], [_w("tion")]])
    assert out[0].bbox == first.bbox


def test_zero_width_ligature_letter_stays_in_word():
    from storyteller.extract.pdfwords import RawSpan

    span = RawSpan("ti", 0, (0, 0, 10, 10), 9.0, 0, False, 0, 0)
    chars = [
        {"c": "t", "bbox": (0, 0, 10, 10)},
        {"c": "i", "bbox": (10, 0, 10, 10)},  # zero width, full height
        {"c": "n", "bbox": (10, 0, 16, 10)},
    ]
    words = span_words(span, chars)
    assert _texts(words) == ["tin"]
    assert words[0].bbox == (0, 0, 16, 10)


def test_real_pack_keeps_ligature_letters(real_pack):
    import re

    bad = re.compile(r"\b(Evoluton|populaton|selecton)\b")
    with pymupdf.open(real_pack) as doc:
        texts = [
            w.text
            for i in range(6)
            for s, c in read_spans_with_chars(doc[i], i)
            for w in span_words(s, c)
        ]
    assert not [t for t in texts if bad.search(t)]
    assert "Evolution" in [t.strip(":,.;()") for t in texts]


class _FakePage:
    def __init__(self, spans):
        self._spans = spans

    def get_text(self, mode, sort=False):
        line = {"spans": self._spans}
        return {"blocks": [{"type": 0, "lines": [line]}]}


def _fake_span(chars, font="Helvetica", flags=0):
    return {"chars": chars, "font": font, "flags": flags, "size": 9.0, "color": 0x1F2933}


def test_zero_area_non_alnum_dropped():
    chars = [
        {"c": "a", "bbox": (0, 0, 5, 10)},
        {"c": "#", "bbox": (5, 0, 5, 10)},
        {"c": "b", "bbox": (5, 0, 10, 10)},
    ]
    (span,) = read_spans(_FakePage([_fake_span(chars)]), 3)
    assert span.text == "ab"
    assert span.page == 3


def test_span_bbox_ignores_whitespace_chars():
    chars = [
        {"c": " ", "bbox": (0, 0, 4, 10)},
        {"c": "a", "bbox": (4, 0, 9, 10)},
        {"c": " ", "bbox": (9, 0, 14, 10)},
    ]
    (span,) = read_spans(_FakePage([_fake_span(chars)]), 0)
    assert span.bbox == (4, 0, 9, 10)


def test_bold_rule():
    c = [{"c": "a", "bbox": (0, 0, 5, 10)}]
    spans = read_spans(
        _FakePage(
            [
                _fake_span(c, font="Foo-Bold"),
                _fake_span(c, font="Foo", flags=16),
                _fake_span(c, font="Foo", flags=0),
            ]
        ),
        0,
    )
    assert [s.bold for s in spans] == [True, True, False]
