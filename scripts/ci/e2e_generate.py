"""CI end-to-end check: add a real book with the core pipeline and generate 2 chapters.

Steps: pipeline.add_book(84) (real Gutenberg download, cleaning, splitting, library) →
chapters 3+ are marked "skipped" before the worker starts, so the real JobQueue
generates exactly chapters 1 and 2 with real Piper + ffmpeg and then goes idle →
queue.stop() → check both .opus files exist, are non-empty Ogg files and have a
duration in book.json. Copies them to --out.

Usage: python scripts/ci/e2e_generate.py --library <empty dir> --out ci-out/audio [--id 84]
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAPTERS = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--id", type=int, default=84)
    parser.add_argument("--attempts", type=int, default=3, help="tries for the network part")
    parser.add_argument("--timeout", type=float, default=900, help="seconds to wait for generation")
    args = parser.parse_args(argv)

    os.environ["TINBOOK_LIBRARY_DIR"] = str(args.library.resolve())
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="  log: %(levelname)s %(name)s: %(message)s")

    import gutenberg_source
    from core import gutenberg, jobs, library, pipeline
    from core.config import get_config

    gutenberg_source.install()
    print(f"Library: {get_config().library_dir}")
    print(f"Voice:   {get_config().default_voice}, format {get_config().audio_format}")

    # Network part (download + clean + split + create), with retries.
    book = None
    for attempt in range(1, args.attempts + 1):
        start = gutenberg_source.mark()
        try:
            book = pipeline.add_book(args.id)
        except gutenberg.GutenbergError as error:
            print(f"add_book attempt {attempt}/{args.attempts} failed: {error}")
            for line in gutenberg_source.describe(start, args.id):
                print(line)
            if attempt < args.attempts:
                time.sleep(15 * attempt)
            continue
        for line in gutenberg_source.describe(start, args.id):
            print(line)
        break
    if book is None:
        print("FAIL: could not add the book")
        return 1
    print(f"Added {book.id}: {len(book.chapters)} chapters")
    for ch in book.chapters[:CHAPTERS]:
        print(f"  chapter {ch.index + 1}: {ch.title} ({ch.word_count:,} words)")
    if len(book.chapters) < CHAPTERS:
        print(f"FAIL: expected at least {CHAPTERS} chapters")
        return 1

    # Only generate the first 2 chapters: skip the rest before the worker starts.
    book = library.get_book(book.id)
    for ch in book.chapters[CHAPTERS:]:
        ch.status = "skipped"
    library.save_book(book)

    queue = jobs.get_queue()
    started = time.monotonic()
    queue.start()
    try:
        last = None
        while True:
            book = library.get_book(book.id)
            done = [ch.index for ch in book.chapters[:CHAPTERS] if ch.status == "done"]
            state = (book.status, tuple(done))
            if state != last:
                print(f"  [{time.monotonic() - started:6.1f} s] status {book.status}, done {[i + 1 for i in done]}")
                last = state
            if len(done) == CHAPTERS or book.status == "error":
                break
            if time.monotonic() - started > args.timeout:
                print(f"FAIL: generation did not finish within {args.timeout:.0f} s")
                return 1
            time.sleep(1)
    finally:
        queue.stop()
    elapsed = time.monotonic() - started
    print(f"Queue stopped after {elapsed:.1f} s")
    if book.status == "error":
        print(f"FAIL: book error: {book.error}")
        return 1

    ok = True
    args.out.mkdir(parents=True, exist_ok=True)
    total_audio = 0.0
    for ch in book.chapters[:CHAPTERS]:
        path = library.chapter_audio_path(book.id, ch.index, book.audio_format)
        size = path.stat().st_size if path.exists() else 0
        with_header = size > 4 and path.read_bytes()[:4] == b"OggS"
        has_duration = isinstance(ch.duration_sec, (int, float)) and ch.duration_sec > 0
        good = size > 0 and has_duration and (book.audio_format != "opus" or with_header)
        ok &= good
        total_audio += ch.duration_sec or 0
        print(f"  {'OK  ' if good else 'FAIL'} {path.name}: {size:,} bytes, duration {ch.duration_sec} s, Ogg header {with_header}")
        if path.exists():
            shutil.copy2(path, args.out / f"{book.id}-{path.name}")
    extra = [p.name for p in library.book_dir(book.id).joinpath("audio").iterdir() if p.name[:3] not in ("000", "001")]
    if extra:
        print(f"Note: other files in audio/: {extra}")
    if total_audio:
        print(f"Generated {total_audio / 60:.1f} min of audio in {elapsed:.0f} s ({total_audio / elapsed:.1f}x real time)")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
