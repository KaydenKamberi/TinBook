import re

from core.models import Book, Chapter, Progress, SearchResult, now_iso, slugify


def test_search_result_round_trip_ignores_unknown_keys() -> None:
    result = SearchResult(2554, "Crime and Punishment", ["Dostoyevsky"], "en", 12, None)
    data = result.to_dict()
    data["future_key"] = "ignored"
    assert SearchResult.from_dict(data) == result


def test_chapter_round_trip() -> None:
    chapter = Chapter(0, "Chapter I", 120, "done", 45.5)
    assert Chapter.from_dict(chapter.to_dict()) == chapter


def test_book_round_trip_and_helpers() -> None:
    book = Book(
        id="2554-crime-and-punishment",
        gutenberg_id=2554,
        title="Crime and Punishment",
        authors=["Dostoyevsky"],
        voice="en_US-lessac-medium",
        audio_format="opus",
        status="ready",
        chapters=[
            Chapter(0, "Chapter I", 120, "done", 45.5),
            Chapter(1, "Chapter II", 80, "pending"),
        ],
        added_at="2026-09-24T18:03:11Z",
    )
    assert Book.from_dict(book.to_dict()) == book
    assert book.chapters_done() == 1
    assert book.total_duration_sec() == 45.5


def test_book_from_dict_without_chapters_and_zero_duration() -> None:
    book = Book.from_dict(
        {
            "id": "84-frankenstein",
            "gutenberg_id": 84,
            "title": "Frankenstein",
            "authors": [],
            "voice": "en_US-lessac-medium",
            "audio_format": "opus",
            "status": "queued",
            "added_at": "2026-09-24T18:03:11Z",
        }
    )
    assert book.chapters == []
    assert book.chapters_done() == 0
    duration = book.total_duration_sec()
    assert duration == 0.0
    assert isinstance(duration, float)


def test_progress_round_trip() -> None:
    progress = Progress(2, 83.25, 1.2, False, "2026-09-24T18:03:11Z")
    assert Progress.from_dict(progress.to_dict()) == progress


def test_slugify_examples() -> None:
    assert slugify("Crime and Punishment") == "crime-and-punishment"
    assert slugify("  Hello!!  World ") == "hello-world"


def test_slugify_cuts_at_last_hyphen_before_40() -> None:
    title = "A very long title with many words that exceeds forty characters"
    # Full slug: "a-very-long-title-with-many-words-that-exceeds-..."; char 40 falls inside "exceeds".
    assert slugify(title) == "a-very-long-title-with-many-words-that"
    # A word ending exactly at 40 chars is kept whole.
    assert slugify("aaaaaaaaa bbbbbbbbb ccccccccc dddddddddd eeee") == "aaaaaaaaa-bbbbbbbbb-ccccccccc-dddddddddd"
    # No hyphen to cut at: hard cut at 40.
    assert slugify("x" * 60) == "x" * 40


def test_slugify_transliterates_accents() -> None:
    assert slugify("Les Misérables") == "les-miserables"
    assert slugify("Ünïcödé Tïtle") == "unicode-title"


def test_slugify_empty_falls_back_to_book() -> None:
    assert slugify("!!!") == "book"
    assert slugify("") == "book"
    assert slugify("战争与和平") == "book"


def test_now_iso_is_utc_z_timestamp() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", now_iso())