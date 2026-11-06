"""Gutenberg fallback tests (catalog CSV + direct download); all HTTP is mocked."""

import csv
import io
import os
import time
from pathlib import Path

import pytest
import requests
import responses

from core import config as config_module
from core import gutenberg
from core.config import get_config

GUTENDEX = "https://gutendex.com/books/"
CATALOG = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"
HEADER = ["Text#", "Type", "Issued", "Title", "Language", "Authors",
          "Subjects", "LoCC", "Bookshelves"]


def direct(book_id: int) -> str:
    return f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"


def catalog_csv(rows: list[tuple]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(HEADER)
    for book_id, kind, title, language, authors in rows:
        writer.writerow([book_id, kind, "2001-01-01", title, language, authors, "", "", ""])
    return out.getvalue()


ROWS = [
    (2554, "Text", "Crime and Punishment", "en",
     "Dostoyevsky, Fyodor, 1821-1881; Garnett, Constance, 1861-1946 [Translator]"),
    (28054, "Text", "The Brothers Karamazov", "en", "Dostoyevsky, Fyodor, 1821-1881"),
    (100, "Text", "Crime:\nA Study in Punishment", "en", "Doe, Jane"),
    (9999, "Sound", "Crime and Punishment", "en", "Dostoyevsky, Fyodor, 1821-1881"),
    (5000, "Text", "Crime et châtiment", "fr", "Dostoyevsky, Fyodor, 1821-1881"),
    (135, "Text", "Les Misérables", "en; fr", "Hugo, Victor, 1802-1885"),
    ("not-a-number", "Text", "Broken row", "en", ""),
]
CSV = catalog_csv(ROWS)


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module, "_ROOT_DIR", tmp_path)
    for name in ("TINBOOK_LIBRARY_DIR", "TINBOOK_VOICES_DIR",
                 "TINBOOK_DEFAULT_VOICE", "TINBOOK_PORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TINBOOK_LIBRARY_DIR", str(tmp_path / "library"))
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    monkeypatch.setattr(gutenberg, "_gutendex_skip_until", 0.0)
    monkeypatch.setattr(gutenberg, "_catalog_retry_at", 0.0)
    monkeypatch.setattr(gutenberg, "_catalog_cache", None)


@pytest.fixture
def http():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def catalog_path() -> Path:
    return get_config().library_dir / "pg_catalog.csv"


def calls_to(http, url: str) -> list:
    return [call for call in http.calls if call.request.url.split("?")[0] == url]


def gutendex_down(http, error=None, status=None) -> None:
    pattern = responses.matchers.query_param_matcher({}, strict_match=False)
    if error is not None:
        http.get(GUTENDEX, body=error, match=[pattern])
        http.get(f"{GUTENDEX}2554/", body=error)
    else:
        http.get(GUTENDEX, status=status, match=[pattern])
        http.get(f"{GUTENDEX}2554/", status=status)


def write_cache(text: str, age_days: float) -> None:
    path = catalog_path()
    path.write_bytes(text.encode())
    stamp = time.time() - age_days * 24 * 60 * 60
    os.utime(path, (stamp, stamp))


# --- search -----------------------------------------------------------------


@pytest.mark.parametrize("failure", [
    {"error": requests.Timeout("slow")},
    {"error": requests.ConnectionError("offline")},
    {"status": 503},
    {"status": 500},
])
def test_search_falls_back_to_catalog_when_gutendex_fails(http, failure) -> None:
    gutendex_down(http, **failure)
    http.get(CATALOG, body=CSV)
    results = gutenberg.search("crime and punishment")
    assert [result.gutenberg_id for result in results] == [2554, 9999]  # all words must match
    first = results[0]
    assert first.title == "Crime and Punishment"
    assert first.authors == ["Dostoyevsky, Fyodor"]  # dates and translator dropped
    assert first.language == "en"
    assert first.download_count == 0
    assert first.text_url == direct(2554)
    assert results[1].text_url is None  # audio book: shown, but disabled
    assert catalog_path().read_bytes() == CSV.encode()
    assert calls_to(http, CATALOG)[0].request.headers["User-Agent"] == get_config().user_agent


