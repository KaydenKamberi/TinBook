"""CP1B storage and mocked Gutenberg client tests; no network access."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests
import responses

from core import config as config_module
from core import gutenberg, library
from core.config import get_config
from core.models import SearchResult


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "_ROOT_DIR", tmp_path)
    for name in (
        "TINBOOK_LIBRARY_DIR",
        "TINBOOK_VOICES_DIR",
        "TINBOOK_DEFAULT_VOICE",
        "TINBOOK_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TINBOOK_LIBRARY_DIR", str(tmp_path / "library"))
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture(autouse=True)
def http():
    with responses.RequestsMock() as mock:
        yield mock


@pytest.fixture
def metadata() -> SearchResult:
    return SearchResult(2554, "Crime and Punishment", ["Dostoyevsky, Fyodor"], "en", 123, None)


def create_sample(metadata: SearchResult):
    return library.create_book(
        metadata, "Original text: café", [("I", "One two\nthree"), ("II", "Four five")],
        "en_US-lessac-medium", "opus",
    )


def test_create_book_writes_contract_layout(metadata) -> None:
    book = create_sample(metadata)
    directory = get_config().library_dir / book.id
    assert book.id == "2554-crime-and-punishment"
    assert book.status == "queued"
    assert [chapter.status for chapter in book.chapters] == ["pending", "pending"]
    assert [chapter.word_count for chapter in book.chapters] == [3, 2]
    assert book.added_at.endswith("Z")
    assert (directory / "raw.txt").read_text(encoding="utf-8") == "Original text: café"
    assert (directory / "text/000.txt").read_text(encoding="utf-8") == "One two\nthree"
    assert (directory / "text/001.txt").read_text(encoding="utf-8") == "Four five"
    assert (directory / "audio").is_dir()
    assert json.loads((directory / "book.json").read_text(encoding="utf-8")) == book.to_dict()
    assert library.get_book(book.id) == book


def test_duplicate_creation_preserves_original(metadata) -> None:
    book = create_sample(metadata)
    with pytest.raises(library.LibraryError, match="already exists"):
        library.create_book(metadata, "Replacement", [], "another-voice", "mp3")
    assert library.get_book(book.id) == book
    assert (library.book_dir(book.id) / "raw.txt").read_text(encoding="utf-8") == "Original text: café"


def test_save_book_updates_metadata_atomically(metadata) -> None:
    book = create_sample(metadata)
    book.status = "ready"
    book.chapters[0].status = "done"
    book.chapters[0].duration_sec = 12.5
    library.save_book(book)
    assert library.get_book(book.id) == book
    assert not (library.book_dir(book.id) / "book.json.tmp").exists()


def test_list_books_sorted_and_skips_unreadable(metadata, caplog) -> None:
    older = create_sample(metadata)
    older.added_at = "2026-01-01T00:00:00Z"
    library.save_book(older)
    newer_meta = SearchResult(2, "Another Book", [], "en", 1, None)
    newer = library.create_book(newer_meta, "", [], "voice", "mp3")
    newer.added_at = "2026-02-01T00:00:00Z"
    library.save_book(newer)
    root = get_config().library_dir
    for name, contents in (("broken", "{"), ("invalid", "{}"), ("not-object", "[]")):
        (root / name).mkdir()
        (root / name / "book.json").write_text(contents, encoding="utf-8")
    (root / "missing-json").mkdir()
    (root / "not-a-book.txt").write_text("ignore me", encoding="utf-8")
    assert [book.id for book in library.list_books()] == [newer.id, older.id]
    assert caplog.text.count("Skipping unreadable book folder") == 4


def test_list_books_skips_deeply_nested_json(metadata, caplog) -> None:
    book = create_sample(metadata)
    broken = get_config().library_dir / "deeply-nested"
    broken.mkdir()
    (broken / "book.json").write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
    assert library.list_books() == [book]
    assert "Skipping unreadable book folder deeply-nested" in caplog.text
    with pytest.raises(library.LibraryError):
        library.get_book("deeply-nested")


@pytest.mark.parametrize("error", [RecursionError("deep metadata"), RuntimeError("unexpected")])
def test_list_books_catches_unexpected_loader_exceptions(metadata, monkeypatch, caplog, error):
    book = create_sample(metadata)
    (get_config().library_dir / "bad-book").mkdir()
    real_get_book = library.get_book

    def fail_bad_book(book_id):
        if book_id == "bad-book":
            raise error
        return real_get_book(book_id)

    monkeypatch.setattr(library, "get_book", fail_bad_book)
    assert library.list_books() == [book]
    assert "Skipping unreadable book folder bad-book" in caplog.text


@pytest.mark.parametrize("field, value", [
    ("id", 2554), ("id", "wrong-directory"),
    ("title", None), ("title", 123),
    ("gutenberg_id", None), ("gutenberg_id", "2554"), ("gutenberg_id", True),
    ("gutenberg_id", 1.5), ("gutenberg_id", 0), ("gutenberg_id", -1),
    ("authors", None), ("authors", "Author"), ("authors", [None]),
    ("voice", None), ("voice", []),
    ("status", None), ("status", []), ("status", "unknown"),
    ("audio_format", None), ("audio_format", []), ("audio_format", "wav"),
    ("chapters", None), ("chapters", {}), ("chapters", "text"), ("chapters", [None]),
    ("added_at", None), ("added_at", 123),
    ("error", False), ("error", []),
    ("schema_version", None), ("schema_version", True), ("schema_version", "1"),
    ("schema_version", 0),
])
def test_get_book_rejects_invalid_book_fields(metadata, field, value) -> None:
    book = create_sample(metadata)
    data = book.to_dict()
    data[field] = value
    library.write_json_atomic(library.book_dir(book.id) / "book.json", data)
    with pytest.raises(library.LibraryError):
        library.get_book(book.id)


@pytest.mark.parametrize("field, value", [
    ("index", None), ("index", "0"), ("index", True), ("index", -1),
    ("title", None), ("title", 123),
    ("word_count", None), ("word_count", "3"), ("word_count", False), ("word_count", -1),
    ("status", None), ("status", []), ("status", "queued"),
    ("duration_sec", "1.5"), ("duration_sec", True), ("duration_sec", -1),
    ("duration_sec", float("nan")), ("duration_sec", float("inf")),
])
def test_get_book_rejects_invalid_chapter_fields(metadata, field, value) -> None:
    book = create_sample(metadata)
    data = book.to_dict()
    data["chapters"][0][field] = value
    library.write_json_atomic(library.book_dir(book.id) / "book.json", data)
    with pytest.raises(library.LibraryError):
        library.get_book(book.id)


@pytest.mark.parametrize("status", ["queued", "generating", "ready", "error"])
@pytest.mark.parametrize("audio_format", ["opus", "mp3"])
def test_get_book_accepts_valid_statuses_and_audio_formats(metadata, status, audio_format):
    book = create_sample(metadata)
    book.status = status
    book.audio_format = audio_format
    book.error = "Error details" if status == "error" else None
    library.save_book(book)
    assert library.get_book(book.id) == book


def test_create_book_publishes_only_complete_staged_folder(metadata, monkeypatch) -> None:
    final = library.book_dir("2554-crime-and-punishment")
    real_rename = Path.rename
    published = []

    def inspect_rename(staging, destination):
        assert destination == final
        assert staging.parent == final.parent
        assert staging != final
        assert not final.exists()
        assert (staging / "text/000.txt").read_text(encoding="utf-8") == "One two\nthree"
        assert (staging / "raw.txt").is_file()
        assert (staging / "audio").is_dir()
        assert json.loads((staging / "book.json").read_text(encoding="utf-8"))["status"] == "queued"
        assert library.list_books() == []
        published.append(staging)
        return real_rename(staging, destination)

    monkeypatch.setattr(Path, "rename", inspect_rename)
    book = create_sample(metadata)
    assert library.get_book(book.id) == book
    assert len(published) == 1
    assert not published[0].exists()


def test_create_book_replaces_leftover_without_book_json(metadata) -> None:
    final = library.book_dir("2554-crime-and-punishment")
    final.mkdir()
    (final / "old-partial.txt").write_text("crash debris", encoding="utf-8")
    book = create_sample(metadata)
    assert library.get_book(book.id) == book
    assert not (final / "old-partial.txt").exists()
    assert list(final.parent.iterdir()) == [final]


def test_orphaned_staging_folder_does_not_block_readding(metadata) -> None:
    orphan = get_config().library_dir / ".2554-crime-and-punishment-crashed.tmp"
    orphan.mkdir()
    (orphan / "book.json").write_text("{}", encoding="utf-8")
    assert library.list_books() == []
    book = create_sample(metadata)
    assert library.list_books() == [book]
    assert library.get_book(book.id) == book


def test_creation_failure_preserves_leftover_until_ready_to_publish(metadata, monkeypatch):
    final = library.book_dir("2554-crime-and-punishment")
    final.mkdir()
    debris = final / "old-partial.txt"
    debris.write_text("crash debris", encoding="utf-8")

    def fail_write(*args):
        raise library.LibraryError("disk error")

    monkeypatch.setattr(library, "write_json_atomic", fail_write)
    with pytest.raises(library.LibraryError):
        create_sample(metadata)
    assert debris.read_text(encoding="utf-8") == "crash debris"
    assert list(final.parent.iterdir()) == [final]


def test_publish_failure_removes_staging_and_allows_retry(metadata, monkeypatch) -> None:
    with monkeypatch.context() as patch:
        def fail_rename(*args):
            raise OSError("rename failed")

        patch.setattr(Path, "rename", fail_rename)
        with pytest.raises(library.LibraryError, match="rename failed"):
            create_sample(metadata)
    assert list(get_config().library_dir.iterdir()) == []
    book = create_sample(metadata)
    assert library.get_book(book.id) == book


def test_completed_book_appearing_during_staging_is_not_overwritten(metadata, monkeypatch):
    final = library.book_dir("2554-crime-and-punishment")
    real_write = library.write_json_atomic

    def concurrent_publication(path, data):
        real_write(path, data)
        final.mkdir()
        existing = dict(data, title="Existing book")
        real_write(final / "book.json", existing)

    monkeypatch.setattr(library, "write_json_atomic", concurrent_publication)
    with pytest.raises(library.LibraryError, match="already exists"):
        create_sample(metadata)
    assert library.get_book(final.name).title == "Existing book"
    assert list(final.parent.iterdir()) == [final]


def test_delete_book_removes_all_files(metadata) -> None:
    book = create_sample(metadata)
    library.chapter_audio_path(book.id, 0, "opus").write_bytes(b"audio")
    library.delete_book(book.id)
    assert not library.book_dir(book.id).exists()
    assert library.list_books() == []


def test_missing_book_operations_raise_library_error(metadata) -> None:
    book = create_sample(metadata)
    library.delete_book(book.id)
    for operation in (lambda: library.get_book(book.id), lambda: library.save_book(book),
                      lambda: library.delete_book(book.id)):
        with pytest.raises(library.LibraryError):
            operation()


def test_chapter_paths(metadata) -> None:
    book = create_sample(metadata)
    directory = library.book_dir(book.id)
    assert library.chapter_text_path(book.id, 7) == directory / "text/007.txt"
    assert library.chapter_audio_path(book.id, 12, "opus") == directory / "audio/012.opus"
    assert library.chapter_audio_path(book.id, 1, "mp3") == directory / "audio/001.mp3"


@pytest.mark.parametrize("book_id", ["", ".", "..", "../outside", "a/b", "a\\b", "C:outside"])
def test_unsafe_book_ids_rejected(book_id) -> None:
    with pytest.raises(library.LibraryError):
        library.delete_book(book_id)


@pytest.mark.parametrize("index", [-1, "1", True])
def test_invalid_chapter_index_rejected(index) -> None:
    with pytest.raises(library.LibraryError):
        library.chapter_text_path("book", index)


def test_unsafe_audio_format_rejected() -> None:
    with pytest.raises(library.LibraryError):
        library.chapter_audio_path("book", 0, "../outside")


def test_symlink_escape_rejected(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = get_config().library_dir / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this platform")
    with pytest.raises(library.LibraryError):
        library.delete_book("linked")
    assert outside.is_dir()


def test_atomic_json_uses_utf8_and_replace(tmp_path, monkeypatch) -> None:
    path = tmp_path / "nested/data.json"
    real_replace = library.os.replace
    calls = []

    def track_replace(source, destination):
        calls.append((source, destination))
        assert source.read_text(encoding="utf-8") == '{\n  "title": "café"\n}'
        real_replace(source, destination)

    monkeypatch.setattr(library.os, "replace", track_replace)
    library.write_json_atomic(path, {"title": "café"})
    assert calls == [(path.with_name("data.json.tmp"), path)]
    assert json.loads(path.read_text(encoding="utf-8")) == {"title": "café"}


def test_atomic_failure_preserves_previous_json(tmp_path, monkeypatch) -> None:
    path = tmp_path / "book.json"
    library.write_json_atomic(path, {"old": True})

    def fail_replace(*args):
        raise OSError("disk error")

    monkeypatch.setattr(library.os, "replace", fail_replace)
    with pytest.raises(library.LibraryError):
        library.write_json_atomic(path, {"new": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
    assert not path.with_name("book.json.tmp").exists()


def test_serialization_failure_is_library_error(tmp_path) -> None:
    with pytest.raises(library.LibraryError):
        library.write_json_atomic(tmp_path / "data.json", {"bad": object()})


def test_failed_creation_rolls_back_only_new_directory(metadata, monkeypatch) -> None:
    def fail_write(*args):
        raise library.LibraryError("disk error")

    monkeypatch.setattr(library, "write_json_atomic", fail_write)
    with pytest.raises(library.LibraryError):
        create_sample(metadata)
    assert not library.book_dir("2554-crime-and-punishment").exists()
    assert list(get_config().library_dir.iterdir()) == []


@pytest.mark.parametrize("file_name", ["raw.txt", "001.txt"])
def test_text_write_failure_rolls_back_and_preserves_other_books(
    metadata, monkeypatch, file_name
) -> None:
    existing = create_sample(metadata)
    new_metadata = SearchResult(2, "Another Book", [], "en", 1, None)
    real_write_text = Path.write_text

    def fail_selected_file(path, *args, **kwargs):
        if path.name == file_name:
            raise OSError("disk is full")
        return real_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_selected_file)
    with pytest.raises(library.LibraryError, match="disk is full"):
        library.create_book(
            new_metadata, "Raw", [("I", "First"), ("II", "Second")], "voice", "opus"
        )
    assert not library.book_dir("2-another-book").exists()
    assert library.get_book(existing.id) == existing
    assert list(get_config().library_dir.iterdir()) == [library.book_dir(existing.id)]


def test_concurrent_json_writers_leave_one_complete_document(tmp_path) -> None:
    path = tmp_path / "data.json"
    start = threading.Barrier(4)

    def write_document(index):
        start.wait(timeout=10)
        library.write_json_atomic(path, {"index": index, "text": "café" * 1000})

    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(write_document, range(4)))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["index"] in range(4)
    assert data["text"] == "café" * 1000
    assert not path.with_name("data.json.tmp").exists()


def test_get_book_ignores_unknown_fields_and_supports_missing_chapters(metadata) -> None:
    book = create_sample(metadata)
    data = book.to_dict()
    data["future"] = "ignored"
    data["chapters"][0]["future"] = "ignored"
    path = library.book_dir(book.id) / "book.json"
    library.write_json_atomic(path, data)
    assert library.get_book(book.id) == book
    del data["chapters"]
    library.write_json_atomic(path, data)
    assert library.get_book(book.id).chapters == []


def api_book(formats=None) -> dict:
    return {
        "id": 2554, "title": "Crime and Punishment",
        "authors": [{"name": "Dostoyevsky, Fyodor"}], "languages": ["en"],
        "download_count": 123,
        "formats": {"text/plain; charset=utf-8": "https://example.com/book.txt"}
        if formats is None else formats,
    }


def test_search_retains_books_without_text_and_sends_settings(http) -> None:
    http.get("https://gutendex.com/books/", json={"results": [api_book(), api_book({})]})
    results = gutenberg.search("crime and punishment", page=2)
    assert len(results) == 2
    assert results[0].gutenberg_id == 2554
    assert results[0].authors == ["Dostoyevsky, Fyodor"]
    assert results[0].language == "en"
    assert results[0].download_count == 123
    assert results[1].text_url is None
    request = http.calls[0].request
    assert "search=crime+and+punishment" in request.url
    assert "languages=en" in request.url
    assert "page=2" in request.url
    assert request.headers["User-Agent"] == get_config().user_agent


@pytest.mark.parametrize("formats, expected", [
    ({"text/plain": "https://x/plain", "text/plain; charset=us-ascii": "https://x/ascii",
      "text/plain; charset=utf-8": "https://x/utf8"}, "https://x/utf8"),
    ({"text/plain": "https://x/plain", "text/plain; charset=us-ascii": "https://x/ascii"},
     "https://x/ascii"),
    ({"text/plain; charset=utf-8": "https://x/book.zip", "text/plain": "https://x/plain"},
     "https://x/plain"),
    ({"text/plain": "https://x/book.zip?download=true"}, None),
    ({"text/html": "https://x/book.html"}, None),
])
def test_metadata_text_url_priority_and_zip_exclusion(http, formats, expected) -> None:
    http.get("https://gutendex.com/books/2554/", json=api_book(formats))
    assert gutenberg.get_metadata(2554).text_url == expected


def test_download_decodes_bytes_as_utf8_with_replacement(http) -> None:
    http.get("https://gutendex.com/books/2554/", json=api_book())
    http.get("https://example.com/book.txt", body=b"*** START OF caf\xc3\xa9 \xff")
    assert gutenberg.download_text(2554) == "*** START OF café \ufffd"
    assert http.calls[1].request.headers["User-Agent"] == get_config().user_agent


def test_download_without_text_raises_gutenberg_error(http) -> None:
    http.get("https://gutendex.com/books/2554/", json=api_book({}))
    with pytest.raises(gutenberg.GutenbergError, match="no plain-text"):
        gutenberg.download_text(2554)


@pytest.mark.parametrize("error, message", [
    (requests.Timeout("timeout"), "timed out"),
    (requests.ConnectionError("offline"), "Could not reach"),
])
def test_request_failures_are_user_friendly(http, error, message) -> None:
    http.get("https://gutendex.com/books/", body=error)
    with pytest.raises(gutenberg.GutenbergError, match=message):
        gutenberg.search("book")


@pytest.mark.parametrize("status", [201, 404, 500])
def test_non_200_status_is_gutenberg_error(http, status) -> None:
    http.get("https://gutendex.com/books/", status=status)
    with pytest.raises(gutenberg.GutenbergError, match=f"HTTP {status}"):
        gutenberg.search("book")


@pytest.mark.parametrize("body", ["not JSON", "[]", '{"results": null}'])
def test_bad_json_or_metadata_is_gutenberg_error(http, body) -> None:
    http.get("https://gutendex.com/books/", body=body)
    with pytest.raises(gutenberg.GutenbergError):
        gutenberg.search("book")


@pytest.mark.parametrize("bad_result", [
    dict(api_book(), download_count=None), dict(api_book(), title=None),
    dict(api_book(), authors=[None]), {}, None,
])
def test_search_skips_bad_results_and_keeps_valid_order(http, caplog, bad_result) -> None:
    last = dict(api_book({}), id=2, title="Another Book")
    http.get(
        "https://gutendex.com/books/",
        json={"results": [api_book(), bad_result, last]},
    )
    results = gutenberg.search("crime and punishment")
    assert [result.gutenberg_id for result in results] == [2554, 2]
    assert results[1].text_url is None
    assert "Skipping invalid Gutenberg search result 2" in caplog.text


def test_search_returns_empty_list_if_all_results_invalid(http, caplog) -> None:
    http.get("https://gutendex.com/books/", json={"results": [{}, None]})
    assert gutenberg.search("book") == []
    assert caplog.text.count("Skipping invalid Gutenberg search result") == 2


def test_get_metadata_still_raises_for_malformed_single_book(http) -> None:
    http.get("https://gutendex.com/books/2554/", json=dict(api_book(), download_count=None))
    with pytest.raises(gutenberg.GutenbergError):
        gutenberg.get_metadata(2554)


def test_http_timeout_uses_configuration(monkeypatch) -> None:
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"results": []}'
        return response

    monkeypatch.setattr(gutenberg.requests, "get", fake_get)
    assert gutenberg.search("book") == []
    assert captured["timeout"] == get_config().http_timeout


@pytest.mark.parametrize("page", [0, -1, True])
def test_invalid_search_page_rejected(page) -> None:
    with pytest.raises(gutenberg.GutenbergError):
        gutenberg.search("book", page)