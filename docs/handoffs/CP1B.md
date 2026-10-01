# CP1B handoff — Replit Agent

## Done
- Implemented `core/gutenberg.py` against the contracted Gutendex endpoints using `requests`, configured User-Agent and timeout, English search, and UTF-8 replacement decoding.
- Plain-text downloads prefer UTF-8, then US-ASCII, then other plain-text formats; ZIP URLs are excluded. Search results without text remain visible.
- Timeouts, connection failures, non-200 responses, invalid JSON, and malformed metadata raise user-friendly `GutenbergError`.
- Implemented library creation, loading, newest-first listing, updates, deletion, and zero-padded chapter paths.
- New books have queued status, pending chapters, split-based word counts, UTF-8 raw/chapter text, and an audio directory. Existing books are never overwritten.
- JSON is written to the prescribed sibling `.tmp` file before `os.replace`; threaded writes are serialized within the process. Failed creation rolls back its new directory.
- Added offline storage and mocked HTTP tests in the CP1B-owned `tests/test_library.py`, including error cases, atomicity, rollback, concurrency, path safety, and shared-model compatibility.
- Verification: all 77 repository tests passed, including 48 CP1B tests. Read-only code review found no blocking implementation defects. The unchanged browser scaffold still displays `Tinbook OK`.
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
- GitHub rejected the branch push because remote authentication is unavailable. The CP1B changes are committed locally on `cp1b-replit`; after restoring remote access, run `git push -u origin cp1b-replit`.

## Contract change requests
- None.

## New dependencies needed
- None. Uses the existing `requests`, `pytest`, and `responses` dependencies.

## Notes for the next agent
- `write_json_atomic` is now implemented and can be used by CP1C progress persistence.
- `create_book` writes `book.json` last; a failed creation cleans up only its newly created directory. It does not create `progress.json`, since missing progress means default progress under the contract.
- `save_book` requires an existing book directory. Missing/unreadable books and failed storage operations raise `LibraryError`.
- Path helpers reject traversal, book-directory symlinks, negative indices, and unsupported audio extensions. Supported audio formats are `opus` and `mp3`.
- Library and Gutenberg tests share `tests/test_library.py` to keep this checkpoint's edits within its ownership list. All HTTP in these tests is mocked.
- Record the first three actual search results here after the live check succeeds; do not treat the checkpoint's live acceptance criterion as passed yet.