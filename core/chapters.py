"""Chapter detection (CP1C; integration fixes by Claude Code).

Rules are specified in docs/CHECKPOINTS.md, CP1C.
"""

import re
from dataclasses import dataclass, field

MAX_HEADING_CHARS = 80
MAX_TITLE_PARTS = 3  # longer merged titles keep first and last only
TINY_WORDS = 50  # sections with fewer body words are merged
OVERSIZE_WORDS = 15_000  # sections with more body words are split
PART_WORDS = 5_000  # a part ends at the first paragraph boundary at/after this many words
REAL_WORDS = 20  # front matter: a section needs this many story words to count as "real"

_KEYWORD = r"chapter|book|part|volume|letter|act|scene"
_ROMAN = r"[ivxlcdm]+"
_NUMBER_WORD = (
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    r"eighty|ninety|hundred|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|"
    r"tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
    r"eighteenth|nineteenth|twentieth|thirtieth|fortieth|fiftieth|last|final"
)
_NUMERAL = rf"{_ROMAN}|\d+|(?:{_NUMBER_WORD})(?:[-\s](?:{_NUMBER_WORD}))?"
# "<keyword> [the] <numeral>", then nothing, or a separator (. : - – —) and a subtitle.
_KEYWORD_HEADING = re.compile(rf"^(?:{_KEYWORD})\s+(?:the\s+)?(?:{_NUMERAL})(?:\s*[.:\-–—].*)?$", re.IGNORECASE)
# Same prefix followed by any subtitle, allowed only when the paragraph has no lowercase letters.
_KEYWORD_HEADING_CAPS = re.compile(rf"^(?:{_KEYWORD})\s+(?:the\s+)?(?:{_NUMERAL})\b.*$", re.IGNORECASE)
# A bare numeral: Arabic, or UPPERCASE Roman ("did." or "mix" are words, not headings).
_BARE_NUMERAL = re.compile(r"^(?:[IVXLCDM]+|\d+)\.?$")
# Named sections: Prologue, Epilogue, Preface, Introduction, Conclusion, Foreword, Afterword,
# optionally "The Author's / Translator's / Editor's / Publisher's / Transcriber's ...".
_NAMED = r"prologue|epilogue|preface|introduction|conclusion|foreword|afterword"
_QUALIFIER = r"(?:(?:the\s+)?(?:author|translator|editor|publisher|transcriber)(?:['’]s)?\s+)?"
_NAMED_HEADING = re.compile(rf"^{_QUALIFIER}(?:{_NAMED})(?:\s*[.:\-–—].*)?$", re.IGNORECASE)
_NAMED_HEADING_CAPS = re.compile(rf"^{_QUALIFIER}(?:{_NAMED})\b.*$", re.IGNORECASE)
_NAMED_WORD = re.compile(rf"\b({_NAMED})\b", re.IGNORECASE)
_NOT_AUTHOR = re.compile(r"\b(translator|editor|publisher|transcriber)", re.IGNORECASE)
_KEYWORD_THE = re.compile(rf"^((?:{_KEYWORD})\s+)The\b", re.IGNORECASE)
# A word for title-casing; keeps "DON'T" -> "Don't".
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
# The Roman numeral after the keyword, kept uppercase when title-casing.
_NUMERAL_TOKEN = re.compile(rf"^((?:{_KEYWORD})\s+(?:the\s+)?)({_ROMAN})\b", re.IGNORECASE)


def _words(paragraphs: list[str]) -> int:
    return sum(len(p.split()) for p in paragraphs)


def _strip_heading(paragraph: str) -> str:
    """A heading without surrounding brackets left over from illustration captions."""
    return paragraph.strip().strip("[]").strip()


