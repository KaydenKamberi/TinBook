# Checkpoints

Work is split into **waves**. Checkpoints in the same wave run **in parallel** on separate branches and never touch the same files. Merge a whole wave into `main`, test, then start the next wave.

```
PHASE 1 — DESKTOP
CP0  Replit ─────────────── scaffold + smoke test (solo)
        │
Wave 1 ├─ CP1A Claude   tts.py + jobs.py
       ├─ CP1B Replit   gutenberg.py + library.py
       └─ CP1C Mistral  text_cleaner.py + chapters.py + progress.py + tests
        │   merge order: 1C → 1B → 1A
Wave 2 ├─ CP2A Replit   server.py + pipeline.py + app.py
       ├─ CP2B Claude   frontend (html/css/js)
       └─ CP2C Mistral  tests for gutenberg/library + run.bat
        │   merge order: 2A → 2C → 2B
CP3  Claude ─────────────── integration + review (solo)
        │
Wave 4 ├─ CP4A Claude   player polish (media keys, edge cases)
       ├─ CP4B Replit   settings + regenerate + delete UI
       └─ CP4C Mistral  error-message pass + test cleanup
             ★ PHASE 1 MILESTONE: listen to a book on your PC while coding

PHASE 2 — DEVICE (after parts arrive)
CP5  Claude + Kayden ────── Pi OS setup script + library image (solo)
        │
Wave 6 ├─ CP6A Claude   player.py + bluetooth.py
       ├─ CP6B Replit   display.py + buttons.py
       └─ CP6C Mistral  power.py + desktop/device_sync.py
        │
CP7  Claude ─────────────── device main app + USB sync mode + service (solo)
CP8  Kayden + Claude ────── assembly, Altoids fit, battery tuning, field test
             ★ PHASE 2 MILESTONE: a full walk listening from the tin
```

