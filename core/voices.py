"""Voice IDs, the curated voice catalog, and installed voices.

Contract: docs/ARCHITECTURE.md §9.

CP3 implemented the parts every Wave 4 checkpoint depends on: voice ID parsing,
the catalog file, and "is this voice installed". CP4A implements the stubs at
the bottom (catalog view, downloads, delete, preview).

Voice IDs are ``"<engine>:<name>"``, e.g. ``"piper:en_US-ryan-high"`` or
``"kokoro:af_heart"``. A plain name without an engine (``"en_US-lessac-medium"``,
as stored in books and config before CP3) means Piper and stays valid forever.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from .config import get_config

log = logging.getLogger(__name__)

ENGINES = ("piper", "kokoro")
CATALOG_PATH = Path(__file__).with_name("voice_catalog.json")

# Same name rule as scripts/download_voice.py: language_REGION-speaker-quality.
_PIPER_NAME = re.compile(r"[a-z]{2,3}_[A-Z]{2}-[a-z0-9_]+-[a-z0-9_]+")
# Kokoro: two-letter prefix (language + gender, e.g. "af"), then the speaker.
_KOKORO_NAME = re.compile(r"[a-z]{2}_[a-z]+")
_NAME_RULES = {"piper": _PIPER_NAME, "kokoro": _KOKORO_NAME}


class VoiceError(Exception):
    """Expected voice failure: bad ID, unknown voice, download or delete problem."""


# ---------------------------------------------------------------- voice IDs (CP3)


def parse_voice_id(voice_id: str) -> tuple[str, str]:
    """Split a voice ID into ``(engine, name)``. A plain name means Piper.

    Raises VoiceError for anything else (empty, unknown engine, bad name).
    No whitespace trimming and no case folding.
    """
    if not isinstance(voice_id, str) or not voice_id:
        raise VoiceError("Voice ID must be a non-empty string.")
    engine, separator, name = voice_id.partition(":")
    if not separator:
        engine, name = "piper", voice_id
    if engine not in ENGINES:
        raise VoiceError(f"Unknown voice engine '{engine}' (use piper or kokoro).")
    if not _NAME_RULES[engine].fullmatch(name):
        raise VoiceError(f"'{voice_id}' is not a valid {engine} voice name.")
    return engine, name


def normalize_voice_id(voice_id: str) -> str:
    """Return the canonical ``"<engine>:<name>"`` form. Raises VoiceError."""
    engine, name = parse_voice_id(voice_id)
    return f"{engine}:{name}"


# ---------------------------------------------------------------- catalog file (CP3)


@lru_cache(maxsize=1)
def _catalog_data() -> dict:
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise VoiceError(f"Could not read the voice catalog: {error}") from error
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("packs"), dict)
        or not isinstance(data.get("voices"), list)
    ):
        raise VoiceError("The voice catalog has an unexpected format.")
    return data


def load_catalog() -> dict:
    """The parsed ``core/voice_catalog.json`` (a deep copy; safe to modify)."""
    return copy.deepcopy(_catalog_data())


def _catalog_entry(voice_id: str) -> dict | None:
    canonical = normalize_voice_id(voice_id)
    return next((v for v in _catalog_data()["voices"] if v["id"] == canonical), None)


def pack_files(voice_id: str) -> list[Path]:
    """Absolute paths of every file this voice needs, under ``voices_dir``.

    Piper voices need ``<name>.onnx`` and ``<name>.onnx.json`` (catalogued or not).
    Kokoro voices need their catalog pack's files. Raises VoiceError for an
    invalid ID or a Kokoro voice that isn't in the catalog.
    """
    engine, name = parse_voice_id(voice_id)
    voices_dir = get_config().voices_dir
    if engine == "piper":
        return [voices_dir / f"{name}.onnx", voices_dir / f"{name}.onnx.json"]
    entry = _catalog_entry(voice_id)
    if entry is None:
        raise VoiceError(f"Kokoro voice '{name}' is not in the voice catalog.")
    pack = _catalog_data()["packs"][entry["pack"]]
    return [voices_dir / file["path"] for file in pack["files"]]


def is_installed(voice_id: str) -> bool:
    """True if every file the voice needs exists. False for invalid IDs (never raises)."""
    try:
        return all(path.is_file() for path in pack_files(voice_id))
    except VoiceError:
        return False


def installed_voice_ids() -> list[str]:
    """Canonical IDs of installed voices, sorted.

    Piper: every valid ``<name>.onnx`` in ``voices_dir`` that has its ``.onnx.json``
    (catalogued or not). Kokoro: the catalogued Kokoro voices whose pack is installed.
    """
    voices_dir = get_config().voices_dir
    found: set[str] = set()
    if voices_dir.is_dir():
        for model in voices_dir.glob("*.onnx"):
            name = model.name[: -len(".onnx")]
            if _PIPER_NAME.fullmatch(name) and model.with_name(model.name + ".json").is_file():
                found.add(f"piper:{name}")
    for entry in _catalog_data()["voices"]:
        if entry["engine"] == "kokoro" and is_installed(entry["id"]):
            found.add(entry["id"])
    return sorted(found)


# ---------------------------------------------------------------- CP4A: catalog view, downloads, preview


@dataclass
class VoiceInfo:
    """One voice as shown in the app (catalog fields + what's on disk)."""

    id: str               # canonical, e.g. "kokoro:af_heart"
    engine: str           # "piper" | "kokoro"
    name: str             # display name, e.g. "Heart"
    gender: str           # "female" | "male" | "" (uncatalogued)
    accent: str           # e.g. "American", "British", "" (uncatalogued)
    quality: str          # short note, e.g. "Kokoro · grade A · best-rated Kokoro voice"
    pack: str             # files shared with other voices, e.g. "kokoro-v1.0"
    size_bytes: int       # total download size of the pack
    installed: bool
    recommended: bool
    in_catalog: bool      # False for a Piper voice found on disk but not in the catalog

    def to_dict(self) -> dict:
        return asdict(self)


DownloadStateName = Literal["downloading", "done", "error"]


@dataclass
class DownloadState:
    """Progress of one pack download (packs are what gets downloaded)."""

    pack: str
    state: DownloadStateName
    bytes_done: int
    bytes_total: int      # 0 while unknown
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def catalog() -> list[VoiceInfo]:
    """Every catalog voice in catalog order, then uncatalogued installed Piper voices. CP4A."""
    raise NotImplementedError("voices.catalog is implemented in CP4A")


def get_voice(voice_id: str) -> VoiceInfo:
    """One voice (plain or canonical ID). Raises VoiceError if unknown and not installed. CP4A."""
    raise NotImplementedError("voices.get_voice is implemented in CP4A")


def start_download(voice_id: str) -> DownloadState:
    """Download the voice's pack in a background thread; idempotent. CP4A."""
    raise NotImplementedError("voices.start_download is implemented in CP4A")


def download_states() -> dict[str, DownloadState]:
    """Downloads started in this process, keyed by pack (finished ones included). CP4A."""
    raise NotImplementedError("voices.download_states is implemented in CP4A")


def delete_voice(voice_id: str) -> list[str]:
    """Delete the voice's pack files; return the IDs of every voice removed. CP4A."""
    raise NotImplementedError("voices.delete_voice is implemented in CP4A")


def preview_file(voice_id: str) -> Path:
    """A short cached sample of an installed voice, synthesized on first use. CP4A."""
    raise NotImplementedError("voices.preview_file is implemented in CP4A")
