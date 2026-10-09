"""Piper text-to-speech engine (CP1A).

Text → WAV (Piper, paragraph by paragraph) → ffmpeg → ``out_path.part`` → rename.

Two Piper engines are supported:
1. The ``piper-tts`` Python package (preferred).
2. A ``piper`` executable on PATH (fallback when the package fails to import),
   driven via subprocess with ``--output_raw`` so audio streams to disk.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any, BinaryIO

from .config import get_config

log = logging.getLogger(__name__)

# Encoder name and ffmpeg muxer per supported audio format.
_FORMATS = {
    "opus": ("libopus", "opus"),
    "mp3": ("libmp3lame", "mp3"),
}
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_PARAGRAPH_PAUSE_SEC = 0.4
_PIPE_CHUNK = 64 * 1024
# ffmpeg encode timeout: never less than this, and at least the audio's own length
# (encoding is far faster than real time, so hitting it means ffmpeg is stuck).
_ENCODE_TIMEOUT_MIN_SEC = 300

_voice_cache: dict[str, Any] = {}
_voice_lock = threading.Lock()


class TTSError(Exception):
    """Expected text-to-speech failure."""


# ---------------------------------------------------------------- discovery


def list_voices() -> list[str]:
    """Voice names in voices_dir that have both ``.onnx`` and ``.onnx.json`` files."""
    voices_dir = get_config().voices_dir
    if not voices_dir.is_dir():
        return []
    return sorted(
        path.name[: -len(".onnx")]
        for path in voices_dir.glob("*.onnx")
        if path.with_name(path.name + ".json").is_file()
    )


def _piper_voice_class() -> Any | None:
    """Return ``piper.PiperVoice`` or None if the package cannot be imported."""
    try:
        from piper import PiperVoice
    except Exception as error:  # ImportError, or a broken onnxruntime DLL on Windows
        log.debug("piper package unavailable: %s", error)
        return None
    return PiperVoice


def _piper_executable() -> str | None:
    return shutil.which("piper")


def _ffmpeg_candidates() -> list[str]:
    candidates: list[str] = []
    try:
        import imageio_ffmpeg

        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError, RuntimeError, OSError) as error:
        log.debug("imageio-ffmpeg unavailable: %s", error)
    system = shutil.which("ffmpeg")
    if system and system not in candidates:
        candidates.append(system)
    return candidates


def _encoders(ffmpeg: str) -> str:
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        log.warning("Could not run %s: %s", ffmpeg, error)
        return ""
    return result.stdout


_ffmpeg_lock = threading.Lock()
_ffmpeg_good: tuple[str, frozenset[str]] | None = None


def _reset_ffmpeg_cache() -> None:
    """Forget the detected ffmpeg (for tests)."""
    global _ffmpeg_good
    with _ffmpeg_lock:
        _ffmpeg_good = None


def _detect_ffmpeg() -> tuple[str | None, frozenset[str]]:
    """Find ffmpeg, preferring the first candidate with libopus (bundled, then PATH).

    Returns (path or None, set of supported formats among ``_FORMATS``). Only a
    complete result (ffmpeg with libopus) is cached; "not found" or "no libopus"
    is re-checked on the next call, so installing ffmpeg needs no restart.
    """
    global _ffmpeg_good
    with _ffmpeg_lock:
        if _ffmpeg_good is None:
            found = _probe_ffmpeg()
            if found[0] is None or "opus" not in found[1]:
                return found
            _ffmpeg_good = (found[0], found[1])
        return _ffmpeg_good


def _probe_ffmpeg() -> tuple[str | None, frozenset[str]]:
    first: tuple[str | None, frozenset[str]] = (None, frozenset())
    for ffmpeg in _ffmpeg_candidates():
        encoders = _encoders(ffmpeg)
        if not encoders:
            continue
        formats = frozenset(
            fmt for fmt, (encoder, _) in _FORMATS.items() if re.search(rf"\b{encoder}\b", encoders)
        )
        if "opus" in formats:
            log.info("Using ffmpeg %s (formats: %s)", ffmpeg, sorted(formats))
            return ffmpeg, formats
        if first[0] is None:
            first = (ffmpeg, formats)
    if first[0] is None:
        log.warning("ffmpeg not found")
    else:
        log.warning("ffmpeg %s has no libopus (formats: %s)", first[0], sorted(first[1]))
    return first


def check_environment() -> dict:
    """Report engine availability: ``{"piper", "ffmpeg", "opus", "voices"}``."""
    ffmpeg, formats = _detect_ffmpeg()
    return {
        "piper": _piper_voice_class() is not None or _piper_executable() is not None,
        "ffmpeg": ffmpeg,
        "opus": "opus" in formats,
        "voices": list_voices(),
    }


# ---------------------------------------------------------------- synthesis


def _voice_paths(voice: str) -> tuple[Path, Path]:
    voices_dir = get_config().voices_dir
    model = voices_dir / f"{voice}.onnx"
    config = voices_dir / f"{voice}.onnx.json"
    if not model.is_file() or not config.is_file():
        raise TTSError(
            f"Voice '{voice}' is not installed. "
            f"Run: python scripts/download_voice.py {voice}"
        )
    return model, config


def _load_voice(voice_class: Any, voice: str) -> Any:
    """Load a PiperVoice once per voice name and cache it."""
    with _voice_lock:
        if voice not in _voice_cache:
            model, config = _voice_paths(voice)
            log.info("Loading Piper voice %s", voice)
            try:
                _voice_cache[voice] = voice_class.load(str(model), config_path=str(config))
            except Exception as error:
                raise TTSError(f"Could not load voice '{voice}': {error}") from error
        return _voice_cache[voice]


def _paragraphs(text: str) -> list[str]:
    paragraphs = (" ".join(p.split()) for p in _PARAGRAPH_SPLIT.split(text))
    return [p for p in paragraphs if p]


def _write_silence(wav_file: wave.Wave_write, seconds: float) -> None:
    frames = int(wav_file.getframerate() * seconds)
    wav_file.writeframes(b"\x00" * frames * wav_file.getsampwidth() * wav_file.getnchannels())


def _synthesize_with_package(voice_obj: Any, paragraphs: list[str], wav_file: wave.Wave_write) -> None:
    """Stream each paragraph's chunks into one WAV so memory stays flat."""
    format_set = False
    for paragraph in paragraphs:
        if format_set:
            _write_silence(wav_file, _PARAGRAPH_PAUSE_SEC)
        for chunk in voice_obj.synthesize(paragraph):
            if not format_set:
                wav_file.setframerate(chunk.sample_rate)
                wav_file.setsampwidth(chunk.sample_width)
                wav_file.setnchannels(chunk.sample_channels)
                format_set = True
            wav_file.writeframes(chunk.audio_int16_bytes)
    if not format_set:
        raise TTSError("Piper produced no audio")