def _is_heading(paragraph: str) -> bool:
    """True if a cleaned paragraph is a chapter/part/named-section heading (CP1C rule 1)."""
    text = _strip_heading(paragraph)
    if not text or len(text) > MAX_HEADING_CHARS:
        return False
    if _BARE_NUMERAL.match(text) or _KEYWORD_HEADING.match(text) or _NAMED_HEADING.match(text):
        return True
    caps = text == text.upper()
    return caps and bool(_KEYWORD_HEADING_CAPS.match(text) or _NAMED_HEADING_CAPS.match(text))


def _kind(heading: str) -> str:
    """"numeral", a named-section word ("epilogue", "preface"…), or the keyword ("chapter"…)."""
    if _BARE_NUMERAL.match(heading):
        return "numeral"
    if _NAMED_HEADING.match(heading) or _NAMED_HEADING_CAPS.match(heading):
        return _NAMED_WORD.search(heading).group(1).lower()
    return heading.split()[0].lower()


def _title_case(heading: str) -> str:
    """Title-case an ALL-CAPS heading; its Roman numeral stays uppercase (rule 5)."""
    if any(c.islower() for c in heading) or _BARE_NUMERAL.match(heading):
        return heading
    titled = _WORD.sub(lambda m: m.group(0).capitalize(), heading)
    titled = _KEYWORD_THE.sub(r"\1the", titled)  # "Chapter The First" -> "Chapter the First"
    numeral = _NUMERAL_TOKEN.match(titled)
    if numeral:
        titled = titled[: numeral.start(2)] + numeral.group(2).upper() + titled[numeral.end(2) :]
    return titled


# Sections that live in another heading (CP3): a bare numeral ("II") inside any container,
# a Scene inside an Act. Their title becomes "<container> — <own title>" ("Epilogue — II").
_CONTAINERS = {"part", "book", "volume", "act", "prologue", "epilogue"}
_FRONT_KINDS = {"preface", "introduction", "foreword"}  # may be someone else's: rule 2b

# Front-matter paragraphs (rule 2a).
_CONTENTS_MARK = re.compile(r"^(?:table of\s+)?contents\.?$|^(?:list of\s+)?illustrations\.?$|^page\.?$", re.IGNORECASE)
_TOC_TOKEN = re.compile(rf"^(?:{_KEYWORD}|{_NAMED}|contents|the|{_NUMERAL})[.:,;]?$", re.IGNORECASE)
_PAGE_REFERENCE = re.compile(r"\s(?:\d{1,4}|[ivxlc]{1,7})$", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?…\"”’')]$")
_SIGNATURE_WORD = re.compile(r"^(?:[A-Z][\w’'.-]*|[A-Z]\.|of|de|van|von|the)$")


@dataclass
class _Section:
    title: str
    kind: str | None  # None for the "Opening" (text before the first heading)
    body: list[str] = field(default_factory=list)


def _sections(paragraphs: list[str]) -> list[_Section]:
    """Rule 2: each heading starts a section; text before the first heading is "Opening"."""
    sections: list[_Section] = []
    current = _Section("Opening", None)
    container: _Section | None = None
    for paragraph in paragraphs:
        if not _is_heading(paragraph):
            current.body.append(paragraph)
            continue
        if current.kind is not None or current.body:
            sections.append(current)
        heading = _strip_heading(paragraph)
        kind = _kind(heading)
        title = _title_case(heading.rstrip(".").strip())
        if container is not None and (kind == "numeral" or (kind == "scene" and container.kind == "act")):
            title = f"{container.title} — {title}"
        current = _Section(title, kind)
        if kind in _CONTAINERS:
            container = current
    if current.kind is not None or current.body:
        sections.append(current)
    return sections


# ---------------------------------------------------------------- front matter (rule 2a/2b)


def _is_front_matter_paragraph(paragraph: str) -> bool:
    """Title-page lines, contents entries and list-of-illustrations lines."""
    words = paragraph.split()
    if _CONTENTS_MARK.match(paragraph):
        return True
    if len(words) >= 3 and sum(bool(_TOC_TOKEN.match(w)) for w in words) >= 0.5 * len(words):
        return True  # "Letter 1 Letter 2 … Chapter 24", "PART ONE CHAPTER I. The Arrival …"
    if len(words) <= 15 and _PAGE_REFERENCE.search(paragraph):
        return True  # "Frontispiece iv", "“The efforts of his aunt” 448"
    if len(words) <= 12 and (not any(c.islower() for c in paragraph) or not _SENTENCE_END.search(paragraph)):
        return True  # "PRIDE.", "by Jane Austen,", "Frankenstein;", "London"
    return False


