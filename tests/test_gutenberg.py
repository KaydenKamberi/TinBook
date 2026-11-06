"""CP2C tests for core/gutenberg.py using mocked HTTP responses."""

from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from core import gutenberg
from core.config import get_config
from core.gutenberg import GutenbergError
from core.models import SearchResult


@pytest.fixture(autouse=True)
def reset_gutenberg_state(monkeypatch):
    """Gutenberg keeps outage and catalog state in module globals; reset per test."""
    monkeypatch.setattr(gutenberg, "_gutendex_skip_until", 0.0)
    monkeypatch.setattr(gutenberg, "_catalog_retry_at", 0.0)
    monkeypatch.setattr(gutenberg, "_catalog_cache", None)


def _query(call) -> dict[str, list[str]]:
    """Query-string parameters actually sent in a recorded request."""
    return parse_qs(urlparse(call.request.url).query)


@responses.activate
def test_search_returns_parsed_results():
    """Search parsing extracts id, title, authors, language, download_count, text_url."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 1,
            "results": [
                {
                    "id": 2554,
                    "title": "Crime and Punishment",
                    "authors": [{"name": "Dostoyevsky, Fyodor"}],
                    "languages": ["en"],
                    "download_count": 12345,
                    "formats": {
                        "text/plain; charset=utf-8": "https://www.gutenberg.org/files/2554/2554-0.txt",
                        "application/epub+zip": "https://www.gutenberg.org/ebooks/2554.epub.images",
                    },
                }
            ],
        },
        status=200,
    )
    results = gutenberg.search("crime and punishment")
    assert len(results) == 1
    assert results[0].gutenberg_id == 2554
    assert results[0].title == "Crime and Punishment"
    assert results[0].authors == ["Dostoyevsky, Fyodor"]
    assert results[0].language == "en"
    assert results[0].download_count == 12345
    assert results[0].text_url == "https://www.gutenberg.org/files/2554/2554-0.txt"


@responses.activate
def test_search_text_url_priority_utf8_first():
    """text_url prefers charset=utf-8 over us-ascii over plain."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 1,
            "results": [
                {
                    "id": 1,
                    "title": "Test Book",
                    "authors": [],
                    "languages": ["en"],
                    "download_count": 0,
                    "formats": {
                        "text/plain": "https://example.com/plain.txt",
                        "text/plain; charset=us-ascii": "https://example.com/ascii.txt",
                        "text/plain; charset=utf-8": "https://example.com/utf8.txt",
                    },
                }
            ],
        },
        status=200,
    )
    results = gutenberg.search("test")
    assert results[0].text_url == "https://example.com/utf8.txt"


@responses.activate
def test_search_text_url_priority_us_ascii_second():
    """text_url falls back to us-ascii when utf-8 is absent."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 1,
            "results": [
                {
                    "id": 1,
                    "title": "Test Book",
                    "authors": [],
                    "languages": ["en"],
                    "download_count": 0,
                    "formats": {
                        "text/plain": "https://example.com/plain.txt",
                        "text/plain; charset=us-ascii": "https://example.com/ascii.txt",
                    },
                }
            ],
        },
        status=200,
    )
    results = gutenberg.search("test")
    assert results[0].text_url == "https://example.com/ascii.txt"


@responses.activate
def test_search_text_url_priority_plain_third():
    """text_url falls back to plain text/plain when no charset specified."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 1,
            "results": [
                {
                    "id": 1,
                    "title": "Test Book",
                    "authors": [],
                    "languages": ["en"],
                    "download_count": 0,
                    "formats": {
                        "text/plain": "https://example.com/plain.txt",
                    },
                }
            ],
        },
        status=200,
    )
    results = gutenberg.search("test")
    assert results[0].text_url == "https://example.com/plain.txt"


@responses.activate
def test_search_text_url_none_when_no_plain_text():
    """text_url is None when no text/plain format exists."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 1,
            "results": [
                {
                    "id": 1,
                    "title": "Test Book",
                    "authors": [],
                    "languages": ["en"],
                    "download_count": 0,
                    "formats": {
                        "application/epub+zip": "https://example.com/book.epub",
                        "application/pdf": "https://example.com/book.pdf",
                    },
                }
            ],
        },
        status=200,
    )
    results = gutenberg.search("test")
    assert results[0].text_url is None


@responses.activate
def test_search_skips_zip_urls():
    """text_url skips URLs ending in .zip even if they have text/plain mime."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 1,
            "results": [
                {
                    "id": 1,
                    "title": "Test Book",
                    "authors": [],
                    "languages": ["en"],
                    "download_count": 0,
                    "formats": {
                        "text/plain; charset=utf-8": "https://example.com/book.txt.zip",
                        "text/plain": "https://example.com/book.txt",
                    },
                }
            ],
        },
        status=200,
    )
    results = gutenberg.search("test")
    assert results[0].text_url == "https://example.com/book.txt"


