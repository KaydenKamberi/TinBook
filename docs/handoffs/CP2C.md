# CP2C handoff — Mistral

## Done
- Created `tests/test_gutenberg.py` with 27 tests covering: search parsing, text_url priority rules (utf-8 > us-ascii > plain), .zip URL skipping, None when no plain text, timeout/HTTP errors raising GutenbergError, invalid parameters, metadata fetching, download_text success/failure cases, mixed-case MIME types, non-string MIME/URL handling, and bad JSON responses
- Created `scripts/run.bat` that: creates .venv if missing, installs requirements.txt only on first creation, downloads default voice if missing, runs `python -m desktop.app`, and pauses on error
- All 346 tests pass (including the 27 new ones)
- No network access in tests (all use `responses` mock)

## How to test
- Run tests: `python -m pytest tests/test_gutenberg.py -v`
- Verify batch script syntax (on Windows): double-click `scripts/run.bat` on a fresh clone
- Run all tests: `python -m pytest tests/`

## Not done / known issues
- The batch script cannot be fully tested in the Linux sandbox, but follows standard Windows batch conventions.
- ~~If the first `pip install` failed, `.venv` still existed, so later runs skipped the install and the app crashed with a missing-module error until `.venv` was deleted by hand.~~ **Fixed by Claude Code**, see below.

## Contract change requests
- None

## New dependencies needed
- None (only uses existing `responses` dependency already in requirements.txt)

## Notes for the next agent
- The `run.bat` script assumes Python is in PATH. If this is an issue on Windows, Kayden may need to adjust the PATH or use full paths to python.exe.
- The script activates the virtual environment using the standard `call .venv\Scripts\activate` pattern.
- Voice download uses `scripts\download_voice.py` which is already implemented in CP0.

---

# Fixed by Claude Code (Wave 2 review)

## `scripts/run.bat`
- **Broken-venv trap:** dependencies are now installed whenever the marker file `.venv\.installed` is missing. The marker is written only after `pip install` succeeds, so a failed install is retried on the next run. The script also recreates `.venv` if `.venv\Scripts\activate.bat` is missing (an interrupted `venv` creation).
- Removed `setlocal enabledelayedexpansion`. It was unused, and it breaks paths that contain `!`.
- The voice check now uses `voices\en_US-lessac-medium.onnx`, not `.venv\..\voices\…`.
- `pip` runs as `python -m pip`, so it is always the venv's own pip.
- Comments use `rem`, and no `echo` inside a `( … )` block contains parentheses, which would end the block early.
- Existing installs: the first run after this change reinstalls once (quick, nothing changes), because old `.venv` folders have no marker.

## `.gitattributes` (new)
- `*.bat text eol=crlf`: `run.bat` is checked out with Windows line endings. cmd.exe can misread batch files with Linux (LF) endings.

## `tests/test_gutenberg.py`
- `test_search_pagination` now checks that `page=2` is actually sent.
- New `test_search_sends_query_language_page_and_user_agent`: checks that `search=`, `languages=en`, `page=1` and the configured `User-Agent` are sent.
- New `test_metadata_and_download_send_user_agent`: checks the request order and the `User-Agent` for `download_text` (metadata, then the text file).
- 29 tests in this file. Full suite: 348 passed.

## Still open
- Many tests here duplicate CP1B's Gutenberg tests in `tests/test_library.py`. That cleanup belongs to CP4C.
