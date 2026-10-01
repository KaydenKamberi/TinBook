"""Tests for core/chapters.py owned by CP1C."""

import pytest

from core.chapters import split_chapters
from core.text_cleaner import clean_for_speech


# Helper to create long text with enough words
LONG_TEXT = "word " * 100  # 100 words - more than 50

# Helper to create cleaned text (paragraphs separated by \n\n)
def cleaned_text(*paras):
    return "\n\n".join(paras)


class TestSplitChapters:
    def test_basic_chapter_headings(self):
        text = cleaned_text("Chapter I", LONG_TEXT, "Chapter II", LONG_TEXT)
        result = split_chapters(text)
        assert len(result) == 2
        assert result[0][0] == "Chapter I"
        assert result[1][0] == "Chapter II"
        assert LONG_TEXT in result[0][1]
        assert LONG_TEXT in result[1][1]

    def test_opening_section(self):
        text = cleaned_text(
            "Some opening text before any heading with enough words. " + LONG_TEXT,
            "Chapter I",
            LONG_TEXT
        )
        result = split_chapters(text)
        assert len(result) >= 1
        assert result[0][0] == "Opening"
        assert "Some opening text before any heading" in result[0][1]

    def test_roman_numeral_headings(self):
        text = cleaned_text("PART I", LONG_TEXT, "PART II", LONG_TEXT)
        result = split_chapters(text)
        assert len(result) == 2
        assert result[0][0] == "Part I"
        assert result[1][0] == "Part II"

    def test_bare_roman_numerals(self):
        text = cleaned_text("I", LONG_TEXT, "II", LONG_TEXT)
        result = split_chapters(text)
        assert len(result) == 2
        assert result[0][0] == "I"
        assert result[1][0] == "II"

    def test_merge_tiny_sections(self):
        text = cleaned_text("TOC", "Table of contents here.", "Chapter I", LONG_TEXT, "Chapter II", LONG_TEXT)
        result = split_chapters(text)
        # TOC should be merged into Chapter I
        assert len(result) == 2
        assert "TOC" in result[0][0] or "Table of contents" in result[0][1]

    def test_merge_last_tiny_section(self):
        # Use a recognized heading pattern: "Chapter Epilogue"
        text = cleaned_text("Chapter I", LONG_TEXT, "Chapter Epilogue", "Short.")
        result = split_chapters(text)
        # Epilogue should be merged into Chapter I (tiny section < 50 words)
        assert len(result) == 1
        assert "Epilogue" in result[0][0] or "Short." in result[0][1]

    def test_all_caps_heading_title_case(self):
        text = cleaned_text("CHAPTER I", LONG_TEXT, "CHAPTER II", LONG_TEXT)
        result = split_chapters(text)
        assert result[0][0] == "Chapter I"
        assert result[1][0] == "Chapter II"

    def test_roman_numerals_stay_uppercase(self):
        # Need enough words so it doesn't fall into the tiny section merge
        # Use a section with enough body words to not be tiny (< 50)
        text = cleaned_text("PART XII", LONG_TEXT)
        result = split_chapters(text)
        # The section has 100 words in body, so it should not be merged
        # and the title should be title-cased
        assert result[0][0] == "Part XII"

    def test_oversized_section_splitting(self):
        # Create a very long section (> 15000 words)
        # Each paragraph needs to be separated by \n\n
        long_paras = ["word " * 6000] * 3  # 3 paragraphs of 6000 words each = 18000 words
        text = cleaned_text("Chapter I", *long_paras)
        result = split_chapters(text)
        # Should be split into parts
        assert len(result) > 1
        for i, (title, body) in enumerate(result):
            assert "part" in title.lower() or i == 0

    def test_fallback_no_headings(self):
        # Text with no headings at all
        long_paras = ["word " * 6000] * 3  # 18000 words
        result = split_chapters(cleaned_text(*long_paras))
        # Should create parts
        assert len(result) > 1
        assert result[0][0] == "Opening, part 1"

    def test_sample_book_chapters(self):
        with open("tests/fixtures/sample_book.txt", "r", encoding="utf-8") as f:
            raw = f.read()
        cleaned = clean_for_speech(raw)
        result = split_chapters(cleaned)
        # Should have chapters from the sample
        assert len(result) >= 3
        # Check that TOC/heading sections are merged
        titles = [r[0] for r in result]
        assert any("Chapter I" in t or "Chapter One" in t for t in titles)

    def test_no_chapters_fixture(self):
        with open("tests/fixtures/no_chapters.txt", "r", encoding="utf-8") as f:
            raw = f.read()
        cleaned = clean_for_speech(raw)
        result = split_chapters(cleaned)
        # The cleaned text should have enough words to trigger splitting
        # The no_chapters.txt has enough words to split into multiple parts
        assert len(result) >= 2

    def test_never_empty_list(self):
        result = split_chapters("")
        assert len(result) >= 1

    def test_never_empty_body(self):
        text = cleaned_text("Chapter I", LONG_TEXT)
        result = split_chapters(text)
        assert len(result) >= 1
        for title, body in result:
            assert body  # Body should never be empty

    def test_book_heading_pattern(self):
        text = cleaned_text("Book One", LONG_TEXT, "Book Two", LONG_TEXT)
        result = split_chapters(text)
        assert len(result) == 2
        assert result[0][0] == "Book One"
        assert result[1][0] == "Book Two"

    def test_volume_heading_pattern(self):
        text = cleaned_text("Volume I", LONG_TEXT, "Volume II", LONG_TEXT)
        result = split_chapters(text)
        assert len(result) == 2
        assert result[0][0] == "Volume I"
        assert result[1][0] == "Volume II"

    def test_letter_heading_pattern(self):
        text = cleaned_text("Letter A", LONG_TEXT, "Letter B", LONG_TEXT)
        result = split_chapters(text)
        assert len(result) == 2
        assert result[0][0] == "Letter A"
        assert result[1][0] == "Letter B"

    def test_part_heading_pattern(self):
        text = cleaned_text("Part One", LONG_TEXT, "Part Two", LONG_TEXT)
        result = split_chapters(text)
        assert len(result) == 2
        assert result[0][0] == "Part One"
        assert result[1][0] == "Part Two"
