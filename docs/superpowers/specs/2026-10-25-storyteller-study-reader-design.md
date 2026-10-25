# Storyteller: local read-along study reader — design

Date: 2026-10-25 · Status: approved in brainstorming, awaiting spec review

## 1. Purpose and success criteria

**Who:** Matt, a university science student with ADHD/autism-friendly study needs, on a Windows laptop (i7-11800H, RTX 3050 Ti 4 GB, Intel UHD).

**Problem:** Microsoft Edge Read Aloud is slow, setting a start point is fiddly, it fails for no clear reason, and on PDFs it reads page numbers, footers and citations, pauses at every line break, and mangles formulas and tables. Paid tools (Speechify etc.) are expensive and still poor on study PDFs.

**Goal:** a free, offline app for *focused, eyes-on-page study* that reads Matt's study-pack PDFs cleanly with synchronized highlighting.

**Success looks like:**
- Opening an existing study pack (no re-generation) and pressing play reads it with no footers, page numbers or slide cites, no mid-sentence pauses, step tags read as labels, and formulas spoken in words.
- Clicking any sentence starts reading there in under 1 second.
- The current sentence and word are highlighted on the real PDF page, without drift.
- Works fully offline after install; no account, no usage limits.

**Out of scope for v1 (planned later):** audiobook (M4B) export, quiz pauses at Reasoning kits, listening-script output from the study-notes skills, desktop (.exe) packaging, non-English.

## 2. Decisions made

| Decision | Choice | Why |
|---|---|---|
| Use mode | Eyes on the page, read-along | Matt's stated study style; audio-paced bimodal reading is where the evidence shows benefit (Clinton-Lisell 2023, g = .41 when audio sets pace) |
| Inputs | (C) Study packs first, best-effort any PDF second | Existing packs must work without spending tokens on rewrites |
| App form | Local Python server + browser UI, wrappable as a desktop app later | Easiest to build, test and change |
| Engine | Kokoro-82M (Apache-2.0) via the `kokoro` Python package, CUDA with CPU fallback | Best quality among models that run well on modest hardware; `KPipeline` returns per-token `start_ts`/`end_ts` (verified in `kokoro/pipeline.py`, `join_timestamps`) |
| Display | Real PDF pages by default (pdf.js), toggle to a clean reflowed text view | Keeps the pack's visual design; clean view for low-distraction sessions |

## 3. User experience

**Library screen:** recent packs with "resume where you left off"; drag a PDF in to add it. Nothing autoplays, ever.

**Reader screen:**
- Left: outline built from the PDF bookmarks (lectures → chunks), with a progress tick per chunk; click to jump.
- Centre: PDF pages (pdf.js), or the clean view (toggle `V`). Current sentence gets a soft background; current word a stronger underline; each independently switchable. Auto-scroll keeps the reading line in view; if the user scrolls away, auto-scroll pauses and a "Back to reading" button appears.
- Bottom: play/pause, speed, whole-pack progress bar, time remaining.
- Click any sentence to start reading there.

**Keyboard:** `Space` play/pause · `←/→` previous/next sentence · `Shift+←/→` previous/next block (paragraph, box, table) · `↑/↓` previous/next chunk · `R` replay sentence · `[`/`]` slower/faster · `V` page/clean view · `T` skip current table.

