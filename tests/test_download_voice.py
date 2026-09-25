import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "download_voice.py"
_spec = importlib.util.spec_from_file_location("download_voice", _SCRIPT)
download_voice = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(download_voice)


@pytest.mark.parametrize(
    ("voice", "directory"),
    [
        ("en_US-lessac-medium", "en/en_US/lessac/medium"),
        ("en_US-libritts_r-medium", "en/en_US/libritts_r/medium"),
        ("en_GB-northern_english_male-medium", "en/en_GB/northern_english_male/medium"),
        ("en_US-amy-x_low", "en/en_US/amy/x_low"),
        ("de_DE-thorsten_emotional-medium", "de/de_DE/thorsten_emotional/medium"),
    ],
)
def test_voice_files_builds_huggingface_paths(voice: str, directory: str) -> None:
    model, metadata = download_voice.voice_files(voice)
    assert model == f"{directory}/{voice}.onnx"
    assert metadata == f"{directory}/{voice}.onnx.json"


@pytest.mark.parametrize(
    "voice",
    ["", "lessac", "en_US-lessac", "en-lessac-medium", "EN_us-lessac-medium", "en_US-lessac-medium.onnx", "en_US-less ac-medium"],
)
def test_voice_files_rejects_malformed_names(voice: str) -> None:
    with pytest.raises(ValueError):
        download_voice.voice_files(voice)
