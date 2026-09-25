"""Download a Piper voice model into the configured voice directory."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

from core.config import get_config


BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def voice_files(voice: str) -> tuple[str, str]:
    """Return the relative model and metadata paths for a voice name."""
    match = re.fullmatch(r"([a-z]{2,3}_[A-Z]{2})-([a-z0-9]+)-([a-z0-9]+)", voice)
    if not match:
        raise ValueError(
            "Voice must look like 'en_US-lessac-medium' "
            "(language_region-speaker-quality)."
        )
    language_region, speaker, quality = match.groups()
    language = language_region.split("_", maxsplit=1)[0]
    directory = f"{language}/{language_region}/{speaker}/{quality}"
    return f"{directory}/{voice}.onnx", f"{directory}/{voice}.onnx.json"


def download(url: str, destination: Path) -> None:
    """Stream a model file, reporting progress and preserving partial downloads."""
    temporary = destination.with_suffix(destination.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        written = 0
        with temporary.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                output.write(chunk)
                written += len(chunk)
                if total:
                    percent = written * 100 // total
                    print(f"\r{destination.name}: {percent:3d}%", end="", flush=True)
                else:
                    print(f"\r{destination.name}: {written:,} bytes", end="", flush=True)
    temporary.replace(destination)
    print(f"\r{destination.name}: complete")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("voice_name", help="for example en_US-lessac-medium")
    args = parser.parse_args()

    try:
        paths = voice_files(args.voice_name)
        voice_dir = get_config().voices_dir
        voice_dir.mkdir(parents=True, exist_ok=True)
        for relative_path in paths:
            destination = voice_dir / Path(relative_path).name
            if destination.exists():
                print(f"Already present: {destination}")
                continue
            url = f"{BASE_URL}/{relative_path}"
            print(f"Downloading {url}")
            download(url, destination)
    except (ValueError, requests.RequestException, OSError) as error:
        print(f"Voice download failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())