"""Piper text-to-speech engine owned by CP1A."""

from pathlib import Path


class TTSError(Exception):
    """Expected text-to-speech failure."""


def list_voices() -> list[str]:
    """List available voices. Implemented by CP1A."""
    raise NotImplementedError


def synthesize_to_file(
    text: str,
    out_path: Path,
    voice: str,
    audio_format: str,
    bitrate: str,
) -> float:
    """Synthesize speech and return its duration in seconds. Implemented by CP1A."""
    raise NotImplementedError


def check_environment() -> dict:
    """Report Piper, ffmpeg, Opus, and voice availability. Implemented by CP1A."""
    raise NotImplementedError