"""Tests for core/chapters.py (CP1C). These check the actual titles and text, not just counts."""

from pathlib import Path

import pytest

from core.chapters import _is_heading, split_chapters
from core.text_cleaner import clean

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LONG_TEXT = " ".join(["word"] * 100)  # 100 words: never "tiny"


def cleaned_text(*paras: str) -> str:
    return "\n\n".join(paras)


def titles(result):
    return [title for title, _ in result]


def assert_text_intact(result, source_paragraphs):
    """No mangling: every body is made of whole source paragraphs, nothing lost or duplicated."""
    for title, body in result:
        for paragraph in body.split("\n\n"):
            assert len(paragraph) > 1, f"single-character paragraph in {title!r}"
    joined = [p for _, body in result for p in body.split("\n\n")]
    assert joined == source_paragraphs


# ---------------------------------------------------------------- rule 1: headings


@pytest.mark.parametrize(
    "heading",
    [
        "Chapter I", "CHAPTER XII", "Chapter 1", "Chapter 12.", "Letter 4", "Book One", "Part Two",
        "Volume III", "Chapter the First", "BOOK THE LAST", "Chapter Twenty-One", "Chapter Twenty One",
        "Chapter I. The Arrival", "Chapter 3: In Which Nothing Happens", "Volume II — Notes",
        "CHAPTER I THE ARRIVAL", "PART ONE", "IV", "XII.", "42",
    ],
)  # fmt: skip
def test_headings(heading):
    assert _is_heading(heading)


@pytest.mark.parametrize(
    "prose",
    [
        "Part of me wanted to stay.", "Book him, Danno.", "Part I of my life was hard.", "Book two was better.",
        "Letter I received yesterday.", "Chapter Epilogue", "Letter A", "did.", "Mix", "Volume",
        "Chapter I. " + "x" * 80,  # over 80 characters
    ],
)  # fmt: skip
def test_prose_is_not_a_heading(prose):
    assert not _is_heading(prose)


def test_prose_starting_with_keyword_stays_in_its_chapter():
    text = cleaned_text("Chapter I", LONG_TEXT, "Part of me wanted to stay.", "Book him, Danno.", LONG_TEXT)
    result = split_chapters(text)
    assert titles(result) == ["Chapter I"]
    assert "Part of me wanted to stay.\n\nBook him, Danno." in result[0][1]


# ---------------------------------------------------------------- rule 2: sections


def test_basic_chapter_headings():
    result = split_chapters(cleaned_text("Chapter I", LONG_TEXT, "Chapter II", LONG_TEXT))
    assert result == [("Chapter I", LONG_TEXT), ("Chapter II", LONG_TEXT)]


def test_opening_section_before_first_heading():
    opening = "Some opening text before any heading. " + LONG_TEXT
    result = split_chapters(cleaned_text(opening, "Chapter I", LONG_TEXT))
    assert result == [("Opening", opening), ("Chapter I", LONG_TEXT)]


def test_no_opening_when_book_starts_with_heading():
    result = split_chapters(cleaned_text("Chapter I", LONG_TEXT, "Chapter II", LONG_TEXT))
    assert "Opening" not in titles(result)


def test_trailing_period_stripped_from_title():
    result = split_chapters(cleaned_text("Chapter 12.", LONG_TEXT, "XII.", LONG_TEXT))
    assert titles(result) == ["Chapter 12", "XII"]


# ---------------------------------------------------------------- rule 3: tiny sections


def test_part_one_chapter_one_stack():
    result = split_chapters(cleaned_text("PART ONE", "CHAPTER I", LONG_TEXT, "CHAPTER II", LONG_TEXT))
    assert result == [("Part One — Chapter I", LONG_TEXT), ("Chapter II", LONG_TEXT)]


def test_tiny_sections_cascade_until_big_enough():
    text = cleaned_text("Contents", "CHAPTER I", "short", "CHAPTER II", "short", "CHAPTER III", LONG_TEXT,
                        "CHAPTER IV", LONG_TEXT)  # fmt: skip
    result = split_chapters(text)
    assert titles(result) == ["Opening — Chapter I — Chapter II — Chapter III", "Chapter IV"]
    assert result[0][1] == cleaned_text("Contents", "short", "short", LONG_TEXT)
    assert all(len(body.split()) >= 50 for _, body in result)


def test_tiny_last_section_merges_into_previous_and_keeps_its_title():
    result = split_chapters(cleaned_text("Chapter I", LONG_TEXT, "Chapter II", LONG_TEXT, "Chapter III", "Fin."))
    assert result == [("Chapter I", LONG_TEXT), ("Chapter II", cleaned_text(LONG_TEXT, "Fin."))]


