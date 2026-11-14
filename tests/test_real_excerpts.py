"""CP3: chapter splitting on short real excerpts of Frankenstein (84), Crime and Punishment (2554)
and Pride and Prejudice (1342): front matter, first chapters and the end of each book.

These check the actual titles and that chapter 1 starts with the real story text.
"""

from pathlib import Path

import pytest

from core.chapters import split_chapters
from core.text_cleaner import clean

FIXTURES = Path(__file__).resolve().parent / "fixtures"

BOOKS = {
    84: ("excerpt_84_frankenstein.txt", ["Shelley, Mary Wollstonecraft"]),
    2554: ("excerpt_2554_crime_and_punishment.txt", ["Dostoyevsky, Fyodor"]),
    1342: ("excerpt_1342_pride_and_prejudice.txt", ["Austen, Jane"]),
}


def split(gutenberg_id: int, with_authors: bool = True) -> list[tuple[str, str]]:
    name, authors = BOOKS[gutenberg_id]
    raw = (FIXTURES / name).read_text(encoding="utf-8")
    return split_chapters(clean(raw), authors if with_authors else None)


def test_frankenstein_starts_at_letter_1_without_title_page_or_contents():
    result = split(84)
    assert [t for t, _ in result] == ["Letter 1", "Letter 2", "Chapter 1"]
    assert result[0][1].startswith("To Mrs. Saville, England.\n\nSt. Petersburgh, Dec. 11th, 17—.\n\n"
                                   "You will rejoice to hear that no disaster has accompanied")  # fmt: skip
    assert result[2][1].startswith("I am by birth a Genevese, and my family is one of the most distinguished")


def test_crime_and_punishment_drops_translators_preface_and_names_the_epilogue():
    result = split(2554)
    assert [t for t, _ in result] == ["Part I — Chapter I", "Chapter II", "Epilogue — I", "Epilogue — II"]
    assert result[0][1].startswith("On an exceptionally hot evening early in July a young man came out of")
    assert result[2][1].startswith("Siberia. On the banks of a broad solitary river stands a town")
    assert result[3][1].endswith("That might be the subject of a new story, but our present story is ended.")
    text = "\n\n".join(body for _, body in result)
    assert "Dostoevsky was the son of a doctor" not in text  # translator's preface
    assert "TRANSLATOR" not in text and "CONTENTS" not in text


def test_pride_and_prejudice_drops_editors_preface_and_illustrations():
    result = split(1342)
    assert [t for t, _ in result] == ["Chapter I", "Chapter II"]
    assert result[0][1].startswith("It is a truth universally acknowledged, that a single man in possession "
                                   "of a good fortune must be in want of a wife.\n\n")  # fmt: skip
    assert result[1][1].startswith("Mr. Bennet was among the earliest of those who waited on Mr. Bingley.")
    assert result[1][1].endswith("had been the means of uniting them.")  # no "THE END" / printer's imprint
    text = "\n\n".join(body for _, body in result)
    for leftover in ["Saintsbury", "Walt Whitman", "Frontispiece", "Copyright", "Illustration", "PRIDE AND PREJUDICE",
                     "GEORGE ALLEN", "CHISWICK", "]", "[", "^{"]:  # fmt: skip
        assert leftover not in text, leftover


@pytest.mark.parametrize("gutenberg_id", BOOKS)
def test_same_titles_without_author_names(gutenberg_id):
    """The author list only matters for prefaces signed by the author; these books have none."""
    assert [t for t, _ in split(gutenberg_id, with_authors=False)] == [t for t, _ in split(gutenberg_id)]


@pytest.mark.parametrize("gutenberg_id", BOOKS)
def test_no_bracket_fragments_or_tiny_chapters(gutenberg_id):
    for title, body in split(gutenberg_id):
        assert "[" not in title and "]" not in title
        assert len(body.split()) >= 50, title
        assert all(p.strip("[]. ") for p in body.split("\n\n")), title
