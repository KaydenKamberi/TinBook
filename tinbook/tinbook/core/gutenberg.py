"""Project Gutenberg client owned by CP1B."""

from .models import SearchResult


class GutenbergError(Exception):
    """Expected Gutenberg API or download failure."""


def search(query: str, page: int = 1) -> list[SearchResult]:
    """Search Project Gutenberg. Implemented by CP1B."""
    raise NotImplementedError


def get_metadata(gutenberg_id: int) -> SearchResult:
    """Fetch metadata for one book. Implemented by CP1B."""
    raise NotImplementedError


def download_text(gutenberg_id: int) -> str:
    """Download raw UTF-8 book text. Implemented by CP1B."""
    raise NotImplementedError