def test_whole_book_tiny_is_one_section():
    assert split_chapters("Just a few words.") == [("Opening", "Just a few words.")]


# ---------------------------------------------------------------- rule 4: fallback / oversize


def paragraphs(count: int, words: int, prefix: str = "p") -> list[str]:
    return [f"{prefix}{i} " + " ".join(["lorem"] * (words - 1)) for i in range(count)]


def test_whole_book_fallback_titles_and_text():
    source = paragraphs(60, 200)  # 12,000 words, no headings
    result = split_chapters(cleaned_text(*source))
    assert titles(result) == ["Part 1", "Part 2", "Part 3"]
    assert [len(body.split()) for _, body in result] == [5000, 5000, 2000]
    assert_text_intact(result, source)


def test_part_ends_at_first_boundary_after_5000_words():
    source = paragraphs(5, 3000)  # 15,000 words
    result = split_chapters(cleaned_text(*source))
    # 3000 < 5000, then 6000 >= 5000 -> cut; then 6000 -> cut; then 3000
    assert [len(body.split()) for _, body in result] == [6000, 6000, 3000]
    assert_text_intact(result, source)


def test_oversize_chapter_split_keeps_other_chapters():
    big = paragraphs(80, 200, prefix="b")  # 16,000 words
    result = split_chapters(cleaned_text("Chapter I", LONG_TEXT, "Chapter II", *big, "Chapter III", LONG_TEXT))
    assert titles(result) == [
        "Chapter I", "Chapter II, part 1", "Chapter II, part 2", "Chapter II, part 3", "Chapter II, part 4",
        "Chapter III",
    ]  # fmt: skip
    assert [len(body.split()) for _, body in result[1:5]] == [5000, 5000, 5000, 1000]
    assert_text_intact(result, [LONG_TEXT, *big, LONG_TEXT])


def test_15000_words_exactly_is_not_oversize():
    chapter = paragraphs(75, 200)  # 15,000 words
    result = split_chapters(cleaned_text("Chapter I", *chapter, "Chapter II", LONG_TEXT))
    assert titles(result) == ["Chapter I", "Chapter II"]


def test_short_single_section_is_not_renamed():
    result = split_chapters(cleaned_text("Chapter I", LONG_TEXT))
    assert result == [("Chapter I", LONG_TEXT)]


def test_no_single_character_paragraphs_ever():
    source = ["The cat sat on the mat. " * 40] * 100
    for _, body in split_chapters(cleaned_text(*source)):
        assert all(len(p) > 1 for p in body.split("\n\n"))
        assert body.startswith("The cat sat")


# ---------------------------------------------------------------- rule 5: title case


@pytest.mark.parametrize(
    ("heading", "title"),
    [
        ("CHAPTER I", "Chapter I"),
        ("CHAPTER XII. THE DIM LIVID MIX", "Chapter XII. The Dim Livid Mix"),
        ("CHAPTER THE FIRST", "Chapter the First"),
        ("BOOK TWENTY-ONE: DON'T STOP", "Book Twenty-One: Don't Stop"),
        ("PART XII", "Part XII"),
        ("Chapter IV. The Mixed Case Stays", "Chapter IV. The Mixed Case Stays"),
        ("XIV", "XIV"),
    ],
)
def test_title_case(heading, title):
    result = split_chapters(cleaned_text(heading, LONG_TEXT))
    assert titles(result) == [title]


# ---------------------------------------------------------------- rule 6: never empty


def test_never_empty_list_or_body():
    for text in ["", "CHAPTER I", "Chapter I\n\nChapter II"]:
        result = split_chapters(text)
        assert result
        assert all(body for _, body in result)


# ---------------------------------------------------------------- fixtures through the full pipeline


def test_sample_book_fixture():
    result = split_chapters(clean((FIXTURES / "sample_book.txt").read_text(encoding="utf-8")))
    assert titles(result) == ["Opening — Part One — Chapter I", "Chapter II", "Chapter III"]
    assert result[0][1].startswith("CONTENTS\n\n")  # TOC absorbed into the first chapter
    assert "This is the first chapter." in result[0][1]
    assert result[1][1].startswith("This is the second chapter.")
    assert result[2][1].startswith("This is the third chapter.")
    for _, body in result:
        assert len(body.split()) >= 250  # "a few hundred words each"
        assert all(len(p) > 1 for p in body.split("\n\n"))


def test_no_chapters_fixture_gives_exactly_three_parts():
    cleaned = clean((FIXTURES / "no_chapters.txt").read_text(encoding="utf-8"))
    assert 11_000 <= len(cleaned.split()) <= 13_000
    result = split_chapters(cleaned)
    assert titles(result) == ["Part 1", "Part 2", "Part 3"]
    assert_text_intact(result, cleaned.split("\n\n"))
