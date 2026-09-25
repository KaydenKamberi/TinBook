from pathlib import Path

from core.config import get_config


def test_environment_overrides_and_directories_exist(monkeypatch, tmp_path: Path) -> None:
    library_dir = tmp_path / "my-library"
    voices_dir = tmp_path / "my-voices"
    monkeypatch.setenv("TINBOOK_LIBRARY_DIR", str(library_dir))
    monkeypatch.setenv("TINBOOK_VOICES_DIR", str(voices_dir))
    monkeypatch.setenv("TINBOOK_DEFAULT_VOICE", "en_GB-alba-medium")
    monkeypatch.setenv("TINBOOK_PORT", "5000")
    get_config.cache_clear()
    try:
        config = get_config()
        assert config.library_dir == library_dir
        assert config.voices_dir == voices_dir
        assert config.default_voice == "en_GB-alba-medium"
        assert config.port == 5000
        assert library_dir.is_dir()
        assert voices_dir.is_dir()
    finally:
        get_config.cache_clear()