"""Serializable data models shared by desktop and device code."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import Literal, TypeVar


ChapterStatus = Literal["pending", "done", "error"]
BookStatus = Literal["queued", "generating", "ready", "error"]

T = TypeVar("T")


def _known_fields(model: type[T], data: dict) -> dict:
    names = {field.name for field in fields(model)}
    return {key: value for key, value in data.items() if key in names}


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 timestamp ending in Z."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slugify(title: str) -> str:
    """Convert a title to a lowercase, URL-safe slug of at most 40 characters."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(slug) > 40:
        prefix = slug[:40]
        last_hyphen = prefix.rfind("-")
        slug = prefix[:last_hyphen] if last_hyphen > 0 else prefix
    return slug.rstrip("-")


@dataclass
class SearchResult:
    """A Gutenberg search result with an optional plain-text download."""

    gutenberg_id: int
    title: str
    authors: list[str]
    language: str
    download_count: int
    text_url: str | None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SearchResult:
        return cls(**_known_fields(cls, data))


@dataclass
class Chapter:
    """Metadata and generation state for one zero-based book chapter."""

    index: int
    title: str
    word_count: int
    status: ChapterStatus = "pending"
    duration_sec: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Chapter:
        return cls(**_known_fields(cls, data))


@dataclass
class Book:
    """A book and its chapters as stored in the Tinbook library."""

    id: str
    gutenberg_id: int
    title: str
    authors: list[str]
    voice: str
    audio_format: str
    status: BookStatus
    chapters: list[Chapter]
    added_at: str
    error: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Book:
        values = _known_fields(cls, data)
        values["chapters"] = [
            chapter if isinstance(chapter, Chapter) else Chapter.from_dict(chapter)
            for chapter in values["chapters"]
        ]
        return cls(**values)

    def chapters_done(self) -> int:
        """Return the number of chapters with completed audio."""
        return sum(chapter.status == "done" for chapter in self.chapters)

    def total_duration_sec(self) -> float:
        """Sum chapter durations that are known."""
        return sum(
            chapter.duration_sec
            for chapter in self.chapters
            if chapter.duration_sec is not None
        )


@dataclass
class Progress:
    """Playback position and speed for a book."""

    chapter_index: int = 0
    position_sec: float = 0.0
    speed: float = 1.0
    finished: bool = False
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Progress:
        return cls(**_known_fields(cls, data))