"""Chapter detection functions owned by CP1C."""

import re


def split_chapters(text: str) -> list[tuple[str, str]]:
    """Split cleaned book text into titled chapters."""
    # Split into paragraphs on double newlines
    paragraphs = text.split("\n\n")

    # Define heading patterns
    heading_pattern1 = re.compile(
        r"^(chapter|book|part|volume|letter)\s+([ivxlcdm]+|\d+|[a-z]+(-[a-z]+)?)\b.*$",
        re.IGNORECASE
    )
    heading_pattern2 = re.compile(
        r"^([ivxlcdm]+|\d+)\.?$",
        re.IGNORECASE
    )

    def is_heading(para: str) -> bool:
        para = para.strip()
        if len(para) > 80:
            return False
        return bool(heading_pattern1.match(para) or heading_pattern2.match(para))

    # Step 1: Identify sections
    sections = []
    current_title = "Opening"
    current_body_paragraphs = []

    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if not stripped:
            continue

        if is_heading(stripped):
            # Start new section
            if current_body_paragraphs:
                sections.append((current_title, current_body_paragraphs))
            # New title: strip trailing period
            new_title = stripped.rstrip(".")
            current_title = new_title
            current_body_paragraphs = []
        else:
            current_body_paragraphs.append(paragraph)

    # Don't forget the last section
    if current_body_paragraphs:
        sections.append((current_title, current_body_paragraphs))
    elif sections:  # Last paragraph was a heading with no body
        sections.append((current_title, []))

    # If no sections at all, create one with "Opening"
    if not sections:
        sections.append(("Opening", []))

    # Step 2: Merge tiny sections (< 50 words)
    def word_count(paras):
        total = 0
        for p in paras:
            total += len(p.split())
        return total

    merged_sections = []
    i = 0
    while i < len(sections):
        title, body_paras = sections[i]
        wc = word_count(body_paras)

        if wc < 50:
            # Tiny section - merge into next or previous
            if i < len(sections) - 1:
                # Merge into next
                next_title, next_body = sections[i + 1]
                new_title = f"{title} — {next_title}"
                merged_sections.append((new_title, body_paras + next_body))
                i += 2  # Skip next section
            else:
                # Last section is tiny - merge into previous
                if merged_sections:
                    prev_title, prev_body = merged_sections[-1]
                    new_title = f"{prev_title} — {title}"
                    merged_sections[-1] = (new_title, prev_body + body_paras)
                else:
                    # Only one section and it's tiny
                    merged_sections.append((title, body_paras))
                i += 1
        else:
            merged_sections.append((title, body_paras))
            i += 1

    # Step 3: Fallback / oversize check
    # "if there are fewer than 2 sections, or any section has more than 15,000 words"
    # This means: if (fewer than 2 sections) OR (any section > 15000 words), split
    needs_split = len(merged_sections) < 2
    if not needs_split:
        # Check if any section has > 15000 words
        for title, body_paras in merged_sections:
            if word_count(body_paras) > 15000:
                needs_split = True
                break

    if needs_split:
        # Split all sections that need it
        final_sections = []
        for title, body_paras in merged_sections:
            wc = word_count(body_paras)
            if len(merged_sections) < 2 or wc > 15000:
                final_sections.extend(_split_oversized(title, body_paras, 5000))
            else:
                final_sections.append((title, body_paras))
        merged_sections = final_sections

    # Step 4: Title-case ALL CAPS headings, keep Roman numerals uppercase
    def fix_title_case(title: str) -> str:
        # Check if title is ALL CAPS (excluding spaces and hyphens)
        alpha_chars = [c for c in title if c.isalpha()]
        if alpha_chars and all(c.isupper() for c in alpha_chars):
            # Split into words and title-case
            words = title.split()
            result_words = []
            for word in words:
                # Check if word is a Roman numeral (all uppercase letters, no lowercase)
                if word.isupper() and re.match(r"^[IVXLCDM]+$", word):
                    result_words.append(word)
                else:
                    # Title case: capitalize first letter, lowercase rest
                    if word:
                        result_words.append(word[0].upper() + word[1:].lower())
                    else:
                        result_words.append(word)
            return " ".join(result_words)
        return title

    result = []
    for title, body_paras in merged_sections:
        fixed_title = fix_title_case(title)
        body_text = "\n\n".join(body_paras)
        if not body_text:
            # If body is empty, use the title as body to satisfy "never empty body"
            body_text = fixed_title
        result.append((fixed_title, body_text))

    return result


def _split_oversized(title: str, body_paras: list[str], target_words: int) -> list[tuple[str, str]]:
    """Split a section's body into parts of approximately target_words."""
    if not body_paras:
        return [(title, title)]

    parts = []
    current_paras = []
    current_word_count = 0

    for para in body_paras:
        para_wc = len(para.split())
        if current_word_count + para_wc > target_words and current_paras:
            # End current part
            parts.append((list(current_paras), current_word_count))
            current_paras = []
            current_word_count = 0
        current_paras.append(para)
        current_word_count += para_wc

    # Don't forget the last part
    if current_paras:
        parts.append((list(current_paras), current_word_count))

    # If we ended up with no parts (shouldn't happen), add one
    if not parts and body_paras:
        parts.append((list(body_paras), sum(len(p.split()) for p in body_paras)))

    # Create result with numbered titles
    # If only 1 part, return as single section
    if len(parts) <= 1:
        body_text = "\n\n".join(body_paras)
        if not body_text:
            body_text = title
        return [(title, body_text)]

    result = []
    for i, (paras, _) in enumerate(parts):
        part_title = f"{title}, part {i + 1}"
        body_text = "\n\n".join(paras)
        if not body_text:
            body_text = part_title
        result.append((part_title, body_text))

    return result
