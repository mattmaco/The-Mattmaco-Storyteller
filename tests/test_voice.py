import numpy as np
import pytest

from storyteller.voice import get_backend
from storyteller.voice.base import SynthResult, align_words, check_request
from storyteller.voice.stub import StubVoice


def test_align_exact():
    tokens = [("p", 0.0, 0.2), ("squared", 0.2, 0.7)]
    assert align_words(["p", "squared"], tokens, 0.7) == [(0.0, 0.2), (0.2, 0.7)]


def test_align_multi_token_word():
    tokens = [("A", 0.0, 0.1), ("1", 0.1, 0.3)]
    assert align_words(["A1"], tokens, 0.3) == [(0.0, 0.3)]


def test_align_trailing_punctuation_and_punct_tokens():
    tokens = [("genotypes", 0.0, 0.5), (".", 0.5, 0.5), ("matter", 0.6, 1.0)]
    out = align_words(["genotypes.", "matter"], tokens, 1.0)
    assert out == [(0.0, 0.5), (0.6, 1.0)]


def test_align_mismatch_proportional():
    tokens = [("something", 0.0, 0.4), ("else", 0.4, 0.9)]
    words = ["A1A2", "42", "x"]
    out = align_words(words, tokens, 2.0)
    assert len(out) == len(words)
    assert out[-1][1] == pytest.approx(2.0)
    assert out[0][0] == 0.0
    assert all(a[1] <= b[0] + 1e-9 for a, b in zip(out, out[1:]))
    assert all(0 <= s <= e <= 2.0 for s, e in out)


def test_align_none_timestamps():
    tokens = [("p", None, None), ("squared", 0.2, 0.7)]
    out = align_words(["p", "squared"], tokens, 1.0)
    assert len(out) == 2
    assert out[-1][1] == pytest.approx(1.0)
    assert out[0][1] <= out[1][0] + 1e-9


def test_align_pure_punctuation_word_gets_time():
    tokens = [("a", 0.0, 0.2), ("b", 0.3, 0.5)]
    out = align_words(["a", "-", "b"], tokens, 0.5)
    assert out == [(0.0, 0.2), (0.2, 0.2), (0.3, 0.5)]


def test_align_clamps_and_monotonic():
    tokens = [("a", 0.0, 0.5), ("b", 0.3, 0.9)]
    out = align_words(["a", "b"], tokens, 0.8)
    assert out[1][0] >= out[0][0]
    assert all(0 <= s <= e <= 0.8 for s, e in out)


def test_align_empty_words():
    assert align_words([], [], 1.0) == []


def test_stub_lengths():
    r = StubVoice().synth(["hello", "big", "world"], "af_heart")
    assert isinstance(r, SynthResult)
    assert r.sample_rate == 24000
    assert r.audio.dtype == np.float32 and r.audio.ndim == 1
    assert len(r.word_times) == 3
    assert len(r.audio) == pytest.approx(0.06 * len("hello big world") * 24000, abs=2)
    assert all(a[1] <= b[0] + 1e-9 for a, b in zip(r.word_times, r.word_times[1:]))
    assert r.word_times[-1][1] == pytest.approx(len(r.audio) / 24000)
    assert StubVoice().device == "stub"


def test_synth_rejects_empty_and_overlong():
    stub = StubVoice()
    with pytest.raises(ValueError):
        stub.synth([], "af_heart")
    with pytest.raises(ValueError):
        stub.synth(["", " "], "af_heart")
    with pytest.raises(ValueError):
        stub.synth(["x" * 301], "af_heart")
    with pytest.raises(ValueError):
        check_request(["a" * 150, "b" * 150], "af_heart")  # joined = 301
    check_request(["a" * 149, "b" * 150], "af_heart")  # joined = 300, ok


def test_get_backend_stub_cached():
    a = get_backend()
    assert isinstance(a, StubVoice)
    assert get_backend() is a


def test_import_without_voice_extra():
    import storyteller.voice.kokoro_backend  # noqa: F401  (must not import kokoro at module load)


def test_kokoro_smoke():
    pytest.importorskip("kokoro")
    from storyteller.voice.kokoro_backend import KokoroVoice

    r = KokoroVoice().synth(["Hardy-Weinberg", "equilibrium."], "af_heart")
    assert len(r.audio) > 0
    assert len(r.word_times) == 2
    assert r.word_times[0][0] <= r.word_times[1][0]
    assert all(s <= e for s, e in r.word_times)


def test_kokoro_wpm():
    pytest.importorskip("kokoro")
    from storyteller.voice.kokoro_backend import KokoroVoice

    text = (
        "Natural selection acts on heritable variation within a population, and over many "
        "generations the frequency of alleles that improve survival and reproduction tends "
        "to increase. When mating is random and no other forces act, genotype frequencies "
        "settle into the Hardy Weinberg proportions, which gives us a useful null model "
        "against which real populations can be compared."
    )
    words = text.split()
    voice = KokoroVoice()
    seconds = 0.0
    for i in range(0, len(words), 15):  # real sentences are <= 300 chars
        r = voice.synth(words[i : i + 15], "af_heart")
        seconds += len(r.audio) / r.sample_rate
    print(f"\nKokoro speed 1.0: {len(words)} words, {len(words) / (seconds / 60):.1f} wpm")


