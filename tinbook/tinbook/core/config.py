"""Load and cache Tinbook configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    """Resolved paths and runtime settings for Tinbook."""

    root_dir: Path
    library_dir: Path
    voices_dir: Path
    default_voice: str
    audio_format: str
    audio_bitrate: str
    host: str
    port: int
    user_agent: str
    http_timeout: int


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration file must contain a JSON object: {path}")
    return data


def _resolve_path(value: str | Path, root_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root_dir / path
    return path.resolve()


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load defaults, project settings, local settings, and environment overrides."""
    root_dir = Path(__file__).resolve().parent.parent
    settings: dict[str, Any] = {
        "library_dir": "library",
        "voices_dir": "voices",
        "default_voice": "en_US-lessac-medium",
        "audio_format": "opus",
        "audio_bitrate": "32k",
        "host": "127.0.0.1",
        "port": 0,
        "user_agent": "Tinbook/0.1 (personal audiobook project)",
        "http_timeout": 20,
    }
    settings.update(_read_json(root_dir / "config.json"))
    settings.update(_read_json(root_dir / "config.local.json"))

    for env_name, setting_name in (
        ("TINBOOK_LIBRARY_DIR", "library_dir"),
        ("TINBOOK_VOICES_DIR", "voices_dir"),
        ("TINBOOK_DEFAULT_VOICE", "default_voice"),
        ("TINBOOK_PORT", "port"),
    ):
        value = os.environ.get(env_name)
        if value is not None:
            settings[setting_name] = value

    port = int(settings["port"])
    http_timeout = int(settings["http_timeout"])
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    if http_timeout <= 0:
        raise ValueError("http_timeout must be a positive integer")

    config = Config(
        root_dir=root_dir,
        library_dir=_resolve_path(settings["library_dir"], root_dir),
        voices_dir=_resolve_path(settings["voices_dir"], root_dir),
        default_voice=str(settings["default_voice"]),
        audio_format=str(settings["audio_format"]),
        audio_bitrate=str(settings["audio_bitrate"]),
        host=str(settings["host"]),
        port=port,
        user_agent=str(settings["user_agent"]),
        http_timeout=http_timeout,
    )
    config.library_dir.mkdir(parents=True, exist_ok=True)
    config.voices_dir.mkdir(parents=True, exist_ok=True)
    return config