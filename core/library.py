"""Book storage and atomic JSON persistence for Tinbook."""

import json
import logging
import math
import os
import shutil
import tempfile
import threading
from pathlib import Path

from .config import get_config
from .models import Book, Chapter, SearchResult, now_iso, slugify

log = logging.getLogger(__name__)
_json_write_lock = threading.RLock()
_book_create_lock = threading.Lock()


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
    """Stage a queued book, then publish it without overwriting complete books."""
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
    with _book_create_lock:
        try:
            if directory.exists() and (
                not directory.is_dir() or (directory / "book.json").exists()
            ):
                raise LibraryError(f"Book {book.id} already exists in the library.")
            with tempfile.TemporaryDirectory(
                prefix=f".{book.id}-", suffix=".tmp", dir=directory.parent
            ) as temporary_dir:
                staging = Path(temporary_dir)
                (staging / "text").mkdir()
                (staging / "audio").mkdir()
                (staging / "raw.txt").write_text(raw_text, encoding="utf-8")
                for index, (_, text) in enumerate(chapters):
                    (staging / "text" / f"{index:03d}.txt").write_text(text, encoding="utf-8")
                write_json_atomic(staging / "book.json", book.to_dict())
                # Recheck before publishing: never delete a completed book or symlink.
                directory = book_dir(book.id)
                if directory.exists():
                    if not directory.is_dir() or (directory / "book.json").exists():
                        raise LibraryError(f"Book {book.id} already exists in the library.")
                    shutil.rmtree(directory)
                staging.rename(directory)
        except (OSError, LibraryError) as error:
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
        try:
            if not directory.is_dir() or (
                directory.name.startswith(".") and directory.name.endswith(".tmp")
            ):
                continue
            books.append(get_book(directory.name))
        except Exception as error:
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
        if not isinstance(data.get("chapters", []), list):
            raise ValueError("chapters must be a list")
        if not all(isinstance(chapter, dict) for chapter in data.get("chapters", [])):
            raise ValueError("Each chapter must be a JSON object")
        book = Book.from_dict(data)
        _validate_book(book)
        if book.id != book_id:
            raise ValueError("Book ID does not match its directory")
        return book
    except (
        OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError
    ) as error:
        raise LibraryError(f"Could not read book {book_id}: {error}") from error


def _validate_book(book: Book) -> None:
    """Reject malformed metadata before it reaches callers."""
    for field in ("id", "title", "voice", "added_at"):
        if not isinstance(getattr(book, field), str):
            raise ValueError(f"{field} must be a string")
    for field in ("gutenberg_id", "schema_version"):
        value = getattr(book, field)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{field} must be a positive integer")
    if not isinstance(book.authors, list) or not all(
        isinstance(author, str) for author in book.authors
    ):
        raise ValueError("authors must be a list of strings")
    if not isinstance(book.status, str) or book.status not in {
        "queued", "generating", "ready", "error"
    }:
        raise ValueError("Invalid book status")
    if not isinstance(book.audio_format, str) or book.audio_format not in {"opus", "mp3"}:
        raise ValueError("audio_format must be opus or mp3")
    if book.error is not None and not isinstance(book.error, str):
        raise ValueError("error must be a string or null")
    if not isinstance(book.chapters, list):
        raise ValueError("chapters must be a list")
    for chapter in book.chapters:
        if not isinstance(chapter, Chapter):
            raise ValueError("Each chapter must be a Chapter")
        for field in ("index", "word_count"):
            value = getattr(chapter, field)
            if type(value) is not int or value < 0:
                raise ValueError(f"Chapter {field} must be a non-negative integer")
        if not isinstance(chapter.title, str):
            raise ValueError("Chapter title must be a string")
        if not isinstance(chapter.status, str) or chapter.status not in {
            "pending", "done", "error"
        }:
            raise ValueError("Invalid chapter status")
        duration = chapter.duration_sec
        if duration is not None and (
            type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0
        ):
            raise ValueError("Chapter duration_sec must be a finite non-negative number or null")


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