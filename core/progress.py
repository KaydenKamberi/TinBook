"""Playback progress persistence owned by CP1C."""

import json
import os
from pathlib import Path

from .models import Progress, now_iso


def _write_json_atomic(path: Path, data: dict) -> None:
    """Write JSON through a temporary file and atomic replace."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def load_progress(book_dir: Path) -> Progress:
    """Load progress for a book directory. Returns default Progress if file missing/corrupt."""
    progress_path = book_dir / "progress.json"
    if not progress_path.exists():
        return Progress()

    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Progress.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return Progress()


def save_progress(book_dir: Path, progress: Progress) -> Progress:
    """Set updated_at, persist progress, and return the saved copy."""
    progress.updated_at = now_iso()
    progress_path = book_dir / "progress.json"
    _write_json_atomic(progress_path, progress.to_dict())
    return progress


def newer(a: Progress, b: Progress) -> Progress:
    """Return the progress with the later updated_at value. Tie -> a."""
    a_time = a.updated_at if a.updated_at else ""
    b_time = b.updated_at if b.updated_at else ""

    if a_time == "" and b_time == "":
        return a
    if b_time == "":
        return a
    if a_time == "":
        return b
    if a_time >= b_time:
        return a
    return b