def _story_words(section: _Section) -> int:
    return sum(len(p.split()) for p in section.body if not _is_front_matter_paragraph(p))


def _surnames(authors: list[str]) -> list[str]:
    return [a.split(",")[0].strip().lower() for a in authors if a.strip()]


def _initials(authors: list[str]) -> set[str]:
    return {w[0].upper() for a in authors for w in re.findall(r"[A-Za-z]+", a)}


def _signature(section: _Section) -> str | None:
    """The preface's closing signature ("GEORGE SAINTSBURY.", "M. W. S."), if it has one."""
    for paragraph in reversed(section.body):
        if _CONTENTS_MARK.match(paragraph) or (_is_front_matter_paragraph(paragraph) and not paragraph.isupper()):
            continue  # list-of-illustrations lines etc. after the signature
        words = paragraph.split()
        if 1 <= len(words) <= 6 and all(_SIGNATURE_WORD.match(w) for w in words):
            return paragraph
        return None
    return None


def _by_author(name: str, authors: list[str] | None) -> bool:
    """True if a name ("George Saintsbury", "M. W. S.", "The Author") is the book's author."""
    if re.search(r"\bauthor\b", name, re.IGNORECASE):
        return True
    if not authors:
        return False
    if any(surname and surname in name.lower() for surname in _surnames(authors)):
        return True
    letters = re.findall(r"[A-Za-z]+", name)
    return bool(letters) and all(len(w) == 1 for w in letters) and {w.upper() for w in letters} <= _initials(authors)


def _is_authors_own(sections: list[_Section], index: int, authors: list[str] | None) -> bool:
    """Rule 2b: is this preface/introduction/foreword by the book's own author?"""
    section = sections[index]
    if _NOT_AUTHOR.search(section.title):
        return False  # "Translator's Preface"
    earlier = " ".join(p for s in sections[:index] for p in [s.title, *s.body])
    credit = re.search(rf"\b{section.kind}\s+by\s+(.{{3,60}}?)(?=\s+and\b|\s+with\b|[.;:,]|$)", earlier, re.IGNORECASE)
    if credit and not _by_author(credit.group(1), authors):
        return False  # title page: "with a Preface by George Saintsbury"
    signature = _signature(section)
    if signature and not _by_author(signature, authors):
        return False  # signed by someone else
    return True


def _drop_front_matter(sections: list[_Section], authors: list[str] | None) -> list[_Section]:
    """Rule 2a: drop title pages, contents and lists of illustrations before the first real
    section; rule 2b: drop prefaces/introductions/forewords that are not the author's own."""
    real = [i for i, s in enumerate(sections) if _story_words(s) >= REAL_WORDS]
    if not real:
        return sections  # nothing looks like a chapter: leave the text alone
    dropped: set[int] = set()
    first = None
    for i in real:
        if sections[i].kind in _FRONT_KINDS:
            if _is_authors_own(sections, i, authors):
                first = i if first is None else first
            else:
                dropped.add(i)
            continue
        first = i if first is None else first
        break
    if first is None:
        return sections  # only prefaces: keep everything rather than lose the book

    # Headings directly before the first real section that belong to it ("PART I" + "CHAPTER I"):
    # short sections with some story text, and at most one empty container heading.
    start = first
    while start > 0:
        previous = sections[start - 1]
        if start - 1 in dropped or previous.kind is None:
            break
        if _story_words(previous) > 0 and _story_words(previous) < REAL_WORDS:
            start -= 1
            continue
        if not previous.body and previous.kind in _CONTAINERS:
            start -= 1
        break

    kept = [s for i, s in enumerate(sections) if i >= start and i not in dropped]
    if kept and kept[0].kind is None:  # a real "Opening": drop its leading title-page lines
        body = kept[0].body
        while body and _is_front_matter_paragraph(body[0]):
            body = body[1:]
        kept[0] = _Section(kept[0].title, None, body)
    # Back matter: ALL-CAPS lines after the story ("THE END", a printer's imprint).
    last = kept[-1].body if kept else []
    while len(last) > 1 and _is_front_matter_paragraph(last[-1]) and not any(c.islower() for c in last[-1]):
        last.pop()
    return kept


