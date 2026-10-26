import json
import threading

import numpy as np
import pymupdf
import pytest
import soundfile as sf

from storyteller.extract import NoTextLayerError
from storyteller.library import Library, PackInfo
from storyteller.settings import Settings, home
from storyteller.speech import BOX_KINDS
from storyteller.voice.base import SynthResult


@pytest.fixture
def lib():
    return Library()


@pytest.fixture
def mini_bytes(mini_pdf):
    return mini_pdf.read_bytes()


@pytest.fixture
def plain_bytes(plain_pdf):
    return plain_pdf.read_bytes()


def test_add_same_bytes_returns_existing(lib, mini_bytes):
    first = lib.add_pdf(mini_bytes, "pack.pdf")
    assert isinstance(first, PackInfo)
    assert first.id and len(first.id) == 16
    script = lib.script(first.id)
    lib.set_position(first.id, script.sentences[3].id)
    again = lib.add_pdf(mini_bytes, "renamed.pdf")
    assert again.id == first.id
    assert again.position == script.sentences[3].id
    assert again.filename == "pack.pdf"
    assert again.added == first.added
    assert len(lib.list()) == 1


def test_same_name_different_bytes_new_pack(lib, mini_bytes, plain_bytes):
    a = lib.add_pdf(mini_bytes, "notes.pdf")
    b = lib.add_pdf(plain_bytes, "notes.pdf")
    assert a.id != b.id
    assert {p.id for p in lib.list()} == {a.id, b.id}


def test_script_cached_and_rebuilt(lib, plain_bytes):
    info = lib.add_pdf(plain_bytes, "plain.pdf")
    script_file = home() / "packs" / info.id / "script.json"
    assert script_file.exists()
    n = len(lib.script(info.id).sentences)
    script_file.unlink()
    assert len(lib.script(info.id).sentences) == n
    assert script_file.exists()
    lib.add_skip_pattern(info.id, r"Confidential")
    assert len(lib.script(info.id).sentences) == n - 1
    skip = json.loads((home() / "packs" / info.id / "skip.json").read_text())
    assert skip == ["Confidential"]
    lib.add_skip_pattern(info.id, r"Confidential")
    assert json.loads((home() / "packs" / info.id / "skip.json").read_text()) == skip


def test_bad_skip_pattern_rejected(lib, plain_bytes):
    info = lib.add_pdf(plain_bytes, "plain.pdf")
    with pytest.raises(ValueError):
        lib.add_skip_pattern(info.id, "(")
    assert not (home() / "packs" / info.id / "skip.json").exists()


def test_rebuild_merges_unknown_symbols(lib, plain_bytes):
    info = lib.add_pdf(plain_bytes, "plain.pdf")
    s = Settings.load()
    s.unknown_symbols = ["Ω"]
    s.save()
    lib.rebuild_script(info.id)
    assert "Ω" in Settings.load().unknown_symbols


def test_clip_roundtrip(lib, mini_bytes):
    from storyteller.voice import get_backend

    info = lib.add_pdf(mini_bytes, "pack.pdf")
    sentence = lib.script(info.id).sentences[0]
    result = get_backend().synth([w.text for w in sentence.spoken], "af_heart")
    path = lib.clip_path(info.id, sentence, "af_heart")
    assert path.parent == home() / "packs" / info.id / "clips" / "af_heart"
    assert path.suffix == ".wav"
    assert lib.load_clip_meta(path) is None
    lib.save_clip(path, result)
    meta = lib.load_clip_meta(path)
    assert len(meta["words"]) == len(result.word_times)
    assert meta["duration"] == pytest.approx(len(result.audio) / result.sample_rate)
    assert all(isinstance(w, list) and len(w) == 2 for w in meta["words"])
    data = sf.info(path)
    assert (data.samplerate, data.subtype, data.channels) == (24000, "PCM_16", 1)


