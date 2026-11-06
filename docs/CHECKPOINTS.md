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
Wave 4 ├─ CP4A Claude 1 Kokoro engine + voice catalog/downloads/preview (core, scripts)
       ├─ CP4B Claude 2 start-from-chapter + priority (jobs, pipeline) + ALL frontend
       ├─ CP4C Replit   Wave 4 routes + settings (server.py)
       └─ CP4D Mistral  tests for the CP3 groundwork
        │   merge order: 4D → 4A → 4B → 4C
CP4Z Claude + Kayden ────── Wave 4 review + Windows walkthrough
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
4. In the first 40 lines of what remains, remove lines starting with `Produced by`, `E-text prepared by`, or `Transcribed by` (case-insensitive), plus any lines directly after them up to (not including) the next blank line. A block that starts within the first 40 lines is removed in full even if it runs past line 40.
5. Strip leading/trailing whitespace of the whole result.

**`clean_for_speech(text)`**
1. Split into paragraphs on one or more blank lines (`\n\s*\n`).
2. Within each paragraph, join lines with a single space (unwrap hard wraps) and collapse runs of spaces/tabs to one space.
3. Remove `[Illustration...]` blocks (regex `\[Illustration[^\]]*\]`, case-insensitive) and footnote markers like `[1]`, `[23]` (regex `\[\d+\]`).
4. Remove underscores used for italics: `_word_` → `word` (regex `_([^_]+)_` → `\1`).
5. Drop paragraphs that are empty, or that consist only of `*`, `-`, `=` characters and spaces (scene-break rules). This runs **before** rule 6, so `-----` is dropped instead of becoming commas.
6. Replace each run of two or more dashes (`--`, `----`) with `, `, then tidy only the commas that creates: `, ,` / `,,` → `,`; ` ,` → `,`; a comma directly before `.;:!?` is removed (`Wait--.` → `Wait.`); a comma directly after `.;:!?` is removed (`Mr. ----` → `Mr.`); a leading `, ` is removed. Do **not** touch other commas: `1,000` and `"Hello," he said` stay exactly as they are. Collapse spaces again and drop the paragraph if it is now empty.
7. Rejoin paragraphs with `\n\n`. Keep headings as their own paragraphs (they're just short paragraphs).

**`split_chapters(text)`** (input is cleaned text: paragraphs separated by `\n\n`)
1. A paragraph is a **heading** if it is ≤ 80 characters and is one of:
   - **Keyword + numeral**, case-insensitive: `chapter|book|part|volume|letter`, whitespace, an optional `the `, then a **numeral** (a Roman numeral `[ivxlcdm]+`, digits, or a number word such as `one`…`twenty`, `thirty`…`hundred`, `first`…`twentieth`, `last`, `final`, optionally compound like `twenty-one` / `twenty one`). After the numeral there must be either nothing, or a separator (`.` `:` `-` `–` `—`) followed by a subtitle. Examples: `Chapter 1`, `Letter 4`, `Chapter the First`, `Chapter I. The Arrival`, `Volume II — Notes`.
   - The same keyword + numeral followed by any subtitle **if the paragraph has no lowercase letters** (`CHAPTER I THE ARRIVAL`).
   - A bare numeral: digits, or an **uppercase** Roman numeral, with an optional trailing `.` (`IV`, `XII.`, `42`).

   Not headings (ordinary prose): `Part of me wanted to stay.`, `Book him, Danno.`, `Part I of my life was hard.`, `Book two was better.`, `did.`
2. Walk paragraphs. Each heading starts a new section, **even if no text follows it before the next heading** (an empty section); its title is the heading text (strip trailing `.`). Paragraphs before the first heading form a section titled `"Opening"` (omitted if there are none).
3. **Merge tiny sections:** any section whose body has fewer than 50 words is merged **into the next** section: the next section's title becomes `"<tiny title> — <next title>"` and the tiny body (if any) is prepended. Merging **cascades**: if the merged section is still under 50 words it merges into the next one too, so `PART ONE` + `CHAPTER I` gives `"Part One — Chapter I"` and a run of tiny sections becomes one title. A merged title keeps at most 3 parts: when more than 3 headings merge, it is `"<first> — … — <last>"` (CP3: a table of contents whose entries are separate paragraphs used to give a 30-part title). If the last section is still tiny, merge its body into the previous one and **keep the previous title unchanged**.
4. **Fallback / oversize:** if there are fewer than 2 sections (whole-book fallback), or a section has more than 15,000 words, split that section's body at paragraph boundaries into parts: a part ends at the first paragraph boundary **at or after** 5,000 words (so parts are ≥ 5,000 words, except the last). Titles: `"<title>, part 1"`, `"<title>, part 2"`…; for the whole-book fallback, `"Part 1"`, `"Part 2"`…. If splitting yields only one part, keep the section unchanged. A single paragraph is never cut.
5. Title-case headings that are ALL CAPS (`"CHAPTER I"` → `"Chapter I"`, `"CHAPTER THE FIRST"` → `"Chapter the First"`); keep the heading's Roman numeral uppercase (`Chapter XII`, bare `IV`). Other words are title-cased even if they look like Roman numerals (`THE DIM MIX` → `The Dim Mix`). Headings that already contain lowercase letters are left alone.
6. Return `[(title, body_text)]` with bodies joined by `\n\n`. Never return an empty list; never return an empty body (if a section has no text at all, e.g. empty input, its body is its title).

**`progress.py`** exactly per ARCHITECTURE §5. "Corrupt" includes unreadable files, invalid JSON, non-UTF-8 bytes, and JSON that is not an object (`[]`, `null`); each returns `Progress()`. A field with the wrong type or range (e.g. `"speed": "fast"`, negative position) falls back to that field's default. `save_progress` must not modify the object passed in.

**Fixtures & tests**
- `tests/fixtures/sample_book.txt`: ~150 lines, fake Gutenberg header + footer, "Produced by" line, a 4-entry table of contents, `PART ONE`, `CHAPTER I`, `CHAPTER II`, `CHAPTER III` with a few hundred words each (use lorem-style filler), an `[Illustration: x]`, a `_italic_` word, a `--`.
- `tests/fixtures/no_chapters.txt`: header/footer + ~12,000 words of filler paragraphs, no headings.
- Tests: boilerplate removed; illustration/footnote/underscore removed; hard wraps unwrapped; TOC merged (first chapter title contains "Chapter I"); `no_chapters.txt` → exactly `"Part 1"`, `"Part 2"`, `"Part 3"`; progress save/load round-trip; corrupt progress.json (`[]`, `null`, non-UTF-8) → default; `newer()` picks later timestamp. **Tests must check the actual output text, not just counts** (e.g. no single-character paragraphs, `1,000` survives, every source paragraph appears exactly once).

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
**Status:** done — see `docs/handoffs/CP3.md`. CP3 also designed Wave 4 (ARCHITECTURE §9–10) and landed its shared groundwork.
**Owner:** Claude Code · **Depends on:** Wave 2 · **Branch:** `cp3-claude`
**Owns:** anything (integration checkpoint — see CLAUDE.md)

**Tasks**
1. Read all handoffs. Resolve every Contract change request (update ARCHITECTURE.md if changed).
2. Review Mistral's modules for correctness on 3 real books: *Crime and Punishment* (2554), *Frankenstein* (84), *Pride and Prejudice* (1342). Report chapter counts and first 5 titles for each; fix splitting issues.
3. Walk through Flows A and B (PRD §4) with Kayden on Windows. Fix bugs.
4. Make sure a crash mid-generation resumes cleanly and `pytest` passes.

**Acceptance criteria:** Kayden listens to Frankenstein chapter 1 → 2 auto-advance on Windows, closes the app, reopens, and resumes correctly.

---

## Wave 4 — Voice options, start from a chapter, polish (parallel)

Four checkpoints, four branches, **no file is owned by two of them**. Everything they share already exists on `main` from CP3: the `"skipped"` status (`core/models.py`, `core/library.py`), voice-ID parsing and the catalog (`core/voices.py`, `core/voice_catalog.json`), and stubs with the exact signatures for everything that is still to be written. Contracts: ARCHITECTURE §5, §6, §9 (voices) and §10 (start from a chapter). PRD: D-14–D-25, P-11.

| File(s) | Owner |
|---|---|
| `core/voices.py`, `core/voice_catalog.json`, `core/tts.py`, `core/tts_kokoro.py`, `scripts/download_voice.py`, `scripts/verify_voice_catalog.py`, `scripts/smoke_test.py`, `tests/test_tts.py`, `tests/test_voices.py`, `tests/test_tts_kokoro.py`, `tests/test_download_voice.py` | CP4A |
| `core/jobs.py`, `core/pipeline.py`, `tests/test_jobs.py`, `tests/test_pipeline.py`, `desktop/templates/*`, `desktop/static/*` | CP4B |
| `desktop/server.py`, `desktop/settings.py`, `tests/test_server.py` | CP4C |
| `tests/conftest.py`, `tests/test_voice_ids.py`, `tests/test_voice_catalog_file.py`, `tests/test_skipped_status.py`, `tests/test_check_real_books.py` | CP4D |
| everything else (incl. `core/models.py`, `core/library.py`, `core/config.py`, `core/gutenberg.py`, `core/chapters.py`, `core/progress.py`, `desktop/app.py`, `requirements.txt`, `config.json`, `tests/fixtures/*`, other tests, docs except your own handoff) | nobody — read only |

Each checkpoint writes `docs/handoffs/CP4<x>.md`. A contract you think is wrong → implement it as written and file a Contract change request. `kokoro-onnx` is already in `requirements.txt` — reinstall (`pip install -r requirements.txt`) before starting.

### CP4A — Kokoro engine, voice catalog, downloads & preview (backend)
**Owner:** Claude Code (session 1) · **Depends on:** CP3 · **Branch:** `cp4a-claude`
**Owns:** `core/voices.py`, `core/voice_catalog.json`, `core/tts.py`, `core/tts_kokoro.py` (new), `scripts/download_voice.py`, `scripts/verify_voice_catalog.py` (new), `scripts/smoke_test.py`, `tests/test_tts.py`, `tests/test_voices.py`, `tests/test_tts_kokoro.py` (new), `tests/test_download_voice.py`
**Reads:** everything else — especially `core/jobs.py`, `core/pipeline.py` (CP4B) and `desktop/server.py` (CP4C), which call your functions.

**Tasks**
1. **Kokoro engine** (`core/tts_kokoro.py`) exactly per ARCHITECTURE §9.2: lazy `import kokoro_onnx`, one cached `Kokoro` per process behind a lock, `lang` from the name's first letter, paragraph-by-paragraph float→int16 into a 24 kHz mono WAV with 0.4 s pauses. `tts.synthesize_to_file` dispatches on `voices.parse_voice_id(voice)[0]`; Piper behavior is unchanged. `check_environment()["kokoro"]` becomes "the engine can actually be used" (import succeeds). `synthesize_to_file` must be safe from two threads at once (job worker + preview).
2. **`core/voices.py`**: implement the six CP4A stubs exactly per §9.4 (`catalog`, `get_voice`, `start_download`, `download_states`, `delete_voice`, `preview_file`). Keep the CP3 functions' behavior (CP4D tests them).
3. **`scripts/download_voice.py`**: accept any voice ID (`en_US-lessac-medium`, `piper:en_US-ryan-high`, `kokoro:af_heart`), downloading the voice's pack with the same code as `start_download` (run synchronously) and a console progress line; exit 1 with a clear message on failure. `run.bat` still calls it with `en_US-lessac-medium`.
4. **`scripts/verify_voice_catalog.py`** (new): for every catalog file, request the URL (HEAD, follow redirects), print a table `pack | path | catalog size | real size | OK/DIFF/ERROR`, exit 1 if any ERROR. `--write` updates `size_bytes` from the real `Content-Length`. `--hash` downloads each file, computes SHA-256, and (with `--write`) stores it and sets `verified: true`. huggingface.co is blocked in the cloud sandboxes, so Kayden runs it on Windows; write exact commands in the handoff.
5. Re-check the Kokoro grades in `voice_catalog.json` against `hexgrad/Kokoro-82M` `VOICES.md` if your network allows; otherwise note it as open.
6. **`scripts/smoke_test.py`**: also synthesize "Hello from Tinbook." with `kokoro:af_heart` when the Kokoro pack is installed (else print SKIP), and report its real-time factor.
7. **Tests** (no network, no real models): fake `kokoro_onnx` via `sys.modules`; HTTP via `responses`. Cover at least: Kokoro WAV format, rate, pauses, `lang` mapping, missing package → `TTSError`, Piper unaffected; downloads (progress numbers, already-installed → done without HTTP, second call while running returns the same state, sha256 mismatch → error and no `.part` left, resume skips finished files, missing Content-Length); delete (Kokoro pack removes all Kokoro IDs + previews; refuses while downloading or when not installed); preview cached and re-made after delete; `catalog()` order and uncatalogued Piper voices; `get_voice` errors.
8. If your sandbox lets you, run one real Kokoro synthesis and record the real-time factor; if it doesn't, say so.

**Acceptance criteria**
- `pytest` passes with no network and no real models.
- Existing books with plain voice names (`en_US-lessac-medium`) still generate.
- On Kayden's Windows: `python scripts\download_voice.py kokoro:af_heart` shows progress and finishes (~354 MB); `python scripts\smoke_test.py` shows Piper and Kokoro PASS; `python scripts\verify_voice_catalog.py` prints OK for every file (after `--write` if sizes differed).

### CP4B — Start from a chapter, priority generation, and the whole frontend
**Owner:** Claude Code (session 2) · **Depends on:** CP3 · **Branch:** `cp4b-claude`
**Owns:** `core/jobs.py`, `core/pipeline.py`, `tests/test_jobs.py`, `tests/test_pipeline.py` (new), `desktop/templates/index.html`, `desktop/static/*` (`app.js`, `style.css`, any new `.js`/`.css`)
**Reads:** `core/voices.py` (CP4A implements it — code against §9.4), `desktop/server.py` (CP4C implements the new routes — code against §6), everything else.

**Backend tasks**
1. `pipeline.preview_book`, `add_book(start_chapter=…)`, `generate_chapter`, `generate_skipped` exactly per ARCHITECTURE §10.2–10.4 (text cache in `<library_dir>/.cache/`, 24 h). `regenerate_book` already keeps skipped chapters — keep it that way.
2. `JobQueue.prioritize` and the per-book cursor per §10.4. The worker may need to switch books between chapters; keep "save after every chapter", "reload before save", resume-on-start, and retry-once behavior.
3. Tests in `tests/test_jobs.py` (threaded, like the existing ones) and `tests/test_pipeline.py` (mock `gutenberg` and `jobs.get_queue`): skipped never generated; start chapter → earlier chapters skipped + progress at start; preview uses and deletes the cache; bad `start_chapter` (`-1`, `len`, `True`, `"2"`) → `ValueError`; `generate_chapter` on skipped/error/pending/done; prioritize within a book (jump ahead, then continues, then wraps), across books (other book resumes after), newer prioritize wins.

**Frontend tasks** (vanilla JS; window ~420 px; light + dark)
4. **Add dialog** (Search → Add): voice dropdown of installed voices from `GET /api/voices` (grouped Piper/Kokoro, preselected `default`, falling back to the first installed voice; a "Get more voices" link opens the Voices screen); "Start from" select filled from `GET /api/preview/<id>` (spinner while loading; if preview fails you can still add from the beginning); Add → `POST /api/books` with `voice` and `start_chapter`.
5. **Voices screen** (D-16–D-19): catalog grouped by engine, recommended first; each row: name, gender · accent, quality note, size in MB, Installed badge. Download button with a progress bar (poll `GET /api/voices` every 1 s while any `download.state` is `"downloading"`; show `error`); Preview (installed only; separate `Audio` object; pauses the book); Delete with confirm ("This removes all N Kokoro voices (354 MB)" for Kokoro). Warn when `engines.kokoro` is false.
6. **Player / library for Feature B** (§10.4): skipped chapters show "Skipped" + **Generate**; **Generate all skipped (N)**; any jump or auto-advance to a chapter without audio calls `POST …/chapters/<n>/generate` once, then the waiting state "Generating chapter N…"; library cards show "· N skipped". A book that opens at its start chapter must not try to play skipped chapters on "previous".
7. **Book actions**: Regenerate with a chosen voice and Delete (confirm) from the library card or player.
8. **Health warnings** from `GET /api/health`: no ffmpeg, no Opus (mp3 fallback), no voices installed, Kokoro unavailable.
9. **Player polish** (old CP4A): keyboard D-9 (Space play/pause, ←/→ −30/+30 s; ignored while typing in an input/select); Media Session API (title = chapter, artist = author, album = book; play, pause, seekbackward, seekforward, previoustrack, nexttrack); buffering spinner on `waiting`/`stalled`; clear audio error states.
10. Build against the contracts. Use a scratch mock server outside the repo if you need one; **commit no mocks**.

**Acceptance criteria**
- `pytest` passes.
- Checked in Chromium (Playwright) against a server or scratch mock: add from chapter 5 → player opens at chapter 5 with chapters 1–4 "Skipped"; Generate on chapter 2 → it is generated next; jumping to chapter 20 while chapter 6 is generating → 20 is next, then 21…; voice download progress, preview and delete; keyboard and Media Session handlers.
- After the wave is merged, Kayden can do all of the above on Windows (CP4Z).

### CP4C — Wave 4 routes and settings
**Owner:** Replit · **Depends on:** CP3 · **Branch:** `cp4c-replit`
**Owns:** `desktop/server.py`, `desktop/settings.py` (new), `tests/test_server.py`
**Reads:** all of `core/` (`voices` and the new `pipeline`/`jobs` functions are stubs on `main` until CP4A/CP4B merge — mock them in tests), ARCHITECTURE §6, §9, §10.

**Tasks**
1. `desktop/settings.py` exactly per ARCHITECTURE §9.5; `PUT /api/settings` uses it.
2. Every new or changed route in §6, with the exact request/response shapes and status codes:
   - `GET /api/voices` (new shape: `voices` = list of VoiceView, `default` canonical, `engines` from `check_environment()`);
   - `POST /api/voices/<voice_id>/download` (202 downloading / 200 installed);
   - `DELETE /api/voices/<voice_id>`;
   - `GET /api/voices/<voice_id>/preview` (`send_file`, `conditional=True`, `audio/ogg` or `audio/mpeg`);
   - `GET /api/preview/<int:gutenberg_id>`;
   - `POST /api/books` with optional `start_chapter` (must be an int; `bool` → 400) and the last-used voice;
   - `POST /api/books/<id>/chapters/<int:n>/generate`;
   - `POST /api/books/<id>/generate-skipped`;
   - `POST …/regenerate` remembers the voice;
   - `BookView` gets `chapters_skipped`.
3. Error mapping per §6: `ValueError` → 400, `IndexError` from `generate_chapter` → 404, voice routes in the order normalize (400) → `get_voice` (404) → action (409). A failed settings write must not fail an add/regenerate (log a warning).
4. Keep every existing route and test working; keep the CP3 additions in `tests/test_server.py` (close hook, 409 race, regenerate format, canonical voices).
5. Tests with the Flask test client; monkeypatch `voices.*`, `pipeline.preview_book/generate_chapter/generate_skipped`; voice IDs URL-encoded (`kokoro%3Aaf_heart`); no network.

**Acceptance criteria**
- `pytest` passes.
- In `--browser` mode, `curl` returns the documented shapes and codes for every new route. The routes that need CP4A/CP4B code may return 500 (`NotImplementedError`) before those merge; say which in the handoff.

### CP4D — Tests for the CP3 groundwork
**Owner:** Mistral · **Depends on:** CP3 · **Branch:** `cp4d-mistral`
**Owns:** `tests/conftest.py` (new), `tests/test_voice_ids.py` (new), `tests/test_voice_catalog_file.py` (new), `tests/test_skipped_status.py` (new), `tests/test_check_real_books.py` (new). **No other file.** No production code changes. Every test must pass on `main` as of CP3.

**`tests/conftest.py`** — two fixtures, **not** `autouse`:
- `tmp_library(monkeypatch, tmp_path)`: `monkeypatch.setattr(core.config, "_ROOT_DIR", tmp_path)`; `monkeypatch.delenv(name, raising=False)` for `TINBOOK_LIBRARY_DIR`, `TINBOOK_VOICES_DIR`, `TINBOOK_DEFAULT_VOICE`, `TINBOOK_PORT`; `get_config.cache_clear()`; `yield get_config().library_dir`; then `get_config.cache_clear()`.
- `tmp_voices_dir(tmp_library)`: `yield get_config().voices_dir`.

**`tests/test_voice_ids.py`** — use `pytest.mark.parametrize` with exactly these cases:
- Valid: `voices.parse_voice_id(x)` returns the tuple and `voices.normalize_voice_id(x)` returns `"engine:name"`:
  `"en_US-lessac-medium"` → `("piper", "en_US-lessac-medium")`; `"piper:en_US-lessac-medium"` → same; `"piper:en_US-ryan-high"`; `"piper:en_GB-northern_english_male-medium"`; `"piper:en_US-amy-x_low"`; `"yue_HK-test-medium"` → piper; `"kokoro:af_heart"` → `("kokoro", "af_heart")`; `"kokoro:bm_george"`; `"kokoro:ef_dora"`.
- `normalize_voice_id(normalize_voice_id(x)) == normalize_voice_id(x)` for every valid case.
- Invalid: each raises `voices.VoiceError` from both functions, and `voices.is_installed(x)` returns `False` without raising:
  `""`, `None`, `42`, `["piper:x"]`, `"kokoro:"`, `"piper:"`, `":af_heart"`, `"espeak:af_heart"`, `"Kokoro:af_heart"`, `"kokoro:AF_heart"`, `"kokoro:af-heart"`, `"kokoro:afheart"`, `"kokoro:a_heart"`, `"af_heart"`, `"en_US-lessac"`, `"en_us-lessac-medium"`, `" en_US-lessac-medium"`, `"en_US-lessac-medium "`, `"piper:kokoro:af_heart"`, `"kokoro:af_heart:extra"`, `"kokoro:af_heart2"`.
- With `tmp_voices_dir`: after creating empty files `en_US-lessac-medium.onnx` and `en_US-lessac-medium.onnx.json`, `is_installed` is `True` for both `"en_US-lessac-medium"` and `"piper:en_US-lessac-medium"`; with only the `.onnx` file it is `False`. `"kokoro:af_heart"` is `False` until both `kokoro/kokoro-v1.0.onnx` and `kokoro/voices-v1.0.bin` exist, then `True`; `"kokoro:ef_dora"` stays `False`.

**`tests/test_voice_catalog_file.py`** — one test function per rule 1–11 in ARCHITECTURE §9.3, named `test_rule_01_…` to `test_rule_11_…`. Load the file with `json.loads((ROOT / "core" / "voice_catalog.json").read_text(encoding="utf-8"))` where `ROOT = Path(__file__).resolve().parent.parent`. For rule 3 use `voices.normalize_voice_id`. For rule 6 split the Piper name as `lang_region, rest = name.split("-", 1)`, `speaker, quality = rest.rsplit("-", 1)`, `lang = lang_region.split("_")[0]`. For rule 11 read `ROOT / "config.json"`. Assertion messages must name the offending voice or file.

**`tests/test_skipped_status.py`**:
1. Parametrized table for `Book(...)` with chapters of these statuses → `(chapters_done(), chapters_skipped(), is_complete())`: `[]` → `(0, 0, True)`; `["skipped", "skipped"]` → `(0, 2, True)`; `["done", "skipped", "pending"]` → `(1, 1, False)`; `["done", "error"]` → `(1, 0, False)`; `["done", "done"]` → `(2, 0, True)`; `["skipped", "error"]` → `(0, 1, False)`.
2. `Chapter.from_dict({"index": 0, "title": "A", "word_count": 1, "status": "skipped"}).status == "skipped"`, and a `Book` with a skipped chapter survives `Book.from_dict(book.to_dict())` unchanged.
3. With `tmp_library`: `library.create_book(SearchResult(84, "Frankenstein", ["Shelley, Mary"], "en", 1, None), "raw", [("One", "a b"), ("Two", "c d"), ("Three", "e f")], "en_US-lessac-medium", "opus")`; set chapter 0 to `"skipped"`, `library.save_book`; `library.get_book` returns statuses `["skipped", "pending", "pending"]`. Then write `book.json` by hand with chapter 0 status `"Skipped"` → `library.get_book` raises `LibraryError`; again with `"skipped "` → `LibraryError`.
4. `jobs._needs_audio(book, 0)` is `False` when chapter 0 is `"skipped"` and `True` when it is `"pending"` (build the `Book` in memory; no files needed).
5. With `tmp_voices_dir`: create empty `en_US-lessac-medium.onnx` + `.onnx.json`; create a book as in 3 with statuses `["skipped", "done", "error"]` and an audio file `library.chapter_audio_path(book.id, 1, "opus")` (create its parent folder); `queue = unittest.mock.Mock()`; `monkeypatch.setattr(pipeline.jobs, "get_queue", lambda: queue)`; `pipeline.regenerate_book(book.id, "en_US-lessac-medium")` returns a book with statuses `["skipped", "pending", "pending"]`, every `duration_sec` `None`, `voice == "piper:en_US-lessac-medium"`, `status == "queued"`; the `audio` folder exists and is empty; `queue.enqueue.assert_called_once_with(book.id)`.

**`tests/test_check_real_books.py`** — load the script with `importlib.util.spec_from_file_location("check_real_books", ROOT / "scripts" / "check_real_books.py")`. Monkeypatch `core.gutenberg.get_metadata` to return `SearchResult(84, "Frankenstein", ["Shelley, Mary Wollstonecraft"], "en", 1, "u")` and `core.gutenberg.download_text` to return the text of `tests/fixtures/sample_book.txt`. Use `capsys`.
1. `main(["84"])` returns `0`; stdout contains exactly these lines: `=== Book 84`, `Title:      Frankenstein`, `Authors:    Shelley, Mary Wollstonecraft`, `Chapters:   3  (words per chapter: min 279, max 327)`, `First 3:`, `    1. Opening — Part One — Chapter I  (327 words)`, `    2. Chapter II  (279 words)`, `    3. Chapter III  (302 words)`, `Summary: 84 OK`. A line starts with `Downloaded: 7,056 characters (` (don't check the seconds).
2. `main([])` checks 84, 2554, 1342 in that order: the last line is `Summary: 84 OK, 2554 OK, 1342 OK`.
3. `get_metadata` raising `gutenberg.GutenbergError("offline")` → `main(["84"])` returns `1`, stdout has `FAILED to download: offline` and `Summary: 84 FAILED`.
4. `--all`: `main(["--all", "84"])` prints `All titles:` and no line containing `last:`.
5. More than 5 chapters: monkeypatch the module's `chapters.split_chapters` to return `[(f"T{i}", "w " * i) for i in range(1, 8)]`; `main(["84"])` prints `First 5:`, the line `    5. T5  (5 words)`, no `T6` line, and `  ...  last: T7`.

**Acceptance criteria:** `pytest` passes on the branch (all files, not just yours); only the five files above are added; no test touches the network.

**Merge Wave 4:** 4D → 4A → 4B → 4C (no file overlaps, so no conflicts; this order keeps `pytest` green after each merge). Then **CP4Z**.

### CP4Z — Wave 4 review & Windows walkthrough (solo)
**Owner:** Claude Code (+ Kayden on Windows) · **Branch:** `cp4z-claude`
Same as the Wave 2 review: ownership, contracts, acceptance criteria, trial merge, full `pytest`, live `--browser` checks of every route, every `fetch()` in the frontend checked against `server.py`. Then Kayden on Windows: download a Kokoro voice, add a book from chapter 5 with it, Generate a skipped chapter, jump ahead, close and reopen. Fix what breaks. ★ **Phase 1 done.**

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
- `device_sync.py`: `find_device() -> Path | None` — Windows: check drive letters `D:`–`Z:` for volume label `TINBOOK` via `ctypes.windll.kernel32.GetVolumeInformationW`; Linux: look for `/media/*/TINBOOK` and `/run/media/*/TINBOOK`. `sync_books(book_ids) -> dict`: for each **ready** book (every chapter done or skipped), copy `book.json` and `audio/` to `<drive>/library/<id>/` (skip audio files with identical size; **skipped chapters have no audio and are not an error**, ARCHITECTURE §8 / PRD P-11), then merge progress with `core.progress.newer()` and write the winner to **both** sides. Returns `{"copied": [...], "skipped": [...], "progress_updated": [...], "errors": [...]}`. Also add routes `GET /api/device` and `POST /api/device/sync` to `desktop/server.py` (approved exception: only add these two routes).

## CP7 — Device app (solo)
**Owner:** Claude Code · **Branch:** `cp7-claude` · **Owns:** `device/main.py`, `device/usb_sync.py`, `scripts/pi/tinbook.service`, plus integration fixes anywhere.
State machine: Library ↔ Now Playing ↔ Menu (Bluetooth, Speed, Sync mode, Battery, Shut down) ↔ Sync mode. Implements PRD P-1…P-11 (P-11: chapters that aren't "done" — e.g. skipped — are skipped by next/previous/auto-advance, ARCHITECTURE §8) and the button map in HARDWARE.md §5. `usb_sync.py`: enter = stop player, save progress, `sync`, unmount `/mnt/tinbook`, `modprobe g_mass_storage file=<img> removable=1 stall=0`; exit = `modprobe -r g_mass_storage`, `fsck.vfat -a <img>`, remount. Needs a sudoers drop-in limited to exactly these commands (include it in setup notes). systemd user service with `Restart=on-failure`.

## CP8 — Assembly & field test
**Owner:** Kayden + Claude Code · **Owns:** `docs/handoffs/CP8.md`, tuning fixes
Follow HARDWARE.md §6 assembly. Measure real battery life (full charge → playback until shutdown), Bluetooth range with lid closed, button feel. Tune timeouts and power settings. ★ **Phase 2 done.**
