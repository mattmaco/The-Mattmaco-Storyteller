# Local (Offline) Open-Source TTS Engines for a Study-Reading App (state as of Oct 2026)

> Method note: researched 2026-10-25. Direct page fetches (Hugging Face, artificialanalysis.ai, blogs) were blocked by the session's network policy, so findings come from web-search result summaries of the cited pages. Numbers should be re-checked on the live pages before final decisions. Many sources are SEO/blog aggregators; vendor and primary-repo sources are flagged where possible.

## 1. Which local TTS models lead in naturalness (TTS Arena / Artificial Analysis)?

### Takeaway
As of Oct 2026 the top open-weight voices on Artificial Analysis (AA) are large, mostly GPU-class or non-commercial models (Fish Audio Drama 3 Preview / S2 Pro, Breeze TTS 2, Ant Group Ming-3.0-tts, Mistral Voxtral TTS, Step Audio EditX). Kokoro-82M is no longer #1 but remains the best-ranked *tiny, CPU-friendly, Apache-2.0* model (~1060 Elo, roughly 6th-8th among open weights), which makes it the natural-quality/efficiency sweet spot for a laptop study app.

### Cited Findings
- AA overall TTS board: Gemini 3.1 Flash TTS (cloud) leads at Elo 1214; among open weights Step Audio EditX (Mar 2026) ~1111 Elo is above Kokoro 82M v1.0 ~1062 — [AA leaderboard](https://artificialanalysis.ai/text-to-speech/leaderboard)
- AA open-weights provider-voice board: Kokoro 82M v1.0 at 1066 ±11 (5,450 samples), ranked ~7th-8th — [AA open weights](https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice/open-weights); an Aug 2026 summary puts Kokoro at 1,060 Elo, 6th, "ahead of models fifty times larger" — [offlinetts.com ranking 2026](https://offlinetts.com/blog/tts-model-ranking-2026/)
- Kokoro's "#1 on TTS Arena" claim dates to its v0.19 launch on the HF blind-vote TTS Arena; it has since slid as newer entries arrived (treat "#1" claims as dated) — [texttolab Kokoro review](https://texttolab.com/blog/kokoro-tts-review); [ocdevel](https://ocdevel.com/blog/20250720-tts)
- AA Provider-Voice snapshot (Oct 2026): Fish Audio Drama 3 Preview 1248±15, Breeze TTS 2 1230, Ming-3.0-tts 1191, Fish Audio S2 Pro 1110 — [AA on X](https://x.com/ArtificialAnlys/status/2112389514404462613); Breeze TTS 2 claimed #1 open weights at 1,215 Elo, 50 languages, at an earlier point — [orcarouter](https://www.orcarouter.ai/blog/breeze-tts-2-tops-open-weights-speech-arena); [breezeblue (vendor)](https://breezeblue.ai/blog/breeze-tts-2-artificial-analysis-open-weights-no-1)
- AA Controlled Voice Arena (same 8 cloned voices): Ming-3.0-tts #1 open weights at 1,069 (1,827 appearances), ahead of Fish Drama 3 Preview 1,059 and Breeze TTS 2 1,019; Ming also #1 on Pronunciation Robustness — [AA on X](https://x.com/ArtificialAnlys/status/2112389514404462613)
- Earlier (July 8, 2026) Controlled Voice snapshot: Fish S2 Pro 1,034; Mistral Voxtral TTS 1,024; Resemble Chatterbox 930; Microsoft VibeVoice 7B 916; OpenVoice v2 806 — [AA on X](https://x.com/ArtificialAnlys/status/2074886571166462405?lang=en)
- Kokoro is AA's cheapest listed model at $0.65 per 1M characters (hosted) — [AA leaderboard](https://artificialanalysis.ai/text-to-speech/leaderboard)
- 2026 roundup: Kokoro = best small English model (Apache 2.0; weak in non-English); Chatterbox = strongest clearly-open (MIT) model for expressive English + cloning, "ranks highest among clearly open-weight models on TTS Arena"; Qwen3-TTS = instruction-steerable delivery, Apache 2.0 but heavy/slow without CUDA; Supertonic 3 small multilingual CPU model with use-restricted license, repo archived; Piper for Raspberry Pi/Home Assistant — [yaps.ai best local TTS 2026](https://www.yaps.ai/blog/best-local-tts-models)
- CosyVoice2-0.5B (multilingual, streaming), Fish Audio and IndexTTS are listed as frequently recommended in r/LocalLLaMA (claim by list author, unverified) — [texttolab open-source TTS](https://texttolab.com/blog/open-source-text-to-speech)
- Zyphra has released Zonos2, described in its README as "a leading open-weight text-to-speech MoE" — [Zonos2 GitHub](https://github.com/Zyphra/Zonos2/)
- Qwen3-TTS released Jan 22, 2026 (Apache 2.0): 1.7B VoiceDesign/CustomVoice/Base and 0.6B CustomVoice/Base — [MarkTechPost](https://www.marktechpost.com/2026/01/22/qwen-researchers-release-qwen3-tts-an-open-multilingual-tts-suite-with-real-time-latency-and-fine-grained-voice-control/); [Qwen3-TTS tech report](https://arxiv.org/html/2601.15621v1)
- Newer small CPU models appearing in 2026 benchmarks: Kyutai Pocket TTS (~100M), Supertonic 3 (99M, 31 languages), Inflect-Nano-v1 — [heyneo CPU benchmark](https://heyneo.com/blog/kokoro-supertonic-inflect-nano-pocket-tts-cpu-benchmark); [ai-deck Supertonic](https://ai-deck.app/blog/supertonic/)

### Inferences
- For a free laptop app reading 50+ pages, the leaderboard leaders (4-5B Fish, Ming, Breeze, VibeVoice 7B) are not practical defaults: GPU-heavy and/or non-commercial. The practical frontier is Kokoro (quality/size), Pocket TTS / Supertonic / Kitten (tiny CPU), Chatterbox Turbo / Qwen3-TTS 0.6B (GPU tier, more expressive).
- Arena Elo measures short-clip preference (often expressive/conversational); for calm long-form expository reading, a stable "audiobook narrator" voice matters more than emotion, which favors Kokoro-style non-autoregressive models.

### Gaps
- Could not load the live AA/HF TTS Arena pages; no single snapshot ranking all requested models (Orpheus, Dia, Sesame CSM, Spark-TTS, Higgs Audio, MeloTTS, Parler, StyleTTS2, F5) found. No AA Elo found for Qwen3-TTS, Pocket TTS, Kitten.
- Breeze TTS 2 and Ming-3.0-tts licenses and hardware needs not verified.

## 2. Speed (CPU vs GPU RTF), RAM/VRAM, model size, streaming

### Takeaway
Kokoro-82M runs faster than real time on ordinary CPUs (RTF ~0.45-0.65 on 4-core server CPUs; ~0.16 on Apple M3 Pro) and ~0.03 on an A100; tiny models (Supertonic, Pocket TTS, Kitten, Piper) are faster still. LLM-based models (Chatterbox, Qwen3-TTS, Orpheus, Fish S2) generally need a GPU. Benchmarks disagree heavily on first-audio latency depending on method; sentence-level chunked streaming hides most latency for document reading.

### Cited Findings
- Kokoro-82M ONNX on 4-core Intel Xeon Platinum 8272CL, CPU only: mean RTF 0.641 (~1.6x real time) in one post; 0.5711 (~1.8x) in another post on same hardware — [heyneo Pocket comparison](https://heyneo.com/blog/kokoro-supertonic-inflect-nano-pocket-tts-cpu-benchmark); [heyneo Inflect comparison](https://heyneo.com/blog/kokoro-supertonic-inflect-nano-cpu-tts-benchmark)
- Kokoro on AMD EPYC 7763 (4 cores, CPUExecutionProvider): RTF ~0.45-0.72 across text lengths — [heyneo Kokoro vs Supertonic 3](https://heyneo.com/blog/kokoro-tts-vs-supertonic-3-tts)
- Kokoro on Apple M3 Pro: 22 s narration rendered in 3.5 s (RTF ~0.16; runtime unspecified) — [VisionStory review](https://www.visionstory.ai/open-source/kokoro-tts)
- Kokoro RTF ~0.03 on A100 GPU — [Spheron](https://www.spheron.network/blog/deploy-open-source-tts-gpu-cloud-2026/)
- Kokoro ONNX 8-bit quantized export is 92.4 MB (onnx-community/Kokoro-82M-v1.0-ONNX, model_quantized.onnx) — via [search summary of heyneo/HF](https://heyneo.com/blog/kokoro-tts-vs-supertonic-3-tts)
- Picovoice CPU benchmark (Ryzen 7 5700X; vendor-run, code Apache-2.0): Piper first-token latency 1,720 ms, peak memory 2.6 GB; Kokoro 3,658 ms, 2.0 GB peak, 341 MB model; Kitten TTS Nano 320 MB peak memory, does not stream; Chatterbox and Kitten synthesize whole clip before playback — [Picovoice on-device TTS](https://picovoice.ai/blog/on-device-tts/); [Picovoice benchmark repo](https://github.com/Picovoice/tts-latency-benchmark)
- Contradicting measurement on Apple M5 Max: ~40 ms first audio for Piper, ~90 ms for Kokoro; ~300 MB RAM Piper, ~900 MB Kokoro — [Contra Collective](https://contracollective.com/blog/kokoro-vs-piper-vs-xtts-local-text-to-speech-m5-max-2026)
- Kitten TTS Nano: 15M params, 56 MB float, 25 MB int8 (official README); ONNX, CPU-only, no GPU required; Picovoice reports 42 MB INT8 (conflict); some users report issues with nano-int8, fp32 more stable — [KittenTTS GitHub](https://github.com/KittenML/KittenTTS); [Picovoice](https://picovoice.ai/blog/on-device-tts/); [binaryverseai](https://binaryverseai.com/kitten-tts-v0-8-local-cpu-install-guide-docker/)
- Kitten TTS v0.8 marketed as "sub-25MB SOTA speech for edge devices" — [jangwook.net](https://jangwook.net/en/blog/en/kitten-tts-v08-tiny-sota/)
- Kyutai Pocket TTS: ~100M params, reported ~6x real time on MacBook Air M4 and ~200 ms to first audio chunk on 2 CPU cores (secondary sources); generates audio token-by-token (streams) — [BrightCoding](https://www.blog.brightcoding.dev/2026/06/10/pocket-tts-why-developers-are-ditching-gpu-tts-forever); [Kyutai](https://kyutai.org/tts/); [nahornyi.ai](https://nahornyi.ai/en/news/kyutai-pocket-tts-open-source-lightweight-tts)
- Supertonic 3: project benchmark 5.00x real time on 16-thread CPU; third-party CPU RTF ~0.165 (2-step) and ~0.313 (5-step); another blog reports lower MOS at 2-step; README claims up to 167x real time on M4 Pro (outlier) — [localclaw](https://localclaw.io/tts/supertonic-3); [heyneo](https://heyneo.com/blog/kokoro-tts-vs-supertonic-3-tts); [ai-trove](https://ai-trove.com/en/supertonic)
- Chatterbox Turbo (Dec 2025): 350M params, MIT; decoder distilled from 10 steps to 1; vendor claims 75 ms latency and 6x real time; third-party spec RTF 0.499 on RTX 4090 (~2x real time); <150 ms first chunk; VRAM guidance from guides: min 6 GB, 10 GB+ recommended (unofficial) — [Resemble (via translate)](https://translate.google.com/translate?u=https%3A%2F%2Fwww.resemble.ai%2Flearn%2Fmodels%2Fchatterbox-turbo&hl=es&sl=en&tl=es&client=srp); [Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server); [codersera](https://codersera.com/blog/chatterbox-turbo-run-and-install-locally-free-elevenlabs-alternative-2026/); [localaimaster](https://localaimaster.com/blog/chatterbox-tts-setup-guide)
- Chatterbox-TTS-Server runs on NVIDIA CUDA, AMD ROCm and CPU, with audiobook-scale text processing — [devnen/Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server)
- Qwen3-TTS first-packet latency 97 ms (0.6B) / 101 ms (1.7B) at concurrency 1 (rises to ~299/333 ms at concurrency 6), measured in optimized environment; slow without CUDA GPU — [Qwen3-TTS report](https://arxiv.org/html/2601.15621v1); [glbgpt review](https://www.glbgpt.com/hub/qwen3-tts-review/); [yaps.ai](https://www.yaps.ai/blog/best-local-tts-models)
- Fish Audio S2 Pro: 4B Slow AR + 400M Fast AR (HF card says 5B); bf16 ~10.3 GB; GGUF 9.3 GB (f16) down to 2.4 GB (q2_k); ships SGLang streaming engine — [fish-speech GitHub](https://github.com/fishaudio/fish-speech); [HF s2-pro](https://huggingface.co/fishaudio/s2-pro); [s2-pro-gguf](https://huggingface.co/rodrigomt/s2-pro-gguf)
- Orpheus adapter silently truncates at 2,048 tokens (~25 s audio, ~70 words) without chunking — [mstar issue #680](https://github.com/mstar-project/mstar/issues/680)
- F5-TTS caps generation ~30 s per pass; CLI/Gradio auto-chunk — [localaimaster F5 guide](https://localaimaster.com/blog/f5-tts-setup-guide)

### Inferences
- A 50-page study doc (~25k words, roughly 2.5-3 h of audio at ~150 wpm) on Kokoro CPU at RTF ~0.5 would take ~1.3-1.5 h to fully pre-render, but with sentence-level streaming playback starts after the first chunk (sub-second to a few seconds) and generation stays ahead of playback. Tiny models (Pocket/Supertonic/Kitten/Piper) give more headroom on weak laptops.
- The Picovoice "first-token latency" numbers (seconds) reflect feeding text token-by-token (LLM-agent scenario); for a reader app that has the full text, chunk-by-sentence latency is the relevant metric, which the M5 Max numbers better reflect.
- GPU-tier models (Chatterbox, Qwen3-TTS, Fish S2) are only viable for users with a ~6-12 GB NVIDIA GPU; not a safe default for a student laptop.

### Gaps
- No controlled benchmark on a typical consumer laptop CPU (e.g., Intel Core Ultra / Ryzen 7 mobile) or mid-range GPU (RTX 3060/4060) covering all models in one run. Piper RTF numbers specifically not found in this pass. VRAM for Kokoro GPU, Orpheus 3B, Dia 1.6B, Sesame CSM 1B, Spark-TTS, Higgs Audio not found.

## 3. Licenses and voice availability

### Takeaway
Permissive and safe to bundle: Kokoro (Apache-2.0 weights), Chatterbox/Turbo (MIT), Qwen3-TTS (Apache-2.0), Kitten nano/micro (Apache-2.0 per sherpa-onnx review; check per model). Caveated: Piper engine is now GPL-3.0 (piper1-gpl) with per-voice licenses (some CC BY-NC-SA); Pocket TTS weights CC-BY-4.0 (gated download); Supertonic OpenRAIL-M (use restrictions, archived). Non-commercial: XTTS-v2 (CPML), Fish S2 Pro (Fish Audio Research License), VibeVoice (research release, pulled).

### Cited Findings
- Kokoro: Apache 2.0, weak at non-English — [yaps.ai](https://www.yaps.ai/blog/best-local-tts-models); 54 voices usable in-browser — [offlinetts Kokoro guide](https://offlinetts.com/blog/kokoro-tts-complete-guide/); sherpa-onnx ships kokoro-multi-lang-v1_1 (Chinese+English, 103 speakers) and kokoro-en-v0_19 (11 speakers) — [sherpa-onnx TTS docs](https://k2-fsa.github.io/sherpa/onnx/tts/index.html)
- Kokoro and Kitten weights Apache-2.0; Supertonic 3 BigScience OpenRAIL-M; Piper, Kitten and Kokoro v0.19 depend on espeak-ng (relevant for GPL redistribution) — [rtchat license review issue](https://github.com/muxable/rtchat/issues/1500)
- KittenTTS: code Apache-2.0 but README warns models are licensed separately; larger KittenTTS 2 under "Stellon Labs Community License" — [KittenTTS GitHub](https://github.com/KittenML/KittenTTS)
- Piper: original rhasspy/piper (MIT) archived Oct 2025; successor OHF-Voice/piper1-gpl is GPL-3.0; voices remain in rhasspy/piper-voices on HF; each voice has its own license (public domain, CC-BY, Blizzard custom, CC BY-NC-SA) — [piper1-gpl](https://github.com/OHF-voice/piper1-gpl); [qwe.edu.pl](https://www.qwe.edu.pl/ai-tools/install-piper-tts-open-source/); [voiced issue #68](https://github.com/JulianBeaulieu/voiced/issues/68); MIT-licensed third-party fork piper-plus with no espeak-ng dependency (self-claim) — [piper-plus](https://github.com/ayutaz/piper-plus/blob/dev/README_EN.md)
- Chatterbox Turbo MIT, commercial use incl. closed source allowed; sources conflict on Turbo being English-only vs 23 languages (Chatterbox Multilingual v3 covers 25 languages) — [Resemble](https://translate.google.com/translate?u=https%3A%2F%2Fwww.resemble.ai%2Flearn%2Fmodels%2Fchatterbox-turbo&hl=es&sl=en&tl=es&client=srp); [texttolab Chatterbox (20 voices)](https://texttolab.com/chatterbox); [localaimaster multilingual v3](https://localaimaster.com/blog/chatterbox-multilingual-v3)
- Qwen3-TTS: Apache 2.0; CustomVoice has preset speakers (one guide says 9 presets; "49+" claim looks unreliable); 3 s voice cloning — [Qwen3-TTS guide](https://dev.to/czmilo/qwen3-tts-the-complete-2026-guide-to-open-source-voice-cloning-and-ai-speech-generation-1a2efca05cd6); [clore docs](https://docs.clore.ai/guides/audio-and-voice/qwen3-tts)
- Kyutai Pocket TTS: code MIT; weights CC-BY-4.0 with auto-gated HF download (some blogs wrongly say MIT); language support conflicting (English-only vs EN/FR/DE/ES/PT/IT) — [tapioca issue #31](https://github.com/kyndlo/tapioca/issues/31); [Kyutai](https://kyutai.org/tts/)
- Supertonic: code MIT, weights OpenRAIL-M; supertone-oss-archive repo archived (Supertonic 1 & 2); Voice Builder access ends Aug 31, 2026 — [supertonic archive](https://github.com/supertone-oss-archive/supertonic); [HF supertonic license](https://huggingface.co/Supertone/supertonic/blob/main/README.md); [localclaw](https://localclaw.io/tts/supertonic-3)
- XTTS-v2: weights under Coqui Public Model License 1.0.0 (non-commercial); Coqui shut down (late 2023/Jan 2024), no commercial license available; maintained fork idiap/coqui-ai-TTS (PyPI coqui-tts, MPL-2.0 toolkit), v0.27.5 Jan 2026 — [PromptQuorum XTTS review](https://www.promptquorum.com/power-local-llm/xtts-v2-review); [PromptQuorum Coqui review](https://www.promptquorum.com/power-local-llm/coqui-tts-review); [vantaige](https://vantaige.io/ai-tool/coqui-tts)
- Fish S2 Pro: Fish Audio Research License — research/non-commercial free, commercial needs separate license — [HF fishaudio/s2-pro](https://huggingface.co/fishaudio/s2-pro); [fish-speech](https://github.com/fishaudio/fish-speech)
- VibeVoice: Microsoft removed VibeVoice-TTS code Sept 2025 over misuse; original supported up to 90 min / 4 speakers; code MIT but models are research releases not recommended for real-world deployment; community fork preserves 1.5B; official repo now centers on ASR and a realtime 0.5B TTS — [microsoft/VibeVoice](https://github.com/microsoft/VibeVoice); [community fork](https://github.com/vibevoice-community/VibeVoice); [VibeVoice page](https://microsoft.github.io/VibeVoice/)

### Inferences
- For a free app that may later be shared publicly, Kokoro (Apache) + optional Chatterbox Turbo (MIT) is the cleanest license combination. Using Piper via piper1-gpl or espeak-ng-based phonemizers inside a distributed binary pulls in GPL obligations — acceptable if the app is itself open source (GPL-compatible), a risk otherwise.
- Non-commercial models (XTTS-v2, Fish S2) are legally fine for a student's personal use but poor foundations for an app intended to be distributed.

### Gaps
- Exact Kokoro v1.0 English voice breakdown (American vs British counts) not confirmed in this pass; no Canadian-English-specific voices identified in any open model (Canadian users typically get American or British accents).
- Licenses for Ming-3.0-tts, Breeze TTS 2, Step Audio EditX, Dia, Orpheus, Sesame CSM, Spark-TTS, Higgs Audio, MeloTTS, Parler-TTS not verified in this pass.

## 4. Prosody control (speed, pauses, SSML/phonemes, emphasis)

### Takeaway
Kokoro offers a native `speed` parameter (model-level duration scaling, not resampling), phoneme input via its misaki G2P, and chunk control; SSML is only via wrappers (Kokoro-FastAPI). LLM-style models (Qwen3-TTS, Fish S2) offer natural-language style/emotion instructions but less deterministic control. OS engines support SSML/rate natively.

### Cited Findings
- Kokoro `KPipeline(text, voice, speed=1.0, split_pattern=...)` yields (graphemes, phonemes, audio @24 kHz) per chunk; uses misaki as G2P — [PyPI kokoro](https://pypi.org/project/kokoro/); [HF space example](https://huggingface.co/spaces/NeuralFalcon/KOKORO-TTS-1.0/blob/c366e2b0fa712f3d03f09a7d648b31c6004fa3a4/app.py)
- Kokoro-FastAPI adds OpenAI-compatible API, SSML, multi-voice mixing, per-word caption timestamps, readalong web UI; CPU/AMD/NVIDIA — [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI)
- Qwen3-TTS steers delivery through plain-language instructions (VoiceDesign) — [yaps.ai](https://www.yaps.ai/blog/best-local-tts-models); [MarkTechPost](https://www.marktechpost.com/2026/01/22/qwen-researchers-release-qwen3-tts-an-open-multilingual-tts-suite-with-real-time-latency-and-fine-grained-voice-control/)
- Fish S2 Pro: emotion in speech controlled with natural language — [dev.to S2-Pro](https://dev.to/gary_yan_86eb77d35e0070f5/fish-audio-s2-pro-a-tts-model-with-emotion-in-speech-controlled-with-natural-language-1e7n)

### Inferences
- For study notes (formulas, units, Latin binomials, acronyms), the key control is pronunciation: Kokoro/Piper/Kitten's phoneme pipelines allow custom lexicon overrides; LLM-based models can't be corrected at phoneme level. A text-normalization pre-pass (expand "mL", "°C", "p < 0.05", chemical formulas) will matter more than SSML.
- Pause control can be implemented app-side by chunking at headings/bullets and inserting silence between chunks, independent of engine.

### Gaps
- No confirmed source on whether Kokoro's speed parameter preserves pitch at extremes (likely, since it scales predicted durations, but unverified). No sources on emphasis control in Kokoro/Piper. SSML support of Piper/sherpa-onnx not verified.

## 5. Long-form stability (hallucination, skipping, drift, chunking)

### Takeaway
Autoregressive LLM-style TTS (Orpheus, Qwen3-TTS, F5, Dia, VibeVoice, Chatterbox) degrades on long inputs — skipping, hallucinating, truncating — so every engine should be fed sentence/paragraph chunks. Non-autoregressive small models (Kokoro, Piper, Kitten) don't hallucinate in the LLM sense but still have per-pass length limits and are chunked by their pipelines.

### Cited Findings
- "Taming Long-form TTS" (2026): defines skip = ≥10 contiguous deleted words, hallucination = ≥20-word run of substitutions/insertions; Qwen3-TTS-0.6B worst-of-N WER rises from 5.4% (<500 words) to 35.2% (>1,500 words concatenated) — [arXiv 2609.16989](https://arxiv.org/pdf/2609.16989)
- Orpheus: silent truncation at 2,048-token cap (~25 s) without chunking; open issue on hallucinated audio at end of synthesis (#289) — [mstar #680](https://github.com/mstar-project/mstar/issues/680); [Orpheus issues](https://github.com/canopyai/Orpheus-TTS/issues)
- F5-TTS paper: high deletion rate = word-skipping on stacks of repeated words; ~30 s per pass, chunk + cross-fade — [F5-TTS paper](https://arxiv.org/pdf/2410.06885); [HartsyInference PR #421](https://github.com/HartsyAI/HartsyInference/pull/421)
- Zonos2 auto-splits long text into overlapping chunks, each a teacher-forced continuation of prior audio (for consistency) — [Zonos2](https://github.com/Zyphra/Zonos2/)
- Chatterbox-TTS-Server explicitly supports "large audiobook-scale text processing" (chunking) — [Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server)
- Kokoro guides cover chunking for long text — [explainx Kokoro guide](https://explainx.ai/blog/kokoro-local-cpu-tts-openai-compatible-guide-2026)

### Inferences
- Design the app around sentence-level chunks (also needed for highlighting, resume, and seeking); this neutralizes most long-form failure modes and makes engines swappable.
- For autoregressive engines, consider an ASR check (e.g., Whisper) to detect skipped words if quality matters; unnecessary for Kokoro/Piper.

### Gaps
- No sources found on Dia, Sesame CSM, Spark-TTS or Higgs Audio long-form behaviour; no comparative skip/hallucination rates across engines. No measurement of Kokoro voice drift across chunk boundaries.

## 6. Word/phoneme-level timestamps (for synchronized highlighting)

### Takeaway
Native timing exists for Kokoro in Python (token-level durations, exposed by Kokoro-FastAPI as per-word captions) and via HeadTTS in the browser (phoneme timestamps); kokoro-js's public streaming API does not expose alignment, so browser apps estimate or forced-align. OS engines (SAPI word-boundary events, Apple willSpeakRange) give word callbacks natively. LLM-based models give no timestamps (need forced alignment).

### Cited Findings
- Kokoro Python exposes per-token timings; kokoro-js streaming returns text+audio per chunk but not alignment — workaround: spread chunk duration over characters — [Ryan Welch blog](https://ryanwelch.co.uk/blog/kokoro-word-timestamps/)
- Kokoro-FastAPI: per-word timestamped captions — [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI)
- HeadTTS: Kokoro in-browser (WebGPU/WASM) or Node, with phoneme-level timestamps and visemes; WebGPU only default in latest desktop browsers, WASM fallback much slower — [HeadTTS](https://github.com/met4citizen/HeadTTS)
- "onnx-community/Kokoro-82M-v1.0-ONNX-timestamped" model used with device:"webgpu" in a three.js forum thread (timestamp output not confirmed) — [three.js forum](https://discourse.threejs.org/t/local-browser-tts-with-kokoro-for-npc-dialogue-and-narration/91424)
- A Chromium WebGPU PR notes Kokoro on WebGPU garbles on Firefox and iOS (excluded); highlighting estimated — [batcave PR #27](https://github.com/kyletolle/batcave/pull/27); OfflineTTS uses local Whisper alignment with estimate fallback — [offlinetts Kokoro guide](https://offlinetts.com/blog/kokoro-tts-complete-guide/)
- Apple AVSpeechSynthesizer delegate `willSpeakRangeOfSpeechString` fires before each word with its character range (older reports of wrong ranges for numerals, and callbacks not firing on Big Sur/Catalina) — [useyourloaf](https://useyourloaf.com/blog/synthesized-speech-from-text/); [Apple forum 133104](https://developer.apple.com/forums/thread/133104); [Apple forum 678287](https://developer.apple.com/forums/thread/678287)

### Inferences
- Simplest robust approach: highlight at sentence level always (exact, since chunks are sentences), and word level via Kokoro's Python token durations (desktop) or HeadTTS/timestamped ONNX (browser); fall back to proportional estimation within a sentence.

### Gaps
- Not verified whether Piper or sherpa-onnx expose phoneme durations through public APIs; no confirmation for Kitten/Pocket/Supertonic timestamps.

## 7. Integration paths (Python, ONNX, Rust/sherpa-onnx, browser, mobile)

### Takeaway
Kokoro has the broadest integration surface: Python (`kokoro` pip), ONNX (onnx-community exports incl. 8-bit), browser (kokoro-js/transformers.js WebGPU/WASM, HeadTTS), Docker server (Kokoro-FastAPI), and sherpa-onnx (C/C++ with Python, Go, Android APKs etc.). sherpa-onnx is the best single runtime to support multiple small engines (Kokoro, Kitten, Piper/VITS, Matcha, Pocket, Supertonic, ZipVoice).

### Cited Findings
- sherpa-onnx TTS supports Kokoro, KittenTTS (kitten-nano-en-v0_2, kitten-mini-en-v0_1), Piper/VITS voices, Matcha (en_US ljspeech) — [sherpa-onnx TTS docs](https://k2-fsa.github.io/sherpa/onnx/tts/index.html); Go bindings list Vits, Matcha, Kokoro, Kitten, Zipvoice, Pocket, Supertonic config types; providers cpu/cuda/coreml — [Go package](https://pkg.go.dev/github.com/k2-fsa/sherpa-onnx-go-windows)
- Prebuilt Android system TTS-engine APKs for kokoro-multi-lang-v1_1, kitten-micro-en-v0_8, matcha — [sherpa-onnx APK engine](https://k2-fsa.github.io/sherpa/onnx/tts/apk-engine.html)
- LiveKit plugin for local sherpa-onnx TTS (Kokoro, Kitten, Piper) — [livekit issue #7747](https://github.com/livekit/agents/issues/7747)
- Kokoro in browser with 54 voices — [offlinetts Kokoro guide](https://offlinetts.com/blog/kokoro-tts-complete-guide/); Supertonic 3 as 31-language browser TTS — [offlinetts Supertonic guide](https://offlinetts.com/blog/supertonic-3-browser-tts-guide/)
- Qwen3-TTS GGUF port exists (llama.cpp-style) — [Qwen3-TTS-GGUF](https://github.com/HaujetZhao/Qwen3-TTS-GGUF/blob/main/Qwen3-TTS%20Technical%20Report.md); Fish S2 Pro MLX port for Apple Silicon — [mlx-community](https://huggingface.co/mlx-community/fish-audio-s2-pro-bf16)
- KittenTTS: lightweight ONNX, pip-installable — [KittenTTS GitHub](https://github.com/KittenML/KittenTTS)

### Inferences
- Architecture suggestion for the report: Python/desktop or local web app with sherpa-onnx or Kokoro ONNX as the default engine; browser build using kokoro-js with WebGPU and WASM fallback (avoid Firefox/iOS WebGPU issues); OS voices as zero-download fallback.

### Gaps
- iOS sherpa-onnx support and Rust-native crates (e.g., kokoro Rust ports) not confirmed in this pass.

## 8. OS-native free voices as baselines/fallbacks

### Takeaway
Windows 11 Narrator "natural" voices are high quality and offline but not officially available to third-party apps (only via the unofficial, fragile NaturalVoiceSAPIAdapter); classic SAPI/OneCore voices are robotic but universal with word-boundary events. macOS/iOS AVSpeechSynthesizer gives offline voices with per-word range callbacks — a strong built-in baseline for highlighting.

### Cited Findings
- NaturalVoiceSAPIAdapter exposes Narrator natural, Edge Read Aloud and Azure voices to any SAPI 5 app; uses keys extracted from system files ("more like a hack"); latest Narrator natural voice versions stopped working with it — recommends older voice versions; can break after system updates — [NaturalVoiceSAPIAdapter](https://github.com/gexgd0419/NaturalVoiceSAPIAdapter); [README](https://github.com/gexgd0419/NaturalVoiceSAPIAdapter/blob/master/README.md)
- Microsoft limits third-party access to embedded natural speech models (application form required) — [TextToTalk issue #121](https://github.com/karashiiro/TextToTalk/issues/121); Wikipedia (2024): no third-party apps can use these voices — [Wikipedia](https://en.wikipedia.org/wiki/Microsoft_text-to-speech_voices)
- AVSpeechSynthesizer: offline synthesis, many voices, word-range delegate for highlighting; Personal Voice exposed via API — [useyourloaf](https://useyourloaf.com/blog/synthesized-speech-from-text/); [apireview](https://catalog.apireview.net/catalog/f44f6fd56c6425f0be746390606e4b8f)

### Inferences
- Web Speech API (speechSynthesis) in browsers wraps these OS voices and provides `boundary` events on many platforms — usable as a zero-install fallback, but quality/availability varies per OS.

### Gaps
- No sources retrieved on eSpeak NG quality/licensing (commonly known as GPL-3.0 and robotic but tiny; unverified here), on Apple premium/enhanced voice download/offline details, or on whether Edge "online natural" voices work offline (they are generally cloud-based; unverified).