def test_save_clip_clips_to_pcm16_range(lib, mini_bytes):
    info = lib.add_pdf(mini_bytes, "pack.pdf")
    sentence = lib.script(info.id).sentences[0]
    path = lib.clip_path(info.id, sentence, "af_heart")
    lib.save_clip(path, SynthResult(np.array([2.0, -3.0, 0.5], dtype=np.float32), 24000, [(0.0, 0.1)]))
    audio, _ = sf.read(path, dtype="int16")
    assert list(audio[:2]) == [32767, -32768]
    assert audio[2] == pytest.approx(16384, abs=1)
    assert not list(path.parent.glob("*.tmp*"))


def test_clip_path_independent_of_speed(lib, mini_bytes):
    info = lib.add_pdf(mini_bytes, "pack.pdf")
    sentence = lib.script(info.id).sentences[0]
    before = lib.clip_path(info.id, sentence, "af_heart")
    s = Settings.load()
    s.speed = 1.75
    s.save()
    assert lib.clip_path(info.id, sentence, "af_heart") == before
    assert lib.clip_path(info.id, sentence, "am_michael") != before


def test_clip_path_rejects_unsafe_voice(lib, mini_bytes):
    info = lib.add_pdf(mini_bytes, "pack.pdf")
    sentence = lib.script(info.id).sentences[0]
    with pytest.raises(ValueError):
        lib.clip_path(info.id, sentence, "../evil")


