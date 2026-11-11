"""Record which Gutenberg source served each request, for the CI log.

``install()`` wraps ``core.gutenberg._request`` (the single place that module makes
HTTP requests) without changing its behavior, so CI can say whether Gutendex or the
fallback (Project Gutenberg catalog / direct text URL) was used.
"""

from __future__ import annotations

from dataclasses import dataclass

from core import gutenberg

CATALOG_URL = gutenberg._CATALOG_URL


@dataclass
class Request:
    url: str
    ok: bool
    detail: str


log: list[Request] = []
_installed = False


def install() -> None:
    """Start recording every request made by core.gutenberg (idempotent)."""
    global _installed
    if _installed:
        return
    original = gutenberg._request

    def recording_request(url, params=None, **kwargs):
        try:
            response = original(url, params, **kwargs)
        except Exception as error:
            log.append(Request(url, False, f"{type(error).__name__}: {error}"))
            raise
        log.append(Request(url, True, f"HTTP {response.status_code}"))
        return response

    gutenberg._request = recording_request
    _installed = True


def mark() -> int:
    """Position in the log, to describe only the requests made after it."""
    return len(log)


def describe(start: int, gutenberg_id: int) -> list[str]:
    """Human-readable lines: which source gave the metadata and which gave the text."""
    requests = log[start:]
    direct = gutenberg._DIRECT_TEXT_URL.format(id=gutenberg_id)
    gutendex = [r for r in requests if "gutendex" in r.url]
    catalog = [r for r in requests if r.url == CATALOG_URL]
    texts = [r for r in requests if r not in gutendex and r not in catalog]

    lines = []
    for r in requests:
        lines.append(f"  request: {'OK  ' if r.ok else 'FAIL'} {r.url}  ({r.detail})")

    if any(r.ok for r in gutendex):
        meta = "Gutendex (primary)"
    elif catalog and catalog[-1].ok:
        meta = "FALLBACK: Project Gutenberg catalog (downloaded pg_catalog.csv)"
    elif gutendex or catalog:
        meta = "FALLBACK: Project Gutenberg catalog (cached pg_catalog.csv)"
    else:
        meta = "Project Gutenberg catalog (Gutendex skipped after an earlier failure)"
    ok_text = [r for r in texts if r.ok]
    if not ok_text:
        text = "none (download failed)"
    elif ok_text[-1].url == direct:
        text = f"FALLBACK: direct gutenberg.org URL {direct}"
    else:
        text = f"Gutendex text_url {ok_text[-1].url} (primary)"
    lines.append(f"Source:     metadata from {meta}")
    lines.append(f"Source:     text from {text}")
    return lines


def gutendex_was_up() -> bool | None:
    """True if any Gutendex request succeeded, False if all failed, None if none were made."""
    gutendex = [r for r in log if "gutendex" in r.url]
    if not gutendex:
        return None
    return any(r.ok for r in gutendex)