def test_search_falls_back_on_invalid_gutendex_response(http) -> None:
    http.get(GUTENDEX, json={"results": None})
    http.get(CATALOG, body=CSV)
    assert [result.gutenberg_id for result in gutenberg.search("karamazov")] == [28054]


def test_catalog_search_is_english_only(http) -> None:
    gutendex_down(http, status=503)
    http.get(CATALOG, body=CSV)
    ids = [result.gutenberg_id for result in gutenberg.search("crime")]
    assert 5000 not in ids
    assert ids == [100, 2554, 9999]  # "crime" phrase at title start, text before audio
    titles = {result.gutenberg_id: result.title for result in gutenberg.search("crime")}
    assert titles[100] == "Crime: A Study in Punishment"  # newlines collapsed


def test_catalog_search_matches_authors_and_ignores_accents(http) -> None:
    gutendex_down(http, status=503)
    http.get(CATALOG, body=CSV)
    assert [r.gutenberg_id for r in gutenberg.search("DOSTOYEVSKY")] == [2554, 28054, 9999]
    assert [r.gutenberg_id for r in gutenberg.search("fyodor karamazov")] == [28054]
    miserables = gutenberg.search("miserables hugo")
    assert [r.gutenberg_id for r in miserables] == [135]
    assert miserables[0].language == "en"
    assert gutenberg.search("no such book anywhere") == []


def test_catalog_search_paginates_32_per_page(http) -> None:
    rows = [(n, "Text", f"Sea Story {n}", "en", "Writer, A") for n in range(1, 41)]
    gutendex_down(http, status=503)
    http.get(CATALOG, body=catalog_csv(rows))
    assert [r.gutenberg_id for r in gutenberg.search("sea", page=1)] == list(range(1, 33))
    assert [r.gutenberg_id for r in gutenberg.search("sea", page=2)] == list(range(33, 41))
    assert gutenberg.search("sea", page=3) == []


def test_gutendex_skipped_briefly_after_outage_then_retried(http, monkeypatch) -> None:
    gutendex_down(http, error=requests.Timeout("slow"))
    http.get(CATALOG, body=CSV)
    gutenberg.search("crime")
    gutenberg.search("karamazov")
    assert len(calls_to(http, GUTENDEX)) == 1  # second search went straight to the catalog
    assert len(calls_to(http, CATALOG)) == 1  # catalog downloaded once, then reused
    monkeypatch.setattr(gutenberg, "_gutendex_skip_until", 0.0)  # the 60 s pause is over
    gutenberg.search("crime")
    assert len(calls_to(http, GUTENDEX)) == 2


def test_gutendex_404_does_not_pause_gutendex(http) -> None:
    gutendex_down(http, status=404)
    http.get(CATALOG, body=CSV)
    gutenberg.search("crime")
    gutenberg.search("crime")
    assert len(calls_to(http, GUTENDEX)) == 2


def test_gutendex_404_past_last_page_ends_results_without_catalog(http) -> None:
    gutendex_down(http, status=404)  # Gutendex answers 404 for a page past the end
    assert gutenberg.search("crime", page=2) == []
    assert gutenberg.search("crime", page=7) == []
    assert calls_to(http, CATALOG) == []  # no catalog results mixed into later pages
    assert len(calls_to(http, GUTENDEX)) == 2


def test_gutendex_404_on_first_page_still_uses_catalog(http) -> None:
    gutendex_down(http, status=404)
    http.get(CATALOG, body=CSV)
    assert [r.gutenberg_id for r in gutenberg.search("karamazov", page=1)] == [28054]


