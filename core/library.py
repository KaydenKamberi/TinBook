"""Book storage and atomic JSON persistence for Tinbook."""

import json
import logging
import os
import shutil
import threading
from pathlib import Path

from .config import get_config
from .models import Book, Chapter, SearchResult, now_iso, slugify

log = logging.getLogger(__name__)
_json_write_lock = threading.RLock()


class LibraryError(Exception):
    """Expected library storage failure."""


def write_json_atomic(path: Path, data: dict) -> None:
    """Write UTF-8 JSON to path.tmp, then atomically replace the destination."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with _json_write_lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as output:
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        except (OSError, TypeError, ValueError) as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                log.warning("Could not remove temporary JSON file %s", temporary)
            raise LibraryError(f"Could not save JSON file {path.name}: {error}") from error


def book_dir(book_id: str) -> Path:
    """Return a safe, direct child of the configured library directory."""
    if (
        not isinstance(book_id, str)
        or not book_id
        or book_id in {".", ".."}
        or any(character in book_id for character in ("/", "\\", "\0", ":"))
    ):
        raise LibraryError("Invalid book ID.")
    try:
        root = get_config().library_dir.resolve()
        path = root / book_id
        if path.is_symlink() or path.resolve().parent != root:
            raise LibraryError("Book path must stay inside the library.")
        return path
    except OSError as error:
        raise LibraryError(f"Could not locate the library: {error}") from error


def create_book(
    meta: SearchResult,
    raw_text: str,
    chapters: list[tuple[str, str]],
    voice: str,
    audio_format: str,
) -> Book:
    """Create a queued book without overwriting any existing book directory."""
    book = Book(
        id=f"{meta.gutenberg_id}-{slugify(meta.title)}",
        gutenberg_id=meta.gutenberg_id,
        title=meta.title,
        authors=list(meta.authors),
        voice=voice,
        audio_format=audio_format,
        status="queued",
        chapters=[
            Chapter(index=index, title=title, word_count=len(text.split()))
            for index, (title, text) in enumerate(chapters)
        ],
        added_at=now_iso(),
    )
    directory = book_dir(book.id)
    try:
        directory.mkdir()
    except FileExistsError as error:
        raise LibraryError(f"Book {book.id} already exists in the library.") from error
    except OSError as error:
        raise LibraryError(f"Could not create book {book.id}: {error}") from error
    try:
        (directory / "text").mkdir()
        (directory / "audio").mkdir()
        (directory / "raw.txt").write_text(raw_text, encoding="utf-8")
        for index, (_, text) in enumerate(chapters):
            (directory / "text" / f"{index:03d}.txt").write_text(text, encoding="utf-8")
        write_json_atomic(directory / "book.json", book.to_dict())
    except (OSError, LibraryError) as error:
        try:
            shutil.rmtree(directory)
        except OSError:
            log.warning("Could not clean up failed book creation at %s", directory)
        raise LibraryError(f"Could not create book {book.id}: {error}") from error
    return book


def list_books() -> list[Book]:
    """List readable book folders, sorted by added_at descending."""
    try:
        directories = list(get_config().library_dir.iterdir())
    except OSError as error:
        raise LibraryError(f"Could not list the library: {error}") from error
    books = []
    for directory in directories:
        if not directory.is_dir():
            continue
        try:
            books.append(get_book(directory.name))
        except LibraryError as error:
            log.warning("Skipping unreadable book folder %s: %s", directory.name, error)
    return sorted(books, key=lambda book: book.added_at, reverse=True)


def get_book(book_id: str) -> Book:
    """Load a book, raising LibraryError for missing or unreadable metadata."""
    path = book_dir(book_id) / "book.json"
    try:
        with path.open(encoding="utf-8") as source:
            data = json.load(source)
        if not isinstance(data, dict):
            raise ValueError("Book metadata must be a JSON object")
        book = Book.from_dict(data)
        if book.id != book_id or not isinstance(book.added_at, str):
            raise ValueError("Invalid book ID or added_at timestamp")
        return book
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise LibraryError(f"Could not read book {book_id}: {error}") from error


def save_book(book: Book) -> None:
    """Atomically update metadata for an existing book directory."""
    directory = book_dir(book.id)
    if not directory.is_dir():
        raise LibraryError(f"Book {book.id} is not in the library.")
    write_json_atomic(directory / "book.json", book.to_dict())


def delete_book(book_id: str) -> None:
    """Delete a book and all its generated files."""
    directory = book_dir(book_id)
    try:
        shutil.rmtree(directory)
    except OSError as error:
        raise LibraryError(f"Could not delete book {book_id}: {error}") from error


def chapter_text_path(book_id: str, index: int) -> Path:
    """Return the zero-padded chapter text path."""
    _validate_index(index)
    return book_dir(book_id) / "text" / f"{index:03d}.txt"


def chapter_audio_path(book_id: str, index: int, audio_format: str) -> Path:
    """Return the zero-padded chapter audio path."""
    _validate_index(index)
    if audio_format not in {"opus", "mp3"}:
        raise LibraryError("Audio format must be opus or mp3.")
    return book_dir(book_id) / "audio" / f"{index:03d}.{audio_format}"


def _validate_index(index: int) -> None:
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise LibraryError("Chapter index must be a non-negative integer.")