def test_scanned_pdf_add_raises(lib, tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
    pix.clear_with(200)
    page.insert_image(page.rect, pixmap=pix)
    data = doc.tobytes()
    with pytest.raises(NoTextLayerError):
        lib.add_pdf(data, "scan.pdf")
    packs = home() / "packs"
    assert not packs.exists() or list(packs.iterdir()) == []
    assert lib.list() == []


def test_rendered_and_total(lib, mini_bytes):
    info = lib.add_pdf(mini_bytes, "pack.pdf")
    script = lib.script(info.id)
    assert (info.rendered, info.total) == (0, len(script.sentences))
    lib.save_clip(
        lib.clip_path(info.id, script.sentences[0], "af_heart"),
        SynthResult(np.zeros(2400, dtype=np.float32), 24000, [(0.0, 0.1)]),
    )
    got = lib.list()[0]
    assert got.rendered >= 1
    s = Settings.load()
    s.voice = "am_michael"
    s.save()
    assert lib.list()[0].rendered == 0


def test_list_most_recent_first(lib, mini_bytes, plain_bytes):
    a = lib.add_pdf(mini_bytes, "a.pdf")
    b = lib.add_pdf(plain_bytes, "b.pdf")
    assert [p.id for p in lib.list()] == [b.id, a.id]
    lib.set_position(a.id, lib.script(a.id).sentences[0].id)
    assert [p.id for p in lib.list()] == [a.id, b.id]


def test_pdf_path_and_unknown_id(lib, mini_bytes):
    info = lib.add_pdf(mini_bytes, "a.pdf")
    assert lib.pdf_path(info.id).read_bytes() == mini_bytes
    with pytest.raises(KeyError):
        lib.script("0" * 16)
    with pytest.raises(KeyError):
        lib.pdf_path("../x")


def test_concurrent_set_position_keeps_meta_valid(lib, mini_bytes):
    info = lib.add_pdf(mini_bytes, "a.pdf")
    ids = [s.id for s in lib.script(info.id).sentences[:8]]

    def work(sid):
        for _ in range(20):
            lib.set_position(info.id, sid)

    threads = [threading.Thread(target=work, args=(i,)) for i in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    meta = json.loads((home() / "packs" / info.id / "meta.json").read_text())
    assert meta["position"] in ids


def test_settings_roundtrip_and_clamp():
    s = Settings.load()
    assert s.speed == 1.0 and s.voice == "af_heart"
    s.speed = 5
    s.voice = "bf_emma"
    s.pronunciations = {"ATP": "A T P"}
    s.save()
    loaded = Settings.load()
    assert loaded.speed == 2.0
    assert loaded.voice == "bf_emma"
    assert loaded.pronunciations == {"ATP": "A T P"}
    (home() / "settings.json").write_text(json.dumps({"speed": 0.1}))
    assert Settings.load().speed == 0.75


def test_settings_defaults_have_all_box_kinds():
    s = Settings.load()
    assert set(s.read_boxes) == set(BOX_KINDS) and len(BOX_KINDS) == 10
    assert all(s.read_boxes.values())
    assert s.pauses == {"sentence": 250, "block": 600, "section": 1000}
    assert (s.skip_flags, s.read_badges) == (True, True)
    assert (s.sentence_color, s.word_color) == ("#fff3b0", "#f2a900")


def test_settings_merge_old_file_over_defaults():
    (home() / "settings.json").write_text(
        json.dumps({"read_boxes": {"chain": False}, "pauses": {"block": 900}, "bogus": 1})
    )
    s = Settings.load()
    assert s.read_boxes["chain"] is False
    assert s.read_boxes["traps"] is True and len(s.read_boxes) == 10
    assert s.pauses == {"sentence": 250, "block": 900, "section": 1000}
    assert not hasattr(s, "bogus")


def test_settings_corrupt_file_gives_defaults_and_backup():
    path = home() / "settings.json"
    path.write_text("{not json")
    s = Settings.load()
    assert s == Settings()
    assert (home() / "settings.json.bak").read_text() == "{not json"


def test_settings_wrong_types_fall_back():
    (home() / "settings.json").write_text(json.dumps({"speed": "fast", "voice": 3, "read_badges": "yes"}))
    s = Settings.load()
    assert (s.speed, s.voice, s.read_badges) == (1.0, "af_heart", True)


def test_settings_reads_home_at_call_time(monkeypatch, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    s = Settings.load()
    s.voice = "bm_george"
    s.save()
    monkeypatch.setenv("STORYTELLER_HOME", str(other))
    assert Settings.load().voice == "af_heart"


def test_script_options_mapping():
    s = Settings()
    s.skip_flags = False
    s.read_boxes["analogy"] = False
    s.pronunciations = {"x": "y"}
    o = s.script_options()
    assert o.read_flags is True
    assert o.read_boxes["analogy"] is False
    assert o.pronunciations == {"x": "y"} and o.pauses == s.pauses
    assert Settings().script_options().read_flags is False


def test_settings_non_utf8_file_gives_defaults_and_backup():
    (home() / "settings.json").write_bytes(b"\xff\xfe")
    assert Settings.load() == Settings()
    assert (home() / "settings.json.bak").read_bytes() == b"\xff\xfe"


def test_settings_invalid_voice_falls_back():
    (home() / "settings.json").write_text(json.dumps({"voice": "../evil"}))
    assert Settings.load().voice == "af_heart"


def test_settings_update_partial():
    s = Settings.update(speed=1.5, voice="bf_emma")
    assert (s.speed, s.voice) == (1.5, "bf_emma")
    assert Settings.load().speed == 1.5
    assert Settings.update(speed=9).speed == 2.0
    with pytest.raises(ValueError):
        Settings.update(bogus=1)


def test_position_survives_rebuild(lib, plain_bytes):
    info = lib.add_pdf(plain_bytes, "plain.pdf")
    old = lib.script(info.id)
    target = next(s for s in old.sentences if "Confidential" in " ".join(w.text for w in s.display))
    later = old.sentences[old.sentences.index(target) + 1 :]
    lib.set_position(info.id, target.id)
    lib.add_skip_pattern(info.id, r"Confidential")
    new = lib.script(info.id)
    pos = lib.list()[0].position
    assert pos in {s.id for s in new.sentences}
    assert target.block_id not in {s.block_id for s in new.sentences}
    assert not later or pos is not None
    # an earlier sentence keeps its place
    keep = new.sentences[1]
    lib.set_position(info.id, keep.id)
    lib.rebuild_script(info.id)
    assert lib.list()[0].position == keep.id
