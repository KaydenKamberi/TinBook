"""Chapter detection (CP1C; integration fixes by Claude Code).

Rules are specified in docs/CHECKPOINTS.md, CP1C.
"""

import re

MAX_HEADING_CHARS = 80
TINY_WORDS = 50  # sections with fewer body words are merged
OVERSIZE_WORDS = 15_000  # sections with more body words are split
PART_WORDS = 5_000  # a part ends at the first paragraph boundary at/after this many words

_KEYWORD = r"chapter|book|part|volume|letter"
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
_KEYWORD_THE = re.compile(rf"^((?:{_KEYWORD})\s+)The\b", re.IGNORECASE)
# A word for title-casing; keeps "DON'T" -> "Don't".
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")
# The Roman numeral after the keyword, kept uppercase when title-casing.
_NUMERAL_TOKEN = re.compile(rf"^((?:{_KEYWORD})\s+(?:the\s+)?)({_ROMAN})\b", re.IGNORECASE)


def _words(paragraphs: list[str]) -> int:
    return sum(len(p.split()) for p in paragraphs)


def _is_heading(paragraph: str) -> bool:
    """True if a cleaned paragraph is a chapter/part heading (CP1C rule 1)."""
    text = paragraph.strip()
    if not text or len(text) > MAX_HEADING_CHARS:
        return False
    if _BARE_NUMERAL.match(text) or _KEYWORD_HEADING.match(text):
        return True
    return text == text.upper() and bool(_KEYWORD_HEADING_CAPS.match(text))


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


def _sections(paragraphs: list[str]) -> list[tuple[str, list[str]]]:
    """Rule 2: each heading starts a section; text before the first heading is "Opening"."""
    sections: list[tuple[str, list[str]]] = []
    title, body = "Opening", []
    started = False  # an empty "Opening" (book starts with a heading) is not a section
    for paragraph in paragraphs:
        if _is_heading(paragraph):
            if started or body:
                sections.append((title, body))
            title, body, started = _title_case(paragraph.strip().rstrip(".")), [], True
        else:
            body.append(paragraph)
    if started or body:
        sections.append((title, body))
    return sections


def _merge_tiny(sections: list[tuple[str, list[str]]]) -> list[tuple[str, list[str]]]:
    """Rule 3: a section under 50 words merges into the next one, cascading.

    The merged title is "<tiny> — <next>". A tiny last section merges into the
    previous one, which keeps its title.
    """
    merged: list[tuple[str, list[str]]] = []
    carry: tuple[str, list[str]] | None = None
    for title, body in sections:
        if carry is not None:
            title, body = f"{carry[0]} — {title}", carry[1] + body
            carry = None
        if _words(body) < TINY_WORDS:
            carry = (title, body)
        else:
            merged.append((title, body))
    if carry is not None:
        if merged:
            previous_title, previous_body = merged[-1]
            merged[-1] = (previous_title, previous_body + carry[1])
        else:
            merged.append(carry)
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


def split_chapters(text: str) -> list[tuple[str, str]]:
    """Split cleaned text (paragraphs separated by blank lines) into [(title, body)]."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sections = _merge_tiny(_sections(paragraphs)) or [("Opening", [])]

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
