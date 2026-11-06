# CP2C handoff  Mistral

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
- None. The batch script cannot be fully tested in the Linux sandbox, but follows standard Windows batch conventions.

## Contract change requests
- None

## New dependencies needed
- None (only uses existing `responses` dependency already in requirements.txt)

## Notes for the next agent
- The `run.bat` script assumes Python is in PATH. If this is an issue on Windows, Kayden may need to adjust the PATH or use full paths to python.exe.
- The script activates the virtual environment using the standard `call .venv\Scripts\activate` pattern.
- Voice download uses `scripts\download_voice.py` which is already implemented in CP0.