# ---------------------------------------------------------------- tiny sections (rule 3)


def _merged_title(parts: list[str]) -> str:
    """Join merged headings; a long run keeps only its first and last ("A — … — Z").

    A heading already repeated at the start of the next one is not repeated
    ("Epilogue" + "Epilogue — I" → "Epilogue — I"). A table of contents whose entries
    are separate paragraphs would otherwise give a title like "Opening — Letter 1 — …".
    """
    parts = [p for i, p in enumerate(parts)
             if i + 1 == len(parts) or not (parts[i + 1] == p or parts[i + 1].startswith(p + " — "))]  # fmt: skip
    if len(parts) > MAX_TITLE_PARTS:
        parts = [parts[0], "…", parts[-1]]
    return " — ".join(parts)


def _merge_tiny(sections: list[_Section]) -> list[tuple[str, list[str]]]:
    """Rule 3: a section under 50 words merges into the next one, cascading.

    The merged title is "<tiny> — <next>" (at most 3 parts, see ``_merged_title``).
    A tiny last section merges into the previous one, which keeps its title.
    """
    merged: list[tuple[str, list[str]]] = []
    carry: tuple[list[str], list[str]] | None = None  # (title parts, body)
    for section in sections:
        parts, body = [section.title], list(section.body)
        if carry is not None:
            parts, body = carry[0] + parts, carry[1] + body
            carry = None
        if _words(body) < TINY_WORDS:
            carry = (parts, body)
        else:
            merged.append((_merged_title(parts), body))
    if carry is not None:
        if merged:
            previous_title, previous_body = merged[-1]
            merged[-1] = (previous_title, previous_body + carry[1])
        else:
            merged.append((_merged_title(carry[0]), carry[1]))
    return merged


def _split_parts(paragraphs: list[str]) -> list[list[str]]:
    """A part ends at the first paragraph boundary at or after PART_WORDS words."""
    parts: list[list[str]] = []
    current: list[str] = []
    count = 0
    for paragraph in paragraphs:
        current.append(paragraph)
        count += len(paragraph.split())
        if count >= PART_WORDS:
            parts.append(current)
            current, count = [], 0
    if current:
        parts.append(current)
    return parts


def split_chapters(text: str, authors: list[str] | None = None) -> list[tuple[str, str]]:
    """Split cleaned text (paragraphs separated by blank lines) into [(title, body)].

    ``authors`` (e.g. ``["Austen, Jane"]``) lets rule 2b keep the author's own preface.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sections = _merge_tiny(_drop_front_matter(_sections(paragraphs), authors)) or [("Opening", [])]

    # Rule 4: whole-book fallback (fewer than 2 sections) or oversize sections.
    result: list[tuple[str, list[str]]] = []
    whole_book = len(sections) < 2
    for title, body in sections:
        if not whole_book and _words(body) <= OVERSIZE_WORDS:
            result.append((title, body))
            continue
        parts = _split_parts(body)
        if len(parts) < 2:
            result.append((title, body))
        elif whole_book:
            result.extend((f"Part {n}", part) for n, part in enumerate(parts, 1))
        else:
            result.extend((f"{title}, part {n}", part) for n, part in enumerate(parts, 1))

    # Rule 6: bodies joined by blank lines, never empty.
    return [(title, "\n\n".join(body) or title) for title, body in result]
