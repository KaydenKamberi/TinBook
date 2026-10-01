"""Search and download Project Gutenberg books through Gutendex."""

import logging
from urllib.parse import urlparse

import requests

from .config import get_config
from .models import SearchResult

log = logging.getLogger(__name__)
_BASE_URL = "https://gutendex.com/books/"


class GutenbergError(Exception):
    """Expected Gutenberg API or download failure."""


def search(query: str, page: int = 1) -> list[SearchResult]:
    """Search English books, retaining results without plain-text downloads."""
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise GutenbergError("Search page must be a positive integer.")
    data = _get_json(_BASE_URL, {"search": query, "languages": "en", "page": page})
    if not isinstance(data.get("results"), list):
        raise GutenbergError("Gutenberg returned invalid search results. Please try again.")
    return [_parse_metadata(item) for item in data["results"]]


def get_metadata(gutenberg_id: int) -> SearchResult:
    """Fetch metadata for one Gutenberg book."""
    if (
        not isinstance(gutenberg_id, int)
        or isinstance(gutenberg_id, bool)
        or gutenberg_id <= 0
    ):
        raise GutenbergError("Gutenberg book ID must be a positive integer.")
    return _parse_metadata(_get_json(f"{_BASE_URL}{gutenberg_id}/"))


def download_text(gutenberg_id: int) -> str:
    """Download raw book text, replacing invalid UTF-8 sequences."""
    metadata = get_metadata(gutenberg_id)
    if metadata.text_url is None:
        raise GutenbergError(f"Book {gutenberg_id} has no plain-text download available.")
    return _request(metadata.text_url).content.decode("utf-8", errors="replace")


def _request(url: str, params: dict | None = None) -> requests.Response:
    config = get_config()
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": config.user_agent},
            timeout=config.http_timeout,
        )
    except requests.Timeout as error:
        raise GutenbergError("The Gutenberg request timed out. Please try again.") from error
    except requests.RequestException as error:
        raise GutenbergError(
            "Could not reach Gutenberg. Check your connection and try again."
        ) from error
    if response.status_code != 200:
        raise GutenbergError(
            f"Gutenberg returned HTTP {response.status_code}. Please try again later."
        )
    return response


def _get_json(url: str, params: dict | None = None) -> dict:
    response = _request(url, params)
    try:
        data = response.json()
    except ValueError as error:
        raise GutenbergError("Gutenberg returned invalid JSON. Please try again.") from error
    if not isinstance(data, dict):
        raise GutenbergError("Gutenberg returned invalid metadata. Please try again.")
    return data


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
    except (KeyError, TypeError, ValueError) as error:
        log.warning("Unreadable Gutenberg metadata: %s", error)
        raise GutenbergError("Gutenberg returned invalid book metadata. Please try again.") from error