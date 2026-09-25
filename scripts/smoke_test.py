"""Check Piper synthesis and conversion to Opus."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import get_config


def find_ffmpeg() -> str | None:
    """Find ffmpeg from imageio-ffmpeg or the system PATH."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return shutil.which("ffmpeg")


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    config = get_config()
    voice_path = config.voices_dir / f"{config.default_voice}.onnx"
    ffmpeg = find_ffmpeg()

    try:
        from piper import PiperVoice

        voice = PiperVoice.load(str(voice_path))
        results.append(("Piper voice load", True, str(voice_path)))
    except Exception as error:
        voice = None
        results.append(("Piper voice load", False, f"{type(error).__name__}: {error}"))

    if voice is not None and ffmpeg:
        try:
            with tempfile.TemporaryDirectory() as temporary_dir:
                wav_path = Path(temporary_dir) / "smoke.wav"
                opus_path = Path(temporary_dir) / "smoke.opus"
                with wave.open(str(wav_path), "wb") as wav_file:
                    voice.synthesize_wav("Hello from Tinbook.", wav_file)
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        str(wav_path),
                        "-c:a",
                        "libopus",
                        "-b:a",
                        "32k",
                        "-ac",
                        "1",
                        str(opus_path),
                    ],
                    check=True,
                )
                if not opus_path.exists() or opus_path.stat().st_size == 0:
                    raise RuntimeError("ffmpeg did not create a non-empty Opus file")
            results.append(("Piper synthesis + Opus conversion", True, ""))
        except Exception as error:
            results.append(
                ("Piper synthesis + Opus conversion", False, f"{type(error).__name__}: {error}")
            )
    else:
        reason = "ffmpeg unavailable" if not ffmpeg else "Piper voice did not load"
        results.append(("Piper synthesis + Opus conversion", False, reason))

    print(f"{'CHECK':42} {'RESULT':8} DETAILS")
    print("-" * 100)
    for name, passed, details in results:
        print(f"{name:42} {'PASS' if passed else 'FAIL':8} {details}")
    return 0 if all(passed for _, passed, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())