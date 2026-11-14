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
    text = cleaned_text("CHAPTER I", LONG_TEXT, "CHAPTER II", "A short scene.", "CHAPTER III", "Another one.",
                        "CHAPTER IV", "And a third.", "CHAPTER V", LONG_TEXT)  # fmt: skip
    result = split_chapters(text)
    # 4 merged headings: only the first and last are kept (CP3 title cap).
    assert titles(result) == ["Chapter I", "Chapter II — … — Chapter V"]
    assert result[1][1] == cleaned_text("A short scene.", "Another one.", "And a third.", LONG_TEXT)
    assert all(len(body.split()) >= 50 for _, body in result)


def test_three_merged_headings_keep_every_part():
    text = cleaned_text("PART ONE", "CHAPTER I", "A short opening scene.", "CHAPTER II", LONG_TEXT, "CHAPTER III", LONG_TEXT)
    result = split_chapters(text)
    assert titles(result) == ["Part One — Chapter I — Chapter II", "Chapter III"]
    assert result[0][1] == cleaned_text("A short opening scene.", LONG_TEXT)


def test_table_of_contents_with_paragraph_entries_is_dropped():
    """CP3: a TOC whose entries are separate headings is front matter, not part of Letter 1."""
    toc = ["Frankenstein;", "CONTENTS"] + [f"Letter {i}" for i in range(1, 5)] + [f"Chapter {i}" for i in range(1, 25)]
    body = []
    for i in range(1, 5):
        body += [f"Letter {i}", LONG_TEXT]
    for i in range(1, 3):
        body += [f"Chapter {i}", LONG_TEXT]
    result = split_chapters(cleaned_text(*toc, *body))
    assert titles(result) == ["Letter 1", "Letter 2", "Letter 3", "Letter 4", "Chapter 1", "Chapter 2"]
    assert result[0][1] == LONG_TEXT


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
    assert titles(result) == ["Part One — Chapter I", "Chapter II", "Chapter III"]
    assert result[0][1].startswith("This is the first chapter.")  # contents dropped (CP3 rule 2a)
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


# ---------------------------------------------------------------- CP3: named sections, plays, containers


@pytest.mark.parametrize(
    "heading",
    [
        "Epilogue", "EPILOGUE", "Prologue.", "Preface", "PREFACE.", "Introduction", "Conclusion", "Foreword",
        "Afterword", "TRANSLATOR’S PREFACE", "Author's Preface", "The Editor's Introduction",
        "Epilogue: Siberia", "PROLOGUE IN HEAVEN", "ACT I", "Act II. Scene 3", "SCENE II. A room in the castle.",
        "Scene 4", "[Chapter I.]", "Chapter I.]",
    ],
)  # fmt: skip
def test_cp3_headings(heading):
    assert _is_heading(heading)


@pytest.mark.parametrize(
    "prose",
    ["Epilogue to a long life was quiet.", "The preface was long.", "Act now, or never.", "Scene two was better.",
     "Introduction of the new rules went badly.", "Conclusion reached"],
)  # fmt: skip
def test_cp3_prose_is_not_a_heading(prose):
    assert not _is_heading(prose)


def test_epilogue_with_bare_numeral_chapters():
    """Crime and Punishment: EPILOGUE, then I and II."""
    text = cleaned_text("CHAPTER VIII", LONG_TEXT, "EPILOGUE", "I", LONG_TEXT, "II", LONG_TEXT)
    assert titles(split_chapters(text)) == ["Chapter VIII", "Epilogue — I", "Epilogue — II"]


def test_play_acts_and_scenes():
    text = cleaned_text("ACT I", "SCENE I. ELSINORE.", LONG_TEXT, "Scene II. A room of state.", LONG_TEXT,
                        "ACT II", "SCENE I", LONG_TEXT)  # fmt: skip
    assert titles(split_chapters(text)) == ["Act I — Scene I. Elsinore", "Act I — Scene II. A room of state",
                                            "Act II — Scene I"]  # fmt: skip


