# Storyteller Study Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A free, offline, read-along study reader that opens Matt's study-pack PDFs (and, best-effort, any PDF), reads them with Kokoro TTS, and highlights the current sentence and word on the real PDF page.

**Architecture:** A Python package (`storyteller`) turns a PDF into a *listening script* (extract → speechify), renders sentence clips with a pluggable voice backend (Kokoro or a silent stub), caches them per pack, and serves everything through FastAPI. A no-build vanilla-JS browser UI renders pages with pdf.js, overlays highlights from PDF coordinates, and plays clips with pitch-preserving speed control.

**Tech Stack:** Python 3.11–3.12, uv, PyMuPDF (`pymupdf`), FastAPI + uvicorn, platformdirs, numpy + soundfile, `kokoro` (optional extra, PyTorch CUDA 12.4 on Windows), pytest, Python Playwright for E2E; browser: ES modules, pdf.js `pdfjs-dist@4.10.38` (vendored).

**Spec:** `docs/superpowers/specs/2026-10-25-storyteller-study-reader-design.md` (read it before Task 1).

## Global Constraints

- Fully offline after install: no network calls at runtime except Kokoro's first-run weight download from Hugging Face.
- Never commit real study-pack PDFs (the repo is public). Real packs go in `tests/fixtures/local/` (git-ignored); tests that need them `pytest.skip` when absent.
- Nothing autoplays. Playback starts only on a user action (play button, `Space`, or click on a sentence).
- Speed range 0.75×–2.0×, step 0.05, default 1.0 (Kokoro at 1.0 ≈ 160 wpm; Task 8 measures and records the real figure). Speed is applied only in the browser (`playbackRate`, `preservesPitch = true`); audio is always rendered at Kokoro speed 1.0.
- Default pauses: sentence 250 ms, block 600 ms, section (after a heading) 1000 ms; constant across speeds.
- Default voice `af_heart`; preview list `af_heart, af_bella, af_nicole, am_michael, bf_emma, bm_george` (`b*` voices use Kokoro `lang_code="b"`, others `"a"`).
- Kokoro sample rate 24000 Hz; clips stored as 16-bit PCM WAV.
- App data under `platformdirs.user_data_dir("Storyteller", appauthor=False)`, overridable by env `STORYTELLER_HOME`.
- Voice backend chosen by env `STORYTELLER_VOICE` = `kokoro` (default) | `stub`.
- Server binds `127.0.0.1` only, default port 8765 (env `STORYTELLER_PORT`).
- No `spoken` text longer than 300 characters is ever sent to the voice backend; empty spoken text is never sent.
- Keyboard map (exact): `Space` play/pause · `←/→` prev/next sentence · `Shift+←/→` prev/next block · `↑/↓` prev/next chunk (outline level-2 entry) · `R` replay sentence · `[`/`]` slower/faster · `V` page/clean view · `T` skip current table.

## Study-pack template facts (measured on the real BIOL 2040 pack)

Coordinates are PyMuPDF points, top-left origin, Letter page 612 × 792. Colours are sRGB ints as PyMuPDF reports them.

| Thing | Signature |
|---|---|
| Body text | colour `0x1f2933`, not bold, size varies 8.5–9.9 (pages are shrink-fitted, so never key on exact size) |
| Slide cites `(P1 5)` | colour `0x5c6774` or `0x55606c`, not bold |
| Chunk source line `L8 deck, slides 2–7` | matches regex `\bdeck,? slides?\b` |
| Footer | spans with `y0 > page_height - 40`; text e.g. `BIOL 2040 Evolution, Lectures 8–13: study notes`, `Page 5 of 56` |
| Chunk title | colour `0x1f2933`, bold, size ≥ 1.35 × page body median |
| Chunk number circle | white `0xffffff` bold, digits only, size ≥ 12 |
| Subheading | colour `0x0f6b6b`, bold, size ≥ 1.05 × page body median, not inside a box |
| Lecture banner | white bold text inside a filled rect `#0e6a6a` of width > 300 |
| Chain step tag (Entry/Route/…) | white bold, ≤ 3 words, inside a filled rect of width < 120 |
| Table | `page.find_tables()` finds them correctly (chain boxes are *not* detected as tables); its cell *text* is garbled by ligatures, so take cell text from spans clipped to each cell bbox |
| Badges | text exactly `Stated` or `Follows`, bold, size < 8.5 |
| "★ Likely tested" flag | colour `0x9b1c1c`, text `★` or `Likely tested` |
| Boxes | a filled rect (width > 300) whose first contained span is a bold label; kind by label colour: `0x0f6b6b`→`chain`, `0x1d5a8e`→`figure`, `0x4a5562`→`note`, `0x8a4a00`→`analogy`, `0x9b1c1c`→`key`, `0x14602f`→`kit`. Inside a `kit` rect, a label `Traps` starts sub-kind `traps`. `note` sub-kind by label prefix: `What the slides don’t say`→`gap`, `Background`→`background`, `Reading aid`→`reading_aid`, else `note` |
| Outline | `doc.get_toc()` gives lectures (level 1) and chunks (level 2) |
| Detection | study pack ⇔ ≥ 3 pages whose footer matches `^Page \d+ of \d+$` **and** ≥ 20 spans with colour `0x1f2933` **and** ≥ 5 spans with colour in {`0x5c6774`,`0x55606c`} |

Symbols found in the real pack (all must have rules): `– ’ ² “ ” − ω × ★ ÷ µ ≈ ½ ̄ ′ Δ √ … Σ ≠ α á ¼`.

## Review Focus

1. **Re-adding a PDF already in the library** (same bytes) must return the existing pack and keep its reading position; a different file with the same filename must become a new pack. → test in Task 9.
2. **Rapid navigation** (holding `→`, clicking several sentences quickly) must never play two clips at once; only the latest request plays. → test in Task 14 (`test_rapid_navigation_single_audio`).
3. **Blocks that are entirely skipped content** (a line of only cites, a footer-only block) must produce no sentence, and no empty string ever reaches the voice backend. → test in Task 7.
4. **Kokoro token/word count mismatch** (e.g. `A1A2`, numbers, punctuation tokens) must still yield one `(start, end)` per spoken word, monotonic and within clip duration. → test in Task 8.
5. **Over-long sentences** (a table row or run-on > 300 chars) are split at `; , — :` boundaries before synthesis. → test in Task 7.

---

## File Structure

