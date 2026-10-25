# Document-to-Speech Pipeline and App Architecture for a Free Local TTS Study Reader (2026)

Scope: turning self-generated study PDFs (rendered from HTML) with headings, numbered chunks, "chain" step boxes (Entry/Route/Result tags), tables, Unicode formulas (p², 2pq, q², ½ f[A1A2], dN/dS), slide citations "(P1 5)", footers "Page 3 of 56", and badges into clean speech, plus app architecture options. Free, local, English, Windows/Edge user.

Research note: about 18 tool calls. Several primary doc sites (pymupdf.readthedocs.io, a 2026 comparison blog) failed to resolve, so PyMuPDF details are thinner than the others. Vendor benchmarks are flagged as such.

## Q1. PDF extraction tools that preserve structure (header/footer removal, line-break repair, tables)

### Takeaway
Marker and Docling are the strongest free, local, structure-aware extractors. Marker strips running headers and footers by default and labels them PageHeader/PageFooter in JSON. Docling (MIT, runs on Windows) gives a typed DoclingDocument with reading order, tables and formulas. Independent benchmarks put Marker, MinerU and Docling close together. None of the benchmarks found measure header/footer removal directly. For this user's own PDFs, parsing the PDF at all is the weaker option (see Q2).

### Cited Findings
- **Marker** strips running headers and footers by default. You keep them with `--keep_pageheader_in_output` / `--keep_pagefooter_in_output`. In JSON output they appear as `PageHeader` and `PageFooter` block types. — [Marker README](https://raw.githubusercontent.com/datalab-to/marker/master/README.md)
- Marker outputs `markdown`, `json`, `html` or `chunks`. JSON is a block tree, and each block has `block_type`, `html`, `polygon` and `children`. Equations come out as LaTeX (`$$` in Markdown, `<math>` in HTML). Inline math converts automatically in balanced mode and needs `--force_ocr` / `--ocr_inline_math` in fast mode. Tables are rebuilt from the PDF text layer and output as HTML `<table>`, with a VLM fallback when confidence is low. — [Marker README](https://raw.githubusercontent.com/datalab-to/marker/master/README.md)
- Marker can call a local LLM. `--use_llm --llm_service=marker.services.ollama.OllamaService` with `--ollama_base_url` / `--ollama_model` helps with tables that span pages or have complex spans. — [Marker README](https://raw.githubusercontent.com/datalab-to/marker/master/README.md)
- Marker licensing: the code is Apache-2.0. The model weights use a modified AI Pubs Open RAIL-M license, free for research, personal use and startups under $5M. It needs Python 3.10+ and PyTorch, and runs on GPU, CPU or MPS. Fast mode is the default on CPU. The README does not mention Windows. — [Marker README](https://raw.githubusercontent.com/datalab-to/marker/master/README.md)
- **Docling** handles "page layout, reading order, table structure, code, formulas, image classification". It produces a unified DoclingDocument. It accepts HTML as well as PDF and exports Markdown, HTML, WebVTT, DocTags and lossless JSON. An optional VLM pipeline is available (`--pipeline vlm --vlm-model granite_docling`), along with an MCP server. Code is MIT. It runs on macOS, Linux and Windows (x86_64 and arm64) and needs Python 3.10+. — [Docling README](https://raw.githubusercontent.com/docling-project/docling/main/README.md); [Docling tech report](https://arxiv.org/pdf/2501.17887)
- Benchmarks:
  - **READoc (academic):** Marker and MinerU are nearly tied overall (46.44 vs 46.08). On text concatenation Marker scores 59.34 and MinerU 57.28. On table concatenation Marker scores 40.68 and MinerU 38.75. — [READoc arXiv](https://arxiv.org/pdf/2409.05137)
  - **Survey of unclear methodology:** Docling 0.882 overall / 0.887 table fidelity, Marker 0.861 / 0.808, MinerU 0.831 / 0.873, MarkItDown 0.589. — [yage.ai survey](https://yage.ai/share/markitdown-survey-en-20260412.html)
  - **Vendor (Datalab, maker of Marker) on olmOCR-bench:** Marker balanced scored 76.0 overall vs MinerU 72.7 and Docling 50.3 (Docling on its default pipeline). The two are effectively tied on born-digital PDFs. Marker ran at about 2.9 pages/s vs MinerU 0.54. These are vendor numbers. — via search summary of [Datalab benchmarks](https://simplify.jobs/c/Datalab) (original Datalab post not fetched directly)
  - The sources disagree on Docling: it ranks best in the yage.ai survey and far behind in Datalab's benchmark.
- **PyMuPDF4LLM:** the 4llm code moved into the `pymupdf` 2.x package, and `pymupdf4llm` is now an empty shim package "required by pymupdf-2.x". — [pymupdf4llm README](https://raw.githubusercontent.com/pymupdf/pymupdf4llm/main/README.md)
- **Tagged PDF / PDF/UA:** PDF/UA-1 (ISO 14289-1) clause 7.8 requires running headers and footers to be tagged as Pagination artifacts (Header/Footer subtypes). Screen readers then skip them. — [Qoppa KB / PDF/UA summary](https://kbpdfstudio.qoppa.com/?p=9607); [Oracle BI Publisher accessible PDF docs](https://docs.oracle.com/en/middleware/bi/analytics-server/design-publish/generate-accessible-pdf-output.html); [davidmacd.com on PDF headers/footers](https://davidmacd.com/blog/pdf-headers-footers.html)
- In practice, readers make no distinction between a pagination artifact and any other artifact. — [W3C WAI-IG list, Duff Johnson](https://lists.w3.org/Archives/Public/w3c-wai-ig/2013JanMar/0141.html)

### Inferences
- Edge Read Aloud reads "Page 3 of 56" because the generator's footers are probably painted as ordinary content rather than tagged as artifacts. Chromium's print-to-PDF tagging of CSS `@page` margin boxes is unverified. If the generator is WeasyPrint/Chromium, check the PDF with PAC or Acrobat's checker.
- For third-party PDFs (slides, papers), use Marker (best default header/footer stripping, JSON block types) or Docling (MIT, Windows-friendly, typed labels). For the user's own PDFs, skip them (Q2).
- None of the tools were confirmed to do hyphenation and line-break repair. Layout-model tools rebuild paragraphs from blocks, which in effect fixes mid-sentence line breaks. Hyphen rejoining should still be done with a simple regex pass (`(\w)-\n(\w)` → `\1\2`, checked against a dictionary).

### Gaps
- No benchmark measures header/footer removal or line-break/hyphenation repair directly.
- Not verified: pdfplumber, GROBID, unstructured.io and MinerU's current (2.x/VLM) features and licensing (MinerU reported as AGPL in secondary sources). PyMuPDF layout-mode parameters (docs site unreachable). pdf.js text-layer and structure-tree support.
- Whether Chrome/Edge print-to-PDF marks CSS margin-box footers as artifacts.

## Q2. Skip PDF parsing: consume the source HTML/Markdown or emit an "audio script" sidecar

### Takeaway
Because the user generates the PDFs from HTML, the most robust route is to generate the audio from the source, ideally as a dedicated listening-script sidecar (JSON) emitted by the same generator. Each chunk then carries a section id, display text, `speak` text and alt-speech for formulas and tables. That removes the need for extraction and noise heuristics, and keeps a stable id to highlight in the document.

### Cited Findings
- Docling accepts HTML directly and exports a typed document, so source HTML can go through the same structure model without the lossy PDF step. — [Docling README](https://raw.githubusercontent.com/docling-project/docling/main/README.md)
- Abogen uses inline chapter tags (`<<CHAPTER_MARKER:Title>>`) in the text it converts. It adds them automatically for EPUB, PDF and Markdown, and users can add them to plain text. The tags drive chapter splitting and let failed chapters be re-processed. This is a lightweight sidecar-style convention already in use. — [abogen GitHub](https://github.com/denizsafak/abogen)
- Kokoro-FastAPI supports inline voice tags (`allow_voice_tags`) and returns per-word timestamps that carry the voice name. Markup embedded in the script can therefore steer synthesis. — [Kokoro-FastAPI README](https://raw.githubusercontent.com/remsky/Kokoro-FastAPI/master/README.md)

### Inferences
- **Pros of a sidecar:** exact reading order. Zero headers, footers, page numbers or badges, since they are never emitted. Authored alt-speech for every formula and table (written once, at generation time, by the same LLM step that writes the notes, and reviewable). Stable ids for highlighting and chapter markers. Chain boxes can be voiced as "Step 1, Entry: ...".
- **Cons of a sidecar:** the generator workflow has to change. The sidecar can drift from the PDF if one is edited without the other. Spoken text needs its own QA. It does not help with third-party PDFs.
- **Suggested schema:** `{doc_id, title, sections:[{id, heading, level, blocks:[{id, kind: heading|para|chain_step|table|formula|list, display_text, speak, pause_after_ms, tag?: Entry|Route|Result, skip?: bool}]}]}`. HTML attributes such as `data-speak="p squared"` and `data-tts-skip` on citations and badges let one HTML source drive both outputs.
- **Middle option:** parse the source HTML with BeautifulSoup and CSS-class rules (drop `.badge`, `.cite`, `.footer`; map `.chain-step[data-tag]`). This needs no generator change, but formulas still need verbalization.

### Gaps
- No published standard for a "listening script" JSON was found. EPUB 3 Media Overlays (SMIL) and W3C SSML are the closest standards, but neither was fetched.

## Q3. Math to speech (MathCAT, SRE, MathSpeak/ClearSpeak, plain-Unicode formulas, LLM rewriting)

### Takeaway
The mature engines need MathML input, with limited LaTeX input in SRE. Neither reads plain Unicode like "p²" or "½ f[A1A2]". For the user's own notes, the most reliable path is authored alt-speech, or a small deterministic rule table for recurring formulas. Fall back to SRE (Node, Apache-2.0, has ClearSpeak/MathSpeak and SSML output) when the source has LaTeX/MathML. LLM rewriting is convenient, but its output needs review.

### Cited Findings
- **MathCAT** converts MathML to speech, braille and navigation. Input is MathML only, with no ASCIIMath or LaTeX input mentioned. It has Python, C/C++ and Java interfaces and no JS/WASM binding is mentioned. It is MIT-licensed. — [MathCAT GitHub](https://github.com/NSoiffer/MathCAT)
- MathCAT adds prosody to its speech, is used in production NVDA and the JAWS 2024 beta, and is the intended successor to MathPlayer. — [docs.rs libmathcat](https://docs.rs/mathcat); [TPGi "Making Math Accessible"](https://www.tpgi.com/making-math-accessible)
- **Speech Rule Engine (SRE)**:
  - API methods (`toSpeech`, `toSemantic`, etc.) take MathML. The CLI `-t/--latex` flag accepts LaTeX "for certain locale/modality combinations".
  - MathSpeak and ClearSpeak are implemented "in full", with `brief`/`sbrief` styles.
  - Output markup can be SSML, VoiceXML, Sable or ACSS. Nemeth braille is also supported.
  - Install with `npm install speech-rule-engine` and run with `npx sre`. Apache-2.0.
  - — [SRE GitHub](https://github.com/Speech-Rule-Engine/speech-rule-engine)
- Marker can output detected equations as LaTeX/`<math>`, which could feed SRE (LaTeX) or a LaTeX→MathML step then MathCAT. — [Marker README](https://raw.githubusercontent.com/datalab-to/marker/master/README.md)

### Inferences
- For Unicode formulas in the user's notes, a deterministic preprocessor covers most cases:
  - `²`→" squared", `³`→" cubed". Other superscript digits → " to the power n". Subscript digits → " sub n".
  - `½`→"one half". `p²`→"p squared". `2pq`→"two p q". `dN/dS`→"d N over d S" (or the domain term "dN over dS ratio").
  - `f[A1A2]`→"the frequency of A1 A2".
  - Implement it as a regex plus a per-course glossary (CSV) the user can edit.
- Converting Unicode to MathML (e.g. via a Unicode-math/UnicodeMath parser) and then running MathCAT/SRE is possible, but heavy for this volume of fairly simple formulas.
- LLM rewriting with a small local model (Ollama/llama.cpp) risks:
  - dropped or reordered terms
  - hallucinated words
  - inconsistent naming across runs
  - silently "simplifying" formulas
  The mitigations are temperature 0, a constrained prompt, caching per unique formula string, and a symbol-coverage check (every variable in the source must appear in the output). Better still, do the rewriting at note-generation time with the stronger model that writes the notes, and store it in the sidecar.

### Gaps
- No quantitative study on local-LLM accuracy for verbalizing formulas or tables was found.
- Whether MathCAT supports ClearSpeak specifically was not confirmed on the fetched page (its docs mention configurable speech styles only).

## Q4. Table linearization for audio

### Takeaway
No authoritative source was found in this pass. Standard practice (from screen-reader behaviour) is to read row by row with column headers repeated. Small tables (2–3 columns) can become sentences; large tables should be summarized, with a "table skipped, see notes" option.

### Cited Findings
- Marker outputs tables as HTML `<table>` and Docling exports table structure in its document model. Both give header and cell structure that can be linearized programmatically. — [Marker README](https://raw.githubusercontent.com/datalab-to/marker/master/README.md); [Docling README](https://raw.githubusercontent.com/docling-project/docling/main/README.md)

### Inferences
- **Recommended template:**
  1. Announce the shape first: "Table: Hardy-Weinberg genotype frequencies, 3 rows, 2 columns."
  2. Read each row: "Row 1. Genotype: A1A1. Frequency: p squared."
  3. Add a pause of about 400 ms between rows and about 800 ms after the table.
- If there are more than about 6 rows or 4 columns, use an authored or LLM summary plus "full table in notes".
- Comparison tables (X vs Y) read better column-wise: "For X: ...; For Y: ...".

### Gaps
- No user studies or published guidelines on table-to-audio comprehension were retrieved.

## Q5. Text normalization for neural TTS (Kokoro/Piper; misaki/espeak)

### Takeaway
Kokoro's front end (misaki G2P with an espeak-ng fallback) and Kokoro-FastAPI's normalizer handle common numbers and currency. They do not handle domain symbols, superscripts, slide citations or abbreviations, and they offer no SSML. Do normalization yourself before TTS. Use misaki's inline `[word](/phonemes/)` override as the pronunciation lexicon.

### Cited Findings
- Misaki supports custom pronunciation inline as markdown links, e.g. `[Kokoro](/kˈOkəɹO/)`. Out-of-dictionary words fall back to espeak-ng via `espeak.EspeakFallback`. Its TODOs include homograph disambiguation ("lead", "tear", "wind", "bass") and seq2seq fallback models. It documents no handling of symbols or superscripts. — [misaki README](https://raw.githubusercontent.com/hexgrad/misaki/main/README.md)
- A C# port says misaki's English G2P covers lexicon, stress, numbers, currency and homographs, verified against misaki 0.9.4. — [MisakiSharp](https://github.com/Lyrcaxis/MisakiSharp)
- Kokoro-FastAPI has `normalization_options`. The README notes setting `"normalize": False` can fix missing words or timestamps, so its normalizer can itself drop words. The full option list is in `docs/configuration.md`. It pins Kokoro 0.9.4 / Misaki 0.9.4. — [Kokoro-FastAPI README](https://raw.githubusercontent.com/remsky/Kokoro-FastAPI/master/README.md)
- Kokoro-FastAPI chunks text at sentence boundaries. Defaults are `TARGET_MIN_TOKENS` 175, `TARGET_MAX_TOKENS` 250, `ABSOLUTE_MAX_TOKENS` 450. The model takes up to 510 phoneme tokens, but long chunks sound "rushed". — [Kokoro-FastAPI README](https://raw.githubusercontent.com/remsky/Kokoro-FastAPI/master/README.md)
- WhisperX notes that words containing numbers or currency symbols get no alignment timings. This is one more reason to spell numbers and symbols out before synthesis. — [WhisperX GitHub](https://github.com/m-bain/whisperX)

### Inferences
- **Normalization pass, in order:**
  1. Strip noise: `\(P\d+\s+\d+\)` slide citations, "Page n of m", badges.
  2. Repair hyphens and line breaks.
  3. Expand formulas, superscripts and subscripts (Q3).
  4. Expand Greek letters (α→alpha, β→beta, χ²→chi squared, Δ→delta).
  5. Expand units and abbreviations from a glossary (e.g. "e.g."→"for example", "vs."→"versus", "Fst"→"F S T", "dN/dS"→"d N over d S").
  6. Expand numbers and ranges ("10–20"→"10 to 20").
  7. Put pronunciation overrides into misaki link syntax.
- Kokoro/Piper do not accept SSML (inferred from the absence of SSML in Kokoro-FastAPI/misaki docs; not confirmed). Pauses are produced by splitting into separate synthesis calls and inserting silence of the desired length, rather than by `<break>`. If SSML is kept as an intermediate format, the app has to interpret `<break>`, `<sub alias>` and `<say-as>` itself.

### Gaps
- Specific misaki failure cases for Unicode superscripts (², ³) and symbols such as "→", "≈", "±" were not found in issues. They should be tested empirically.
- Piper's normalization behaviour was not researched in this pass.

## Q6. Synchronized highlighting (word timestamps and mapping back)

### Takeaway
Kokoro gives word timings natively, so forced alignment is usually unnecessary. Kokoro-FastAPI's `/dev/captioned_speech` returns per-word timestamps, and OpenReader uses Kokoro phoneme durations for word-by-word highlighting. Map back to the document by keeping block ids. Highlight at sentence or block level when normalization changes the word count (e.g. "p²" → "p squared").

### Cited Findings
- `POST /dev/captioned_speech` returns base64 audio plus a `timestamps` field. In streaming mode it returns JSON lines, each with audio and timestamps. The built-in web UI read-along uses chunk-level timing (`X-Timing-Path` sidecar), not word-level. — [Kokoro-FastAPI README](https://raw.githubusercontent.com/remsky/Kokoro-FastAPI/master/README.md)
- OpenReader does "word-by-word highlighting" from local Kokoro phoneme durations and uses ONNX Whisper alignment for other providers. PDF read-along uses layout-aware parsing. — [OpenReader-WebUI GitHub](https://github.com/richardr1126/OpenReader-WebUI)
- kokoro-js streaming yields text, phonemes and audio per chunk. Its README does not mention word-level timestamps. — [kokoro-js README](https://github.com/hexgrad/kokoro/tree/main/kokoro.js)
- **WhisperX** force-aligns with wav2vec2 to get per-word timing. Alignment models are language-specific (English included). Words with numbers or currency symbols get no timing. It needs CUDA 12.8 for GPU, or CPU int8. BSD-2-Clause. Aligning known text is not documented directly. — [WhisperX GitHub](https://github.com/m-bain/whisperX)
- Abogen produces SRT/ASS subtitles with word-level modes (English only) alongside the audio. — [abogen GitHub](https://github.com/denizsafak/abogen)

### Inferences
- **Mapping strategy:** synthesize per block (sentence or paragraph), store `{block_id, audio_offset, duration}`, and highlight the block. For word-level highlighting, keep a token alignment between `display_text` and `speak` text. For a formula span, highlight the whole formula while its spoken expansion plays.
- aeneas and Montreal Forced Aligner are only needed for TTS engines without timings. MFA and aeneas were not researched.

### Gaps
- Not verified: whether kokoro-js exposes per-word durations in its API, or whether the Python `kokoro` package's `KPipeline` result tokens include start/end timestamps (believed to exist, not confirmed in this pass).

## Q7. App architecture options (Windows, free, local, non-developer install)

### Takeaway
The easiest options for a non-developer on Windows, in order:
1. An existing packaged app: OpenReader desktop app (MIT, Windows build, Kokoro, word highlighting, M4B/MP3 export), or Abogen (`WINDOWS_INSTALL.bat`, PDF/MD/EPUB → M4B with chapters plus subtitles).
2. A custom Python CLI or small local web app that consumes the sidecar script and calls Kokoro, for tailored preprocessing.
3. A fully in-browser kokoro-js/WebGPU page, which needs no install but has fewer export features.

Tauri/Electron with a sidecar is the most polished option and the most work.

### Cited Findings
- **OpenReader-WebUI:**
  - Inputs: EPUB, PDF, TXT, MD and DOCX. HTML is not listed.
  - TTS: local Kokoro (no API key), or OpenAI-compatible servers (Kokoro-FastAPI, KittenTTS, Orpheus, Supertonic).
  - Word-by-word highlighting. M4B/MP3 export (chapter markers not stated).
  - Deployment: Docker Compose, or a desktop app for macOS, Windows and Linux with "no server or Docker setup".
  - MIT.
  - — [OpenReader-WebUI GitHub](https://github.com/richardr1126/OpenReader-WebUI)
- **Abogen:**
  - Inputs: EPUB, PDF, Markdown, TXT and subtitles.
  - Outputs: WAV, FLAC, MP3, OPUS and M4B with chapters. Chapters can be separate files, merged, or both. SRT/ASS subtitles.
  - Windows: `WINDOWS_INSTALL.bat` installs Python and dependencies, and espeak-ng must be installed first. Optional NVIDIA CUDA.
  - Has a web UI (`abogen-web`). Kokoro-82M. MIT.
  - PDF header/footer handling is not documented.
  - — [abogen GitHub](https://github.com/denizsafak/abogen)
- **Kokoro-FastAPI:**
  - OpenAI-compatible `/v1/audio/speech`.
  - Outputs mp3, wav, opus, flac, aac and pcm.
  - Web UI at `localhost:8880/web`.
  - Windows via `.\start-cpu.ps1` / `.\start-gpu.ps1` with astral-uv (espeak-ng optional), or Docker images `ghcr.io/remsky/kokoro-fastapi-cpu`.
  - — [Kokoro-FastAPI README](https://raw.githubusercontent.com/remsky/Kokoro-FastAPI/master/README.md)
- **audiblez:** a Python CLI/GUI that converts EPUB to M4B with Kokoro-82M. It writes per-chapter WAVs and merges them into `.m4b` (needs ffmpeg and espeak-ng). It has voice, speed (0.5–2.0) and `--cuda` options. EPUB only. — [audiblez README](https://cdn.jsdelivr.net/gh/santinic/audiblez@main/README.md)
- **kokoro-js:**
  - `npm i kokoro-js`. Model `onnx-community/Kokoro-82M-v1.0-ONNX`.
  - Devices: `wasm`/`webgpu` in the browser, `cpu` in Node. fp32 is recommended for WebGPU. Dtypes: fp32, fp16, q8, q4, q4f16.
  - Streaming via `TextSplitterStream`.
  - — [kokoro-js README](https://github.com/hexgrad/kokoro/tree/main/kokoro.js)
- **sherpa-onnx:**
  - Runs Kokoro with no Python, with eSpeak NG data bundled in the model archive. Windows x64 builds exist (v1.13.5 cited). It has C#, C++ and Python APIs. Kokoro 1.0 support was added around v1.10.42.
  - These claims come from a secondary guide (Aug 2026) that inspected the archives but did not run them.
  - — [localaimaster guide](https://localaimaster.com/blog/best-local-tts-windows); [sherpa_onnx changelog](https://pub-web-s1.flutter-io.cn/packages/sherpa_onnx/versions/1.10.43/changelog)
- **KokoroSharp:** a .NET NuGet package for Kokoro (v0.8.4), a route for a native Windows app. — [NuGet KokoroSharp](https://packages.nuget.org/packages/KokoroSharp/)
- A Windows guide covers Kokoro TTS and Abogen setup. — [mybyways Kokoro/Abogen on Windows](https://www.mybyways.com/blog/tag:guide)

### Inferences
Architecture comparison:

| Option | Install friction (non-dev, Windows) | Fit for this user | Existing examples |
|---|---|---|---|
| Use an existing app | Lowest (installer or .bat) | Good for PDFs, but formulas, citations and footers are not handled | OpenReader desktop, Abogen |
| Python CLI → M4B/MP3 | Medium (uv/pip, ffmpeg, espeak-ng). Can be bundled with PyInstaller or a .bat | Best for a sidecar-driven batch "study audiobook" for phone listening | audiblez, Abogen CLI |
| Local web app (FastAPI + browser UI) | Medium. One .bat starts the server and opens Edge | Good for read-along with highlighting of the HTML notes | Kokoro-FastAPI web UI, OpenReader (Docker) |
| Fully in-browser (kokoro-js WebGPU) | Lowest. A static HTML page that can sit next to the notes; first run downloads about 80–300 MB of weights | Good for read-along. Export is harder, and WebGPU needs a recent Edge/GPU | kokoro-js demos |
| Tauri/Electron + Python/Rust sidecar | Lowest for the end user once built, highest dev effort | Polished, but overkill for v1 | OpenReader desktop (Electron-type packaging, not verified) |
| Python desktop (PySide6) | Medium (PyInstaller bundle around 500 MB+ with torch; smaller with ONNX/sherpa-onnx) | Workable | (none verified) |
| Browser extension | Medium. Edge has limited WebGPU in service workers | Weakest fit, because the user's own content is better served by sidecars | (none verified) |

- Recommended for this user:
  1. A sidecar JSON emitted by the note generator.
  2. A small Python CLI using the `kokoro` package or sherpa-onnx (ONNX, no torch) that renders M4B with chapters per section and a timing JSON.
  3. Optionally, a static HTML player that plays the audio and highlights blocks from the timing JSON.

### Gaps
- pdf2audiobook was not found. Install sizes, Windows reliability for each option, and OpenReader desktop's packaging technology were not verified.

## Q8. Audio export with chapter markers (M4B, MP3 ID3 chapters)

### Takeaway
M4B with chapters built through ffmpeg's FFMETADATA file is the standard, well-trodden path, and Abogen and audiblez already do it. MP3 chapter support (ID3v2 CHAP frames) is less reliable across phone players and was not verified.

### Cited Findings
- Build an M4B with ffmpeg:
  1. Write a `;FFMETADATA1` file with `[CHAPTER]` entries whose times come from the `ffprobe` durations of each clip.
  2. Concatenate the clips with `-map_metadata` from that file.
  3. Add cover art in a second pass.
  — [mybyways: Creating an audiobook (.m4b) with FFmpeg](https://mybyways.com/blog/creating-an-audiobook-m4b-with-ffmpeg/); [audify m4b_builder source](https://audify.readthedocs.io/en/latest/_modules/audify/utils/m4b_builder.html)
- Merging chaptered M4B files in ffmpeg keeps only the first file's chapters (long-standing ticket). Build chapters from the clips, not by merging M4Bs. — [ffmpeg ticket #2522](https://fftrac-bg.ffmpeg.org/ticket/2522)
- Abogen outputs M4B with chapters and can also split chapters into separate files. audiblez merges per-chapter WAVs into M4B. — [abogen](https://github.com/denizsafak/abogen); [audiblez README](https://cdn.jsdelivr.net/gh/santinic/audiblez@main/README.md)

### Inferences
- For phone listening, an M4B with one chapter per note section (title = heading) works in most audiobook apps. Also offering per-section MP3 files in a folder is the universal fallback.

### Gaps
- ffmpeg's support for writing ID3v2 CHAP frames to MP3, and phone player support for them, were not verified. Which Android/iOS players honour M4B chapters was not researched.
