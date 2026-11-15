"""Build tests/fixtures/studypack_mini.pdf: a synthetic 3-page study pack.

It reproduces the visual signatures of the real study-pack template (colours,
bold/size relations, filled boxes, ruled tables, footer) with invented text,
so detection code can be tested on it without committing a real pack.

Usage: uv run python scripts/make_fixture.py
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "studypack_mini.pdf"
PLAIN_OUT = OUT.with_name("plain_report.pdf")

PAGE_W, PAGE_H = 612, 792
LEFT, RIGHT = 50.25, 562.5

# Fonts: DejaVu Sans has every glyph the fixture needs (², ½, ★, – and the
# combining macron in w̄), which the PDF base-14 fonts lack.
FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/Library/Fonts",
    "C:/Windows/Fonts",
]


def find_font(name: str) -> str:
    for d in FONT_DIRS:
        p = Path(d) / name
        if p.exists():
            return str(p)
    raise SystemExit(f"{name} not found; install DejaVu Sans to rebuild the fixture")


REG = find_font("DejaVuSans.ttf")
BOLD = find_font("DejaVuSans-Bold.ttf")
_FONTS = {"reg": pymupdf.Font(fontfile=REG), "bold": pymupdf.Font(fontfile=BOLD)}


def rgb(v: int) -> tuple[float, float, float]:
    return ((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255


TEXT = 0x1F2933
CITE = 0x55606C
CITE_SUB = 0x5C6774
TEAL = 0x0F6B6B
BANNER = 0x0E6A6A
RED = 0x9B1C1C
GREEN = 0x14602F
AMBER = 0x8A4A00
GREY = 0x4A5562
WHITE = 0xFFFFFF


def setup_fonts(page: pymupdf.Page) -> None:
    page.insert_font(fontname="dv", fontfile=REG)
    page.insert_font(fontname="dvb", fontfile=BOLD)


def width(text: str, size: float, bold: bool = False) -> float:
    return _FONTS["bold" if bold else "reg"].text_length(text, fontsize=size)


def put(page, x, y, text, size, color=TEXT, bold=False) -> float:
    """Draw one run with its baseline at y; return its right edge."""
    page.insert_text((x, y), text, fontname="dvb" if bold else "dv", fontsize=size, color=rgb(color))
    return x + width(text, size, bold)


def fill(page, rect, color) -> None:
    page.draw_rect(pymupdf.Rect(*rect), color=None, fill=rgb(color), width=0)


# A run is (text, style) with style in: "t" body, "b" body bold, "c" cite.
# A text beginning with "\b" attaches to the previous run with no space.
STYLE = {"t": (TEXT, False, 0), "b": (TEXT, True, 0), "c": (CITE, False, -1.9)}


def flow(page, x, y, w, runs, size=9.2, leading=1.42) -> float:
    """Word-wrap runs into a box; return the y just below the last line.

    Consecutive words of one style on a line are drawn as a single string, so
    PyMuPDF reports long spans (as in the real pack) rather than one per word.
    """
    space = width(" ", size)
    placed: list[list] = []  # [line, x, text, style]
    cx, line = x, 0
    for text, style in runs:
        _, bold, dsize = STYLE[style]
        s = size + dsize
        attach = text.startswith("\b")
        for i, word in enumerate(text.lstrip("\b").split()):
            ww = width(word, s, bold)
            gap = 0 if (attach and i == 0) or cx == x else space
            if cx + gap + ww > x + w and cx != x:
                line += 1
                cx, gap = x, 0
            last = placed[-1] if placed else None
            if last and last[0] == line and last[3] == style and gap:
                last[2] += " " + word
            elif last and last[0] == line and last[3] == style and not gap and cx != x:
                last[2] += word
            else:
                placed.append([line, cx + gap, word, style])
            cx += gap + ww
    for ln, px, text, style in placed:
        color, bold, dsize = STYLE[style]
        put(page, px, y + ln * size * leading, text, size + dsize, color, bold)
    return y + (line + 1) * size * leading


def lines(page, x, y, text_lines, size=9.2, leading=1.42, color=TEXT) -> float:
    """Draw explicitly broken lines (a paragraph wrapped mid-sentence)."""
    for i, t in enumerate(text_lines):
        put(page, x, y + i * size * leading, t, size, color)
    return y + len(text_lines) * size * leading


def footer(page, n: int, total: int) -> None:
    put(page, LEFT, 767, "Test pack: study notes", 8, GREY)
    label = f"Page {n} of {total}"
    put(page, RIGHT - width(label, 8), 767, label, 8, GREY)


def banner(page) -> None:
    fill(page, (LEFT, 36, RIGHT, 58), BANNER)
    put(page, LEFT + 10, 51, "Lecture 1: Test lecture", 11, WHITE, bold=True)


def subheading(page, y, title, cite) -> float:
    right = put(page, LEFT, y, title, 10.8, TEAL, bold=True)
    put(page, right + 4, y, cite, 8.6, CITE_SUB)
    return y + 15


def box(page, top, bottom, accent) -> None:
    fill(page, (LEFT + 1.5, top, RIGHT, bottom), BOX_FILL[accent])
    fill(page, (LEFT, top, LEFT + 3, bottom), accent)


BOX_FILL = {TEAL: 0xE8F2F1, GREEN: 0xECF5EF, AMBER: 0xFBF1E1}


def tag(page, x, y, label, color=0xB5530F) -> None:
    fill(page, (x, y, x + 90, y + 14), color)
    put(page, x + 45 - width(label, 8.2, True) / 2, y + 10.4, label, 8.2, WHITE, bold=True)


def table(page, top, cols, header, rows, row_h=28) -> float:
    bottom = top + 18 + row_h * len(rows)
    fill(page, (cols[0], top, cols[-1], top + 18), TEAL)
    grid = rgb(0xDFE5E5)
    ys = [top, top + 18] + [top + 18 + row_h * (i + 1) for i in range(len(rows))]
    for y in ys:
        page.draw_line((cols[0], y), (cols[-1], y), color=grid, width=0.75)
    for x in cols:
        page.draw_line((x, top), (x, bottom), color=grid, width=0.75)
    for i, h in enumerate(header):
        put(page, cols[i] + 5, top + 12.5, h, 8.8, WHITE, bold=True)
    for r, row in enumerate(rows):
        base = ys[r + 1] + 11.5
        for i, cell in enumerate(row):
            for k, t in enumerate(cell):
                put(page, cols[i] + 5, base + k * 11, t, 8.8, TEXT, bold=(i == 0 and k == 0))
    return bottom


def page_one(page) -> None:
    setup_fonts(page)
    banner(page)
    # Chunk number, title and "Likely tested" flag share one baseline.
    fill(page, (LEFT, 70, LEFT + 24, 94), TEAL)
    put(page, LEFT + 12 - width("1", 13, True) / 2, 87.5, "1", 13, WHITE, bold=True)
    put(page, LEFT + 34, 87.5, "Hardy-Weinberg basics", 14.5, TEXT, bold=True)
    put(page, RIGHT - width("★ Likely tested", 9, True), 87.5, "★ Likely tested", 9, RED, bold=True)
    put(page, LEFT, 106, "L1 deck, slides 2–7", 8.5, GREY)

    y = subheading(page, 126, "The principle", "(P1 5)")
    y = flow(page, LEFT, y + 2, RIGHT - LEFT, [
        ("Genotype frequencies follow p² + 2pq + q² = 1", "t"), ("(P1 5)", "c"), ("\b.", "t"),
        ("Allele frequencies hold steady when no force acts on them.", "t"), ("(P1 6)", "c"), ("\b.", "t"),
        ("The ratio dN/dS compares changes that alter a protein with silent ones.", "t"), ("(P1 6)", "c"),
        ("\b.", "t"),
    ])
    y = flow(page, LEFT, y + 5, RIGHT - LEFT, [
        ("Write the allele share as f[A1] and the mean fitness as w̄", "t"), ("(P1 7)", "c"), ("\b.", "t"),
        ("A carrier holds ½ of its alleles in common with a sibling.", "t"), ("(P1 7)", "c"), ("\b.", "t"),
    ])

    # Chain box: tag rects hold the step names, body text sits beside them.
    top = y + 12
    box(page, top, top + 74, TEAL)
    put(page, LEFT + 11, top + 14, "Chain: one generation", 9, TEAL, bold=True)
    for i, (name, runs) in enumerate([
        ("Entry", [("Parents contribute gametes to one shared pool.", "t"), ("(P1 8)", "c"), ("\b.", "t")]),
        ("Route", [("Gametes pair at random to form the next generation.", "t"), ("(P1 8)", "c"), ("\b.", "t")]),
    ]):
        ry = top + 24 + i * 22
        tag(page, LEFT + 11, ry, name)
        flow(page, LEFT + 110, ry + 10.4, RIGHT - LEFT - 120, runs, size=9.2)

    # Ruled three-column table.
    y = subheading(page, top + 74 + 24, "Quick check", "(P1 9)")
    table(page, y + 4, [LEFT, 180, 340, RIGHT], ["Question", "Answer", "Why"], [
        [["Q1: Is p stable?"], ["Yes, if no force acts"], ["Random mating", "keeps it fixed (P1 9)"]],
        [["Q2: Sum of p, q?"], ["Exactly 1"], ["Only two alleles", "exist here (P1 9)"]],
    ])
    footer(page, 1, 3)


def page_two(page) -> None:
    setup_fonts(page)
    banner(page)
    y = subheading(page, 84, "Where it applies", "(P2 10)")
    y = flow(page, LEFT, y + 2, RIGHT - LEFT, [
        ("Small founder groups drift quickly, so their frequencies wander from expectation", "t"),
        ("(P2 10)", "c"), ("\b.", "t"),
    ])
    y = lines(page, LEFT, y + 6, [
        "Over many generations a population can change until the shift we call evolu-",
        "tion has carried it far from where it began.",
    ])
    # Reasoning kit box with a Stated badge and a Traps label.
    top = y + 14
    box(page, top, top + 112, GREEN)
    put(page, LEFT + 11, top + 14, "Reasoning kit", 9, GREEN, bold=True)
    fill(page, (LEFT + 11, top + 24, LEFT + 50, top + 36), 0x1A7A3E)
    put(page, LEFT + 30.5 - width("Stated", 7.8, True) / 2, top + 33, "Stated", 7.8, WHITE, bold=True)
    flow(page, LEFT + 60, top + 33, RIGHT - LEFT - 70, [
        ("A population is in balance only when five conditions all hold.", "t"), ("(P2 11)", "c"),
        ("\b.", "t"),
    ])
    put(page, LEFT + 11, top + 56, "Traps", 9, RED, bold=True)
    flow(page, LEFT + 11, top + 70, RIGHT - LEFT - 22, [
        ("• Do not assume a large population is also randomly mating.", "t"), ("(P2 11)", "c"),
    ])
    flow(page, LEFT + 11, top + 87, RIGHT - LEFT - 22, [
        ("• Do not read a stable p as proof that selection is absent.", "t"), ("(P2 12)", "c"),
    ])
    # Analogy box.
    top = top + 112 + 16
    box(page, top, top + 54, AMBER)
    put(page, LEFT + 11, top + 14, "Analogy: shuffled deck", 9, AMBER, bold=True)
    flow(page, LEFT + 11, top + 30, RIGHT - LEFT - 22, [
        ("Dealing cards from a well shuffled deck never changes how many hearts the deck holds.", "t"),
        ("(P2 12)", "c"), ("\b.", "t"),
    ])
    footer(page, 2, 3)


def page_three(page) -> None:
    setup_fonts(page)
    banner(page)
    y = subheading(page, 84, "Worked example", "(P3 13)")
    y = flow(page, LEFT, y + 2, RIGHT - LEFT, [
        ("Suppose p = 0.6, so q = 0.4 and the heterozygotes make up 2pq = 0.48 of the group.", "t"),
        ("(P3 13)", "c"), ("\b.", "t"),
        ("The homozygote classes then hold p² = 0.36 and q² = 0.16.", "t"), ("(P3 14)", "c"), ("\b.", "t"),
    ])
    flow(page, LEFT, y + 5, RIGHT - LEFT, [
        ("Summing the three classes returns 1, which confirms the bookkeeping.", "t"), ("(P3 14)", "c"),
        ("\b.", "t"),
    ])
    footer(page, 3, 3)


PLAIN_PAGES = [
    ("Findings", [
        ["Water use fell across the region during the year [3].",
         "Smaller farms led the change (Smith et al., 2020) in most districts."],
        ["Researchers credit new irrigation schedules for the steady decline",
         "and expect the trend to continue next season."],
    ]),
    ("Methods", [
        ["Each site was visited monthly and readings were logged by hand.",
         "Totals were checked against meter records [4–5]."],
        ["Confidential: raw site names are withheld from this report."],
    ]),
    ("Outlook", [
        ["Planners will review the schedules again next spring (Jones, 2021a)",
         "before any new targets are set for the coming years."],
    ]),
]


def plain_page(page, n: int, heading: str, paragraphs: list[list[str]]) -> None:
    """A non-study-pack page: running header and footer, a heading and plain paragraphs."""
    setup_fonts(page)
    put(page, LEFT, 30, "Annual Report 2026", 9, GREY)
    put(page, LEFT, 90, heading, 18, TEXT, bold=True)
    y = 125.0
    for para in paragraphs:
        y = lines(page, LEFT, y, para, size=10.5) + 14
    label = f"- {n} -"
    put(page, PAGE_W / 2 - width(label, 9) / 2, 765, label, 9, GREY)


def make_plain_report() -> None:
    doc = pymupdf.open()
    for n, (heading, paragraphs) in enumerate(PLAIN_PAGES, 1):
        plain_page(doc.new_page(width=PAGE_W, height=PAGE_H), n, heading, paragraphs)
    doc.set_metadata({"title": "", "producer": "make_fixture.py", "creationDate": "", "modDate": ""})
    doc.save(str(PLAIN_OUT), garbage=4, deflate=True, no_new_id=True)
    print(f"wrote {PLAIN_OUT}")


def main() -> None:
    doc = pymupdf.open()
    for build in (page_one, page_two, page_three):
        build(doc.new_page(width=PAGE_W, height=PAGE_H))
    doc.set_toc([[1, "Lecture 1: Test lecture", 1], [2, "1 Hardy-Weinberg basics", 1]])
    doc.set_metadata({"title": "Test pack", "producer": "make_fixture.py", "creationDate": "", "modDate": ""})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT), garbage=4, deflate=True, no_new_id=True)
    print(f"wrote {OUT}")
    make_plain_report()


if __name__ == "__main__":
    main()