def test_prologue_is_story_and_kept():
    text = cleaned_text("CONTENTS", "PROLOGUE", "CHAPTER I", "PROLOGUE", LONG_TEXT, "CHAPTER I", LONG_TEXT)
    assert titles(split_chapters(text)) == ["Prologue", "Chapter I"]


# ---------------------------------------------------------------- CP3: front matter (rule 2a) and prefaces (2b)


def test_title_page_before_first_chapter_is_dropped():
    text = cleaned_text("THE BOOK", "by A. Writer", "London: Printed for the Author", "Chapter I", LONG_TEXT, "Chapter II", LONG_TEXT)
    result = split_chapters(text)
    assert titles(result) == ["Chapter I", "Chapter II"]
    assert result[0][1] == LONG_TEXT


def test_list_of_illustrations_is_dropped():
    text = cleaned_text("List of Illustrations.", "PAGE", "Frontispiece iv", "“The efforts of his aunt” 448",
                        "Chapter I", LONG_TEXT, "Chapter II", LONG_TEXT)  # fmt: skip
    assert titles(split_chapters(text)) == ["Chapter I", "Chapter II"]


def test_book_without_headings_keeps_its_text_but_not_its_title_lines():
    story = "It was a dark and stormy night, and the rain fell in torrents. " + LONG_TEXT
    result = split_chapters(cleaned_text("A DARK NIGHT", "by Someone", story))
    assert result == [("Opening", story)]


def test_authors_own_unsigned_preface_is_kept():
    text = cleaned_text("PREFACE", "I wrote this book because I wanted to. " + LONG_TEXT, "Chapter I", LONG_TEXT)
    assert titles(split_chapters(text, ["Writer, Anne"])) == ["Preface", "Chapter I"]


def test_translators_preface_is_dropped():
    text = cleaned_text("TRANSLATOR’S PREFACE", "A few words about the author. " + LONG_TEXT, "PART I", "CHAPTER I", LONG_TEXT)
    result = split_chapters(text, ["Dostoyevsky, Fyodor"])
    assert titles(result) == ["Part I — Chapter I"]
    assert result[0][1] == LONG_TEXT


def test_preface_credited_to_someone_else_on_the_title_page_is_dropped():
    text = cleaned_text("PRIDE AND PREJUDICE", "by Jane Austen,", "with a Preface by George Saintsbury and Illustrations by Hugh Thomson",
                        "PREFACE.", "Walt Whitman has somewhere a fine distinction. " + LONG_TEXT, "Chapter I.", LONG_TEXT)  # fmt: skip
    assert titles(split_chapters(text, ["Austen, Jane"])) == ["Chapter I"]


@pytest.mark.parametrize(
    "signature, authors, kept",
    [
        ("GEORGE SAINTSBURY.", ["Austen, Jane"], False),
        ("JANE AUSTEN.", ["Austen, Jane"], True),
        ("M. W. S.", ["Shelley, Mary Wollstonecraft"], True),
        ("THE AUTHOR.", ["Shelley, Mary Wollstonecraft"], True),
        ("THE AUTHOR.", None, True),
        ("GEORGE SAINTSBURY.", None, False),
    ],
)
def test_signed_preface(signature, authors, kept):
    text = cleaned_text("PREFACE", "Some thoughts about the novel and its time. " + LONG_TEXT, signature, "Chapter I", LONG_TEXT)
    expected = ["Preface", "Chapter I"] if kept else ["Chapter I"]
    assert titles(split_chapters(text, authors)) == expected


def test_back_matter_in_capitals_is_dropped():
    text = cleaned_text("Chapter I", LONG_TEXT, "Chapter II", LONG_TEXT, "THE END", "CHISWICK PRESS: CHARLES WHITTINGHAM AND CO.")
    assert split_chapters(text)[-1] == ("Chapter II", LONG_TEXT)


def test_only_front_matter_is_left_alone():
    """Nothing looks like a chapter: keep the text rather than drop the whole book."""
    result = split_chapters(cleaned_text("CONTENTS", "Chapter I", "Chapter II"))
    assert result == [("Opening — Chapter I — Chapter II", "CONTENTS")]