```
pyproject.toml                    uv project, extras: voice, dev
.gitignore                        includes tests/fixtures/local/, .venv/, __pycache__/
install.bat, run.bat              Windows setup and launcher (Task 15)
scripts/make_fixture.py           builds tests/fixtures/studypack_mini.pdf (Task 1)
scripts/fetch_vendor.py           downloads pdf.js into storyteller/web/vendor/ (Task 11)
storyteller/
  __init__.py
  __main__.py                     CLI: `serve`, `script <pdf>` (Task 10)
  model.py                        dataclasses shared by all modules (Task 1)
  extract/
    __init__.py                   extract(path) -> Document (Task 5)
    pdfwords.py                   char→word assembly, line joining (Task 2)
    studypack.py                  detection + role/box classification (Task 3)
    tables.py                     table detection + cell text (Task 4)
    besteffort.py                 repeated header/footer + cite heuristics (Task 5)
  speech/
    __init__.py                   build_script(doc, settings) -> Script (Task 7)
    symbols.py, symbols.toml      symbol rulebook (Task 6)
    pronounce.py                  pronunciation list (Task 6)
    sentences.py                  sentence splitting + long-sentence split (Task 7)
    tables.py                     table linearisation (Task 7)
  voice/
    __init__.py                   get_backend() (Task 8)
    base.py                       VoiceBackend protocol, SynthResult, align_words (Task 8)
    stub.py, kokoro_backend.py    (Task 8)
  settings.py                     Settings dataclass, load/save (Task 9)
  library.py                      packs, cache, positions (Task 9)
  worker.py                       priority render queue (Task 10)
  server.py                       FastAPI app (Task 10)
  web/
    library.html, reader.html, style.css
    js/api.js, js/pages.js, js/highlight.js, js/player.js,
    js/keys.js, js/outline.js, js/cleanview.js, js/settings.js, js/reader.js, js/library.js
    vendor/pdfjs/ (pdf.mjs, pdf.worker.mjs)
tests/
  conftest.py                     fixture paths, STORYTELLER_HOME tmp, stub voice
  fixtures/studypack_mini.pdf     committed synthetic pack
  fixtures/plain_report.pdf       committed synthetic non-pack PDF (Task 5)
  fixtures/local/                 git-ignored real packs (biol2040.pdf)
  test_*.py                       per task
  e2e/test_reader.py              Playwright (Task 14)
```

---

### Task 1: Project scaffold, shared model, synthetic fixture

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `storyteller/__init__.py`, `storyteller/model.py`, `scripts/make_fixture.py`, `tests/conftest.py`, `tests/test_model.py`, `tests/fixtures/studypack_mini.pdf` (generated)

**Interfaces:**
- Produces (`storyteller/model.py`, all `@dataclass` with `to_dict()`/`from_dict()` for JSON):
  - `BBox = tuple[float, float, float, float]` (x0, y0, x1, y1)
  - `Word(text: str, page: int, bbox: BBox)` — page is 0-based
  - `Block(id: str, role: str, words: list[Word], page: int, lead: str | None = None, box_kind: str | None = None, table: "Table | None" = None, flagged: bool = False)` — `flagged` marks a chunk heading carrying the "★ Likely tested" flag; `role` ∈ {`heading1`,`heading2`,`heading3`,`body`,`box_label`,`table`}; `id` = `f"b{page:03d}_{n:03d}"`
  - `Table(header: list[list[Word]], rows: list[list[list[Word]]])` — each cell is a list of Words
  - `OutlineEntry(level: int, title: str, page: int, y: float, sentence_id: str | None = None)`
  - `Document(profile: str, page_count: int, blocks: list[Block], outline: list[OutlineEntry], title: str)`; `profile` ∈ {`studypack`,`besteffort`}
  - `SpokenWord(text: str, word_index: int)` — index into the owning sentence's `display: list[Word]`
  - `Sentence(id: str, block_id: str, spoken: list[SpokenWord], display: list[Word], pause_after_ms: int, kind: str)`; `id` = `f"s{n:05d}"`; `kind` ∈ {`heading`,`body`,`table`,`box_label`}; property `spoken_text -> str` = `" ".join(w.text for w in spoken)`
  - `Script(pack_id: str, profile: str, title: str, sentences: list[Sentence], outline: list[OutlineEntry], page_count: int)`

- [ ] **Step 1:** Create `pyproject.toml`: `requires-python = ">=3.11,<3.13"`; deps `pymupdf>=1.24`, `fastapi`, `uvicorn[standard]`, `python-multipart`, `platformdirs`, `numpy`, `soundfile`; extra `voice = ["kokoro>=0.9.4", "torch"]`; extra `dev = ["pytest", "playwright", "httpx"]`; uv sources so Windows gets CUDA torch:
  ```toml
  [tool.uv.sources]
  torch = [{ index = "pytorch-cu124", marker = "sys_platform == 'win32'" }]
  [[tool.uv.index]]
  name = "pytorch-cu124"
  url = "https://download.pytorch.org/whl/cu124"
  explicit = true
  ```
  `.gitignore`: `.venv/`, `__pycache__/`, `tests/fixtures/local/`, `*.egg-info/`.
- [ ] **Step 2:** Write `tests/test_model.py::test_script_roundtrip` — build a `Script` with one `Sentence` (two `SpokenWord`s, two `Word`s) and an `OutlineEntry`; assert `Script.from_dict(json.loads(json.dumps(s.to_dict()))) == s` and `sentence.spoken_text == "p squared"` for spoken words `["p", "squared"]`.
- [ ] **Step 3:** Run `uv run --extra dev pytest tests/test_model.py -v` → FAIL (import error).
- [ ] **Step 4:** Implement `storyteller/model.py` per Interfaces.
- [ ] **Step 5:** Run the test → PASS.
- [ ] **Step 6:** Write `scripts/make_fixture.py` that uses PyMuPDF to draw a 3-page Letter PDF reproducing the template table above (Helvetica is fine; detection must not key on font names): page 1 lecture banner (rect `#0e6a6a`, white bold 11 pt "Lecture 1: Test lecture"), chunk number "1" (white bold 13 pt) + chunk title (bold `0x1f2933` 14.5 pt "Hardy-Weinberg basics"), a source line "L1 deck, slides 2–7", a subheading (bold `0x0f6b6b` 10.8 pt "The principle") followed by a cite "(P1 5)" in `0x5c6774` 8.6 pt, body sentences containing `p² + 2pq + q² = 1`, `dN/dS`, `f[A1]`, `w̄`, `½`, each followed by a cite in `0x55606c`; a chain box (rect `#e8f2f1`, label bold `0x0f6b6b` "Chain: one generation", rows with tag rects `#b5530f` width 90 holding white bold "Entry"/"Route" and body text beside them); a 3-column table drawn with ruled lines (header "Question | Answer | Why", 2 rows); a `kit` box (rect `#ecf5ef`, label bold `0x14602f` "Reasoning kit", items "Stated" badge bold 7.8 pt + text, then label "Traps" in `0x9b1c1c` and two bullet lines); a `★ Likely tested` flag in `0x9b1c1c` beside the chunk title; an `analogy` box (label `0x8a4a00`); a body paragraph that wraps across two lines mid-sentence; footer on every page at y=767 "Test pack: study notes" and "Page N of 3"; TOC via `doc.set_toc([[1,"Lecture 1: Test lecture",1],[2,"1 Hardy-Weinberg basics",1]])`. Run `uv run python scripts/make_fixture.py` and commit `tests/fixtures/studypack_mini.pdf`.
- [ ] **Step 7:** `tests/conftest.py`: fixtures `mini_pdf` (path), `real_pack` (path to `tests/fixtures/local/biol2040.pdf`, `pytest.skip("real pack not present")` if missing), autouse `monkeypatch.setenv("STORYTELLER_HOME", tmp_path)` and `STORYTELLER_VOICE=stub`.
- [ ] **Step 8:** Commit: `git add -A && git commit -m "feat: project scaffold, shared model, synthetic study-pack fixture"`

