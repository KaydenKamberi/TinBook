"""Library storage owned by CP1B."""

from pathlib import Path

from .models import Book, SearchResult


class LibraryError(Exception):
    """Expected library storage failure."""


def write_json_atomic(path: Path, data: dict) -> None:
    """Write JSON through a temporary file and atomic replace. Implemented by CP1B."""
    raise NotImplementedError


def book_dir(book_id: str) -> Path:
    """Return a book's library directory. Implemented by CP1B."""
    raise NotImplementedError


def create_book(
    meta: SearchResult,
    raw_text: str,
    chapters: list[tuple[str, str]],
    voice: str,
    audio_format: str,
) -> Book:
    """Create a queued book and its text files. Implemented by CP1B."""
    raise NotImplementedError


def list_books() -> list[Book]:
    """List readable books, newest first. Implemented by CP1B."""
    raise NotImplementedError


def get_book(book_id: str) -> Book:
    """Load a book or raise LibraryError. Implemented by CP1B."""
    raise NotImplementedError


def save_book(book: Book) -> None:
    """Atomically save a book. Implemented by CP1B."""
    raise NotImplementedError


def delete_book(book_id: str) -> None:
    """Delete a book directory. Implemented by CP1B."""
    raise NotImplementedError


def chapter_text_path(book_id: str, index: int) -> Path:
    """Return a chapter text file path. Implemented by CP1B."""
    raise NotImplementedError


def chapter_audio_path(book_id: str, index: int, audio_format: str) -> Path:
    """Return a chapter audio file path. Implemented by CP1B."""
    raise NotImplementedError