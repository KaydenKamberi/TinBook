"""Audio generation queue (CP1A).

One daemon worker thread generates chapter audio for one book at a time, in
chapter order. The book is reloaded from disk before every save because the API
may change it (delete, regenerate) while the worker runs.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from pathlib import Path

from . import library, tts
from .config import get_config
from .library import LibraryError
from .models import Book

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # a chapter is tried once, then retried once
_DEFAULT_BITRATES = {"opus": "32k", "mp3": "48k"}


def _bitrate_for(audio_format: str) -> str:
    """Config bitrate if it belongs to this format, else that format's default."""
    config = get_config()
    if audio_format == config.audio_format:
        return config.audio_bitrate
    return _DEFAULT_BITRATES.get(audio_format, config.audio_bitrate)


def _needs_audio(book: Book, index: int) -> bool:
    chapter = book.chapters[index]
    if chapter.status != "done":
        return True
    return not library.chapter_audio_path(book.id, index, book.audio_format).is_file()


def _next_chapter(book: Book) -> int | None:
    for index in range(len(book.chapters)):
        if _needs_audio(book, index):
            return index
    return None


def _discard_orphan(audio_path: Path) -> None:
    """Remove audio written for a book that was deleted mid-synthesis."""
    audio_path.unlink(missing_ok=True)
    for directory in (audio_path.parent, audio_path.parent.parent):
        try:
            directory.rmdir()  # only succeeds if empty
        except OSError:
            break


class JobQueue:
    """Single-worker chapter generation queue."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._queue: deque[str] = deque()
        self._current: dict | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    # ------------------------------------------------------------ public API

    def start(self) -> None:
        """Start ONE daemon worker; re-enqueue books left queued/generating."""
        with self._cond:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopping.clear()
        unfinished = [b for b in library.list_books() if b.status in ("queued", "generating")]
        for book in sorted(unfinished, key=lambda b: b.added_at):  # oldest first
            self.enqueue(book.id)
        with self._cond:
            self._thread = threading.Thread(target=self._run, name="tinbook-jobs", daemon=True)
            self._thread.start()
        log.info("Job queue started (%d book(s) resumed)", len(unfinished))

    def enqueue(self, book_id: str) -> None:
        """Queue a book. No-op if it is already waiting.

        A book that is currently generating is queued again, so a regenerate that
        lands after the worker's last check is never missed.
        """
        with self._cond:
            if book_id not in self._queue:
                self._queue.append(book_id)
                self._cond.notify()

    def status(self) -> dict:
        """``{"current": {...} | None, "queued": [book_id, ...]}``."""
        with self._cond:
            return {
                "current": dict(self._current) if self._current else None,
                "queued": list(self._queue),
            }

    def stop(self) -> None:
        """Ask the worker to stop after the current chapter and wait briefly for it."""
        with self._cond:
            self._stopping.set()
            self._cond.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    # ------------------------------------------------------------ worker

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._stopping.is_set():
                    self._cond.wait()
                if self._stopping.is_set():
                    return
                book_id = self._queue.popleft()
                self._current = {
                    "book_id": book_id,
                    "chapter_index": None,
                    "chapters_done": 0,
                    "chapters_total": 0,
                }
            try:
                self._process_book(book_id)
            except Exception:
                log.exception("Unexpected error generating %s", book_id)
            finally:
                with self._cond:
                    self._current = None

    def _set_current(self, book: Book, index: int | None) -> None:
        with self._cond:
            if self._current is not None and self._current["book_id"] == book.id:
                self._current.update(
                    chapter_index=index,
                    chapters_done=book.chapters_done(),
                    chapters_total=len(book.chapters),
                )

    def _process_book(self, book_id: str) -> None:
        """Generate every missing chapter of one book, saving after each chapter."""
        attempts: dict[int, int] = {}
        while not self._stopping.is_set():
            try:
                book = library.get_book(book_id)
            except LibraryError as error:
                log.warning("Skipping %s: %s", book_id, error)
                return

            index = _next_chapter(book)
            if index is None:
                if book.status != "ready" or book.error is not None:
                    book.status, book.error = "ready", None
                    library.save_book(book)
                self._set_current(book, None)
                log.info("Book %s is ready", book_id)
                return

            if book.status != "generating":
                book.status, book.error = "generating", None
                library.save_book(book)
            self._set_current(book, index)

            voice, audio_format = book.voice, book.audio_format
            audio_path = library.chapter_audio_path(book_id, index, audio_format)
            try:
                text = library.chapter_text_path(book_id, index).read_text(encoding="utf-8")
                duration = tts.synthesize_to_file(
                    text, audio_path, voice, audio_format, _bitrate_for(audio_format)
                )
            except Exception as error:
                attempts[index] = attempts.get(index, 0) + 1
                log.warning(
                    "Chapter %d of %s failed (attempt %d/%d): %s",
                    index, book_id, attempts[index], MAX_ATTEMPTS, error,
                )  # fmt: skip
                if attempts[index] >= MAX_ATTEMPTS:
                    self._mark_error(book_id, index, error)
                    return
                continue

            # Reload: the API may have deleted or regenerated the book meanwhile.
            try:
                book = library.get_book(book_id)
            except LibraryError:
                log.info("Book %s was deleted during generation", book_id)
                _discard_orphan(audio_path)
                return
            if book.voice != voice or book.audio_format != audio_format:
                log.info("Book %s settings changed mid-chapter; redoing chapter %d", book_id, index)
                if audio_format != book.audio_format:
                    audio_path.unlink(missing_ok=True)
                attempts.pop(index, None)
                continue
            if index >= len(book.chapters):
                continue
            chapter = book.chapters[index]
            chapter.status, chapter.duration_sec = "done", duration
            book.status = "generating"
            library.save_book(book)
            self._set_current(book, index)

    def _mark_error(self, book_id: str, index: int, error: Exception) -> None:
        try:
            book = library.get_book(book_id)
        except LibraryError:
            return
        if index < len(book.chapters):
            book.chapters[index].status = "error"
            title = book.chapters[index].title
        else:
            title = "?"
        book.status = "error"
        book.error = f"Chapter {index + 1} ({title}) failed twice: {error}"
        library.save_book(book)
        log.error("%s: %s", book_id, book.error)


_queue: JobQueue | None = None
_queue_lock = threading.Lock()


def get_queue() -> JobQueue:
    """Process-wide JobQueue singleton."""
    global _queue
    with _queue_lock:
        if _queue is None:
            _queue = JobQueue()
        return _queue
