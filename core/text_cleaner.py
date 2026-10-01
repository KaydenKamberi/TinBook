"""Gutenberg text cleaning functions owned by CP1C."""

import re


def strip_gutenberg_boilerplate(raw: str) -> str:
    """Remove Project Gutenberg boilerplate."""
    # 1. Normalize line endings and remove BOM
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]

    # 2. Find START marker
    start_pattern = re.compile(
        r"^\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$",
        re.IGNORECASE | re.MULTILINE
    )
    start_match = start_pattern.search(text)
    if start_match:
        text = text[start_match.end():]

    # 3. Find END marker
    end_pattern = re.compile(
        r"^\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$",
        re.IGNORECASE | re.MULTILINE
    )
    end_match = end_pattern.search(text)
    if end_match:
        text = text[:end_match.start()]

    # 4. Remove producer lines and following lines until blank line in first 40 lines
    lines = text.split("\n")
    first_40 = lines[:40]
    producer_pattern = re.compile(
        r"^(Produced by|E-text prepared by|Transcribed by)",
        re.IGNORECASE
    )
    result_lines = []
    skip_until_blank = False
    for i, line in enumerate(lines):
        if i < len(first_40):
            if skip_until_blank:
                if line.strip() == "":
                    skip_until_blank = False
                continue
            if producer_pattern.match(line):
                skip_until_blank = True
                continue
        result_lines.append(line)

    text = "\n".join(result_lines)

    # 5. Strip leading/trailing whitespace
    text = text.strip()

    return text


def clean_for_speech(text: str) -> str:
    """Normalize text for speech synthesis."""
    # 1. Split into paragraphs on one or more blank lines
    paragraphs = re.split(r"\n\s*\n", text)

    cleaned_paragraphs = []

    for paragraph in paragraphs:
        # 2. Join lines with single space and collapse runs of spaces/tabs
        paragraph = re.sub(r"\s+", " ", paragraph).strip()

        # 3. Remove [Illustration...] blocks and footnote markers
        paragraph = re.sub(r"\[Illustration[^\]]*\]", "", paragraph, flags=re.IGNORECASE)
        paragraph = re.sub(r"\[\d+\]", "", paragraph)

        # 4. Remove underscores used for italics
        paragraph = re.sub(r"_([^_]+)_", r"\1", paragraph)

        # 5. Replace -- with comma, then fix doubled punctuation and space-before-punctuation
        paragraph = paragraph.replace("--", ", ")
        paragraph = re.sub(r"\s*,\s*", ", ", paragraph)
        paragraph = re.sub(r"\s*,", ",", paragraph)

        # Clean up multiple spaces that might have been introduced
        paragraph = re.sub(r"\s+", " ", paragraph).strip()

        # 6. Drop empty paragraphs or scene-break paragraphs
        if paragraph.strip() == "":
            continue
        if re.match(r"^[\s\*\-\=]+$", paragraph):
            continue

        cleaned_paragraphs.append(paragraph)

    # 7. Rejoin paragraphs
    return "\n\n".join(cleaned_paragraphs)


def clean(raw: str) -> str:
    """Strip boilerplate and normalize text for speech."""
    return clean_for_speech(strip_gutenberg_boilerplate(raw))
