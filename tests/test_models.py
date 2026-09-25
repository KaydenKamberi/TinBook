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


def test_progress_round_trip() -> None:
    progress = Progress(2, 83.25, 1.2, False, "2026-09-24T18:03:11Z")
    assert Progress.from_dict(progress.to_dict()) == progress


def test_slugify_examples_and_limit() -> None:
    assert slugify("Crime and Punishment") == "crime-and-punishment"
    assert slugify("  Hello!!  World ") == "hello-world"
    assert len(slugify("A very long title with many words that exceeds forty characters")) <= 40


def test_now_iso_is_utc_z_timestamp() -> None:
    assert now_iso().endswith("Z")