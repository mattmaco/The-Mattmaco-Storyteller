import pymupdf
import pytest

from storyteller.extract import extract
from storyteller.extract.besteffort import NoTextLayerError


def _text(doc, role=None):
    return " ".join(
        w.text for b in doc.blocks if role is None or b.role == role for w in b.words
    )


def test_plain_not_studypack(plain_pdf):
    doc = extract(plain_pdf)
    assert doc.profile == "besteffort"
    assert doc.page_count == 3
    assert doc.title == "plain_report"
    assert all(b.words for b in doc.blocks)


def test_headings_and_outline(plain_pdf):
    doc = extract(plain_pdf)
    heads = [" ".join(w.text for w in b.words) for b in doc.blocks if b.role == "heading2"]
    assert heads == ["Findings", "Methods", "Outlook"]
    assert [(o.level, o.title, o.page) for o in doc.outline] == [
        (2, "Findings", 0), (2, "Methods", 1), (2, "Outlook", 2)
    ]
    assert all(b.role in ("heading2", "body") for b in doc.blocks)


def test_repeated_header_footer_removed(plain_pdf):
    text = _text(extract(plain_pdf))
    assert "Annual Report" not in text
    assert "- 1 -" not in text and "- 2 -" not in text
    assert "Water use fell" in text


def test_numeric_cites_removed(plain_pdf):
    text = _text(extract(plain_pdf))
    for gone in ("[3]", "[4–5]", "Smith", "Jones", "2020", "2021a"):
        assert gone not in text
    assert "year." in text  # punctuation reattached after the removed cite
    assert "changed" not in text and "Smaller farms led the change in most districts." in text


def test_skip_pattern(plain_pdf):
    assert "Confidential" in _text(extract(plain_pdf))
    doc = extract(plain_pdf, skip_patterns=["Confidential"])
    text = _text(doc)
    assert "Confidential" not in text and "withheld" not in text
    assert "Each site was visited" in text


def test_skip_patterns_not_shared_between_calls(plain_pdf):
    extract(plain_pdf, skip_patterns=["Confidential"])
    assert "Confidential" in _text(extract(plain_pdf))


def test_scanned_pdf_raises(tmp_path):
    img = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
    img.clear_with(200)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(50, 50, 300, 300), pixmap=img)
    path = tmp_path / "scan.pdf"
    doc.save(str(path))
    with pytest.raises(NoTextLayerError):
        extract(path)


def test_extract_mini_profile(mini_pdf):
    doc = extract(mini_pdf)
    assert doc.profile == "studypack"
    assert doc.title == "Test pack"
    assert doc.blocks and doc.outline


def test_real_pack_profile(real_pack):
    doc = extract(real_pack)
    assert doc.profile == "studypack"
    assert doc.title.strip()
