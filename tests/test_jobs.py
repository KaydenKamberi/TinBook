"""Tests for core.jobs. core.library (a CP1B stub) and core.tts are faked."""

import threading
import time
from pathlib import Path

import pytest

from core import jobs
from core.config import get_config
from core.library import LibraryError
from core.models import Book, Chapter


class FakeLibrary:
    """In-memory core.library following ARCHITECTURE §5. Books round-trip via dicts like disk."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.books: dict[str, dict] = {}
        self.saves: list[Book] = []

    def add(self, book_id: str, chapters: int, status: str = "queued", added_at: str = "2026-01-01T00:00:00Z",
            done: tuple[int, ...] = (), voice: str = "en_US-lessac-medium", audio_format: str = "opus") -> Book:
        book = Book(
            id=book_id, gutenberg_id=1, title=book_id, authors=[], voice=voice, audio_format=audio_format,
            status=status, added_at=added_at,
            chapters=[Chapter(i, f"Chapter {i + 1}", 10, "done" if i in done else "pending",
                              1.0 if i in done else None) for i in range(chapters)],
        )  # fmt: skip
        self.books[book_id] = book.to_dict()
        for i in range(chapters):
            path = self.chapter_text_path(book_id, i)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"Text of chapter {i}.", encoding="utf-8")
        for i in done:
            path = self.chapter_audio_path(book_id, i, audio_format)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"audio")
        return book

    # contract functions
    def book_dir(self, book_id: str) -> Path:
        return self.root / book_id

    def get_book(self, book_id: str) -> Book:
        if book_id not in self.books:
            raise LibraryError(f"No book {book_id}")
        return Book.from_dict(self.books[book_id])

    def save_book(self, book: Book) -> None:
        self.books[book.id] = book.to_dict()
        self.saves.append(Book.from_dict(book.to_dict()))

    def list_books(self) -> list[Book]:
        books = [Book.from_dict(d) for d in self.books.values()]
        return sorted(books, key=lambda b: b.added_at, reverse=True)

    def delete_book(self, book_id: str) -> None:
        self.books.pop(book_id, None)
        import shutil

        shutil.rmtree(self.book_dir(book_id), ignore_errors=True)

    def chapter_text_path(self, book_id: str, index: int) -> Path:
        return self.book_dir(book_id) / "text" / f"{index:03d}.txt"

    def chapter_audio_path(self, book_id: str, index: int, audio_format: str) -> Path:
        return self.book_dir(book_id) / "audio" / f"{index:03d}.{audio_format}"

    def stored(self, book_id: str) -> Book:
        return Book.from_dict(self.books[book_id])


class FakeTTS:
    """Writes a dummy file and returns a duration. Optional failures and per-call hooks."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Path, str, str, str]] = []
        self.fail: dict[str, int] = {}  # out_path.name -> remaining failures
        self.hook = None  # called before writing, with (out_path)

    def __call__(self, text: str, out_path: Path, voice: str, audio_format: str, bitrate: str) -> float:
        self.calls.append((text, out_path, voice, audio_format, bitrate))
        if self.hook:
            self.hook(out_path)
        if self.fail.get(out_path.name, 0) > 0:
            self.fail[out_path.name] -= 1
            raise RuntimeError(f"synthesis failed for {out_path.name}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"audio")
        return 10.0 + int(out_path.stem)

    def indexes(self) -> list[int]:
        return [int(call[1].stem) for call in self.calls]


@pytest.fixture
def lib(monkeypatch, tmp_path: Path) -> FakeLibrary:
    fake = FakeLibrary(tmp_path / "library")
    for name in ("get_book", "save_book", "list_books", "book_dir", "delete_book",
                 "chapter_text_path", "chapter_audio_path"):  # fmt: skip
        monkeypatch.setattr(jobs.library, name, getattr(fake, name))
    monkeypatch.setenv("TINBOOK_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("TINBOOK_VOICES_DIR", str(tmp_path / "voices"))
    get_config.cache_clear()
    yield fake
    get_config.cache_clear()


@pytest.fixture
def synth(monkeypatch) -> FakeTTS:
    fake = FakeTTS()
    monkeypatch.setattr(jobs.tts, "synthesize_to_file", fake)
    return fake


def wait_for(condition, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        time.sleep(0.01)


# ---------------------------------------------------------------- processing one book


def test_generates_all_chapters_and_ends_ready(lib, synth) -> None:
    lib.add("1-a", chapters=3)
    jobs.JobQueue()._process_book("1-a")

    assert synth.indexes() == [0, 1, 2]
    assert synth.calls[0][0] == "Text of chapter 0."
    book = lib.stored("1-a")
    assert book.status == "ready"
    assert [c.status for c in book.chapters] == ["done"] * 3
    assert [c.duration_sec for c in book.chapters] == [10.0, 11.0, 12.0]
    assert all(lib.chapter_audio_path("1-a", i, "opus").is_file() for i in range(3))


def test_status_transitions_and_save_after_every_chapter(lib, synth) -> None:
    lib.add("1-a", chapters=3)
    jobs.JobQueue()._process_book("1-a")

    statuses = [(b.status, b.chapters_done()) for b in lib.saves]
    assert statuses == [
        ("generating", 0),  # started
        ("generating", 1),
        ("generating", 2),
        ("generating", 3),
        ("ready", 3),
    ]


def test_resume_only_generates_missing_chapters(lib, synth) -> None:
    lib.add("1-a", chapters=4, status="generating", done=(0, 1))
    lib.chapter_audio_path("1-a", 1, "opus").unlink()  # "done" but audio missing (killed mid-write)
    lib.chapter_audio_path("1-a", 2, "opus").parent.mkdir(exist_ok=True)
    lib.chapter_audio_path("1-a", 2, "opus").with_suffix(".opus.part").write_bytes(b"partial")

    jobs.JobQueue()._process_book("1-a")

    assert synth.indexes() == [1, 2, 3]
    assert lib.stored("1-a").status == "ready"


def test_failed_chapter_is_retried_once(lib, synth) -> None:
    lib.add("1-a", chapters=2)
    synth.fail["000.opus"] = 1
    jobs.JobQueue()._process_book("1-a")

    assert synth.indexes() == [0, 0, 1]
    book = lib.stored("1-a")
    assert book.status == "ready"
    assert book.error is None


def test_chapter_failing_twice_marks_book_error(lib, synth) -> None:
    lib.add("1-a", chapters=3)
    synth.fail["001.opus"] = 2
    jobs.JobQueue()._process_book("1-a")

    assert synth.indexes() == [0, 1, 1]  # stops at the bad chapter
    book = lib.stored("1-a")
    assert book.status == "error"
    assert "Chapter 2" in book.error and "synthesis failed for 001.opus" in book.error
    assert [c.status for c in book.chapters] == ["done", "error", "pending"]


def test_error_book_reenqueued_retries_the_failed_chapter(lib, synth) -> None:
    lib.add("1-a", chapters=2)
    synth.fail["000.opus"] = 2
    queue = jobs.JobQueue()
    queue._process_book("1-a")
    assert lib.stored("1-a").status == "error"

    queue._process_book("1-a")
    book = lib.stored("1-a")
    assert book.status == "ready"
    assert book.error is None


def test_missing_text_file_counts_as_failure(lib, synth) -> None:
    lib.add("1-a", chapters=1)
    lib.chapter_text_path("1-a", 0).unlink()
    jobs.JobQueue()._process_book("1-a")
    assert lib.stored("1-a").status == "error"
    assert synth.calls == []


def test_reloads_book_before_saving(lib, synth) -> None:
    """A change made by the API while a chapter synthesizes must not be overwritten."""
    lib.add("1-a", chapters=2)

    def api_edit(out_path: Path) -> None:
        stored = lib.books["1-a"]
        stored["title"] = f"edited during {out_path.stem}"

    synth.hook = api_edit
    jobs.JobQueue()._process_book("1-a")
    assert lib.stored("1-a").title == "edited during 001"


def test_book_deleted_mid_chapter_stops_and_cleans_up(lib, synth) -> None:
    lib.add("1-a", chapters=3)
    synth.hook = lambda out_path: lib.delete_book("1-a") if out_path.stem == "001" else None
    jobs.JobQueue()._process_book("1-a")

    assert synth.indexes() == [0, 1]
    assert "1-a" not in lib.books
    assert not lib.book_dir("1-a").exists()  # the orphan audio file did not resurrect the folder


def test_voice_changed_mid_chapter_redoes_chapter(lib, synth) -> None:
    lib.add("1-a", chapters=2)

    def regenerate(out_path: Path) -> None:
        if out_path.stem == "000" and lib.books["1-a"]["voice"] == "en_US-lessac-medium":
            lib.books["1-a"]["voice"] = "en_GB-alba-medium"

    synth.hook = regenerate
    jobs.JobQueue()._process_book("1-a")
    voices = [(int(c[1].stem), c[2]) for c in synth.calls]
    assert voices == [(0, "en_US-lessac-medium"), (0, "en_GB-alba-medium"), (1, "en_GB-alba-medium")]
    assert lib.stored("1-a").status == "ready"


def test_missing_book_is_skipped(lib, synth) -> None:
    jobs.JobQueue()._process_book("nope")
    assert synth.calls == []


def test_bitrate_follows_format(lib, synth) -> None:
    lib.add("1-a", chapters=1)
    lib.add("2-b", chapters=1, audio_format="mp3")
    queue = jobs.JobQueue()
    queue._process_book("1-a")
    queue._process_book("2-b")
    assert [(c[3], c[4]) for c in synth.calls] == [("opus", "32k"), ("mp3", "48k")]


# ---------------------------------------------------------------- queue + worker thread


def test_start_resumes_unfinished_books_oldest_first(lib, synth) -> None:
    lib.add("new", chapters=1, status="queued", added_at="2026-03-01T00:00:00Z")
    lib.add("old", chapters=1, status="generating", added_at="2026-01-01T00:00:00Z")
    lib.add("done", chapters=1, status="ready", done=(0,))
    lib.add("broken", chapters=1, status="error")

    order: list[str] = []
    synth.hook = lambda out_path: order.append(out_path.parent.parent.name)
    queue = jobs.JobQueue()
    queue.start()
    try:
        wait_for(lambda: lib.stored("new").status == "ready" and lib.stored("old").status == "ready")
    finally:
        queue.stop()
    assert order == ["old", "new"]
    assert lib.stored("broken").status == "error"
    assert lib.stored("done").status == "ready"


def test_start_is_idempotent(lib, synth) -> None:
    queue = jobs.JobQueue()
    queue.start()
    first = queue._thread
    queue.start()
    try:
        assert queue._thread is first
        assert sum(t.name == "tinbook-jobs" and t.is_alive() for t in threading.enumerate()) >= 1
    finally:
        queue.stop()
    assert not first.is_alive()


def test_status_while_generating_and_enqueue_dedupes(lib, synth) -> None:
    # status "ready" so start() doesn't resume them; we enqueue by hand.
    lib.add("1-a", chapters=2, status="ready")
    lib.add("2-b", chapters=1, status="ready")
    gate, entered = threading.Event(), threading.Event()

    def block(out_path: Path) -> None:
        entered.set()
        assert gate.wait(timeout=5)

    synth.hook = block
    queue = jobs.JobQueue()
    queue.start()
    try:
        assert queue.status() == {"current": None, "queued": []}
        queue.enqueue("1-a")
        assert entered.wait(timeout=5)
        queue.enqueue("2-b")
        queue.enqueue("2-b")
        assert queue.status() == {
            "current": {"book_id": "1-a", "chapter_index": 0, "chapters_done": 0, "chapters_total": 2},
            "queued": ["2-b"],
        }
        synth.hook = None
        gate.set()
        wait_for(lambda: queue.status() == {"current": None, "queued": []})
    finally:
        gate.set()
        queue.stop()
    assert lib.stored("1-a").status == "ready"
    assert lib.stored("2-b").status == "ready"


def test_book_already_generating_can_be_requeued(lib, synth) -> None:
    lib.add("1-a", chapters=1)
    gate, entered = threading.Event(), threading.Event()
    synth.hook = lambda out_path: (entered.set(), gate.wait(timeout=5))
    queue = jobs.JobQueue()
    queue.start()
    try:
        queue.enqueue("1-a")
        assert entered.wait(timeout=5)
        queue.enqueue("1-a")  # e.g. regenerate while generating
        assert queue.status()["queued"] == ["1-a"]
        synth.hook = None
        gate.set()
        wait_for(lambda: queue.status() == {"current": None, "queued": []})
    finally:
        gate.set()
        queue.stop()


def test_stop_finishes_current_chapter_and_leaves_book_resumable(lib, synth) -> None:
    lib.add("1-a", chapters=3)
    gate, entered = threading.Event(), threading.Event()
    synth.hook = lambda out_path: (entered.set(), gate.wait(timeout=5))
    queue = jobs.JobQueue()
    queue.start()
    queue.enqueue("1-a")
    assert entered.wait(timeout=5)
    stopper = threading.Thread(target=queue.stop)
    stopper.start()
    gate.set()
    stopper.join(timeout=5)
    queue._thread.join(timeout=5)
    assert not queue._thread.is_alive()

    book = lib.stored("1-a")
    assert book.status == "generating"  # resumed on next start()
    assert book.chapters_done() == 1


def test_worker_survives_unexpected_errors(lib, synth, monkeypatch) -> None:
    lib.add("2-b", chapters=1)
    real_get_book = lib.get_book

    def flaky_get_book(book_id: str) -> Book:
        if book_id == "1-a":
            raise ValueError("corrupt book.json")
        return real_get_book(book_id)

    monkeypatch.setattr(jobs.library, "get_book", flaky_get_book)
    queue = jobs.JobQueue()
    queue.start()
    try:
        queue.enqueue("1-a")
        queue.enqueue("2-b")
        wait_for(lambda: lib.stored("2-b").status == "ready")
    finally:
        queue.stop()


def test_get_queue_is_a_singleton() -> None:
    assert jobs.get_queue() is jobs.get_queue()
    assert isinstance(jobs.get_queue(), jobs.JobQueue)
