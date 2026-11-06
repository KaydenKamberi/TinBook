"""Search and download Project Gutenberg books.

Gutendex is tried first. If it fails or times out, metadata and search fall back
to Project Gutenberg's official catalog CSV (cached in the library folder), and
text downloads go straight to gutenberg.org.
"""

import csv
import logging
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar
from urllib.parse import urlparse

import requests

from .config import get_config
from .models import SearchResult

log = logging.getLogger(__name__)
_BASE_URL = "https://gutendex.com/books/"
_GUTENDEX_TIMEOUT = 8  # seconds; short so the fallback kicks in quickly
_GUTENDEX_RETRY_AFTER = 60  # seconds to skip Gutendex after it was unreachable
_CATALOG_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"
_CATALOG_FILE = "pg_catalog.csv"
_CATALOG_MAX_AGE = 7 * 24 * 60 * 60  # seconds
_CATALOG_RETRY_AFTER = 10 * 60  # seconds before retrying a failed refresh of an old copy
_CATALOG_COLUMNS = {"Text#", "Type", "Title", "Language", "Authors"}
_DIRECT_TEXT_URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"
_PAGE_SIZE = 32  # same page size as Gutendex

T = TypeVar("T")


class GutenbergError(Exception):
    """Expected Gutenberg API or download failure."""


class _Unavailable(GutenbergError):
    """The server timed out, was unreachable, or returned a 5xx error."""


class _NotFound(GutenbergError):
    """The server returned HTTP 404."""


@dataclass(frozen=True)
class _Entry:
    result: SearchResult
    title_key: str  # normalized title, for ranking
    haystack: str  # normalized title + authors, for matching


@dataclass(frozen=True)
class _Catalog:
    by_id: dict[int, SearchResult]
    english: list[_Entry]  # in catalog order


_catalog_lock = threading.Lock()
_catalog_cache: tuple[tuple, _Catalog] | None = None  # (file stat key, parsed catalog)
_gutendex_skip_until = 0.0  # time.monotonic() value
_catalog_retry_at = 0.0  # time.monotonic() value


def search(query: str, page: int = 1) -> list[SearchResult]:
    """Search English books, retaining results without plain-text downloads."""
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise GutenbergError("Search page must be a positive integer.")
    try:
        data = _gutendex_json(_BASE_URL, {"search": query, "languages": "en", "page": page})
        if not isinstance(data.get("results"), list):
            raise GutenbergError("Gutenberg returned invalid search results. Please try again.")
    except GutenbergError as error:
        log.warning("Gutendex search failed (%s); searching the Gutenberg catalog.", error)
        return _with_fallback(error, lambda: _catalog_search(_catalog(), query, page))
    results = []
    for position, item in enumerate(data["results"], start=1):
        try:
            results.append(_parse_metadata(item))
        except GutenbergError as error:
            log.warning("Skipping invalid Gutenberg search result %s: %s", position, error)
    return results


def get_metadata(gutenberg_id: int) -> SearchResult:
    """Fetch metadata for one Gutenberg book."""
    _check_id(gutenberg_id)
    try:
        return _gutendex_metadata(gutenberg_id)
    except GutenbergError as error:
        log.warning(
            "Gutendex metadata for book %s failed (%s); using the Gutenberg catalog.",
            gutenberg_id, error,
        )
        catalog = _with_fallback(error, _catalog)
    result = catalog.by_id.get(gutenberg_id)
    if result is None:
        raise GutenbergError(f"Gutenberg book {gutenberg_id} was not found.")
    return result


def download_text(gutenberg_id: int) -> str:
    """Download raw book text, replacing invalid UTF-8 sequences."""
    _check_id(gutenberg_id)
    direct_url = _DIRECT_TEXT_URL.format(id=gutenberg_id)
    try:
        metadata = _gutendex_metadata(gutenberg_id)
    except GutenbergError as error:
        log.warning(
            "Gutendex metadata for book %s failed (%s); downloading from gutenberg.org.",
            gutenberg_id, error,
        )
        return _download_text(direct_url, gutenberg_id)
    if metadata.text_url is None:
        raise GutenbergError(f"Book {gutenberg_id} has no plain-text download available.")
    try:
        return _download_text(metadata.text_url, gutenberg_id)
    except GutenbergError as error:
        if metadata.text_url == direct_url:
            raise
        log.warning("Download from %s failed (%s); trying %s.", metadata.text_url, error, direct_url)
        return _download_text(direct_url, gutenberg_id)


def _check_id(gutenberg_id: int) -> None:
    if (
        not isinstance(gutenberg_id, int)
        or isinstance(gutenberg_id, bool)
        or gutenberg_id <= 0
    ):
        raise GutenbergError("Gutenberg book ID must be a positive integer.")


