# CP0 handoff — Replit Agent
## Done
- Created the Phase 1 package layout and contract stubs for later checkpoints.
- Implemented configuration loading, environment overrides, directory creation, data models, serialization helpers, `slugify`, and `now_iso`.
- Added the Piper voice downloader and verified it with `en_US-lessac-medium`.
- Added a smoke test that loads Piper, synthesizes WAV audio, and converts it to mono 32 kbps Opus with ffmpeg/libopus.
- Added the CP0 browser/pywebview launcher stub and configured the Replit browser workflow.
- Added and passed model and configuration tests.
- Installed and verified `piper-tts==1.8.0`.

## How to test
- `cd tinbook/tinbook`
- `python scripts/download_voice.py en_US-lessac-medium`
- `python scripts/smoke_test.py`
- `pytest -q`
- `python -m desktop.app --browser`, then open `/` on port 5000 and confirm `Tinbook OK`.

## Not done / known issues
- Windows smoke testing has not been run yet; Kayden still needs to run the download and smoke-test commands on Windows.
- The browser stub intentionally has no favicon, so a browser may request `/favicon.ico` and receive 404.

## Contract change requests
- None

## New dependencies needed
- None

## Notes for the next agent
- The exact installed Piper package is `piper-tts==1.8.0`.
- The working Python imports and calls are:
  - `from piper import PiperVoice`
  - `voice = PiperVoice.load(str(model_path))`
  - `with wave.open(str(wav_path), "wb") as wav_file: voice.synthesize_wav("Hello from Tinbook.", wav_file)`
- In 1.8.0, `PiperVoice.synthesize()` returns an iterable of audio chunks; it does not accept a writable file as its second positional argument.
- ffmpeg was found through `imageio_ffmpeg.get_ffmpeg_exe()` and accepted `-c:a libopus -b:a 32k -ac 1`.
---

# CP0 fix — Claude Code (integration)
Branch `cp0-fix-claude`, from `main` after the CP0 merge.

## Changed
- **Repo layout:** used `git mv` to move everything from `tinbook/tinbook/` to the repo root, so `git log --follow` still shows file history. Deleted the empty `tinbook/` folders. **All commands now run from the repo root. Ignore the `cd tinbook/tinbook` line in "How to test" above.**
- **`.replit`:** the run command is now `python -m desktop.app --browser`, with no `cd`. There is no separate `replit.nix`; the Nix packages (`ffmpeg-full`, `xvfb-run`) still live in `.replit`.
- **`.gitignore` (new):** ignores venvs, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `library/`, `voices/`, `*.onnx`, `*.onnx.json`, `*.opus`, `*.wav`, `*.mp3`, `*.img`, `config.local.json`, `.DS_Store` and `Thumbs.db`.
- **`scripts/download_voice.py`:** the speaker and quality parts can now contain `_`, e.g. `en_US-libritts_r-medium`, `en_GB-northern_english_male-medium`, `en_US-amy-x_low`.
- **`core/models.py`:**
  - `slugify` converts accented letters to ASCII (NFKD, then drops combining marks) and returns `"book"` if the slug would be empty.
  - Bug fix: a word ending exactly at character 40 used to be dropped. It is now kept (`slug[:41].rfind("-")`).
  - `Book.from_dict` defaults a missing `chapters` key to `[]`.
  - `total_duration_sec()` always returns a `float`.
- **`core/config.py`:**
  - Empty-string `TINBOOK_*` env vars are treated as unset.
  - The repo root is now the private module constant `_ROOT_DIR`, so tests can point config at a tmp folder. The public `get_config()` is unchanged.
- **`scripts/smoke_test.py`:** `imageio_ffmpeg` is now imported inside `find_ffmpeg()`, and it falls back to `ffmpeg` on PATH if the import fails.
- **`desktop/app.py`:** removed the unused `socket` import.
- **Tests:**
  - `tests/test_config.py` uses a tmp root, so it never reads a real `config.local.json`. It now covers defaults, local config overriding `config.json`, env overriding both, empty env vars, and invalid `TINBOOK_PORT` values (`abc`, `-1`, `65536`).
  - `tests/test_models.py` covers the exact "cut at last `-`" rule, accent handling, the `"book"` fallback, a missing `chapters` key, and a float zero duration.
  - `tests/test_download_voice.py` (new) covers parsing voice names into paths, and rejecting malformed names.
- Stub modules were not touched: gutenberg, text_cleaner, chapters, progress, library, tts, jobs, pipeline, server and device_sync.

## Contract updates (ARCHITECTURE.md §3)
- The slug rule now covers ASCII transliteration, cutting at the last `-` at or before position 40, and the `"book"` fallback for an empty slug.
- New rule: `Book.from_dict` treats a missing `chapters` key as `[]`.

## How to test (from the repo root)
- `pip install -r requirements.txt`
- `pytest -q`
- `python -m desktop.app --browser`, then `curl http://127.0.0.1:5000/` should return `Tinbook OK`.

## Still open
- Kayden still needs to run the Windows smoke test (`python scripts/download_voice.py en_US-lessac-medium`, then `python scripts/smoke_test.py`). It is a CP0 acceptance criterion.
- Everyone's local checkouts need a fresh pull, because every path changed. Wave 1 branches must be created from `main` after this merges.
