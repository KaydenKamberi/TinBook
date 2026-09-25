import json
from pathlib import Path

import pytest

import core.config
from core.config import get_config

ENV_VARS = ("TINBOOK_LIBRARY_DIR", "TINBOOK_VOICES_DIR", "TINBOOK_DEFAULT_VOICE", "TINBOOK_PORT")


@pytest.fixture
def root(monkeypatch, tmp_path: Path) -> Path:
    """Point config at an isolated tmp root so a real config.local.json is never read."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(core.config, "_ROOT_DIR", tmp_path)
    get_config.cache_clear()
    yield tmp_path
    get_config.cache_clear()


def test_defaults_with_no_config_files(root: Path) -> None:
    config = get_config()
    assert config.root_dir == root
    assert config.library_dir == root.resolve() / "library"
    assert config.voices_dir == root.resolve() / "voices"
    assert config.default_voice == "en_US-lessac-medium"
    assert config.port == 0
    assert config.library_dir.is_dir()
    assert config.voices_dir.is_dir()


def test_local_config_overrides_committed_config(root: Path) -> None:
    (root / "config.json").write_text(json.dumps({"default_voice": "a", "port": 1}), encoding="utf-8")
    (root / "config.local.json").write_text(json.dumps({"default_voice": "b"}), encoding="utf-8")
    config = get_config()
    assert config.default_voice == "b"
    assert config.port == 1


def test_environment_overrides_and_directories_exist(monkeypatch, root: Path) -> None:
    (root / "config.local.json").write_text(json.dumps({"default_voice": "local"}), encoding="utf-8")
    library_dir = root / "my-library"
    voices_dir = root / "my-voices"
    monkeypatch.setenv("TINBOOK_LIBRARY_DIR", str(library_dir))
    monkeypatch.setenv("TINBOOK_VOICES_DIR", str(voices_dir))
    monkeypatch.setenv("TINBOOK_DEFAULT_VOICE", "en_GB-alba-medium")
    monkeypatch.setenv("TINBOOK_PORT", "5000")
    config = get_config()
    assert config.library_dir == library_dir.resolve()
    assert config.voices_dir == voices_dir.resolve()
    assert config.default_voice == "en_GB-alba-medium"
    assert config.port == 5000
    assert library_dir.is_dir()
    assert voices_dir.is_dir()


def test_empty_environment_variables_are_ignored(monkeypatch, root: Path) -> None:
    for name in ENV_VARS:
        monkeypatch.setenv(name, "")
    config = get_config()
    assert config.library_dir == root.resolve() / "library"
    assert config.default_voice == "en_US-lessac-medium"
    assert config.port == 0


@pytest.mark.parametrize("port", ["abc", "-1", "65536"])
def test_invalid_port_raises(monkeypatch, root: Path, port: str) -> None:
    monkeypatch.setenv("TINBOOK_PORT", port)
    with pytest.raises(ValueError):
        get_config()
