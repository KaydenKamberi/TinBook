"""Tests for core/text_cleaner.py owned by CP1C."""

import pytest

from core.text_cleaner import clean, clean_for_speech, strip_gutenberg_boilerplate


class TestStripGutenbergBoilerplate:
    def test_removes_header_and_footer(self):
        raw = """The Project Gutenberg Ebook

*** START OF THE PROJECT GUTENBERG EBOOK TEST ***

Some content here.

*** END OF THE PROJECT GUTENBERG EBOOK TEST ***

More footer text."""
        result = strip_gutenberg_boilerplate(raw)
        assert "Some content here." in result
        assert "START OF" not in result
        assert "END OF" not in result
        assert "Project Gutenberg" not in result

    def test_removes_bom(self):
        raw = "\ufeffThe Project Gutenberg Ebook\n\nContent here."
        result = strip_gutenberg_boilerplate(raw)
        assert not result.startswith("\ufeff")
        assert "Content here." in result

    def test_normalizes_line_endings(self):
        raw = "Line one\r\nLine two\rLine three\n"
        result = strip_gutenberg_boilerplate(raw)
        assert "\r" not in result
        assert "Line one\nLine two\nLine three" in result

    def test_removes_producer_lines(self):
        raw = """*** START OF THE PROJECT GUTENBERG EBOOK TEST ***

Produced by John Doe
E-text prepared by Jane Smith

Actual content here.

*** END OF THE PROJECT GUTENBERG EBOOK TEST ***"""
        result = strip_gutenberg_boilerplate(raw)
        assert "Produced by" not in result
        assert "E-text prepared by" not in result
        assert "Actual content here." in result

    def test_removes_producer_lines_with_following_lines(self):
        raw = """*** START OF THE PROJECT GUTENBERG EBOOK TEST ***

Produced by John Doe
E-text prepared by Jane Smith
Translated by Bob

Actual content here.

*** END OF THE PROJECT GUTENBERG EBOOK TEST ***"""
        result = strip_gutenberg_boilerplate(raw)
        assert "Produced by" not in result
        assert "E-text prepared by" not in result
        assert "Translated by" not in result
        assert "Actual content here." in result

    def test_strips_whitespace(self):
        raw = "\n\n  Content with spaces  \n\n"
        result = strip_gutenberg_boilerplate(raw)
        assert result == "Content with spaces"

    def test_no_start_marker(self):
        raw = "Just some text without markers."
        result = strip_gutenberg_boilerplate(raw)
        assert "Just some text without markers." in result

    def test_no_end_marker(self):
        raw = "*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\n\nContent without end."
        result = strip_gutenberg_boilerplate(raw)
        assert "Content without end." in result


class TestCleanForSpeech:
    def test_unwraps_hard_wraps(self):
        text = "This is\na hard\nwrapped line."
        result = clean_for_speech(text)
        assert "This is a hard wrapped line." in result

    def test_removes_illustration_blocks(self):
        text = "Some text [Illustration: test] more text."
        result = clean_for_speech(text)
        assert "[Illustration: test]" not in result
        assert "Some text more text." in result

    def test_removes_footnote_markers(self):
        text = "Some text[1] and more[23] text."
        result = clean_for_speech(text)
        assert "[1]" not in result
        assert "[23]" not in result
        assert "Some text and more text." in result

    def test_removes_underscores_for_italics(self):
        text = "This has _italic_ text here."
        result = clean_for_speech(text)
        assert "_italic_" not in result
        assert "This has italic text here." in result

    def test_replaces_dashes_with_comma(self):
        text = "This is a test--with a dash."
        result = clean_for_speech(text)
        assert "--" not in result
        assert "This is a test, with a dash." in result

    def test_fixes_doubled_punctuation(self):
        text = "This has, , double commas and  , space before."
        result = clean_for_speech(text)
        assert ", ," not in result
        assert " ," not in result

    def test_drops_empty_paragraphs(self):
        text = "First para.\n\n\n\nSecond para."
        result = clean_for_speech(text)
        assert result == "First para.\n\nSecond para."

    def test_drops_scene_break_paragraphs(self):
        text = "First para.\n\n***\n\nSecond para."
        result = clean_for_speech(text)
        assert "***" not in result
        assert result == "First para.\n\nSecond para."

    def test_drops_dash_scene_breaks(self):
        text = "First para.\n\n---\n\nSecond para."
        result = clean_for_speech(text)
        assert "---" not in result
        # After cleaning, the --- becomes ", " and then gets cleaned up
        # The scene break paragraph should be dropped
        assert "First para." in result
        assert "Second para." in result

    def test_keeps_headings_as_paragraphs(self):
        text = "Chapter One\n\nSome content here."
        result = clean_for_speech(text)
        assert "Chapter One" in result
        assert "Some content here." in result


class TestClean:
    def test_full_clean(self):
        raw = """*** START OF THE PROJECT GUTENBERG EBOOK TEST ***

Produced by John Doe

Actual [Illustration: x] content with _italic_ and--dashes.

*** END OF THE PROJECT GUTENBERG EBOOK TEST ***"""
        result = clean(raw)
        assert "START OF" not in result
        assert "END OF" not in result
        assert "Produced by" not in result
        assert "[Illustration: x]" not in result
        assert "_italic_" not in result
        assert "--" not in result
        assert "Actual content with italic and, dashes." in result


class TestFixtures:
    def test_sample_book_clean(self):
        with open("tests/fixtures/sample_book.txt", "r", encoding="utf-8") as f:
            raw = f.read()
        result = clean(raw)
        assert "*** START OF" not in result
        assert "*** END OF" not in result
        assert "Produced by" not in result
        assert "E-text prepared by" not in result
        assert "[Illustration: test image]" not in result
        assert "_italic_" not in result
        assert "--" not in result
        assert "This is the first chapter" in result

    def test_no_chapters_clean(self):
        with open("tests/fixtures/no_chapters.txt", "r", encoding="utf-8") as f:
            raw = f.read()
        result = clean(raw)
        assert "*** START OF" not in result
        assert "*** END OF" not in result
        assert "[Illustration: something]" not in result
        assert "[1]" not in result
        assert "_italic_" not in result
        assert "--" not in result
