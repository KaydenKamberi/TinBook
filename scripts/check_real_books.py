"""Run real Gutenberg books through download -> clean -> split and print the chapters.

CP3 check of the text pipeline on real books. Needs internet. Nothing is added to
the library and no audio is generated.

Usage (from the repo root):
    python scripts/check_real_books.py               # 84, 2554 and 1342
    python scripts/check_real_books.py 84 98         # any Gutenberg IDs
    python scripts/check_real_books.py --all 2554    # print every chapter title
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import chapters, gutenberg, text_cleaner

DEFAULT_BOOKS = [84, 2554, 1342]  # Frankenstein, Crime and Punishment, Pride and Prejudice
TITLES_SHOWN = 5


def check_book(gutenberg_id: int, show_all: bool = False) -> bool:
    """Print a report for one book. Returns False if any step failed."""
    print(f"=== Book {gutenberg_id}")
    started = time.monotonic()
    try:
        meta = gutenberg.get_metadata(gutenberg_id)
        print(f"Title:      {meta.title}")
        print(f"Authors:    {', '.join(meta.authors) or 'unknown'}")
        raw = gutenberg.download_text(gutenberg_id)
    except gutenberg.GutenbergError as error:
        print(f"FAILED to download: {error}\n")
        return False
    cleaned = text_cleaner.clean(raw)
    sections = chapters.split_chapters(cleaned)
    words = [len(body.split()) for _, body in sections]
    print(f"Downloaded: {len(raw):,} characters ({time.monotonic() - started:.1f} s)")
    print(f"Cleaned:    {len(cleaned):,} characters, {sum(words):,} words")
    print(f"Chapters:   {len(sections)}  (words per chapter: min {min(words):,}, max {max(words):,})")
    shown = sections if show_all else sections[:TITLES_SHOWN]
    label = "All titles:" if show_all else f"First {len(shown)}:"
    print(label)
    for index, (title, body) in enumerate(shown, start=1):
        print(f"  {index:>3}. {title}  ({len(body.split()):,} words)")
    if not show_all and len(sections) > TITLES_SHOWN:
        print(f"  ...  last: {sections[-1][0]}")
    print()
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", type=int, help="Gutenberg book IDs (default: 84 2554 1342)")
    parser.add_argument("--all", action="store_true", help="print every chapter title")
    args = parser.parse_args(argv)
    ids = args.ids or DEFAULT_BOOKS
    results = {gid: check_book(gid, args.all) for gid in ids}
    print("Summary: " + ", ".join(f"{gid} {'OK' if ok else 'FAILED'}" for gid, ok in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