---

### Task 2: PDF words and line joining

**Files:**
- Create: `storyteller/extract/__init__.py` (empty for now), `storyteller/extract/pdfwords.py`, `tests/test_pdfwords.py`

**Interfaces:**
- Consumes: `Word`, `BBox` (Task 1)
- Produces:
  - `RawSpan(text: str, page: int, bbox: BBox, size: float, color: int, bold: bool, block_no: int, line_no: int)` dataclass
  - `read_spans(page: pymupdf.Page, page_no: int) -> list[RawSpan]` — from `page.get_text("rawdict", sort=False)`, dropping whitespace-only spans and zero-area glyphs; `bold` = `"Bold" in font or flags & 16`
  - `span_words(span: RawSpan, chars: list) -> list[Word]` — splits on whitespace using per-char bboxes; a word's bbox is the union of its chars
  - `join_lines(lines: list[list[Word]]) -> list[Word]` — concatenates; de-hyphenation rule below

De-hyphenation: if a line's last word ends with `-` and the next line's first word starts with a lowercase letter **and** the char before `-` is lowercase, merge the two into one Word (hyphen removed, bbox = first part's bbox — highlight shows the first half, acceptable). If the next word starts uppercase (e.g. `Hardy-` / `Weinberg`), merge keeping the hyphen. Otherwise no merge.

- [ ] **Step 1:** Tests: `test_words_have_bboxes_on_page` (every Word from page 0 of `mini_pdf` has `x0<x1, y0<y1` within 612×792); `test_join_lines_dehyphenates` (`[["evolu-"],["tion","acts"]]` → texts `["evolution","acts"]`); `test_join_lines_keeps_compound` (`[["Hardy-"],["Weinberg"]]` → `["Hardy-Weinberg"]`); `test_join_lines_plain` (`[["a","b"],["c"]]` → `["a","b","c"]`).
- [ ] **Step 2:** Run `uv run --extra dev pytest tests/test_pdfwords.py -v` → FAIL.
- [ ] **Step 3:** Implement `pdfwords.py` per Interfaces.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: pdf word extraction and line joining`.

---

### Task 3: Study-pack detection and classification

**Files:**
- Create: `storyteller/extract/studypack.py`, `tests/test_studypack.py`

**Interfaces:**
- Consumes: `read_spans`, `span_words`, `join_lines` (Task 2); model types (Task 1)
- Produces:
  - `is_studypack(doc: pymupdf.Document) -> bool` — the Detection rule from the template table
  - `classify_span(span: RawSpan, ctx: PageContext) -> str` returning one of `footer, cite, flag, badge, chunk_number, banner, tag, heading2, heading3, box_label, table, body`
  - `PageContext(page_height: float, body_median: float, boxes: list[Box], table_rects: list[BBox], tag_rects: list[BBox])` where `Box(rect: BBox, kind: str)` — built by `page_context(page, spans, table_rects) -> PageContext` from `page.get_drawings()` (filled rects) and the box rules in the template table
  - `studypack_blocks(doc: pymupdf.Document) -> list[Block]`

Assembly rules for `studypack_blocks` (in PyMuPDF native order — Chromium writes DOM order, which is the right reading order):
- Drop spans classified `footer`, `cite`, `flag`, and the chunk source line; a `flag` on the same line as a `heading2` sets that block's `flagged = True`. Drop everything on page 0 inside the chunk-map table rect (the outline replaces it).
- Spans of one PyMuPDF block form one `Block`, lines joined with `join_lines`, then whitespace before `. , ; : ? ! )` collapsed (cites removed mid-sentence leave `genotypes .`).
- `chunk_number` digits are held and prefixed to the next `heading2` block's lead as `"Chunk {n}."`.
- `banner` → `heading1`; `tag` and `badge` set `lead` on the **next** body block (`"Entry:"`, `"Stated:"`) and produce no block of their own.
- `box_label` → block role `box_label`; it and every following block whose centre lies inside the same `Box.rect` get `box_kind` = that box's kind/sub-kind.
- Table spans are skipped here; Task 4 inserts table blocks at the right position (by page and y).

- [ ] **Step 1:** Tests on `mini_pdf`: `test_detects_studypack` (True); `test_no_footer_or_page_numbers` (no Block text matches `Page \d+ of \d+` or `study notes`); `test_no_cites` (no Block text matches `\(P\d`); `test_source_line_dropped` (no text contains `deck, slides`); `test_chain_tags_become_leads` (a block with `lead == "Entry:"` and `box_kind == "chain"`); `test_chunk_heading` (a `heading2` block whose lead is `"Chunk 1."` and text `Hardy-Weinberg basics`); `test_flag_dropped` (no `★`, no `Likely tested`); `test_banner_heading1`; `test_box_kinds` (kinds found ⊇ `{"chain","kit","traps","analogy"}`); `test_wrapped_paragraph_one_block` (the two-line paragraph is one block). On `real_pack`: `test_real_pack_detected`, `test_real_pack_no_noise` (no `Page \d+ of 56`, no `\(P\d \d`, no `\((Lk|SS) \d`).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `studypack.py`.
- [ ] **Step 4:** Run → PASS (real-pack tests PASS or SKIP).
- [ ] **Step 5:** Commit `feat: study-pack detection and role classification`.

---

### Task 4: Tables and outline

**Files:**
- Create: `storyteller/extract/tables.py`, `tests/test_tables.py`
- Modify: `storyteller/extract/studypack.py` (insert table blocks)

**Interfaces:**
- Produces:
  - `find_tables(page: pymupdf.Page, page_no: int, spans: list[RawSpan]) -> list[tuple[BBox, Table]]` — regions from `page.find_tables()`; each cell's Words are built from spans/chars whose centre lies in the cell bbox (never from `table.extract()` text); row 0 is the header; empty cells → `[]`; cites inside cells dropped.
  - `build_outline(doc: pymupdf.Document) -> list[OutlineEntry]` — from `doc.get_toc(simple=False)`; `y` from the entry's destination point (0 if missing); level-2 titles keep the TOC text.

- [ ] **Step 1:** Tests: `test_mini_table` (one table on `mini_pdf`, header texts `["Question","Answer","Why"]`, 2 body rows); `test_table_block_position` (in `studypack_blocks`, the `table` block comes after the paragraph above it and before the block below it); `test_outline_mini` (`[(1,"Lecture 1: Test lecture"),(2,"1 Hardy-Weinberg basics")]` by level/title); `test_real_pack_tables` (page index 4 has 2 tables; first header `["Question","Answer","Why"]`; no cell text contains a ligature-split like `Questoi`); `test_real_outline_has_35_chunks` (35 level-2 entries whose title starts with a digit).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: table extraction and outline`.

---

### Task 5: Best-effort profile and `extract()`

**Files:**
- Create: `storyteller/extract/besteffort.py`, `tests/test_besteffort.py`, `tests/fixtures/plain_report.pdf` (generated by a function added to `scripts/make_fixture.py`)
- Modify: `storyteller/extract/__init__.py`

**Interfaces:**
- Produces:
  - `besteffort_blocks(doc: pymupdf.Document, skip_patterns: list[str]) -> list[Block]` — uses `get_text("rawdict", sort=True)`; header/footer = normalised text (digits replaced by `#`) appearing within the top or bottom 8 % of the page on ≥ 50 % of pages (min 2 pages); cites = regex `\[\d+(?:[,–-]\d+)*\]` and `\([A-Z][A-Za-z]+(?: et al\.)?,? \d{4}[a-z]?\)` removed from words; each `skip_patterns` entry is a regex — words of any block whose text matches are dropped; headings = size ≥ 1.25 × body median → `heading2`, bold and ≥ 1.1× → `heading3`; tables via `find_tables`.
  - `extract(path: str | Path, skip_patterns: list[str] = []) -> Document` — opens the PDF, raises `NoTextLayerError` (defined here) if the PDF has fewer than 20 words total, picks the profile with `is_studypack`, title = PDF metadata title or file stem, outline = `build_outline` (best-effort: if empty, synthesize level-2 entries from `heading2` blocks).

- [ ] **Step 1:** Extend `make_fixture.py` with `plain_report.pdf`: 3 pages, running header "Annual Report 2026" and footer "- N -" on each page, a heading, paragraphs with `[3]` and `(Smith et al., 2020)` cites. Generate and commit.
- [ ] **Step 2:** Tests: `test_plain_not_studypack`; `test_repeated_header_footer_removed`; `test_numeric_cites_removed`; `test_skip_pattern` (`skip_patterns=["Confidential"]` drops a block containing it); `test_scanned_pdf_raises` (a PDF made in-test with an image only → `NoTextLayerError`); `test_extract_mini_profile` (`extract(mini_pdf).profile == "studypack"`).
- [ ] **Step 3:** Run → FAIL. **Step 4:** Implement. **Step 5:** Run → PASS. **Step 6:** Commit `feat: best-effort extraction profile`.

---

### Task 6: Symbol rulebook and pronunciation list

**Files:**
- Create: `storyteller/speech/__init__.py` (stub), `storyteller/speech/symbols.toml`, `storyteller/speech/symbols.py`, `storyteller/speech/pronounce.py`, `tests/test_symbols.py`

**Interfaces:**
- Produces:
  - `speak_word(text: str, rules: Rules) -> list[str]` — spoken tokens for one display word (may be empty, e.g. a bare `★`)
  - `Rules.load(overrides: dict[str, str] | None = None) -> Rules`; `Rules.unknown: set[str]` collects symbols with no rule
  - `apply_pronunciations(tokens: list[str], lexicon: dict[str, str]) -> list[str]` — case-insensitive whole-token replacement; value may be a respelling or Kokoro inline phonemes `[word](/phonemes/)` (passed through unchanged)

Rule order inside `speak_word`: (1) strip surrounding quotes/brackets and trailing punctuation (keep `. , ; : ? !` as a separate trailing token attached to the last word so Kokoro still hears the boundary), (2) whole-word patterns, (3) per-character symbol map, (4) unknown non-ASCII characters that are not letters (`unicodedata.category(ch)[0] != "L"`, so `á` passes through) → `unicodedata.name(ch).lower()` and added to `rules.unknown`.

`symbols.toml` contents (exact):
```toml
[patterns]   # regex → template; applied to the whole word
'^dN/dS$' = "d N over d S"
'^f\[([A-Za-z]\d?)\]$' = "frequency of {1}"
'^([A-Z])(\d)([A-Z])(\d)$' = "{1} {2} {3} {4}"          # A1A2 → A 1 A 2
[chars]
"²" = " squared"
"³" = " cubed"
"′" = " prime"
"̄" = " bar"
"ω" = "omega"
"Δ" = "delta "
"Σ" = "sum of "
"√" = "square root of "
"½" = "one half"
"¼" = "one quarter"
"×" = " times "
"÷" = " divided by "
"−" = " minus "
"≈" = " approximately "
"≠" = " is not equal to "
"µ" = "mu"
"α" = "alpha"
"★" = ""
"…" = "..."
"–" = " to "          # en dash between numbers (2–7); see test
"’" = "'"
"“" = ""
"”" = ""
"+" = " plus "
"=" = " equals "
```
Implemented in code, not the TOML: a lowercase token of 2–3 letters immediately preceded by a digit and made only of `p` and `q` (e.g. `2pq`) is spoken digit-then-letters separated (`two p q` via `"2", "p", "q"`). En dash `–` becomes `to` only between digits (`2–7` → `2 to 7`); elsewhere it becomes a pause comma.

- [ ] **Step 1:** Tests (parametrised `test_speak_word`): `p²`→`["p","squared"]`; `q²`→`["q","squared"]`; `2pq`→`["2","p","q"]`; `p′`→`["p","prime"]`; `w̄` (w + U+0304)→`["w","bar"]`; `ω`→`["omega"]`; `Δp`→`["delta","p"]`; `½`→`["one","half"]`; `dN/dS`→`["d","N","over","d","S"]`; `f[A1]`→`["frequency","of","A1"]`; `A1A2`→`["A","1","A","2"]`; `2–7`→`["2","to","7"]`; `≈`→`["approximately"]`; `★`→`[]`; `genotypes.`→`["genotypes."]`. Plus `test_unknown_symbol_named` (`"⊕"` → `["circled","plus"]` and `"⊕" in rules.unknown`); `test_every_real_pack_symbol_has_rule` (for each symbol in the template list, `speak_word` adds nothing to `rules.unknown`); `test_pronunciation_override` (`{"Fisherian": "fisher-ee-an"}` replaces the token).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: symbol rulebook and pronunciation list`.

---

### Task 7: Sentences, table linearisation, `build_script`

**Files:**
- Create: `storyteller/speech/sentences.py`, `storyteller/speech/tables.py`, `tests/test_script.py`
- Modify: `storyteller/speech/__init__.py`

**Interfaces:**
- Consumes: `Document`, `Block`, `Table`, `Sentence`, `SpokenWord`, `Script` (Task 1); `speak_word`, `Rules`, `apply_pronunciations` (Task 6); `Settings` fields `pauses`, `read_boxes`, `read_badges`, `skip_flags`, `pronunciations` (defined in Task 9; define `ScriptOptions` dataclass here with the matching fields and defaults, `read_flags = not skip_flags`, and have Task 9's `Settings.script_options()` return it)
- Produces:
  - `split_sentences(words: list[Word]) -> list[list[Word]]` — boundary after a word ending in `. ? !` (optionally followed by a closing quote/bracket) when the next word starts uppercase, a digit or a quote; never after abbreviations `e.g. i.e. vs. etc. et al. Fig. Figs. approx. cf. No. St. Dr.` or a single capital + `.`; never inside parentheses
  - `split_long(spoken: list[SpokenWord], limit: int = 300) -> list[list[SpokenWord]]` — splits after the last token ending in `;` `,` `—` `:` that keeps each part ≤ limit chars; hard split at a word boundary if none
  - `linearise_table(table: Table) -> list[tuple[list[str], list[Word]]]` — first item: announcement `"Table, {n} rows: {h1}, {h2}, {h3}."` (`row` when n == 1) with all header Words as display; then per row: for each non-empty cell `"{header}: {cell text}."`, display = that row's Words
  - `ScriptOptions(pauses: dict[str,int] = {"sentence":250,"block":600,"section":1000}, read_boxes: dict[str,bool] = {all kinds True}, read_badges: bool = True, read_flags: bool = False, pronunciations: dict[str,str] = {})` — when `read_flags`, a `flagged` heading is followed by the spoken words `Likely tested.`
  - `build_script(doc: Document, pack_id: str, opts: ScriptOptions) -> Script`

`build_script` rules: skip blocks whose `box_kind` maps to `False` in `read_boxes`; `lead` is spoken first (badges only if `read_badges`) and displayed on the block's first word; each sentence's `pause_after_ms` = `section` if the block is a heading, else `block` for the last sentence of a block, else `sentence`; drop sentences whose spoken text is empty; outline entries get `sentence_id` = first sentence at or after the entry's `(page, y)`; ids are sequential `s00000…`.

- [ ] **Step 1:** Tests: `test_split_basic` (`"Hello there. Next one."` → 2); `test_no_split_abbrev` (`"See Fig. 7 and e.g. this. Done."` → 2); `test_no_split_decimal` (`"p = 0.6 here. Ok."` → 2); `test_split_long` (a 700-char comma list → every part ≤ 300 chars, rejoined text equals the original); `test_linearise_table` (header Question/Answer/Why, one row → joined token strings `["Table, 1 row: Question, Answer, Why.", "Question: Q1. Answer: f[A1] = p. Why: sums to one."]` before symbol rules); `test_mini_script_noise_free` (no sentence spoken text matches `Page \d|\(P\d|deck, slides|★`); `test_mini_script_leads` (some sentence starts `Entry:`; some starts `Chunk 1.`); `test_mini_script_formula` (some sentence contains `p squared plus 2 p q plus q squared equals 1`); `test_no_empty_sentences` (a Document with a block whose only words are cites/★ → no sentence with empty `spoken_text`); `test_read_flags` (`read_flags=True` → a sentence `Likely tested.` follows the chunk heading; default → none); `test_pause_values` (heading → 1000, last-in-block → 600, otherwise 250); `test_skip_box_kind` (`read_boxes["analogy"]=False` → no sentence with `block_id` of the analogy box); `test_outline_sentence_ids` (every outline entry has a `sentence_id` that exists); `test_real_pack_script` (real pack: > 500 sentences, no noise, 35 chunk outline entries with ids).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: listening script builder`.

---

### Task 8: Voice backends and word alignment

**Files:**
- Create: `storyteller/voice/__init__.py`, `storyteller/voice/base.py`, `storyteller/voice/stub.py`, `storyteller/voice/kokoro_backend.py`, `tests/test_voice.py`

**Interfaces:**
- Produces:
  - `SynthResult(audio: np.ndarray, sample_rate: int, word_times: list[tuple[float, float]])` — `audio` float32 mono; `len(word_times) == number of spoken words requested`
  - `class VoiceBackend(Protocol): device: str; notice: str | None; def synth(self, words: list[str], voice: str) -> SynthResult`
  - `align_words(words: list[str], tokens: list[tuple[str, float | None, float | None]], duration: float) -> list[tuple[float, float]]`
  - `StubVoice` — `device="stub"`; 0.06 s per character of `" ".join(words)`, silence; word times proportional to character length
  - `KokoroVoice(device: str | None = None)` — `torch.cuda.is_available()` → `"cuda"` else `"cpu"`; if CUDA init raises, fall back to CPU and set `notice = "GPU unavailable, using CPU"`; keeps one `KPipeline` per lang code (`voice[0]` is `a` or `b`); `synth` runs `pipeline(" ".join(words), voice=voice, speed=1.0, split_pattern=None)`, concatenates audio of all results (with time offsets), and passes each `result.tokens` entry's `(text, start_ts, end_ts)` to `align_words`
  - `get_backend() -> VoiceBackend` — from env `STORYTELLER_VOICE`, cached singleton

`align_words` algorithm (deterministic):
1. Drop tokens whose text is only punctuation. Keep their order.
2. Walk words and tokens with two pointers, comparing normalised text (lowercase, strip non-alphanumerics). When a word equals the concatenation of 1+ consecutive tokens, assign it `(first.start, last.end)`.
3. If matching fails at any point, or any timestamp is `None`, discard all and fall back to proportional: distribute `[0, duration]` across words by character length.
4. Clamp to `[0, duration]` and force non-decreasing starts.

- [ ] **Step 1:** Tests: `test_align_exact` (words `["p","squared"]`, tokens `[("p",0.0,0.2),("squared",0.2,0.7)]` → `[(0.0,0.2),(0.2,0.7)]`); `test_align_multi_token_word` (word `"A1"` vs tokens `("A",0,0.1),("1",0.1,0.3)` → `(0,0.3)`); `test_align_mismatch_proportional` (tokens disagree → `len == len(words)`, monotonic, last end == duration); `test_align_none_timestamps` (→ proportional); `test_stub_lengths` (StubVoice on 3 words → 3 times, audio length ≈ 0.06 × chars × 24000); `test_kokoro_smoke` (`pytest.importorskip("kokoro")`; synth `["Hardy-Weinberg","equilibrium."]` with `af_heart` → audio length > 0, 2 monotonic word times); `test_kokoro_wpm` (importorskip; a 60-word paragraph; print measured wpm at speed 1.0 — record the number in `README.md` under "Voice notes"; no assertion).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS (Kokoro tests SKIP without the extra). **Step 5:** If a machine with the `voice` extra is available, run `uv run --extra voice --extra dev pytest tests/test_voice.py -v -s` and record wpm. **Step 6:** Commit `feat: voice backends with word alignment`.

---

### Task 9: Settings and library

**Files:**
- Create: `storyteller/settings.py`, `storyteller/library.py`, `tests/test_library.py`

**Interfaces:**
- Consumes: `extract` (Task 5), `build_script`, `ScriptOptions` (Task 7), `SynthResult` (Task 8)
- Produces:
  - `Settings` dataclass: `speed: float = 1.0`, `voice: str = "af_heart"`, `pauses: dict` (Task 7 defaults), `read_boxes: dict` (all True), `read_badges: bool = True`, `skip_flags: bool = True`, `highlight_sentence: bool = True`, `highlight_word: bool = True`, `sentence_color: str = "#fff3b0"`, `word_color: str = "#f2a900"`, `pronunciations: dict[str,str] = {}`, `unknown_symbols: list[str] = []`; `load() -> Settings`, `save()`, `script_options() -> ScriptOptions`; JSON at `$HOME/settings.json`; `speed` clamped to 0.75–2.0 on load
  - `home() -> Path` (env `STORYTELLER_HOME` or platformdirs)
  - `PackInfo(id: str, title: str, filename: str, page_count: int, position: str | None, rendered: int, total: int, added: str)`
  - `Library` with: `add_pdf(data: bytes, filename: str) -> PackInfo` (id = first 16 hex of sha256; if exists, return existing unchanged); `list() -> list[PackInfo]` (most recent first); `pdf_path(id) -> Path`; `script(id) -> Script` (cached in `packs/<id>/script.json`; rebuilt when missing or when `rebuild_script(id)` is called); `rebuild_script(id)` (after building, merges `Rules.unknown` into `Settings.unknown_symbols` and saves); `set_position(id, sentence_id)`; `add_skip_pattern(id, regex)` (stored in `packs/<id>/skip.json`, triggers rebuild); `clip_path(id, sentence, voice) -> Path` = `packs/<id>/clips/<voice>/<sha1(spoken_text)[:16]>.wav`; `save_clip(path, result: SynthResult)` writes WAV + sibling `.json` `{"duration":…, "words":[[s,e],…]}`; `load_clip_meta(path) -> dict | None`
  - Layout: `$HOME/packs/<id>/{source.pdf, meta.json, script.json, skip.json, clips/}`

- [ ] **Step 1:** Tests: `test_add_same_bytes_returns_existing` (add twice → same id; `set_position` between adds is preserved); `test_same_name_different_bytes_new_pack`; `test_script_cached_and_rebuilt` (script.json created; `add_skip_pattern` changes sentence count); `test_clip_roundtrip` (save stub result, `load_clip_meta` returns same word count); `test_settings_roundtrip_and_clamp` (speed 5 → loads as 2.0); `test_clip_path_independent_of_speed` (changing `settings.speed` does not change `clip_path`); `test_scanned_pdf_add_raises` (`NoTextLayerError` propagates and no pack directory is left behind).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: settings and pack library`.

---

### Task 10: Render worker, server and CLI

**Files:**
- Create: `storyteller/worker.py`, `storyteller/server.py`, `storyteller/__main__.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `Library`, `Settings` (Task 9), `get_backend` (Task 8)
- Produces:
  - `RenderWorker(library, backend)` — one background thread; `focus(pack_id, sentence_id)` sets the render cursor (renders from that sentence forward to the pack end, then wraps to the start); `render_now(pack_id, sentence_id) -> Path` synchronously renders one clip (called by the clip endpoint when not cached; uses a lock shared with the thread); failures are recorded in `failed: set[(pack_id, sentence_id)]` and never raise out of the thread; `status(pack_id) -> {"rendered": int, "total": int}`
  - FastAPI routes (JSON unless noted):
    - `GET /` → `web/library.html`; `GET /read/{id}` → `web/reader.html`; static `/web/*`
    - `POST /api/packs` (multipart `file`) → `PackInfo`; `422 {"error":"no_text_layer","message":"This PDF has no text layer (it looks scanned). Storyteller can't read it yet."}` on `NoTextLayerError`
    - `GET /api/packs` → `list[PackInfo]`
    - `GET /api/packs/{id}/pdf` → PDF bytes
    - `GET /api/packs/{id}/script` → `Script.to_dict()`
    - `GET /api/packs/{id}/clip/{sid}` → `{"url": "/api/packs/{id}/audio/{voice}/{name}.wav", "duration": float, "words": [[s,e],…]}`; renders on demand; `{"error":"synth_failed"}` with 500 if synthesis fails
    - `GET /api/packs/{id}/audio/{voice}/{name}.wav` → WAV
    - `POST /api/packs/{id}/focus` `{"sentence_id"}` → `204`
    - `PUT /api/packs/{id}/position` `{"sentence_id"}` → `204`
    - `POST /api/packs/{id}/skip` `{"pattern"}` → new `Script` (best-effort packs only; 400 for study packs)
    - `GET /api/settings`, `PUT /api/settings` (partial update; voice change does not delete old clips) → `Settings`
    - `GET /api/status` → `{"device": str, "notice": str|None, "packs": {id: {"rendered","total"}}}`
  - CLI: `python -m storyteller serve [--port N] [--no-browser]` (opens `http://127.0.0.1:N/` in the default browser unless `--no-browser`); `python -m storyteller script <pdf>` prints the spoken text of every sentence, one per line, prefixed by sentence id (debug tool)

- [ ] **Step 1:** Tests with `fastapi.testclient.TestClient` and stub voice: `test_upload_and_list`; `test_upload_scanned_422` (message text exact as above); `test_script_endpoint` (sentence ids sequential); `test_clip_renders_on_demand` (words length == sentence's spoken word count, audio URL returns `audio/wav`); `test_focus_then_status_progresses` (after `focus` and a short wait loop ≤ 5 s, `rendered` > 0); `test_failed_sentence_returns_500_and_worker_survives` (monkeypatch backend to raise for one sentence → 500 for it, next sentence still 200); `test_position_persists` (PUT then `GET /api/packs` shows it); `test_settings_partial_update`; `test_cli_script_output` (run `python -m storyteller script tests/fixtures/studypack_mini.pdf` via subprocess; output contains `Entry:` and no `Page 1 of 3`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: render worker, HTTP API and CLI`.

---

### Task 11: Library screen, page rendering and highlights

**Files:**
- Create: `scripts/fetch_vendor.py`, `storyteller/web/vendor/pdfjs/pdf.mjs`, `storyteller/web/vendor/pdfjs/pdf.worker.mjs`, `storyteller/web/library.html`, `storyteller/web/reader.html`, `storyteller/web/style.css`, `storyteller/web/js/api.js`, `storyteller/web/js/library.js`, `storyteller/web/js/pages.js`, `storyteller/web/js/highlight.js`

**Interfaces:**
- Consumes: HTTP API (Task 10)
- Produces (ES modules):
  - `api.js`: `listPacks()`, `uploadPdf(file)`, `getScript(id)`, `getClip(id, sid)`, `focus(id, sid)`, `savePosition(id, sid)`, `getSettings()`, `putSettings(partial)`, `getStatus()`; every call rejects with `{offline: true}` on network failure
  - `pages.js`: `renderPages(container, pdfUrl) -> Promise<PageView[]>` where `PageView = {pageIndex, el, scale}`; pages render lazily (IntersectionObserver) at container width; `scale = el.clientWidth / 612` (recomputed on resize)
  - `highlight.js`: `buildIndex(script) -> {byPage: Map<page, {sid, wordIndex, bbox}[]>}`; `showSentence(sentence, pageViews)` (one translucent rect per display line, merging adjacent word bboxes on the same line); `showWord(sentence, wordIndex, pageViews)`; `clear()`; `hitTest(pageIndex, x, y) -> sid | null` (nearest word within 12 pt, else null)
- `library.html`: list of packs (title, progress `rendered/total`, "Resume" button → `/read/{id}`), drop zone + file picker; shows the 422 message verbatim on scanned PDFs.
- `reader.html` layout: left `<nav id="outline">`, centre `<main id="pages">` and `<main id="clean" hidden>`, bottom `<footer id="bar">` (play/pause, speed readout, progress bar, time remaining), "Back to reading" button hidden by default. Use `lang="en"`, visible focus outlines, all controls are `<button>` with `aria-label`.

- [ ] **Step 1:** `scripts/fetch_vendor.py` downloads `https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.mjs` and `pdf.worker.mjs` into `storyteller/web/vendor/pdfjs/`; run it and commit the files (Apache-2.0; add `storyteller/web/vendor/pdfjs/LICENSE` from the same package).
- [ ] **Step 2:** Implement `api.js`, `library.js`, `library.html`, `style.css`.
- [ ] **Step 3:** Implement `pages.js` and `highlight.js`; `reader.html` loads the script and PDF and, on click, calls `hitTest` and logs the sid (player comes in Task 12).
- [ ] **Step 4:** Verify manually with `STORYTELLER_VOICE=stub uv run python -m storyteller serve --no-browser` and the Playwright MCP tools or a quick Playwright script: upload `studypack_mini.pdf`, open the reader, screenshot page 1, click the "Entry" row's text and confirm the logged sid's spoken text starts with `Entry:`. Save the screenshot to the scratchpad, not the repo.
- [ ] **Step 5:** Commit `feat: library screen, pdf.js pages and highlight overlay`.

---

### Task 12: Player

**Files:**
- Create: `storyteller/web/js/player.js`, `storyteller/web/js/reader.js`
- Modify: `storyteller/web/reader.html`

**Interfaces:**
- Consumes: `api.js`, `highlight.js`, `pages.js` (Task 11)
- Produces:
  - `class Player` — `constructor({packId, script, onSentence(sid), onWord(sid, i), onState(state), onError(sid)})`; `playFrom(sid)`, `pause()`, `resume()`, `toggle()`, `next()`, `prev()`, `replay()`, `setSpeed(x)`, `get current()`; `state` ∈ `idle|loading|playing|paused`
  - Behaviour: each `playFrom` increments a private `token`; any async continuation whose token is stale exits without side effects (this is what prevents overlapping audio); one `HTMLAudioElement` reused, `preservesPitch = true`, `playbackRate = speed`; word tracking via `requestAnimationFrame` comparing `audio.currentTime` to `words`; on `ended` wait `pause_after_ms` (timer cancelled by any navigation) then play next; prefetch `getClip` for the next 3 sentences; on clip error call `onError(sid)`, show a small "skipped" marker, and continue with the next sentence after 300 ms; position saved (debounced 2 s) on each new sentence; `focus()` called on every `playFrom`
- `reader.js` wires: click on page → `hitTest` → `player.playFrom(sid)`; auto-scroll keeps the current sentence's first bbox between 25 % and 60 % of the viewport height; a user wheel/touch/drag scroll sets `followMode=false` and shows "Back to reading" (click → scroll to current, `followMode=true`); progress bar = sentence index / total, time remaining = sum of remaining durations where known else 0.06 s × chars ÷ speed; on load, position restored but **not** played; when any API call rejects with `offline`, show a `#reconnect` banner ("Reconnecting…") and poll `GET /api/status` every 3 s, hiding the banner when it succeeds.

- [ ] **Step 1:** Implement `player.js` and `reader.js`.
- [ ] **Step 2:** Verify with stub voice in a headless browser: click a sentence → state becomes `playing`, sentence highlight moves through ≥ 3 sentences, no autoplay on load. (E2E tests are written in Task 14.)
- [ ] **Step 3:** Commit `feat: read-along player`.

---

### Task 13: Keyboard, outline, clean view, settings panel

**Files:**
- Create: `storyteller/web/js/keys.js`, `storyteller/web/js/outline.js`, `storyteller/web/js/cleanview.js`, `storyteller/web/js/settings.js`
- Modify: `storyteller/web/js/reader.js`, `storyteller/web/reader.html`, `storyteller/web/style.css`

**Interfaces:**
- Consumes: `Player` (Task 12), `api.js`
- Produces:
  - `keys.js`: `bindKeys(player, nav)` implementing the exact keyboard map from Global Constraints; ignores keys while focus is in an `<input>`/`<select>`; `nav` provides `prevBlock/nextBlock/prevChunk/nextChunk/skipTable/toggleView`
  - `outline.js`: `renderOutline(el, script, onPick(sid))`; level-1 as group labels, level-2 as buttons; a ✓ tick appears when the position has passed that chunk's last sentence; current chunk gets `aria-current="true"`
  - `cleanview.js`: `renderClean(el, script)` — one element per sentence (`data-sid`), grouped by `block_id`; headings as `h2/h3`; table sentences inside a `<div class="tbl">`; same highlight classes; click → `playFrom`; optional "focus line" mode dims all but the current block (toggle in settings)
  - Mark-as-skip (best-effort packs only, `script.profile == "besteffort"`): `Shift+click` a sentence → confirm popover "Skip text like this in this document?" → `POST /api/packs/{id}/skip` with the regex-escaped display text of that sentence's block → reload script keeping position
  - `settings.js`: panel (button in the bar) with speed slider 0.75–2.0 step 0.05, voice select with a "Preview" button that plays a fixed sentence ("Hardy-Weinberg equilibrium is a null model.") via `getClip` on a synthetic id — add `GET /api/preview?voice=` to `server.py` returning the same clip JSON shape; pause sliders (sentence 100–1000, block 200–2000, section 300–3000 ms); per-box read/skip checkboxes (chain, figure, gap, background, reading_aid, analogy, key, kit, traps); read badges; skip flags; highlight toggles and colours; pronunciation list editor (word → say-as rows); shows `unknown_symbols` as "Symbols to teach" with an input to add a reading (writes to `pronunciations`). Saving box/pause/pronunciation settings triggers a script rebuild (`POST /api/packs/{id}/rebuild`, add to `server.py`) and reloads the script keeping the current position by nearest `block_id`.
- Tests (add to `tests/test_server.py`): `test_preview_endpoint`, `test_rebuild_endpoint_applies_box_skip`.

- [ ] **Step 1:** Add the two server endpoints with their tests; run `uv run --extra dev pytest tests/test_server.py -v` → PASS.
- [ ] **Step 2:** Implement the four modules and wire them.
- [ ] **Step 3:** Run the a11y plugin on the web UI: invoke `a11y-enforcer:a11y-check` on `storyteller/web/` and `a11y-enforcer:contrast` for `sentence_color`/`word_color` against white and against the pack's teal `#0f6b6b`; fix every finding.
- [ ] **Step 4:** Commit `feat: keyboard control, outline, clean view and settings`.

---

### Task 14: End-to-end tests

**Files:**
- Create: `tests/e2e/conftest.py`, `tests/e2e/test_reader.py`

**Interfaces:**
- Consumes: the running server (start `python -m storyteller serve --no-browser --port 8799` in a fixture with `STORYTELLER_VOICE=stub`, temp `STORYTELLER_HOME`); browser = Python Playwright Chromium, `executable_path` from env `PLAYWRIGHT_CHROMIUM` when set (cloud sandboxes: `/opt/pw-browsers/chromium`)

- [ ] **Step 1:** Write tests:
  - `test_no_autoplay` — open reader; after 1 s player state is `idle` (expose `window.__player` for tests).
  - `test_click_to_start` — click the "Entry" row on page 1 → within 1 s state `playing` and current sentence spoken text starts `Entry:`.
  - `test_highlight_follows` — after start, the `.hl-sentence` rect's `data-sid` changes at least twice within 5 s.
  - `test_rapid_navigation_single_audio` — press `ArrowRight` 10 times in 300 ms → exactly one `audio` element not paused, and `current` equals the 10th-next sentence.
  - `test_keyboard_map` — `Space` toggles pause; `R` restarts current sid; `]` raises `playbackRate` by 0.05; `ArrowDown` jumps to next chunk's first sid; `V` shows `#clean` and hides `#pages`.
  - `test_resume_position` — play to a sentence, reload → highlight shown on the saved sentence, state `idle`.
  - `test_clip_failure_skips` — `page.route("**/clip/s00002", lambda r: r.fulfill(status=500, body='{"error":"synth_failed"}'))`, start at `s00001` → the skipped marker appears for `s00002` and `current` reaches `s00003`.
  - `test_server_down_banner` — stop the server → UI shows a "Reconnecting…" banner within 5 s instead of a blank page; restart → banner disappears.
- [ ] **Step 2:** Run `uv run --extra dev pytest tests/e2e -v` → fix the implementation until PASS.
- [ ] **Step 3:** Commit `test: end-to-end reader tests`.

---

### Task 15: Windows install and launch, README

**Files:**
- Create: `install.bat`, `run.bat`, `README.md`

**Interfaces:**
- Consumes: CLI from Task 10

- [ ] **Step 1:** `install.bat`: installs `uv` if missing (`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`), runs `uv sync --extra voice`, runs `uv run python -c "from storyteller.voice.kokoro_backend import KokoroVoice; KokoroVoice().synth(['Ready.'], 'af_heart')"` to download weights and confirm the device (prints `cuda` or `cpu`), then creates a desktop shortcut "Storyteller" pointing to `run.bat` (PowerShell `WScript.Shell` CreateShortcut). Fails with a plain-English message at each step.
- [ ] **Step 2:** `run.bat`: `uv run python -m storyteller serve` (opens the browser).
- [ ] **Step 3:** Confirm espeak-ng: `uv run python -c "import espeakng_loader; print(espeakng_loader.get_library_path())"` — if `misaki[en]` pulls in `espeakng_loader` no system install is needed; otherwise add a step to `install.bat` that downloads the espeak-ng MSI and document it.
- [ ] **Step 4:** `README.md`: what it is; install (double-click `install.bat`); use (shortcut → drag a PDF → click a sentence); keyboard map; where data lives; how to add a real pack to `tests/fixtures/local/` for tests; "Voice notes" with the wpm from Task 8; known limits (scanned PDFs, non-English).
- [ ] **Step 5:** Final check: `uv run --extra dev pytest -v` (all non-skipped pass) and `uv run python -m storyteller script tests/fixtures/studypack_mini.pdf | head -30` reads cleanly.
- [ ] **Step 6:** Commit `feat: Windows installer, launcher and README`.