def _with_fallback(primary_error: GutenbergError, action: Callable[[], T]) -> T:
    try:
        return action()
    except GutenbergError as error:
        raise GutenbergError(f"{primary_error} The backup catalog also failed: {error}") from error


def _download_text(url: str, gutenberg_id: int) -> str:
    try:
        response = _request(url, timeout=get_config().http_timeout)
    except _NotFound as error:
        raise GutenbergError(
            f"Book {gutenberg_id} has no plain-text download available."
        ) from error
    return response.content.decode("utf-8", errors="replace")


# --- HTTP -----------------------------------------------------------------


def _request(
    url: str, params: dict | None = None, *, timeout: float, stream: bool = False
) -> requests.Response:
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": get_config().user_agent},
            timeout=timeout,
            stream=stream,
        )
    except requests.Timeout as error:
        raise _Unavailable("The Gutenberg request timed out. Please try again.") from error
    except requests.RequestException as error:
        raise _Unavailable(
            "Could not reach Gutenberg. Check your connection and try again."
        ) from error
    if response.status_code != 200:
        response.close()
        error_class = (
            _Unavailable if response.status_code >= 500
            else _NotFound if response.status_code == 404
            else GutenbergError
        )
        raise error_class(
            f"Gutenberg returned HTTP {response.status_code}. Please try again later."
        )
    return response


def _gutendex_json(url: str, params: dict | None = None) -> dict:
    """GET Gutendex JSON; after an outage, skip Gutendex for a short while."""
    global _gutendex_skip_until
    if time.monotonic() < _gutendex_skip_until:
        raise GutenbergError("Gutendex is not responding right now.")
    timeout = min(_GUTENDEX_TIMEOUT, get_config().http_timeout)
    try:
        response = _request(url, params, timeout=timeout)
    except _Unavailable:
        _gutendex_skip_until = time.monotonic() + _GUTENDEX_RETRY_AFTER
        raise
    try:
        data = response.json()
    except ValueError as error:
        raise GutenbergError("Gutenberg returned invalid JSON. Please try again.") from error
    if not isinstance(data, dict):
        raise GutenbergError("Gutenberg returned invalid metadata. Please try again.")
    return data


def _gutendex_metadata(gutenberg_id: int) -> SearchResult:
    return _parse_metadata(_gutendex_json(f"{_BASE_URL}{gutenberg_id}/"))


# --- Gutendex parsing -------------------------------------------------------


def _text_url(formats: dict) -> str | None:
    candidates = [
        (mime.lower(), url)
        for mime, url in formats.items()
        if isinstance(mime, str)
        and isinstance(url, str)
        and mime.lower().startswith("text/plain")
        and not urlparse(url).path.lower().endswith(".zip")
    ]
    for prefix in (
        "text/plain; charset=utf-8",
        "text/plain; charset=us-ascii",
        "text/plain",
    ):
        for mime, url in candidates:
            if mime.startswith(prefix):
                return url
    return None


def _parse_metadata(data: dict) -> SearchResult:
    try:
        if not isinstance(data, dict):
            raise ValueError("Metadata is not an object")
        formats = data.get("formats", {})
        authors = data.get("authors", [])
        languages = data.get("languages", [])
        if (
            not isinstance(formats, dict)
            or not isinstance(authors, list)
            or not isinstance(languages, list)
            or not all(isinstance(language, str) for language in languages)
        ):
            raise ValueError("Invalid metadata fields")
        title = data["title"]
        author_names = [author["name"] for author in authors]
        if not isinstance(title, str) or not all(
            isinstance(name, str) for name in author_names
        ):
            raise ValueError("Invalid title or authors")
        return SearchResult(
            gutenberg_id=int(data["id"]),
            title=title,
            authors=author_names,
            language="en" if "en" in languages else (languages[0] if languages else ""),
            download_count=int(data.get("download_count", 0)),
            text_url=_text_url(formats),
        )
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        log.warning("Unreadable Gutenberg metadata: %s", error)
        raise GutenbergError("Gutenberg returned invalid book metadata. Please try again.") from error


# --- Catalog fallback -------------------------------------------------------


def _catalog() -> _Catalog:
    """Return the parsed catalog, downloading it if missing or older than 7 days."""
    global _catalog_cache, _catalog_retry_at
    path = get_config().library_dir / _CATALOG_FILE
    with _catalog_lock:
        have_copy = path.is_file()
        if not _is_fresh(path) and (not have_copy or time.monotonic() >= _catalog_retry_at):
            try:
                catalog = _download_catalog(path)
                _catalog_cache = (_stat_key(path), catalog)
                return catalog
            except GutenbergError as error:
                if not have_copy:
                    raise
                _catalog_retry_at = time.monotonic() + _CATALOG_RETRY_AFTER
                log.warning("Could not refresh the Gutenberg catalog (%s); using the old copy.", error)
        key = _stat_key(path)
        if _catalog_cache is None or _catalog_cache[0] != key:
            _catalog_cache = (key, _parse_catalog(path))
        return _catalog_cache[1]