def _synthesize_with_executable(
    piper_exe: str, voice: str, paragraphs: list[str], wav_file: wave.Wave_write
) -> None:
    """Run ``piper --output_raw``: one paragraph per stdin line, raw int16 mono on stdout."""
    model, config = _voice_paths(voice)
    try:
        sample_rate = int(json.loads(config.read_text(encoding="utf-8"))["audio"]["sample_rate"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise TTSError(f"Voice config for '{voice}' is unreadable: {error}") from error
    wav_file.setframerate(sample_rate)
    wav_file.setsampwidth(2)
    wav_file.setnchannels(1)

    with tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                [piper_exe, "--model", str(model), "--config", str(config), "--output_raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
            )
        except OSError as error:
            raise TTSError(f"Could not start piper executable: {error}") from error

        def feed(stdin: BinaryIO) -> None:
            try:
                for paragraph in paragraphs:
                    stdin.write(paragraph.encode("utf-8") + b"\n")
            except OSError:
                pass  # process died; reported via its exit code
            finally:
                try:
                    stdin.close()
                except OSError:
                    pass

        # Feed stdin from a thread so a full stdout pipe can't deadlock us.
        writer = threading.Thread(target=feed, args=(process.stdin,), daemon=True)
        writer.start()
        assert process.stdout is not None
        while chunk := process.stdout.read(_PIPE_CHUNK):
            wav_file.writeframes(chunk)
        writer.join()
        if process.wait() != 0:
            stderr_file.seek(0)
            detail = stderr_file.read().decode("utf-8", errors="replace").strip()[-500:]
            raise TTSError(f"piper exited with code {process.returncode}: {detail}")


def _encode(
    ffmpeg: str, wav_path: Path, part_path: Path, audio_format: str, bitrate: str, audio_sec: float
) -> None:
    encoder, muxer = _FORMATS[audio_format]
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(wav_path),
        "-c:a", encoder, "-b:a", bitrate, "-ac", "1",
        "-f", muxer, str(part_path),
    ]  # fmt: skip
    timeout = max(_ENCODE_TIMEOUT_MIN_SEC, audio_sec)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:  # run() has already killed ffmpeg
        raise TTSError(f"ffmpeg timed out after {timeout:.0f}s") from error
    except OSError as error:
        raise TTSError(f"Could not run ffmpeg: {error}") from error
    if result.returncode != 0:
        raise TTSError(f"ffmpeg failed ({result.returncode}): {result.stderr.strip()[-500:]}")
    if not part_path.is_file() or part_path.stat().st_size == 0:
        raise TTSError("ffmpeg produced no audio")


def synthesize_to_file(text: str, out_path: Path, voice: str, audio_format: str, bitrate: str) -> float:
    """Synthesize ``text`` to ``out_path`` and return its duration in seconds.

    Audio is written to ``out_path.part`` and renamed on success, so a partial file
    never looks complete.
    """
    if audio_format not in _FORMATS:
        raise TTSError(f"Unsupported audio format '{audio_format}' (use 'opus' or 'mp3')")
    paragraphs = _paragraphs(text)
    if not paragraphs:
        raise TTSError("No text to synthesize")

    ffmpeg, formats = _detect_ffmpeg()
    if ffmpeg is None:
        raise TTSError("ffmpeg not found. Reinstall imageio-ffmpeg or put ffmpeg on PATH.")
    if audio_format not in formats:
        raise TTSError(
            f"ffmpeg at {ffmpeg} cannot encode {audio_format} ({_FORMATS[audio_format][0]} missing). "
            f'Install an ffmpeg build with it, or set "audio_format": "mp3" and '
            f'"audio_bitrate": "48k" in config.local.json.'
        )

    voice_class = _piper_voice_class()
    piper_exe = None if voice_class else _piper_executable()
    if voice_class is None and piper_exe is None:
        raise TTSError(
            "Piper is not available: the piper-tts package failed to import and no "
            "'piper' executable is on PATH."
        )
    voice_obj = _load_voice(voice_class, voice) if voice_class else None

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = out_path.with_name(out_path.name + ".part")
    try:
        with tempfile.TemporaryDirectory(prefix="tinbook-tts-") as temp_dir:
            wav_path = Path(temp_dir) / "chapter.wav"
            wav_file = wave.open(str(wav_path), "wb")
            try:
                if voice_obj is not None:
                    _synthesize_with_package(voice_obj, paragraphs, wav_file)
                else:
                    _synthesize_with_executable(piper_exe, voice, paragraphs, wav_file)
            except BaseException:
                # close() raises if no format was set yet; don't let that hide the real error.
                with contextlib.suppress(Exception):
                    wav_file.close()
                raise
            wav_file.close()
            with wave.open(str(wav_path), "rb") as wav_file:
                frames, rate = wav_file.getnframes(), wav_file.getframerate()
            if frames == 0 or rate == 0:
                raise TTSError("Piper produced no audio")
            _encode(ffmpeg, wav_path, part_path, audio_format, bitrate, frames / rate)
        os.replace(part_path, out_path)
    except TTSError:
        part_path.unlink(missing_ok=True)
        raise
    except Exception as error:  # Piper/onnxruntime/wave/OS errors
        part_path.unlink(missing_ok=True)
        raise TTSError(f"Synthesis failed: {type(error).__name__}: {error}") from error
    except BaseException:  # KeyboardInterrupt etc.: still never leave a .part behind
        part_path.unlink(missing_ok=True)
        raise
    duration = frames / rate
    log.info("Wrote %s (%.1fs)", out_path, duration)
    return duration
