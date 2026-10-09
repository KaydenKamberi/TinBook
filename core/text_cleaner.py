"""Gutenberg text cleaning functions (CP1C; integration fixes by Claude Code).

Rules are specified in docs/CHECKPOINTS.md, CP1C.
"""

import re

_START = re.compile(r"^\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$", re.IGNORECASE | re.MULTILINE)
_END = re.compile(r"^\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$", re.IGNORECASE | re.MULTILINE)
_PRODUCER = re.compile(r"^(Produced by|E-text prepared by|Transcribed by)", re.IGNORECASE)
_PRODUCER_WINDOW = 40

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_ILLUSTRATION = re.compile(r"\[Illustration[^\]]*\]", re.IGNORECASE)
_FOOTNOTE = re.compile(r"\[\d+\]")
_ITALICS = re.compile(r"_([^_]+)_")
_SCENE_BREAK = re.compile(r"^[\s*\-=]*$")
_DASHES = re.compile(r"-{2,}")
_DOUBLED_COMMA = re.compile(r",(\s*,)+")
_SPACE_BEFORE_COMMA = re.compile(r"\s+,")
_COMMA_BEFORE_STOP = re.compile(r",\s*([.;:!?])")
_COMMA_AFTER_STOP = re.compile(r"([.;:!?]),")


def strip_gutenberg_boilerplate(raw: str) -> str:
    """Remove the Project Gutenberg header, footer and producer credits."""
    # 1. Normalize line endings; drop a leading BOM.
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]

    # 2. Keep only text after the START line (if any).
    start = _START.search(text)
    if start:
        text = text[start.end():]

    # 3. Keep only text before the END line (if any).
    end = _END.search(text)
    if end:
        text = text[: end.start()]

    # 4. A producer line that starts within the first 40 lines is removed together
    #    with the lines directly after it, up to (not including) the next blank line.
    kept: list[str] = []
    skipping = False
    for number, line in enumerate(text.split("\n")):
        if skipping:
            if line.strip():
                continue
            skipping = False
        elif number < _PRODUCER_WINDOW and _PRODUCER.match(line):
            skipping = True
            continue
        kept.append(line)

    # 5. Strip surrounding whitespace.
    return "\n".join(kept).strip()


def _fix_dashes(paragraph: str) -> str:
    paragraph = _DASHES.sub(", ", paragraph)
    paragraph = _DOUBLED_COMMA.sub(",", paragraph)  # ", ," / ",," -> ","
    paragraph = _SPACE_BEFORE_COMMA.sub(",", paragraph)  # " ," -> ","
    paragraph = _COMMA_BEFORE_STOP.sub(r"\1", paragraph)  # "word--." -> "word."
    paragraph = _COMMA_AFTER_STOP.sub(r"\1", paragraph)  # "Mr. ----" -> "Mr."
    return paragraph.lstrip(", ")  # a paragraph that opened with "--"


def clean_for_speech(text: str) -> str:
    """Normalize book text so Piper reads it naturally."""
    cleaned: list[str] = []
    # 1. Paragraphs are separated by one or more blank lines.
    for paragraph in _PARAGRAPH_SPLIT.split(text):
        # 2. Unwrap hard wraps; collapse whitespace runs.
        paragraph = " ".join(paragraph.split())
        # 3. Drop illustrations and footnote markers.
        paragraph = _ILLUSTRATION.sub("", paragraph)
        paragraph = _FOOTNOTE.sub("", paragraph)
        # 4. Underscore italics: _word_ -> word.
        paragraph = _ITALICS.sub(r"\1", paragraph)
        # 5. Drop empty and scene-break paragraphs (only *, -, = and spaces).
        #    Checked BEFORE the dash rule so "-----" is never turned into commas.
        if _SCENE_BREAK.match(paragraph):
            continue
        # 6. "--" -> ", " and tidy the commas it creates. Other commas ("1,000") are untouched.
        paragraph = " ".join(_fix_dashes(paragraph).split())
        if paragraph:
            cleaned.append(paragraph)
    # 7. Rejoin; headings stay as their own short paragraphs.
    return "\n\n".join(cleaned)


def clean(raw: str) -> str:
    """Strip boilerplate, then normalize for speech."""
    return clean_for_speech(strip_gutenberg_boilerplate(raw))
