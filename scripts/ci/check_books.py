"""CI wrapper for scripts/check_real_books.py: same report, plus which source was used.

Writes the report to stdout and to the file given with --out. Exit code is the same
as check_real_books.py (0 = every book OK). If Gutendex is down but the fallback
works, the books are OK and the run passes; the log says FALLBACK.

Usage: python scripts/ci/check_books.py --out ci-out/check_real_books.txt [ids...]
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gutenberg_source  # noqa: E402  (scripts/ci)


class Tee(io.TextIOBase):
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("ids", nargs="*", type=int)
    args = parser.parse_args(argv)

    spec = importlib.util.spec_from_file_location("check_real_books", ROOT / "scripts" / "check_real_books.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    ids = args.ids or check.DEFAULT_BOOKS

    gutenberg_source.install()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as report, contextlib.redirect_stdout(Tee(sys.stdout, report)):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("  log: %(levelname)s %(name)s: %(message)s"))
        logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

        results = {}
        for gid in ids:
            start = gutenberg_source.mark()
            results[gid] = check.check_book(gid)
            for line in gutenberg_source.describe(start, gid):
                print(line)
            print()

        up = gutenberg_source.gutendex_was_up()
        status = {True: "UP (primary source used)", False: "DOWN (fallback used)", None: "not contacted"}[up]
        print(f"Gutendex:   {status}")
        print("Summary: " + ", ".join(f"{gid} {'OK' if ok else 'FAILED'}" for gid, ok in results.items()))
        logging.getLogger().removeHandler(handler)
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