@responses.activate
def test_search_pagination():
    """Search respects page parameter."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 100,
            "results": [
                {
                    "id": i,
                    "title": f"Book {i}",
                    "authors": [],
                    "languages": ["en"],
                    "download_count": 0,
                    "formats": {},
                }
                for i in range(1, 11)
            ],
        },
        status=200,
    )
    results = gutenberg.search("test", page=2)
    assert len(results) == 10
    assert results[0].gutenberg_id == 1
    assert len(responses.calls) == 1
    assert _query(responses.calls[0])["page"] == ["2"]


@responses.activate
def test_search_sends_query_language_page_and_user_agent():
    """Search sends search=<q>, languages=en, page=<n> and the configured User-Agent."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={"count": 0, "results": []},
        status=200,
    )
    assert gutenberg.search("crime and punishment") == []
    assert len(responses.calls) == 1
    query = _query(responses.calls[0])
    assert query["search"] == ["crime and punishment"]
    assert query["languages"] == ["en"]
    assert query["page"] == ["1"]
    assert responses.calls[0].request.headers["User-Agent"] == get_config().user_agent


@responses.activate
def test_metadata_and_download_send_user_agent():
    """get_metadata and download_text both send the configured User-Agent."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/84/",
        json={
            "id": 84,
            "title": "Frankenstein",
            "authors": [],
            "languages": ["en"],
            "download_count": 0,
            "formats": {"text/plain; charset=utf-8": "https://www.gutenberg.org/files/84/84-0.txt"},
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.gutenberg.org/files/84/84-0.txt",
        body="text",
        status=200,
    )
    gutenberg.download_text(84)
    assert [call.request.url for call in responses.calls] == [
        "https://gutendex.com/books/84/",
        "https://www.gutenberg.org/files/84/84-0.txt",
    ]
    for call in responses.calls:
        assert call.request.headers["User-Agent"] == get_config().user_agent


@responses.activate
def test_search_invalid_page_raises():
    """Search with invalid page raises GutenbergError."""
    with pytest.raises(GutenbergError, match="positive integer"):
        gutenberg.search("test", page=0)


@responses.activate
def test_search_invalid_page_type_raises():
    """Search with non-integer page raises GutenbergError."""
    with pytest.raises(GutenbergError, match="positive integer"):
        gutenberg.search("test", page="1")


@responses.activate
def test_search_timeout_raises():
    """Timeout on search raises GutenbergError."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        body=requests.Timeout(),
    )
    with pytest.raises(GutenbergError, match="timed out"):
        gutenberg.search("test", page=1)


@responses.activate
def test_search_http_500_raises():
    """HTTP 500 on search raises GutenbergError."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        status=500,
    )
    with pytest.raises(GutenbergError, match="HTTP 500"):
        gutenberg.search("test", page=1)


@responses.activate
def test_search_http_404_raises():
    """HTTP 404 on search raises GutenbergError."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        status=404,
    )
    with pytest.raises(GutenbergError, match="HTTP 404"):
        gutenberg.search("test", page=1)


@responses.activate
def test_get_metadata_single_book():
    """get_metadata fetches and parses a single book."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/84/",
        json={
            "id": 84,
            "title": "Frankenstein",
            "authors": [{"name": "Shelley, Mary"}],
            "languages": ["en"],
            "download_count": 54321,
            "formats": {
                "text/plain; charset=utf-8": "https://www.gutenberg.org/files/84/84-0.txt",
            },
        },
        status=200,
    )
    result = gutenberg.get_metadata(84)
    assert result.gutenberg_id == 84
    assert result.title == "Frankenstein"
    assert result.authors == ["Shelley, Mary"]
    assert result.language == "en"
    assert result.download_count == 54321
    assert result.text_url == "https://www.gutenberg.org/files/84/84-0.txt"


@responses.activate
def test_get_metadata_invalid_id_raises():
    """get_metadata with invalid id raises GutenbergError."""
    with pytest.raises(GutenbergError, match="positive integer"):
        gutenberg.get_metadata(0)


@responses.activate
def test_get_metadata_negative_id_raises():
    """get_metadata with negative id raises GutenbergError."""
    with pytest.raises(GutenbergError, match="positive integer"):
        gutenberg.get_metadata(-1)


@responses.activate
def test_get_metadata_boolean_id_raises():
    """get_metadata with boolean id raises GutenbergError."""
    with pytest.raises(GutenbergError, match="positive integer"):
        gutenberg.get_metadata(True)


@responses.activate
def test_get_metadata_http_500_raises():
    """HTTP 500 on get_metadata raises GutenbergError."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/1/",
        status=500,
    )
    with pytest.raises(GutenbergError, match="HTTP 500"):
        gutenberg.get_metadata(1)


