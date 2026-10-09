"""Playback progress persistence (CP1C; integration fixes by Claude Code)."""

import dataclasses
import json
import logging
import math
import os
from pathlib import Path

from .models import Progress, now_iso

log = logging.getLogger(__name__)

PROGRESS_FILE = "progress.json"


def _write_json_atomic(path: Path, data: dict) -> None:
    """Write ``path.tmp`` then ``os.replace``; UTF-8, indent=2 (same as core.library)."""
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validated(data: dict) -> Progress:
    """Build a Progress, replacing any field with a wrong type or range by its default."""
    default = Progress()
    index = data.get("chapter_index")
    position = data.get("position_sec")
    speed = data.get("speed")
    finished = data.get("finished")
    updated_at = data.get("updated_at")
    return Progress(
        chapter_index=index if isinstance(index, int) and not isinstance(index, bool) and index >= 0
        else default.chapter_index,
        position_sec=float(position) if _is_number(position) and position >= 0 else default.position_sec,
        speed=float(speed) if _is_number(speed) and speed > 0 else default.speed,
        finished=finished if isinstance(finished, bool) else default.finished,
        updated_at=updated_at if isinstance(updated_at, str) else default.updated_at,
    )  # fmt: skip


def load_progress(book_dir: Path) -> Progress:
    """Load ``progress.json``; default Progress() if the file is missing or corrupt."""
    path = Path(book_dir) / PROGRESS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Progress()
    except (OSError, ValueError) as error:  # ValueError covers bad JSON and bad UTF-8
        log.warning("Unreadable %s, using defaults: %s", path, error)
        return Progress()
    if not isinstance(data, dict):
        log.warning("Unexpected JSON in %s, using defaults", path)
        return Progress()
    return _validated(data)


def save_progress(book_dir: Path, progress: Progress) -> Progress:
    """Save a copy of ``progress`` with updated_at=now_iso() atomically; return that copy."""
    saved = dataclasses.replace(progress, updated_at=now_iso())
    _write_json_atomic(Path(book_dir) / PROGRESS_FILE, saved.to_dict())
    return saved


def newer(a: Progress, b: Progress) -> Progress:
    """The progress with the later updated_at ("" is oldest); a tie returns a."""
    return b if (b.updated_at or "") > (a.updated_at or "") else a
