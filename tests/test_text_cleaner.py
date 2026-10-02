"""Tests for core/text_cleaner.py owned by CP1C."""

from pathlib import Path

import pytest

from core.text_cleaner import clean, clean_for_speech, strip_gutenberg_boilerplate

FIXTURES = Path(__file__).resolve().parent / "fixtures"


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
        assert result == "First para.\n\nSecond para."

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
        raw = (FIXTURES / "sample_book.txt").read_text(encoding="utf-8")
        result = clean(raw)
        assert "*** START OF" not in result
        assert "*** END OF" not in result
        assert "Produced by" not in result
        assert "E-text prepared by" not in result
        assert "[Illustration" not in result
        assert "_italic_" not in result
        assert "--" not in result
        assert "This is the first chapter" in result

    def test_no_chapters_clean(self):
        raw = (FIXTURES / "no_chapters.txt").read_text(encoding="utf-8")
        result = clean(raw)
        assert "*** START OF" not in result
        assert "*** END OF" not in result
        assert "[Illustration: something]" not in result
        assert "[1]" not in result
        assert "_italic_" not in result
        assert "--" not in result


class TestCommasAndDashes:
    """Rule 6 only tidies commas created by "--"; ordinary commas are untouched."""

    @pytest.mark.parametrize(
        "text",
        ['He paid 1,000 pounds.', '"Hello," he said.', "In 1,234,567 years, maybe.", "Yes, no, maybe."],
    )
    def test_ordinary_commas_untouched(self, text):
        assert clean_for_speech(text) == text

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("This is a test--with a dash.", "This is a test, with a dash."),
            ("word,--then", "word, then"),
            ("a , b", "a, b"),
            ("x, , y", "x, y"),
            ("Wait--.", "Wait."),
            ("Stop--!", "Stop!"),
            ("--Hello there.", "Hello there."),
            ("Mr. ---- came in.", "Mr. came in."),
            ("one---two", "one, two"),
        ],
    )
    def test_dash_rule(self, text, expected):
        assert clean_for_speech(text) == expected


class TestSceneBreaks:
    @pytest.mark.parametrize("brk", ["-----", "---", "* * *", "*****", "= = =", "  -  *  =  "])
    def test_scene_break_dropped_before_dash_rule(self, brk):
        assert clean_for_speech(f"One.\n\n{brk}\n\nTwo.") == "One.\n\nTwo."


class TestProducerBlock:
    def test_blank_line_after_producer_block_is_kept(self):
        raw = "Produced by A\nand B\n\nText."
        assert strip_gutenberg_boilerplate(raw) == "Text."
        raw = "Intro.\nProduced by A\nand B\n\nText."
        assert strip_gutenberg_boilerplate(raw) == "Intro.\n\nText."

    def test_block_starting_in_first_40_lines_continues_past_line_40(self):
        lines = ["filler"] * 39 + ["Produced by A"] + ["continued credit"] * 5 + ["", "Text."]
        result = strip_gutenberg_boilerplate("\n".join(lines))
        assert "Produced by" not in result
        assert "continued credit" not in result
        assert result.endswith("filler\n\nText.")

    def test_producer_line_after_line_40_is_kept(self):
        lines = ["filler"] * 41 + ["Produced by A", "", "Text."]
        assert "Produced by A" in strip_gutenberg_boilerplate("\n".join(lines))


class TestFixtureText:
    def test_sample_book_special_cases(self):
        result = clean((FIXTURES / "sample_book.txt").read_text(encoding="utf-8"))
        assert "1,000 crowns, an absurd sum, and the traveller laughed." in result
        assert "pgdp" not in result and "Online" not in result  # full producer block removed
        assert "* * *" not in result and "-----" not in result and ",," not in result
        assert "Updated editions" not in result  # footer removed
        assert result.startswith("CONTENTS\n\n")
