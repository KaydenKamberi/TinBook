"""Book preparation pipeline owned by CP2A."""

from .models import Book


def add_book(gutenberg_id: int, voice: str | None = None) -> Book:
    """Prepare and enqueue a Gutenberg book. Implemented by CP2A."""
    raise NotImplementedError


def regenerate_book(book_id: str, voice: str) -> Book:
    """Clear generated audio and enqueue a book again. Implemented by CP2A."""
    raise NotImplementedError