def test_kokoro_chunks_get_time_offsets():
    """Multi-result pipeline output is concatenated with per-chunk token offsets."""
    from types import SimpleNamespace as NS

    from storyteller.voice.kokoro_backend import KokoroVoice

    def result(n, toks):
        return NS(audio=np.zeros(n, dtype=np.float32),
                  tokens=[NS(text=t, start_ts=s, end_ts=e) for t, s, e in toks])

    class FakePipeline:
        def __call__(self, text, voice, speed, split_pattern):
            assert (speed, split_pattern) == (1.0, None)
            yield result(24000, [("one", 0.0, 0.5), (",", None, None)])
            yield result(12000, [("two", 0.1, 0.4)])

    kv = object.__new__(KokoroVoice)
    kv.device, kv.notice, kv._pipelines = "cpu", None, {"a": FakePipeline()}
    r = kv.synth(["one,", "two"], "af_heart")
    assert len(r.audio) == 36000
    assert r.word_times == [(0.0, 0.5), (pytest.approx(1.1), pytest.approx(1.4))]


def _fake_torch(monkeypatch, cuda_ok, available=True):
    import sys
    from types import SimpleNamespace as NS

    def zeros(*a, device=None, **k):
        if device == "cuda" and not cuda_ok:
            raise RuntimeError("CUDA error")

    def is_available():
        if available == "raise":
            raise RuntimeError("driver")
        return available

    monkeypatch.setitem(sys.modules, "torch", NS(zeros=zeros, cuda=NS(is_available=is_available)))


def _fake_kokoro(monkeypatch, fail):
    import sys
    from types import SimpleNamespace as NS

    built = []

    class KPipeline:
        def __init__(self, lang_code, device):
            if fail is not None and device == "cuda":
                raise fail
            self.lang_code, self.device = lang_code, device
            built.append((lang_code, device))

    monkeypatch.setitem(sys.modules, "kokoro", NS(KPipeline=KPipeline))
    return built


def test_cuda_init_failure_falls_back(monkeypatch):
    from storyteller.voice.kokoro_backend import KokoroVoice

    _fake_torch(monkeypatch, cuda_ok=False)
    kv = KokoroVoice()
    assert (kv.device, kv.notice) == ("cpu", "GPU unavailable, using CPU")


def test_cuda_probe_exception_falls_back(monkeypatch):
    from storyteller.voice.kokoro_backend import KokoroVoice

    _fake_torch(monkeypatch, cuda_ok=True, available="raise")
    kv = KokoroVoice()
    assert (kv.device, kv.notice) == ("cpu", "GPU unavailable, using CPU")


def test_no_cuda_is_plain_cpu(monkeypatch):
    from storyteller.voice.kokoro_backend import KokoroVoice

    _fake_torch(monkeypatch, cuda_ok=True, available=False)
    kv = KokoroVoice()
    assert (kv.device, kv.notice) == ("cpu", None)


def test_pipeline_runtimeerror_on_cuda_falls_back(monkeypatch):
    from storyteller.voice.kokoro_backend import KokoroVoice

    _fake_torch(monkeypatch, cuda_ok=True)
    _fake_kokoro(monkeypatch, RuntimeError("CUDA out of memory"))
    kv = KokoroVoice()
    assert kv.device == "cuda"
    assert kv._pipeline("a").device == "cpu"
    assert (kv.device, kv.notice) == ("cpu", "GPU unavailable, using CPU")


def test_pipeline_non_runtime_error_propagates(monkeypatch):
    from storyteller.voice.kokoro_backend import KokoroVoice

    _fake_torch(monkeypatch, cuda_ok=True)
    _fake_kokoro(monkeypatch, OSError("weights download failed"))
    kv = KokoroVoice()
    with pytest.raises(OSError):
        kv._pipeline("a")
    assert (kv.device, kv.notice) == ("cuda", None)


def test_late_fallback_rebuilds_other_pipelines_on_cpu(monkeypatch):
    from storyteller.voice.kokoro_backend import KokoroVoice

    _fake_torch(monkeypatch, cuda_ok=True)
    _fake_kokoro(monkeypatch, None)
    kv = KokoroVoice()
    first = kv._pipeline("a")
    assert first.device == "cuda"
    import kokoro

    def failing(lang_code, device):
        if device == "cuda":
            raise RuntimeError("CUDA error")
        return first.__class__(lang_code, device)

    monkeypatch.setattr(kokoro, "KPipeline", failing)
    assert kv._pipeline("b").device == "cpu"
    assert kv.device == "cpu"
    assert kv._pipeline("a").device == "cpu"  # rebuilt, not the stale cuda one


def test_get_backend_thread_safe(monkeypatch):
    import threading

    import storyteller.voice as v
    from storyteller.voice import stub

    monkeypatch.setattr(v, "_backend", None)
    made = []
    orig = stub.StubVoice

    class Slow(orig):
        def __init__(self):
            import time

            time.sleep(0.05)
            made.append(self)

    monkeypatch.setattr(stub, "StubVoice", Slow)
    got = []
    ts = [threading.Thread(target=lambda: got.append(v.get_backend())) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(made) == 1 and len({id(g) for g in got}) == 1
