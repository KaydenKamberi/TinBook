"""Playback progress persistence owned by CP1C."""

from pathlib import Path

from .models import Progress


def load_progress(book_dir: Path) -> Progress:
    """Load progress for a book directory. Implemented by CP1C."""
    raise NotImplementedError


def save_progress(book_dir: Path, progress: Progress) -> Progress:
    """Set updated_at, persist progress, and return the saved copy. Implemented by CP1C."""
    raise NotImplementedError


def newer(a: Progress, b: Progress) -> Progress:
    """Return the progress with the later updated_at value. Implemented by CP1C."""
    raise NotImplementedError