def _is_fresh(path: Path) -> bool:
    try:
        return time.time() - path.stat().st_mtime < _CATALOG_MAX_AGE
    except OSError:
        return False


def _stat_key(path: Path) -> tuple:
    try:
        stat = path.stat()
    except OSError as error:
        raise GutenbergError(f"Could not read the Gutenberg catalog: {error}") from error
    return (str(path), stat.st_mtime_ns, stat.st_size)


def _download_catalog(path: Path) -> _Catalog:
    """Download to a .tmp file, check it parses, then atomically replace the cache."""
    log.info("Downloading the Gutenberg catalog from %s", _CATALOG_URL)
    tmp = path.with_name(path.name + ".tmp")
    response = _request(_CATALOG_URL, timeout=get_config().http_timeout, stream=True)
    try:
        with tmp.open("wb") as out:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                out.write(chunk)
        catalog = _parse_catalog(tmp)
        os.replace(tmp, path)
        return catalog
    except requests.RequestException as error:
        raise GutenbergError(
            "Downloading the Gutenberg catalog failed. Please try again."
        ) from error
    except OSError as error:
        raise GutenbergError(f"Could not save the Gutenberg catalog: {error}") from error
    finally:
        response.close()
        tmp.unlink(missing_ok=True)


def _parse_catalog(path: Path) -> _Catalog:
    by_id: dict[int, SearchResult] = {}
    english: list[_Entry] = []
    try:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as source:
            reader = csv.DictReader(source)
            if not _CATALOG_COLUMNS <= set(reader.fieldnames or []):
                raise GutenbergError("The Gutenberg catalog has an unexpected format.")
            for row in reader:
                try:
                    gutenberg_id = int(row["Text#"])
                except (TypeError, ValueError):
                    continue
                languages = [
                    part.strip() for part in (row["Language"] or "").split(";") if part.strip()
                ]
                title = " ".join((row["Title"] or "").split())
                authors = _catalog_authors(row["Authors"] or "")
                result = SearchResult(
                    gutenberg_id=gutenberg_id,
                    title=title,
                    authors=authors,
                    language="en" if "en" in languages else (languages[0] if languages else ""),
                    download_count=0,  # the catalog has no download counts
                    text_url=(
                        _DIRECT_TEXT_URL.format(id=gutenberg_id)
                        if (row["Type"] or "").strip() == "Text"
                        else None
                    ),
                )
                by_id[gutenberg_id] = result
                if "en" in languages:
                    english.append(_Entry(
                        result=result,
                        title_key=" ".join(_words(title)),
                        haystack=" ".join(_words(" ".join([title, *authors]))),
                    ))
    except (OSError, csv.Error) as error:
        raise GutenbergError(f"Could not read the Gutenberg catalog: {error}") from error
    if not by_id:
        raise GutenbergError("The Gutenberg catalog is empty.")
    return _Catalog(by_id=by_id, english=english)


def _catalog_authors(field: str) -> list[str]:
    """'Dostoyevsky, Fyodor, 1821-1881; Garnett, Constance [Translator]' -> authors only."""
    names = []
    for part in field.split(";"):
        part = part.strip()
        if not part or "[" in part:  # bracketed roles: translators, editors, ...
            continue
        names.append(re.sub(r",\s*[^,]*\d[^,]*$", "", part).strip())  # drop life dates
    return names


def _words(text: str) -> list[str]:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", ascii_text)


def _catalog_search(catalog: _Catalog, query: str, page: int) -> list[SearchResult]:
    """Match every query word against title + authors; best title matches first."""
    words = _words(query)
    phrase = " ".join(words)
    matches = []
    for entry in catalog.english:
        if not all(word in entry.haystack for word in words):
            continue
        title = entry.title_key
        if title == phrase:
            rank = 0
        elif title.startswith(phrase):
            rank = 1
        elif phrase in title:
            rank = 2
        elif all(word in title for word in words):
            rank = 3
        else:
            rank = 4  # matched through the author
        no_text = entry.result.text_url is None
        matches.append((rank, no_text, entry.result.gutenberg_id, entry.result))
    matches.sort(key=lambda match: match[:3])
    start = (page - 1) * _PAGE_SIZE
    return [match[3] for match in matches[start:start + _PAGE_SIZE]]