@pytest.mark.parametrize("failure", [{"status": 503}, {"error": requests.Timeout("slow")}])
def test_later_page_still_falls_back_when_gutendex_is_down(http, failure) -> None:
    gutendex_down(http, **failure)
    http.get(CATALOG, body=catalog_csv(
        [(n, "Text", f"Sea Story {n}", "en", "Writer, A") for n in range(1, 41)]))
    assert [r.gutenberg_id for r in gutenberg.search("sea", page=2)] == list(range(33, 41))


def test_gutendex_request_uses_8_second_timeout(http) -> None:
    gutendex_down(http, error=requests.Timeout("slow"))
    http.get(CATALOG, body=CSV)
    gutenberg.search("crime")
    assert calls_to(http, GUTENDEX)[0].request.req_kwargs["timeout"] == 8
    assert calls_to(http, CATALOG)[0].request.req_kwargs["timeout"] == get_config().http_timeout


# --- catalog cache ------------------------------------------------------------


def test_fresh_cached_catalog_is_used_without_download(http) -> None:
    write_cache(CSV, age_days=6)
    gutendex_down(http, status=503)
    assert [r.gutenberg_id for r in gutenberg.search("karamazov")] == [28054]
    assert calls_to(http, CATALOG) == []


def test_catalog_older_than_7_days_is_refreshed(http) -> None:
    write_cache(catalog_csv(ROWS[:1]), age_days=8)
    gutendex_down(http, status=503)
    http.get(CATALOG, body=CSV)
    assert [r.gutenberg_id for r in gutenberg.search("karamazov")] == [28054]
    assert len(calls_to(http, CATALOG)) == 1
    assert catalog_path().read_bytes() == CSV.encode()
    assert not catalog_path().with_name("pg_catalog.csv.tmp").exists()


def test_old_catalog_used_if_refresh_fails_and_refresh_not_retried_every_search(
    http, caplog
) -> None:
    write_cache(CSV, age_days=30)
    gutendex_down(http, status=503)
    http.get(CATALOG, status=503)
    assert [r.gutenberg_id for r in gutenberg.search("karamazov")] == [28054]
    assert "using the old copy" in caplog.text
    assert [r.gutenberg_id for r in gutenberg.search("karamazov")] == [28054]
    assert len(calls_to(http, CATALOG)) == 1


def test_bad_catalog_download_does_not_replace_old_copy(http) -> None:
    old = catalog_csv(ROWS[:2])
    write_cache(old, age_days=30)
    gutendex_down(http, status=503)
    http.get(CATALOG, body="<html>maintenance</html>")
    assert [r.gutenberg_id for r in gutenberg.search("karamazov")] == [28054]
    assert catalog_path().read_bytes() == old.encode()
    assert not catalog_path().with_name("pg_catalog.csv.tmp").exists()


def test_catalog_download_cut_off_mid_stream_is_gutenberg_error(http) -> None:
    gutendex_down(http, status=503)
    http.get(CATALOG, body=requests.exceptions.ChunkedEncodingError("cut off"))
    with pytest.raises(gutenberg.GutenbergError):
        gutenberg.search("crime")
    assert not catalog_path().exists()


@pytest.mark.parametrize("failure, message", [
    ({"error": requests.Timeout("slow")}, "timed out"),
    ({"status": 503}, "HTTP 503"),
])
def test_search_error_when_gutendex_and_catalog_both_fail(http, failure, message) -> None:
    gutendex_down(http, **failure)
    http.get(CATALOG, status=503)
    with pytest.raises(gutenberg.GutenbergError, match=message) as error:
        gutenberg.search("crime")
    assert "backup catalog also failed" in str(error.value)
    assert not catalog_path().exists()


def test_offline_error_message_does_not_repeat_itself(http) -> None:
    """CP3: when both requests fail identically, say it once."""
    gutendex_down(http, error=requests.ConnectionError("offline"))
    http.get(CATALOG, body=requests.ConnectionError("offline"))
    with pytest.raises(gutenberg.GutenbergError) as error:
        gutenberg.search("crime")
    assert str(error.value) == (
        "Could not reach Gutenberg. Check your connection and try again. "
        "(The backup catalog also failed the same way.)"
    )