Every checkpoint below lists: **Owner · Depends on · Branch · Owns (create/edit) · Reads (don't edit) · Tasks · Acceptance criteria**. Kickoff prompt template is in `README.md`.

---

# PHASE 1 — DESKTOP

## CP0 — Scaffold & smoke test
**Owner:** Replit · **Depends on:** nothing · **Branch:** `cp0-replit`
**Owns:** `requirements.txt`, `config.json`, `core/__init__.py`, `core/config.py`, `core/models.py`, stub files for every other `core/` and `desktop/` module in ARCHITECTURE §1, `desktop/__init__.py`, `desktop/app.py` (stub), `scripts/download_voice.py`, `scripts/smoke_test.py`, `tests/__init__.py`, `tests/test_models.py`, `tests/test_config.py`, Replit config files.

**Tasks**
1. Create the folder layout from ARCHITECTURE §1 (Phase 1 parts only: `core/`, `desktop/`, `scripts/`, `tests/`). For every module owned by a later checkpoint, create a **stub**: module docstring naming its owner checkpoint + the exact signatures from ARCHITECTURE §5 raising `NotImplementedError`, plus its exception class. Other agents will replace these stubs.
2. `requirements.txt` (pin major versions, e.g. `flask>=3,<4`): `flask`, `pywebview`, `requests`, `piper-tts`, `imageio-ffmpeg`, `pytest`, `responses`.
3. Implement `core/config.py` and `core/models.py` **fully** per ARCHITECTURE §2–3 (including `slugify` and `now_iso`).
4. `config.json` with the defaults from ARCHITECTURE §2.
5. `scripts/download_voice.py <voice_name>`: downloads `<voice>.onnx` and `<voice>.onnx.json` into `voices_dir`. URL pattern: `https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{lang_region}/{name}/{quality}/{voice}.onnx` where voice = `{lang_region}-{name}-{quality}` and `lang` = part of `lang_region` before `_` (e.g. `en_US-lessac-medium` → `en/en_US/lessac/medium/`). Show progress; skip if already present.
6. `scripts/smoke_test.py`: (a) imports piper, loads the default voice, synthesizes "Hello from Tinbook." to `smoke.wav`; (b) finds ffmpeg (`imageio_ffmpeg.get_ffmpeg_exe()`, else `ffmpeg` on PATH) and converts `smoke.wav` → `smoke.opus` with `-c:a libopus -b:a 32k -ac 1`; (c) prints a PASS/FAIL table. Check the installed piper-tts version's Python API (it changed between versions) and use the correct one.
7. `desktop/app.py` stub: `python -m desktop.app --browser` starts a Flask app on `0.0.0.0:5000` that returns "Tinbook OK" at `/`. Without `--browser`, opens a pywebview window pointed at a local Flask server on `127.0.0.1` (free port).
8. Tests: `tests/test_models.py` (round-trip to_dict/from_dict, slugify cases: `"Crime and Punishment"`→`crime-and-punishment`, `"  Hello!!  World "`→`hello-world`, long titles ≤40 chars), `tests/test_config.py` (env override works).

**Acceptance criteria**
- `pip install -r requirements.txt` works on Replit.
- `pytest` passes.
- `python scripts/smoke_test.py` passes on Replit. **Kayden also runs it on Windows** — note in the handoff whether that passed (Kayden will tell you) and any fixes needed.
- Handoff lists the exact piper-tts version and the Python API calls that work.

---

## Wave 1 (parallel)

### CP1A — TTS engine + job queue
**Owner:** Claude Code · **Depends on:** CP0 · **Branch:** `cp1a-claude`
**Owns:** `core/tts.py`, `core/jobs.py`, `tests/test_tts.py`, `tests/test_jobs.py`
**Reads:** `core/config.py`, `core/models.py`, `core/library.py` (stub — code against the contract; CP1B implements it)

**Tasks**
1. `tts.py` per ARCHITECTURE §5. Cache loaded `PiperVoice` objects per voice. Synthesize chapter → WAV in a temp dir → ffmpeg → `out_path.part` → rename. Duration from WAV frames. Support engine fallback: if the Python package fails to import, use a `piper` executable on PATH via subprocess (document how to install it in the handoff).
2. Detect ffmpeg + libopus once (run `ffmpeg -hide_banner -encoders` and look for `libopus`). If opus is unavailable, `check_environment()["opus"] = False` and synthesis with `audio_format="opus"` raises `TTSError` with a helpful message (the config can switch to mp3).
3. For long chapters, feed Piper paragraph by paragraph into the same WAV to keep memory flat.
4. `jobs.py` per ARCHITECTURE §5 (singleton, one worker thread, resume on start, retry a failed chapter once, save after each chapter, reload book before save).
5. Tests: mock Piper and ffmpeg (no real synthesis in tests). Test resume logic, retry, status transitions.

**Acceptance criteria**
- With a real voice installed: a 3-chapter fake book created via `core.library` (after merge) generates 3 playable `.opus` files; `book.json` ends `ready` with durations.
- Killing the process mid-book and restarting resumes from the missing chapter.
- `pytest` passes without network or real Piper.

### CP1B — Gutenberg client + library storage
**Owner:** Replit · **Depends on:** CP0 · **Branch:** `cp1b-replit`
**Owns:** `core/gutenberg.py`, `core/library.py`, `tests/test_library.py`
**Reads:** `core/config.py`, `core/models.py`

**Tasks**
1. `gutenberg.py` per ARCHITECTURE §5 using `requests`. Handle timeouts, non-200s, and bad JSON with `GutenbergError` (user-friendly messages).
2. `library.py` per ARCHITECTURE §4–5. Atomic JSON writes. `create_book` writes raw.txt, `text/NNN.txt` (UTF-8), `book.json` with chapters `pending`, word counts via `len(text.split())`.
3. `tests/test_library.py` using `tmp_path` + `TINBOOK_LIBRARY_DIR` (clear `get_config` cache between tests).
4. Manually verify on Replit: `search("crime and punishment")` returns id 2554 near the top; `download_text(2554)` returns text containing "*** START OF".

**Acceptance criteria**
- Library tests pass. Manual Gutendex check documented in handoff (paste the first 3 results).

### CP1C — Text cleaning, chapter splitting, progress
**Owner:** Mistral · **Depends on:** CP0 · **Branch:** `cp1c-mistral`
**Owns:** `core/text_cleaner.py`, `core/chapters.py`, `core/progress.py`, `tests/fixtures/*`, `tests/test_text_cleaner.py`, `tests/test_chapters.py`, `tests/test_progress.py`
**Reads:** `core/models.py`

Implement **exactly** these rules. Do not add extra behavior.

**`strip_gutenberg_boilerplate(raw)`**
1. Normalize line endings to `\n`. Remove a leading BOM (`\ufeff`).
2. Find the first line matching regex `^\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$` (case-insensitive, multiline). Keep only text **after** that line. If not found, keep from the start.
3. Find the first line matching `^\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$` (case-insensitive). Keep only text **before** it. If not found, keep to the end.
4. In the first 40 lines of what remains, remove lines starting with `Produced by`, `E-text prepared by`, or `Transcribed by` (case-insensitive), plus any lines directly after them until the next blank line.
5. Strip leading/trailing whitespace of the whole result.

**`clean_for_speech(text)`**
1. Split into paragraphs on one or more blank lines (`\n\s*\n`).
2. Within each paragraph, join lines with a single space (unwrap hard wraps) and collapse runs of spaces/tabs to one space.
3. Remove `[Illustration...]` blocks (regex `\[Illustration[^\]]*\]`, case-insensitive) and footnote markers like `[1]`, `[23]` (regex `\[\d+\]`).
4. Remove underscores used for italics: `_word_` → `word` (regex `_([^_]+)_` → `\1`).
5. Replace `--` with `, ` then fix doubled punctuation `, ,` → `,` and space-before-punctuation ` ,` → `,`.
6. Drop paragraphs that are empty after cleaning, or that consist only of `*`, `-`, `=` characters and spaces (scene-break rules).
7. Rejoin paragraphs with `\n\n`. Keep headings as their own paragraphs (they're just short paragraphs).

**`split_chapters(text)`** (input is cleaned text: paragraphs separated by `\n\n`)
1. A paragraph is a **heading** if it is ≤ 80 characters and matches (case-insensitive) either:
   - `^(chapter|book|part|volume|letter)\s+([ivxlcdm]+|\d+|[a-z]+(-[a-z]+)?)\b.*$`, or
   - `^([ivxlcdm]+|\d+)\.?$` (a bare Roman or Arabic numeral)
2. Walk paragraphs. Each heading starts a new section; its title is the heading text (strip trailing `.`). Paragraphs before the first heading form a section titled `"Opening"`.
3. **Merge tiny sections:** any section whose body has fewer than 50 words is merged **into the next** section: the next section's title becomes `"<tiny title> — <next title>"` and the tiny body (if any) is prepended. (This absorbs tables of contents and "PART ONE" + "CHAPTER I" stacks.) If the last section is tiny, merge it into the previous one instead (keep the previous title).
4. **Fallback / oversize:** if there are fewer than 2 sections, or any section has more than 15,000 words, split that section's body at paragraph boundaries into parts of ~5,000 words (a part ends at the first paragraph boundary after reaching 5,000 words). Titles: `"<title>, part 1"`, `"<title>, part 2"`… (for the whole-book fallback, title is `"Part 1"`, `"Part 2"`…).
5. Title-case headings that are ALL CAPS (`"CHAPTER I"` → `"Chapter I"`); leave Roman numerals uppercase (`I`, `IV`, `XII`).
6. Return `[(title, body_text)]` with bodies joined by `\n\n`. Never return an empty list; never return an empty body.

**`progress.py`** exactly per ARCHITECTURE §5.

**Fixtures & tests**
- `tests/fixtures/sample_book.txt`: ~60 lines, fake Gutenberg header + footer, "Produced by" line, a 4-entry table of contents, `PART ONE`, `CHAPTER I`, `CHAPTER II`, `CHAPTER III` with a few hundred words each (use lorem-style filler), an `[Illustration: x]`, a `_italic_` word, a `--`.
- `tests/fixtures/no_chapters.txt`: header/footer + ~12,000 words of filler paragraphs, no headings.
- Tests: boilerplate removed; illustration/footnote/underscore removed; hard wraps unwrapped; TOC merged (first chapter title contains "Chapter I"); `no_chapters.txt` → 3 parts; progress save/load round-trip; corrupt progress.json → default; `newer()` picks later timestamp.

**Acceptance criteria:** `pytest tests/test_text_cleaner.py tests/test_chapters.py tests/test_progress.py` passes. Only owned files changed.

**Merge Wave 1:** 1C → 1B → 1A. Kayden runs `pytest` on `main`.

---

## Wave 2 (parallel)

### CP2A — API server, pipeline, launcher
**Owner:** Replit · **Depends on:** Wave 1 · **Branch:** `cp2a-replit`
**Owns:** `desktop/server.py`, `desktop/app.py`, `core/pipeline.py`, `tests/test_server.py`
**Reads:** all of `core/`

**Tasks**
1. `core/pipeline.py` per ARCHITECTURE §5.
2. `desktop/server.py`: `create_app() -> Flask` implementing every Phase 1 route in ARCHITECTURE §6 (skip `/api/device*` — CP6C). Serve `desktop/templates/index.html` and `desktop/static/`. Call `get_queue().start()` once at app creation. `POST /api/books` runs download → clean → split inside the request (a few seconds) and returns 201; only TTS runs in the background queue.
3. `desktop/app.py`: `--browser` → run on `0.0.0.0:5000`. Default → start Flask on `127.0.0.1` free port in a daemon thread, then `webview.create_window("Tinbook", url, width=420, height=720, min_size=(360, 560))` and `webview.start()`. On window close, the frontend already saved progress; exit cleanly (`queue.stop()`).
4. `tests/test_server.py` with Flask test client, mocking `core.gutenberg` network calls.

**Acceptance criteria:** in Replit `--browser` mode, `curl /api/search?q=frankenstein` returns results, `POST /api/books {"gutenberg_id": 84}` creates a book, `/api/jobs` shows it generating, and `/api/books/<id>/chapters/0/audio` serves audio once done (test Range with `curl -r 0-100`).

### CP2B — Frontend
**Owner:** Claude Code · **Depends on:** Wave 1 (contracts only) · **Branch:** `cp2b-claude`
**Owns:** `desktop/templates/index.html`, `desktop/static/app.js`, `desktop/static/style.css`
**Reads:** ARCHITECTURE §6–7

**Tasks**
1. Three views (Library / Search / Player) in a compact, calm, readable UI sized for a ~420px-wide window; dark and light via `prefers-color-scheme`.
2. **Library:** cards with title, author, status pill, "12/39 chapters", % listened, Continue button. Poll every 3s while anything is generating.
3. **Search:** input + results; disabled "No text version" for results without `text_url`; Add button shows spinner, then jumps to Library.
4. **Player:** title, chapter title, seek bar, elapsed/remaining, play/pause, −30/+30, prev/next chapter, speed selector (0.75–2.0), collapsible chapter list with per-chapter status. Implements PRD D-6, D-7, D-8 exactly (auto-advance with waiting state; progress PUT every 5s, on pause, on chapter change, on `beforeunload`/`visibilitychange`).
5. Resume: opening a book loads progress, sets `playbackRate`, seeks to `position_sec` after `loadedmetadata`.
6. Develop against the contract; until CP2A merges, you may use a tiny mock in a local branch but **do not commit mocks**.

**Acceptance criteria:** after merge with CP2A, Kayden can search, add, and listen on Windows; closing and reopening resumes within 5 seconds of where he stopped.

### CP2C — Tests & Windows run script
**Owner:** Mistral · **Depends on:** Wave 1 · **Branch:** `cp2c-mistral`
**Owns:** `tests/test_gutenberg.py`, `scripts/run.bat`
**Reads:** `core/gutenberg.py`, `core/library.py`

**Tasks**
1. `tests/test_gutenberg.py` using `responses` to mock Gutendex: search parsing, `text_url` priority rules (ARCHITECTURE §5), `.zip` URLs skipped, `None` when no plain text, timeout → `GutenbergError`, 500 → `GutenbergError`.
2. `scripts/run.bat`: from repo root, create `.venv` if missing, activate, `pip install -r requirements.txt` only if `.venv` was just created, download the default voice if `voices\en_US-lessac-medium.onnx` is missing (`python scripts\download_voice.py en_US-lessac-medium`), then `python -m desktop.app`. Pause on error so the window doesn't vanish.

**Acceptance criteria:** tests pass with no network. Kayden double-clicks `run.bat` on a fresh clone and the app opens.

**Merge Wave 2:** 2A → 2C → 2B.

---

## CP3 — Integration & review (solo)
**Owner:** Claude Code · **Depends on:** Wave 2 · **Branch:** `cp3-claude`
**Owns:** anything (integration checkpoint — see CLAUDE.md)

**Tasks**
1. Read all handoffs. Resolve every Contract change request (update ARCHITECTURE.md if changed).
2. Review Mistral's modules for correctness on 3 real books: *Crime and Punishment* (2554), *Frankenstein* (84), *Pride and Prejudice* (1342). Report chapter counts and first 5 titles for each; fix splitting issues.
3. Walk through Flows A and B (PRD §4) with Kayden on Windows. Fix bugs.
4. Make sure a crash mid-generation resumes cleanly and `pytest` passes.

**Acceptance criteria:** Kayden listens to Frankenstein chapter 1 → 2 auto-advance on Windows, closes the app, reopens, and resumes correctly.

---

## Wave 4 — Polish (parallel)

### CP4A — Player polish
**Owner:** Claude Code · **Branch:** `cp4a-claude` · **Owns:** `desktop/static/app.js`, `desktop/static/style.css`, `desktop/templates/index.html`
Keyboard shortcuts (D-9), Media Session API (title/artist/chapter, play/pause/seek handlers), buffering/error states, waiting-for-chapter state polish. Leave a `<div id="settings-root"></div>` in the Library view and a `<script src="/static/settings.js">` tag for CP4B. **Do this first and push early** so CP4B can hook in.

### CP4B — Settings, regenerate, delete
**Owner:** Replit · **Branch:** `cp4b-replit` · **Owns:** `desktop/static/settings.js`, `desktop/server.py` (only if a route needs fixing)
Renders into `#settings-root`: voice dropdown from `/api/voices` (saved to `config.local.json` via a new `PUT /api/settings` — this is an approved contract addition), per-book Regenerate (with voice) and Delete (with confirm). Show `/api/health` environment warnings (e.g. "Opus not available").

### CP4C — Error-message pass & test cleanup
**Owner:** Mistral · **Branch:** `cp4c-mistral` · **Owns:** `tests/*` only
Make every test file runnable independently, remove duplicate fixtures, add a `tests/conftest.py` with a shared `tmp_library` fixture (sets `TINBOOK_LIBRARY_DIR`, clears config cache). No production code changes.

**Merge Wave 4:** 4C → 4A → 4B. ★ **Phase 1 done.**

---

# PHASE 2 — DEVICE

> Read `docs/HARDWARE.md` fully before any Phase 2 checkpoint. Kayden runs all Pi commands over SSH; agents can't reach the Pi directly, so give exact commands and expected output.

## CP5 — Pi setup & library image (solo)
**Owner:** Claude Code (+ Kayden running it) · **Branch:** `cp5-claude`
**Owns:** `scripts/pi/setup.sh`, `scripts/pi/make_library_image.sh`, `requirements-device.txt`, `docs/handoffs/CP5.md`
**Tasks:** idempotent `setup.sh` that: enables SPI + I2C (`raspi-config nonint`), adds `dtoverlay=dwc2` to `/boot/firmware/config.txt` and `modules-load=dwc2` handling (dwc2 only; load `g_mass_storage` on demand), installs `mpv`, `python3-venv`, `python3-pil`, `bluez`, PipeWire + WirePlumber + `libspa-0.2-bluetooth`, `dosfstools`; installs PiSugar power manager (HARDWARE.md §4); creates venv and installs `requirements-device.txt` (`displayhatmini`, `pillow`, `python-mpv` or none if using mpv IPC, plus the repo's `core/` deps only); enables `loginctl enable-linger` for the user so PipeWire runs without login; sets CPU governor to `powersave`; disables the activity LED. `make_library_image.sh`: creates a 16 GB FAT32 image at `/home/<user>/tinbook.img`, label `TINBOOK`, mounts it at `/mnt/tinbook` (fstab entry with `uid`/`gid` of the user, `nofail`).
**Acceptance:** after running both, Pimoroni's example draws on the screen, buttons print, `mpv` plays a test `.opus` to AirPods, `pisugar-server` reports battery.

## Wave 6 (parallel)

### CP6A — Audio player + Bluetooth
**Owner:** Claude Code · **Branch:** `cp6a-claude` · **Owns:** `device/player.py`, `device/bluetooth.py`, `device/__init__.py`
`Player` class wrapping mpv via JSON IPC socket: `load(path, start_sec)`, `play()`, `pause()`, `toggle()`, `seek_relative(sec)`, `set_speed(x)`, `position() -> float`, `duration() -> float`, `on_end(callback)`. `Bluetooth`: `scan(seconds) -> list[(mac, name)]`, `pair_and_connect(mac)`, `connect_last()`, `is_connected() -> bool`, `set_wifi(enabled: bool)` (via `rfkill`). Store last device MAC in `~/.config/tinbook/device.json`.

### CP6B — Display + buttons
**Owner:** Replit · **Branch:** `cp6b-replit` · **Owns:** `device/display.py`, `device/buttons.py`
`Display`: renders screens from plain data (no business logic) with Pillow at 320×240: `render_library(items, selected_index, battery, bt)`, `render_now_playing(state)`, `render_menu(items, selected_index)`, `render_message(title, body)`, `sleep()`, `wake()`, `set_led(r,g,b)`. `Buttons`: background thread polling via the `displayhatmini` library at ~50 Hz, emits events `("A"|"B"|"X"|"Y", "tap"|"hold"|"long")` to a queue: `tap` on release if held <600 ms; `hold` once at 600 ms; `long` once at 1500 ms (a single press can emit `hold` then `long`, but never `tap` after `hold`). Include a `--demo` mode (`python -m device.display --demo`) cycling fake screens. Can be developed on Replit by rendering screens to PNG files when the hardware library isn't available.

### CP6C — Battery client + desktop "Send to Tinbook"
**Owner:** Mistral · **Branch:** `cp6c-mistral` · **Owns:** `device/power.py`, `desktop/device_sync.py`, `tests/test_device_sync.py`
- `power.py`: `battery_percent() -> int | None`, `is_charging() -> bool | None` by sending `get battery\n` and `get battery_charging\n` to `pisugar-server` over TCP `127.0.0.1:8423` and parsing the reply (`battery: 87.5` → 87). Return None on any error. Verify the port/commands against the PiSugar docs; note in handoff if different.
- `device_sync.py`: `find_device() -> Path | None` — Windows: check drive letters `D:`–`Z:` for volume label `TINBOOK` via `ctypes.windll.kernel32.GetVolumeInformationW`; Linux: look for `/media/*/TINBOOK` and `/run/media/*/TINBOOK`. `sync_books(book_ids) -> dict`: for each **ready** book, copy `book.json` and `audio/` to `<drive>/library/<id>/` (skip audio files with identical size), then merge progress with `core.progress.newer()` and write the winner to **both** sides. Returns `{"copied": [...], "skipped": [...], "progress_updated": [...], "errors": [...]}`. Also add routes `GET /api/device` and `POST /api/device/sync` to `desktop/server.py` (approved exception: only add these two routes).

## CP7 — Device app (solo)
**Owner:** Claude Code · **Branch:** `cp7-claude` · **Owns:** `device/main.py`, `device/usb_sync.py`, `scripts/pi/tinbook.service`, plus integration fixes anywhere.
State machine: Library ↔ Now Playing ↔ Menu (Bluetooth, Speed, Sync mode, Battery, Shut down) ↔ Sync mode. Implements PRD P-1…P-10 and the button map in HARDWARE.md §5. `usb_sync.py`: enter = stop player, save progress, `sync`, unmount `/mnt/tinbook`, `modprobe g_mass_storage file=<img> removable=1 stall=0`; exit = `modprobe -r g_mass_storage`, `fsck.vfat -a <img>`, remount. Needs a sudoers drop-in limited to exactly these commands (include it in setup notes). systemd user service with `Restart=on-failure`.

## CP8 — Assembly & field test
**Owner:** Kayden + Claude Code · **Owns:** `docs/handoffs/CP8.md`, tuning fixes
Follow HARDWARE.md §6 assembly. Measure real battery life (full charge → playback until shutdown), Bluetooth range with lid closed, button feel. Tune timeouts and power settings. ★ **Phase 2 done.**
