"""espeak-ng ignores data paths longer than its fixed buffer; the backend copies the data to a short one."""

import sys
import types

import pytest

from storyteller.voice import kokoro_backend as kb


@pytest.fixture
def fake_espeak(monkeypatch, tmp_path):
    seen = {}

    def install(data_dir):
        (data_dir / "phontab").parent.mkdir(parents=True, exist_ok=True)
        (data_dir / "phontab").write_bytes(b"x" * 10)
        (data_dir / "en_dict").write_bytes(b"y")
        loader = types.SimpleNamespace(get_data_path=lambda: str(data_dir))
        wrapper_cls = type("EspeakWrapper", (), {"set_data_path": staticmethod(lambda p: seen.setdefault("path", p))})
        wrapper_mod = types.SimpleNamespace(EspeakWrapper=wrapper_cls)
        monkeypatch.setitem(sys.modules, "espeakng_loader", loader)
        monkeypatch.setitem(sys.modules, "misaki", types.ModuleType("misaki"))
        monkeypatch.setitem(sys.modules, "misaki.espeak", types.ModuleType("misaki.espeak"))
        monkeypatch.setitem(sys.modules, "phonemizer.backend.espeak.wrapper", wrapper_mod)
        return seen

    return install


def test_short_bundled_path_is_left_alone(fake_espeak, tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "_ESPEAK_PATH_LIMIT", 10_000)
    seen = fake_espeak(tmp_path / "pkg" / "espeak-ng-data")
    assert kb.ensure_short_espeak_path() is None
    assert "path" not in seen


def test_long_bundled_path_is_copied_to_app_data(fake_espeak, tmp_path, monkeypatch):
    home = tmp_path / "h"
    monkeypatch.setenv("STORYTELLER_HOME", str(home))
    src = tmp_path / ("deep" * 30) / "espeak-ng-data"
    monkeypatch.setattr(kb, "_ESPEAK_PATH_LIMIT", len(str(home)) + 40)
    seen = fake_espeak(src)
    dst = kb.ensure_short_espeak_path()
    assert dst == home / "espeak-ng-data"
    assert (dst / "en_dict").read_bytes() == b"y"
    assert seen["path"] == str(dst)
    assert kb.ensure_short_espeak_path() == dst  # second call reuses the copy