# --- get_metadata -------------------------------------------------------------


@pytest.mark.parametrize("failure", [
    {"error": requests.Timeout("slow")}, {"status": 503}, {"status": 404},
])
def test_get_metadata_falls_back_to_catalog(http, failure) -> None:
    gutendex_down(http, **failure)
    http.get(CATALOG, body=CSV)
    result = gutenberg.get_metadata(2554)
    assert result.gutenberg_id == 2554
    assert result.title == "Crime and Punishment"
    assert result.authors == ["Dostoyevsky, Fyodor"]
    assert result.text_url == direct(2554)


def test_get_metadata_catalog_keeps_non_english_and_audio_books(http) -> None:
    http.get(f"{GUTENDEX}5000/", status=503)
    http.get(CATALOG, body=CSV)
    assert gutenberg.get_metadata(5000).language == "fr"
    http.get(f"{GUTENDEX}9999/", status=503)
    assert gutenberg.get_metadata(9999).text_url is None


def test_get_metadata_unknown_id_in_catalog(http) -> None:
    http.get(f"{GUTENDEX}424242/", status=503)
    http.get(CATALOG, body=CSV)
    with pytest.raises(gutenberg.GutenbergError, match="424242 was not found"):
        gutenberg.get_metadata(424242)


def test_get_metadata_error_when_catalog_also_fails(http) -> None:
    gutendex_down(http, error=requests.Timeout("slow"))
    http.get(CATALOG, body=requests.ConnectionError("offline"))
    with pytest.raises(gutenberg.GutenbergError, match="backup catalog also failed"):
        gutenberg.get_metadata(2554)


# --- download_text ------------------------------------------------------------


@pytest.mark.parametrize("failure", [
    {"error": requests.Timeout("slow")}, {"status": 503}, {"status": 404},
])
def test_download_falls_back_to_direct_gutenberg_url(http, failure) -> None:
    gutendex_down(http, **failure)
    http.get(direct(2554), body=b"*** START OF caf\xc3\xa9 \xff")
    assert gutenberg.download_text(2554) == "*** START OF café �"
    call = calls_to(http, direct(2554))[0]
    assert call.request.headers["User-Agent"] == get_config().user_agent
    assert call.request.req_kwargs["timeout"] == get_config().http_timeout
    assert calls_to(http, CATALOG) == []  # direct download needs no catalog


def test_download_tries_direct_url_if_gutendex_text_url_fails(http) -> None:
    http.get(f"{GUTENDEX}2554/", json={
        "id": 2554, "title": "Crime and Punishment", "authors": [], "languages": ["en"],
        "formats": {"text/plain; charset=utf-8": "https://example.com/book.txt"},
    })
    http.get("https://example.com/book.txt", status=500)
    http.get(direct(2554), body="*** START OF direct")
    assert gutenberg.download_text(2554) == "*** START OF direct"


def test_download_direct_404_means_no_plain_text(http) -> None:
    gutendex_down(http, status=503)
    http.get(direct(2554), status=404)
    with pytest.raises(gutenberg.GutenbergError, match="no plain-text"):
        gutenberg.download_text(2554)


def test_download_error_when_direct_url_also_fails(http) -> None:
    gutendex_down(http, error=requests.Timeout("slow"))
    http.get(direct(2554), body=requests.ConnectionError("offline"))
    with pytest.raises(gutenberg.GutenbergError, match="Could not reach"):
        gutenberg.download_text(2554)


@pytest.mark.parametrize("bad_id", [0, -5, True, "2554"])
def test_download_rejects_bad_id_without_http(http, bad_id) -> None:
    with pytest.raises(gutenberg.GutenbergError, match="positive integer"):
        gutenberg.download_text(bad_id)
    assert len(http.calls) == 0
