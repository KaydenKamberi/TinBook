"""Prepare library books and enqueue background audio generation."""

import shutil

from . import chapters, gutenberg, jobs, library, text_cleaner, tts, voices
from .config import get_config
from .models import Book, slugify


class BookAlreadyExists(library.LibraryError):
    """A complete book with this Gutenberg ID and title already exists."""


def _installed_voice(voice: str) -> str:
    """Canonical ID of an installed voice; plain Piper names are accepted (CP3)."""
    try:
        canonical = voices.normalize_voice_id(voice)
    except voices.VoiceError as error:
        raise tts.TTSError(f"Invalid voice: {error}") from error
    if not voices.is_installed(canonical):
        raise tts.TTSError("Voice is not installed. Download it before adding or regenerating a book.")
    return canonical


def add_book(gutenberg_id: int, voice: str | None = None, start_chapter: int = 0) -> Book:
    """Download, clean, split, save, and enqueue a Gutenberg book.

    ``start_chapter`` > 0 (skip earlier chapters) is implemented in CP4B.
    """
    if type(gutenberg_id) is not int or gutenberg_id <= 0:
        raise ValueError("gutenberg_id must be a positive integer.")
    if start_chapter != 0:
        raise NotImplementedError("add_book(start_chapter=...) is implemented in CP4B")
    config = get_config()
    selected_voice = _installed_voice(config.default_voice if voice is None else voice)
    metadata = gutenberg.get_metadata(gutenberg_id)
    identifier = f"{metadata.gutenberg_id}-{slugify(metadata.title)}"
    if (library.book_dir(identifier) / "book.json").exists():
        raise BookAlreadyExists(f"Book {identifier} already exists in the library.")
    raw = gutenberg.download_text(gutenberg_id)
    sections = chapters.split_chapters(text_cleaner.clean(raw))
    try:
        book = library.create_book(metadata, raw, sections, selected_voice, config.audio_format)
    except library.LibraryError:
        # Two adds of the same book at once: the loser gets a 409, not a 500.
        if (library.book_dir(identifier) / "book.json").exists():
            raise BookAlreadyExists(f"Book {identifier} already exists in the library.") from None
        raise
    jobs.get_queue().enqueue(book.id)
    return book


def regenerate_book(book_id: str, voice: str) -> Book:
    """Reset generated audio while keeping text and playback progress.

    The book also switches to the configured ``audio_format`` (e.g. after moving
    to mp3 because ffmpeg has no libopus, or to repair an unsupported format).
    """
    book = library.get_book(book_id)
    voice = _installed_voice(voice)
    audio_dir = library.book_dir(book_id) / "audio"
    try:
        if audio_dir.exists():
            shutil.rmtree(audio_dir)
        audio_dir.mkdir()
    except OSError as error:
        raise library.LibraryError(f"Could not reset audio for {book_id}: {error}") from error
    book.voice = voice
    book.audio_format = get_config().audio_format
    book.status = "queued"
    book.error = None
    for chapter in book.chapters:
        if chapter.status != "skipped":  # skipped chapters stay skipped (PRD D-23)
            chapter.status = "pending"
        chapter.duration_sec = None
    library.save_book(book)
    jobs.get_queue().enqueue(book.id)
    return book


# ---------------------------------------------------------------- CP4B (start from a chapter)


def preview_book(gutenberg_id: int) -> dict:
    """Chapters a book would get, without adding it (ARCHITECTURE §10). CP4B."""
    raise NotImplementedError("pipeline.preview_book is implemented in CP4B")


def generate_chapter(book_id: str, index: int) -> Book:
    """Generate one chapter next (skipped, pending or failed). CP4B."""
    raise NotImplementedError("pipeline.generate_chapter is implemented in CP4B")


def generate_skipped(book_id: str) -> Book:
    """Queue every skipped chapter of a book. CP4B."""
    raise NotImplementedError("pipeline.generate_skipped is implemented in CP4B")
