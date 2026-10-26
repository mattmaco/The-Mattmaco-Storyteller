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


def _pdf_with(tmp_path, draw):
    doc = pymupdf.open()
    draw(doc.new_page(width=612, height=792))
    path = tmp_path / "gen.pdf"
    doc.save(str(path))
    return path


FILLER = " ".join(["words"] * 12)
SHORT = " ".join(["words"] * 4)  # fits within one column


def test_cite_with_space_after_comma(tmp_path):
    def draw(page):
        page.insert_text((50, 100), f"See [4, 5] and [6] now. {FILLER} {FILLER}", fontsize=10)

    doc = extract(_pdf_with(tmp_path, draw))
    text = _text(doc)
    assert text.startswith("See and now.")
    assert "[" not in text


def test_two_column_order(tmp_path):
    def draw(page):
        for x, tag in ((50, "A"), (330, "B")):
            for i, y in enumerate((100, 200), 1):
                page.insert_text((x, y), f"{tag}{i} {SHORT}", fontsize=10)
        # right column starts higher than the left's second block, so a y-sort would interleave
        page.insert_text((330, 150), f"B1b {SHORT}", fontsize=10)

    doc = extract(_pdf_with(tmp_path, draw))
    firsts = [b.words[0].text for b in doc.blocks]
    assert firsts == ["A1", "A2", "B1", "B1b", "B2"]


def test_heading3_bold_slightly_larger(tmp_path):
    def draw(page):
        page.insert_text((50, 100), "Sub topic", fontsize=11.5, fontname="hebo")
        for i in range(4):
            page.insert_text((50, 130 + 30 * i), f"para{i} {FILLER}", fontsize=10)

    doc = extract(_pdf_with(tmp_path, draw))
    assert doc.blocks[0].role == "heading3"
    assert all(b.role == "body" for b in doc.blocks[1:])
