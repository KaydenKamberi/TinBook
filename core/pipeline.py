"""Prepare library books and enqueue background audio generation."""

import shutil

from . import chapters, gutenberg, jobs, library, text_cleaner, tts
from .config import get_config
from .models import Book, slugify


class BookAlreadyExists(library.LibraryError):
    """A complete book with this Gutenberg ID and title already exists."""


def _validate_voice(voice: str) -> None:
    if not isinstance(voice, str) or not voice or voice not in tts.list_voices():
        raise tts.TTSError("Voice is not installed. Download it before adding or regenerating a book.")


def add_book(gutenberg_id: int, voice: str | None = None) -> Book:
    """Download, clean, split, save, and enqueue a Gutenberg book."""
    if type(gutenberg_id) is not int or gutenberg_id <= 0:
        raise ValueError("gutenberg_id must be a positive integer.")
    config = get_config()
    selected_voice = config.default_voice if voice is None else voice
    _validate_voice(selected_voice)
    metadata = gutenberg.get_metadata(gutenberg_id)
    identifier = f"{metadata.gutenberg_id}-{slugify(metadata.title)}"
    if (library.book_dir(identifier) / "book.json").exists():
        raise BookAlreadyExists(f"Book {identifier} already exists in the library.")
    raw = gutenberg.download_text(gutenberg_id)
    sections = chapters.split_chapters(text_cleaner.clean(raw))
    book = library.create_book(metadata, raw, sections, selected_voice, config.audio_format)
    jobs.get_queue().enqueue(book.id)
    return book


def regenerate_book(book_id: str, voice: str) -> Book:
    """Reset generated audio while keeping text and playback progress."""
    book = library.get_book(book_id)
    _validate_voice(voice)
    audio_dir = library.book_dir(book_id) / "audio"
    try:
        if audio_dir.exists():
            shutil.rmtree(audio_dir)
        audio_dir.mkdir()
    except OSError as error:
        raise library.LibraryError(f"Could not reset audio for {book_id}: {error}") from error
    book.voice = voice
    book.status = "queued"
    book.error = None
    for chapter in book.chapters:
        chapter.status = "pending"
        chapter.duration_sec = None
    library.save_book(book)
    jobs.get_queue().enqueue(book.id)
    return book