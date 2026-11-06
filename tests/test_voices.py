"""core/voices.py: voice IDs, catalog file, installed voices (CP3 part; CP4A extends this file)."""

from pathlib import Path

import pytest

from core import config, voices
from core.config import get_config


@pytest.fixture(autouse=True)
def sandbox(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config, "_ROOT_DIR", tmp_path)
    for key in ("TINBOOK_LIBRARY_DIR", "TINBOOK_VOICES_DIR", "TINBOOK_DEFAULT_VOICE", "TINBOOK_PORT"):
        monkeypatch.delenv(key, raising=False)
    get_config.cache_clear()
    yield get_config().voices_dir
    get_config.cache_clear()


def install_piper(voices_dir: Path, name: str) -> None:
    (voices_dir / f"{name}.onnx").write_bytes(b"model")
    (voices_dir / f"{name}.onnx.json").write_text("{}", encoding="utf-8")


def install_kokoro_pack(voices_dir: Path) -> None:
    (voices_dir / "kokoro").mkdir(exist_ok=True)
    (voices_dir / "kokoro" / "kokoro-v1.0.onnx").write_bytes(b"model")
    (voices_dir / "kokoro" / "voices-v1.0.bin").write_bytes(b"voices")


@pytest.mark.parametrize("voice_id, expected", [
    ("en_US-lessac-medium", ("piper", "en_US-lessac-medium")),
    ("piper:en_US-ryan-high", ("piper", "en_US-ryan-high")),
    ("piper:en_GB-northern_english_male-medium", ("piper", "en_GB-northern_english_male-medium")),
    ("kokoro:af_heart", ("kokoro", "af_heart")),
])
def test_parse_voice_id(voice_id, expected) -> None:
    assert voices.parse_voice_id(voice_id) == expected
    assert voices.normalize_voice_id(voice_id) == ":".join(expected)


@pytest.mark.parametrize("voice_id", ["", "kokoro:", "espeak:af_heart", "af_heart", "kokoro:AF_heart", None, 3])
def test_invalid_voice_ids_raise_voice_error(voice_id) -> None:
    with pytest.raises(voices.VoiceError):
        voices.parse_voice_id(voice_id)
    assert voices.is_installed(voice_id) is False


def test_piper_voice_installed_only_with_both_files(sandbox: Path) -> None:
    assert not voices.is_installed("piper:en_US-ryan-high")
    (sandbox / "en_US-ryan-high.onnx").write_bytes(b"model")
    assert not voices.is_installed("en_US-ryan-high")
    (sandbox / "en_US-ryan-high.onnx.json").write_text("{}", encoding="utf-8")
    assert voices.is_installed("en_US-ryan-high")
    assert voices.is_installed("piper:en_US-ryan-high")


def test_kokoro_voices_share_one_pack(sandbox: Path) -> None:
    assert voices.pack_files("kokoro:af_heart") == voices.pack_files("kokoro:bm_george") == [
        sandbox / "kokoro" / "kokoro-v1.0.onnx", sandbox / "kokoro" / "voices-v1.0.bin",
    ]
    assert not voices.is_installed("kokoro:af_heart")
    install_kokoro_pack(sandbox)
    assert voices.is_installed("kokoro:af_heart") and voices.is_installed("kokoro:bm_george")
    assert not voices.is_installed("kokoro:ef_dora")  # in voices-v1.0.bin, but not in our catalog
    with pytest.raises(voices.VoiceError, match="not in the voice catalog"):
        voices.pack_files("kokoro:ef_dora")


def test_installed_voice_ids_lists_piper_files_and_installed_kokoro_catalog(sandbox: Path) -> None:
    assert voices.installed_voice_ids() == []
    install_piper(sandbox, "en_US-lessac-medium")
    install_piper(sandbox, "en_US-custom-low")  # not in the catalog: still listed
    (sandbox / "en_US-orphan-medium.onnx").write_bytes(b"no json")
    (sandbox / "not a voice.onnx").write_bytes(b"x")
    (sandbox / "not a voice.onnx.json").write_text("{}", encoding="utf-8")
    assert voices.installed_voice_ids() == ["piper:en_US-custom-low", "piper:en_US-lessac-medium"]
    install_kokoro_pack(sandbox)
    kokoro_ids = [v["id"] for v in voices.load_catalog()["voices"] if v["engine"] == "kokoro"]
    assert voices.installed_voice_ids() == sorted(kokoro_ids + ["piper:en_US-custom-low", "piper:en_US-lessac-medium"])


def test_load_catalog_returns_a_copy() -> None:
    catalog = voices.load_catalog()
    catalog["voices"].clear()
    assert voices.load_catalog()["voices"], "the cached catalog must not change"


def test_default_voice_from_config_json_is_in_the_catalog() -> None:
    default = voices.normalize_voice_id(get_config().default_voice)
    assert default in {v["id"] for v in voices.load_catalog()["voices"]}