**Settings (persisted):** speed 0.75×–2× (default ≈160 wpm); voice from a short preview list (one calm default); pause lengths at sentence / block / section boundaries, kept constant across speeds; per-box-type read/skip (Figure detail, Analogy, Background, Reading aid, What the slides don't say, Reasoning kit, Traps); highlight styles and colours; pronunciation list.

## 4. Pipeline: PDF → speech

Each stage is a separate module with a typed interface.

### 4.1 `extract` — PDF → `Span[]`
`Span = {text, role, page, bbox, block_id}`. Roles: `heading1..3`, `body`, `tag` (chain step label), `box_label`, `table_cell`, `cite`, `footer`, `flag`, `badge`, `skip`.

**Study-pack profile** (selected when the PDF's fonts/colours match the template; verified on the BIOL 2040 pack, Chromium/Skia, Carlito fonts):
- Cites: grey (`#5c6774`, `#55606c`), size < 9 → `cite` (skipped).
- Chain tags: white bold, ~8.2 pt → `tag` (read as "Entry: …").
- Headings: teal `#0f6b6b` bold (10.8 pt subheads; larger for chunk titles); lecture banners white bold 11 pt.
- Body: `#1f2933` ~9.9 pt.
- Footer band ("BIOL … study notes", "Page N of M") at a fixed y near the page bottom → `footer` (skipped).
- "★ Likely tested" flags → `flag` (skipped by default).
- Stated/Follows badges → `badge` (read as "Stated:" / "Follows:", configurable).
- Page-1 chunk map table → not read; used with the PDF bookmarks to build the outline.
- Lines are merged into blocks; mid-sentence line breaks and hyphenation are joined.

**Best-effort profile:** PyMuPDF spans; headers/footers detected as text repeated at the same position across pages; bracketed/superscript citation patterns flagged as `cite`; reading order from PyMuPDF block order with column detection. A "mark as skip" action in the UI lets the user teach per-document skip rules.

### 4.2 `speechify` — `Span[]` → listening script
`Sentence = {id, block_id, spoken_text, display_ranges[], pause_after_ms, kind}`, where `display_ranges` maps each spoken word back to span characters/bboxes for highlighting.

- **Symbol rulebook** (data file, user-editable), covering every non-ASCII symbol found in the reference pack: `²`→"squared", `2pq`→"two p q", `′`→"prime", `x̄`→"x bar", `ω`→"omega", `Δ`→"delta", `Σ`→"sum of", `√`→"square root of", `½`/`¼`→"one half"/"one quarter", `×`→"times", `÷`→"divided by", `−`→"minus", `≈`→"approximately", `≠`→"is not equal to", `µ`→"mu", `α`→"alpha", `dN/dS`→"d N over d S", `A1A2`→"A one A two", `f[A1]`→"frequency of A one". A formula's spoken words all map to the whole formula's bbox (highlight the formula as a unit).
- **Pronunciation list** (global, user-editable): word → respelling or Kokoro `[word](/phonemes/)`.
- **Tables:** announce ("Table, 3 rows: Question, Answer, Why"), then row by row with the column header repeated before each cell.
- **Sentence splitting** with abbreviation-aware rules; pauses by boundary type (sentence < block < section).

### 4.3 `voice` — sentence → audio + word timings
Wrapper over `kokoro.KPipeline`: input `spoken_text`, voice, speed; output 24 kHz audio and per-token `(start_ts, end_ts)`. CUDA if available, else CPU, reported once in the UI. Each sentence is synthesized separately (avoids long-input degradation).

### 4.4 `library` — local storage
Per pack: source PDF hash, script JSON, audio cache keyed by `(sentence spoken_text, voice, speed)`, reading position, per-document skip rules. Global: settings, pronunciation list, symbol rulebook overrides. Stored under the user's app-data folder.

### 4.5 `server` + web UI
FastAPI serves the UI, the PDF, the script, and audio clips. A background worker renders audio in priority order: from the current position forward, with click-jumps jumping the queue. Playback uses the Web Audio API with silence inserted for `pause_after_ms`, so pauses don't depend on rendered audio.

## 5. Error handling
- GPU unavailable or CUDA error → CPU fallback, one notice.
- A sentence fails to synthesize → skipped with a visible marker; playback continues.
- PDF without a text layer (scan) → clear message; no silent failure.
- Unrecognized symbol → spoken by its Unicode name and logged to a "symbols to teach" list in settings.
- Server not running when the UI opens → launcher starts it; UI shows a reconnect state rather than a blank page.

## 6. Testing
- **Reference fixture:** the BIOL 2040 Lectures 8–13 pack. Assertions: no `Page \d+ of \d+` or `(P\d \d+…)`-style cites in any `spoken_text`; chain tags appear as "Entry:", "Route:" etc.; listed formulas produce the expected spoken forms; tables read row by row with headers; outline matches the 35 chunks.
- **Unit tests:** every symbol rule; sentence splitter; table linearizer; header/footer detection on a synthetic best-effort PDF.
- **Voice:** a smoke test that a sentence returns audio and monotonically increasing timestamps (skipped when the model isn't available in CI).
- **UI:** Playwright (headless Chromium) tests for click-to-start, highlight movement, keyboard shortcuts, and view toggle, using a stub voice backend that returns silence with synthetic timings.

## 7. Setup and running (Windows)
`install.bat` installs `uv`, which provisions Python, the dependencies (PyTorch with CUDA, `kokoro`, `pymupdf`, `fastapi`), and the Kokoro weights on first run, then creates a desktop shortcut. The shortcut starts the server and opens the browser at `http://127.0.0.1:<port>`. espeak-ng is needed by Kokoro's English fallback for out-of-vocabulary words; the installer handles it.

## 8. Prior art to borrow from (not fork)
- **OpenReader** (`richardr1126/openreader`, MIT): mature read-along reader with a Windows desktop build, local Kokoro, word highlighting from Kokoro's phoneme durations, layout-aware PDF parsing. Heavy stack (Next.js + NATS worker). Matt should try it as a baseline; it lacks study-pack awareness (cites, tags, formula wording) and the keyboard/outline flow above. Borrow: progressive background generation with a single document timeline; geometry-based highlight mapping.
- **YomiKoe** (`kris-jskk/yomikoe`, Apache-2.0, early stage, Oct 2026): FastAPI + React, `ingestion/` → `synthesis/` with a swappable `TTSBackend`, sentence-segment cache, highlight-drift test gate. Closest architectural match; borrow its interface split and test gates.
- **PDF Immersive Reading** (`mircolosi/pdf_immersive_reading`, BSD-3): Gradio app with click-to-seek, prefetch, an on-disk cache keyed by document/engine/voice, and speed applied in the browser. Borrow the cache-key idea.
- **Kokoro** (`hexgrad/kokoro`): `KPipeline.join_timestamps` provides word timings directly.

## 9. Later phases
1. Audiobook export (M4B with chapters via ffmpeg) for phone listening.
2. Optional quiz pauses at Reasoning kits/Traps (retrieval practice; Szpunar et al. 2013).
3. `study-rewrite-notes` / `study-notes-draft-build` emit a listening script embedded in the PDF (attached file via pikepdf) for exact formula wording; the app prefers it when present.
4. Package as a desktop app (Tauri or pywebview).