@responses.activate
def test_download_text_success():
    """download_text returns UTF-8 decoded text."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/84/",
        json={
            "id": 84,
            "title": "Frankenstein",
            "authors": [],
            "languages": ["en"],
            "download_count": 0,
            "formats": {
                "text/plain; charset=utf-8": "https://www.gutenberg.org/files/84/84-0.txt",
            },
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.gutenberg.org/files/84/84-0.txt",
        body="*** START OF THE PROJECT GUTENBERG EBOOK FRANKENSTEIN ***\n\nChapter 1\n\nSome text here.",
        status=200,
    )
    text = gutenberg.download_text(84)
    assert "*** START OF THE PROJECT GUTENBERG EBOOK FRANKENSTEIN ***" in text
    assert "Chapter 1" in text


@responses.activate
def test_download_text_no_text_url_raises():
    """download_text raises GutenbergError when book has no text_url."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/1/",
        json={
            "id": 1,
            "title": "No Text Book",
            "authors": [],
            "languages": ["en"],
            "download_count": 0,
            "formats": {},
        },
        status=200,
    )
    with pytest.raises(GutenbergError, match="no plain-text download"):
        gutenberg.download_text(1)


@responses.activate
def test_download_text_http_404_raises():
    """HTTP 404 on text download raises GutenbergError."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/84/",
        json={
            "id": 84,
            "title": "Frankenstein",
            "authors": [],
            "languages": ["en"],
            "download_count": 0,
            "formats": {
                "text/plain; charset=utf-8": "https://www.gutenberg.org/files/84/84-0.txt",
            },
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.gutenberg.org/files/84/84-0.txt",
        status=404,
    )
    # After the listed URL fails, download_text also tries the direct cache URL.
    responses.add(
        responses.GET,
        "https://www.gutenberg.org/cache/epub/84/pg84.txt",
        status=404,
    )
    with pytest.raises(GutenbergError, match="no plain-text download"):
        gutenberg.download_text(84)
    assert [call.request.url for call in responses.calls] == [
        "https://gutendex.com/books/84/",
        "https://www.gutenberg.org/files/84/84-0.txt",
        "https://www.gutenberg.org/cache/epub/84/pg84.txt",
    ]


@responses.activate
def test_search_skips_results_with_invalid_metadata():
    """Search skips results that cannot be parsed and continues."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 3,
            "results": [
                {
                    "id": 1,
                    "title": "Valid Book",
                    "authors": [{"name": "Author One"}],
                    "languages": ["en"],
                    "download_count": 100,
                    "formats": {"text/plain": "https://example.com/1.txt"},
                },
                {"id": "invalid"},  # Will be skipped
                {
                    "id": 2,
                    "title": "Another Valid Book",
                    "authors": [{"name": "Author Two"}],
                    "languages": ["en"],
                    "download_count": 200,
                    "formats": {"text/plain": "https://example.com/2.txt"},
                },
            ],
        },
        status=200,
    )
    results = gutenberg.search("test")
    assert len(results) == 2
    assert results[0].gutenberg_id == 1
    assert results[1].gutenberg_id == 2


@responses.activate
def test_search_bad_json_raises():
    """Search with invalid JSON response raises GutenbergError."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        body="not valid json",
        status=200,
    )
    with pytest.raises(GutenbergError, match="invalid JSON"):
        gutenberg.search("test")


@responses.activate
def test_search_non_dict_json_raises():
    """Search with non-dict JSON response raises GutenbergError."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json=["not", "a", "dict"],
        status=200,
    )
    with pytest.raises(GutenbergError, match="invalid metadata"):
        gutenberg.search("test")


@responses.activate
def test_get_metadata_bad_json_raises():
    """get_metadata with invalid JSON response raises GutenbergError."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/1/",
        body="not valid json",
        status=200,
    )
    with pytest.raises(GutenbergError, match="invalid JSON"):
        gutenberg.get_metadata(1)


@responses.activate
def test_text_url_with_mixed_case_mime():
    """text_url handles mixed-case MIME types."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 1,
            "results": [
                {
                    "id": 1,
                    "title": "Test",
                    "authors": [],
                    "languages": ["en"],
                    "download_count": 0,
                    "formats": {
                        "TEXT/PLAIN; CHARSET=UTF-8": "https://example.com/book.txt",
                    },
                }
            ],
        },
        status=200,
    )
    results = gutenberg.search("test")
    assert results[0].text_url == "https://example.com/book.txt"


@responses.activate
def test_text_url_skips_non_string_mime():
    """text_url skips non-string MIME type keys."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 1,
            "results": [
                {
                    "id": 1,
                    "title": "Test",
                    "authors": [],
                    "languages": ["en"],
                    "download_count": 0,
                    "formats": {
                        123: "https://example.com/book.txt",
                        "text/plain": "https://example.com/valid.txt",
                    },
                }
            ],
        },
        status=200,
    )
    results = gutenberg.search("test")
    assert results[0].text_url == "https://example.com/valid.txt"


@responses.activate
def test_text_url_skips_non_string_url():
    """text_url skips non-string URL values."""
    responses.add(
        responses.GET,
        "https://gutendex.com/books/",
        json={
            "count": 1,
            "results": [
                {
                    "id": 1,
                    "title": "Test",
                    "authors": [],
                    "languages": ["en"],
                    "download_count": 0,
                    "formats": {
                        "text/plain": 123,
                    },
                }
            ],
        },
        status=200,
    )
    results = gutenberg.search("test")
    assert results[0].text_url is None
