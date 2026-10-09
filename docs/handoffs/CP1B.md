# CP1B handoff — Replit Agent

## Done
- Implemented `core/gutenberg.py` against the contracted Gutendex endpoints using `requests`, configured User-Agent and timeout, English search, and UTF-8 replacement decoding.
- Plain-text downloads prefer UTF-8, then US-ASCII, then other plain-text formats; ZIP URLs are excluded. Search results without text remain visible.
- Timeouts, connection failures, non-200 responses, invalid JSON, and malformed single-book metadata raise user-friendly `GutenbergError`. Search skips individual malformed results with a warning.
- Implemented library creation, loading, newest-first listing, updates, deletion, and zero-padded chapter paths.
- New books have queued status, pending chapters, split-based word counts, UTF-8 raw/chapter text, and an audio directory. Existing books with `book.json` are never overwritten.
- JSON is written to the prescribed sibling `.tmp` file before `os.replace`; threaded writes are serialized within the process. Failed creation rolls back its new directory.
- Added offline storage and mocked HTTP tests in the CP1B-owned `tests/test_library.py`, including error cases, atomicity, rollback, concurrency, path safety, and shared-model compatibility.
- Verification after review fixes: all 151 repository tests passed, including 122 CP1B tests.
- Only CP1B implementation/test files and this required handoff were changed.

## How to test
Run all commands from the repository root:

```bash
python -m pytest -q tests/test_library.py
python -m pytest -q
```

Repeat the required live check when Gutendex is available:

```bash
python - <<'PY'
import json
from core.gutenberg import search, download_text

results = search("crime and punishment")
print(json.dumps([result.to_dict() for result in results[:3]], ensure_ascii=False, indent=2))
assert any(result.gutenberg_id == 2554 for result in results[:3])
text = download_text(2554)
print("Downloaded characters:", len(text))
assert "*** START OF" in text
PY
```

## Not done / known issues
- **The live acceptance check is blocked by Gutendex availability.** On 2026-10-01, `search("crime and punishment")` timed out at the configured 20-second limit. An independent HTTPS request to the same search endpoint, allowing up to 90 seconds, returned HTTP 503 `Service Unavailable`. The metadata endpoint `/books/2554/` also timed out during a separate 40-second diagnostic request.
- **First three live search results:** unavailable; no real search response was obtained. No fixture results are presented as live results.
- Consequently, ID 2554's live rank and `download_text(2554)` containing `*** START OF` could not be verified. Mocked tests cover these code paths and replacement decoding, but do not replace the required live check.
- No service fallback or timeout-contract change was added to conceal the outage.

## Review fixes
- `list_books` catches `Exception` for each folder, logs a warning, and skips it, so deeply nested JSON or unexpected loader failures cannot crash the entire listing.
- `get_book` validates book and chapter field types, enums, integer ranges, and finite non-negative durations. Invalid metadata, including excessive JSON nesting, raises `LibraryError`; unknown fields and missing `chapters` remain supported.
- `create_book` builds all files in a unique temporary sibling directory and renames it to the final book directory only when complete. Existing folders without `book.json` are recoverable crash leftovers; folders with metadata remain protected. Staging folders are excluded from listings, and failed staging is cleaned up.
- Gutenberg search skips malformed individual results, such as `download_count: null`, with a warning while preserving valid results and their order. Whole-response failures and malformed single-book metadata still raise `GutenbergError`.
- Added regression tests for nested JSON, unexpected loader exceptions, invalid book/chapter fields, staged publication, crash recovery, cleanup and retry, protection of complete books, and malformed search results. Removed the stale failed-push note.

## Contract change requests
- None.

## New dependencies needed
- None. Uses the existing `requests`, `pytest`, and `responses` dependencies.

## Notes for the next agent
- `write_json_atomic` is now implemented and can be used by CP1C progress persistence.
- `create_book` writes `book.json` last in a temporary sibling folder, then publishes the complete folder by rename. Failed staging cleans up its temporary folder; folders without `book.json` can be replaced on re-add. It does not create `progress.json`, since missing progress means default progress under the contract.
- `save_book` requires an existing book directory. Missing/unreadable books and failed storage operations raise `LibraryError`.
- Path helpers reject traversal, book-directory symlinks, negative indices, and unsupported audio extensions. Supported audio formats are `opus` and `mp3`.
- Library and Gutenberg tests share `tests/test_library.py` to keep this checkpoint's edits within its ownership list. All HTTP in these tests is mocked.
- Record the first three actual search results here after the live check succeeds; do not treat the checkpoint's live acceptance criterion as passed yet.