# CP3 handoff — Claude Code
Branch `cp3-claude`, from `main` at `25cc843` (Wave 2 merged). Integration checkpoint: I edited files across the repo.

## Done

### Part 1 — open items from every handoff
| Item | From | Fix |
|---|---|---|
| `"mp3": bool` in `check_environment()` | CP1A contract change request | Added; also `"kokoro": bool` (package installed). |
| `progress.py` used its own atomic writer | CP1C / ARCHITECTURE §5 | Now writes through `library.write_json_atomic`. `save_progress` also refuses to recreate a deleted book's folder (that writer creates missing parents) and raises `LibraryError`. |
| `jobs.py` left a book stuck when `audio_format` is unsupported | review | The worker marks the book `error` ("Unsupported audio format 'wav' (use opus or mp3)…"). Any unexpected worker exception now also marks the book `error`, instead of leaving it `queued`/`generating` and re-queuing it on every start. (The real `library.get_book` already rejects such a book, so this guard matters for odd states and fakes.) |
| Window close didn't save progress exactly (PRD D-8) | CP2B | `desktop/app.py` `save_progress_on_close(window)`. pywebview 5.4 runs `closing` handlers on the UI thread (I read its source), and `evaluate_js` needs that thread, so the handler cancels the first close and a helper thread calls `window.tinbook.saveProgress()`. That helper waits up to 2 s, then `window.destroy()`; the second close goes through. |
| Simultaneous duplicate add → 500 | Wave 2 review (CP2A) | The add that loses the race now gets `BookAlreadyExists` → 409. |
| Fallback error repeated itself | Wave 2 review | When both requests fail the same way: "Could not reach Gutenberg. Check your connection and try again. (The backup catalog also failed the same way.)" |
| Regenerate kept a bad/old `audio_format` | found in CP3 | `regenerate_book` switches the book to `config.audio_format`. |
| Table of contents → 30-part chapter title | found in CP3 (simulated Frankenstein TOC) | Merged titles keep at most 3 parts: `"Opening — … — Letter 1"`. CP1C rule 3 updated. |
| `/favicon.ico` 404 | CP0 | Empty inline favicon in `index.html`. |
| `list_books` would warn about cache folders | needed for §10 | All dot-folders are skipped silently. |
| `run.bat` never reinstalls when `requirements.txt` changes | needed for `kokoro-onnx` | The marker `.venv\.installed` is now a copy of `requirements.txt`; any difference triggers `pip install -r requirements.txt`. |
| CP1B live Gutendex check | CP1B | Passed in Replit (CP2A handoff: 2554 is result #1; `download_text(2554)` has `*** START OF`). Closed. |
| Test duplication `test_gutenberg.py` / `test_library.py` | CP2C | Left as is on purpose: harmless, and deleting tests risks losing coverage. |

- **`scripts/check_real_books.py`** (new): runs books through download → clean → split and prints title, size, chapter count, min/max words per chapter, the first 5 titles and the last. It needs internet, adds nothing to the library, and exits 1 if a book fails.
- **Live run** of `python -m desktop.app --browser` (Gutenberg HTTP mocked in-process, Piper replaced by an ffmpeg tone):
  - Every route returned the documented shape and code: health, search (and 400 without `q`), add (201), jobs, book list and detail, progress GET/PUT (and 400 on bad speed), audio, audio for a chapter that doesn't exist (404), voices, settings, regenerate (progress kept), delete during generation (folder gone).
  - Audio with a Range header gives 206 and `audio/ogg`.
  - **`kill -9` in the middle of chapter 2 → after a restart, the book resumed at chapter 2 and ended `ready`.**
  - Unmodified run: this sandbox blocks gutendex.com and gutenberg.org, so search and add give a JSON 502 and no book is created.
- **Tests:** 491 pass (319 at the end of Wave 2). New tests cover every fix above, the close hook (fake pywebview window: cancel, save, destroy; one save for repeated clicks; page errors; timeouts), skipped chapters, and canonical voice IDs.

### Part 2 — Wave 4 design (contracts only, plus the shared groundwork)
- **ARCHITECTURE.md**: new §9 Voices (IDs, engines, files on disk, catalog format with 11 testable rules, `core/voices.py` API, downloads, delete, preview, last-used voice and `desktop/settings.py`) and §10 Start from a chapter (statuses, preview and text cache, `start_chapter`, `generate_chapter`/`generate_skipped`, `JobQueue.prioritize` and the per-book cursor, player rules). §1–§8 updated to match (layout, models, library folder, tts/jobs/pipeline contracts, full API table with status codes, `VoiceView`, `chapters_skipped`, device P-11).
- **PRD.md**: D-14–D-20 (voices), D-21–D-25 (start from a chapter), P-11 (device), D-10/D-11 updated, risks and tech stack.
- **Groundwork on `main` so the four Wave 4 checkpoints share no files:**
  - `models.py`: `ChapterStatus` gains `"skipped"`; `Book.chapters_skipped()`, `Book.is_complete()`.
  - `library.py`: accepts `"skipped"`.
  - `jobs.py`: never generates skipped chapters; `ready` = all done or skipped; `prioritize` stub.
  - `core/voices.py`: ID parsing, catalog loading, `pack_files`, `is_installed` and `installed_voice_ids` are implemented; `VoiceInfo` and `DownloadState` dataclasses; six stubs for CP4A.
  - `core/voice_catalog.json`: 12 Piper + 13 Kokoro voices.
  - `tts.py`: accepts canonical IDs (`piper:` works; `kokoro:` raises "arrives in CP4A"); `list_voices()` returns canonical IDs.
  - `pipeline.py`: validates voices with `voices.is_installed`, stores canonical IDs, keeps skipped chapters on regenerate; `start_chapter` parameter and three stubs for CP4B.
  - `server.py`: canonical voice IDs in `/api/voices` and `/api/settings`.
  - `requirements.txt`: `kokoro-onnx>=0.6,<0.7`.
- **Kokoro research** (details in ARCHITECTURE §9.2):
  - Verified here:
    - **Package:** `kokoro-onnx` 0.6.1 (2026-08-19), MIT; Python 3.10–3.13. It resolves alongside `piper-tts 1.8.0` (`onnxruntime 1.31.1`, `numpy 2.5.4`).
    - **Windows:** `espeakng-loader` ships espeak-ng for `win_amd64`, and upstream CI runs on `windows-2022`.
    - **API:** from the source, `Kokoro(model, voices).create(text, voice, speed, lang) -> (float32, 24000)`.
    - **Model files:** the real files from release `model-files-v1.1`. `kokoro-v1.0.onnx` is 325,505,369 bytes and `voices-v1.0.bin` is 28,214,398 bytes, with SHA-256 in the catalog.
    - **Voices:** `voices-v1.0.bin` holds 54 voices, 28 of them English (listed from the archive without running anything).
  - Not verified:
    - Running Kokoro: the sandbox's permission policy blocked executing the downloaded package and model.
    - Kokoro grades other than `af_heart` = A: huggingface.co is blocked, so they come from `VOICES.md` as I knew it.
    - Piper download sizes are estimates (`verified: false`).
  - CP4A's verify script and Kayden's smoke test close these gaps.

### Part 3 — Wave 4 rewritten in CHECKPOINTS.md
- **CP4A** Claude session 1: Kokoro engine, catalog, downloads, preview (`core/`, `scripts/`).
- **CP4B** Claude session 2: start from a chapter + priority (`jobs`, `pipeline`) and the whole frontend for both features, plus the old CP4A polish and CP4B UI.
- **CP4C** Replit: every new or changed route, `desktop/settings.py`, `tests/test_server.py`.
- **CP4D** Mistral: four exact-spec test files plus `conftest.py`, all runnable against CP3. I ran every expectation in that spec against the code before writing it down.
- An ownership table lists every file. Merge order: 4D → 4A → 4B → 4C, then CP4Z (review + Windows walkthrough).

## How to test
On Windows, after merging `cp3-claude` into `main`:
```
git pull
scripts\run.bat
```
`run.bat` reinstalls once because `requirements.txt` changed (adds `kokoro-onnx`; a few minutes). The app should open as before.

1. **Real books** (CP3 task 2; this sandbox can't reach Gutenberg):
   ```
   .venv\Scripts\activate
   python scripts\check_real_books.py
   ```
   Paste me the output. Expect 3 × "OK", chapter counts around Frankenstein 25–30, Crime and Punishment ~40, Pride and Prejudice ~61, and sensible first titles (no giant "A — B — C — …" titles, no chapters of a few words). `python scripts\check_real_books.py --all 1342` prints every title if something looks off.
2. **Flows A and B + the CP3 acceptance:** add Frankenstein (84), Start, let chapter 1 auto-advance into chapter 2. Note the time, **close the window with ✕**: it should close within about 2 seconds. Run `scripts\run.bat` again, Continue: it should resume within about a second of where you stopped (exactly, not up to 5 s like before).
3. `pytest` → 491 passed.

## Not done / known issues
- **Real books and the Windows walkthrough** are Kayden's steps 1–2 above. I can't fix splitting issues on real books until I see that output.
- **The close hook is untested in a real pywebview/WebView2 window.** Its logic is tested with a fake window, and I read pywebview 5.4's source to design it. If the window ever doesn't close, tell me; removing the `save_progress_on_close(window)` line in `desktop/app.py` restores the old behavior (the 5 s save interval).
- **Kokoro hasn't actually run** (see Part 2), and Piper catalog sizes are estimates.
- **CP1A's real-voice check:** if the Wave 2 Windows test (search, add, listen) worked, it's covered. Please confirm it did.

## Contract change requests
- **Resolved:** CP1A `"mp3"` → applied. CP2A `BookAlreadyExists` → documented in §5. The gutenberg-fallback changes were already applied (approved by Kayden).
- **Contract changes made in CP3** (all in ARCHITECTURE.md):
  - `tts.list_voices()` returns canonical IDs; `check_environment()` adds `mp3` and `kokoro`.
  - `ChapterStatus` adds `"skipped"`; `Book.chapters_skipped()` and `is_complete()`.
  - `save_progress` raises for a missing folder.
  - Worker error rules.
  - `add_book(..., start_chapter=0)`; `regenerate_book` keeps skipped chapters and switches format; `preview_book`, `generate_chapter`, `generate_skipped`, `JobQueue.prioritize`.
  - `list_books` skips dot-folders.
  - Merged chapter titles are capped at 3 parts.
  - `/api/voices` and `/api/settings` use canonical IDs. Wave 4 routes and shapes are in §6.

## New dependencies needed
- `kokoro-onnx>=0.6,<0.7`, already added to `requirements.txt`. It pulls `espeakng-loader`, `phonemizer`, `numpy` 2.x; `onnxruntime` is shared with Piper.

## Notes for the next agent
- **Wave 4:** stubs raise `NotImplementedError` naming the checkpoint that implements them. Mock them in tests; don't implement someone else's.
- **Voice IDs:** always compare canonical IDs (`voices.normalize_voice_id`). Old books store plain names and must keep working.
- **Settings in manual testing:** `PUT /api/settings` writes `config.local.json` in the repo root (gitignored). Delete it after manual tests.
- **Running Kokoro in the cloud:** the sandbox let me download the Kokoro release files from GitHub but blocked running them. CP4A may hit the same block; tests must use a fake `kokoro_onnx`.

---
# CP3 split fix — Claude Code (task 2: real books)
Branch `cp3-split-fix-claude`, from `main` at `50e847d`. It also merges `ci-windows-claude` (PR #6), so the Windows check runs on this PR. Merge #6 first; then this PR only adds the splitting fix.

## Why
The first Windows CI run (`ci-windows-claude`) printed the real books, and their splits had problems:
- Frankenstein's chapter 1 was a 30-second title page and contents.
- Crime and Punishment's chapter 1 was the table of contents read aloud, and its last chapter was a bare "II".
- Pride and Prejudice opened with a 4,967-word editor's preface and list of illustrations, and chapter 2 was titled `Chapter I.]`.

## Changed (rules in CHECKPOINTS CP1C, marked "CP3")
- **`text_cleaner.clean_for_speech` rule 0:** whole `[Illustration …]` blocks are removed, even across blank lines and with nested brackets (`[_Copyright 1894 by George Allen._]]`). A heading inside a block is kept (P&P prints `Chapter I.` only inside a caption). `^{rs}` superscripts become plain text. Lone `[` / `]` paragraphs are dropped.
- **`chapters` rule 1:** new headings:
  - Prologue, Epilogue, Preface, Introduction, Conclusion, Foreword, Afterword, including the `Translator’s/Editor’s/Author's …` forms.
  - `act` and `scene` as keywords, for plays.
  - Brackets around a heading are ignored.
- **Rule 2, sub-sections:**
  - A bare numeral inside a Part/Book/Volume/Act/Prologue/Epilogue gets the container's title (`Epilogue — I`, `Epilogue — II`).
  - A Scene inside an Act does the same (`Act I — Scene II`).
- **Rule 2a, front matter:** title pages, contents (including contents entries that are headings) and lists of illustrations before the first real section (≥ 20 story words) are dropped. The headings that belong to that section are kept (`Part I — Chapter I`). Trailing ALL-CAPS back matter (`THE END`, the printer's imprint) is dropped. If nothing looks like a chapter, nothing is dropped.
- **Rule 2b, prefaces:** a Preface/Introduction/Foreword is kept only if it's the author's own. It is dropped if:
  - its heading names a translator/editor/publisher/transcriber;
  - the title page credits it to someone else (`with a Preface by George Saintsbury`);
  - it is signed by someone else (`GEORGE SAINTSBURY.`).

  The author check uses the surname, the initials (`M. W. S.`) or the word `author`.
- **Rule 3:** a merged title doesn't repeat a heading (`Epilogue` + `Epilogue — I` → `Epilogue — I`).

## Contract change (ARCHITECTURE §5, §10.2)
- `split_chapters(text, authors=None)`. `pipeline.add_book` and `scripts/check_real_books.py` pass `metadata.authors`, and `preview_book` (CP4B) must do the same so the preview shows the same chapters. Without `authors`, only a signature or credit containing "author" counts as the author's.
- §10.2 example titles updated. The CP4D spec for `tests/test_check_real_books.py` now expects `1. Part One — Chapter I  (312 words)` and `max 312`.

## Tests
- New fixtures: `tests/fixtures/excerpt_84_frankenstein.txt`, `excerpt_2554_crime_and_punishment.txt` and `excerpt_1342_pride_and_prejudice.txt`. They are verbatim passages of the real books: front matter, the first chapters and the end.
- `tests/test_real_excerpts.py` checks the exact titles and that chapter 1 starts with the first sentence of the story.
- New rule tests are in `test_chapters.py` and `test_text_cleaner.py`. Four old tests that expected the table of contents to be merged into chapter 1 were updated.
- Full suite: **548 passed**.

## Real books (full texts, run here before pushing)
| Book | Before | After | First 5 | Last |
|---|---|---|---|---|
| Frankenstein (84) | 29 | 28 | Letter 1, Letter 2, Letter 3, Letter 4, Chapter 1 | Chapter 24 |
| Crime and Punishment (2554) | 42 | 41 | Part I — Chapter I, Chapter II, Chapter III, Chapter IV, Chapter V | Epilogue — II |
| Pride and Prejudice (1342) | 62 | 61 | Chapter I, Chapter II, Chapter III, Chapter IV, Chapter V | Chapter LXI |

## Known / not done
- Crime and Punishment footnote markers `[*]` and their notes are still read aloud (`[*] A religious sect. TRANSLATOR’S NOTE.`). The footnote rule only removes `[1]`-style markers.
- A real chapter with fewer than 20 story words before the first long chapter is treated as front matter, unless it sits directly before that chapter.
- Books already in a library keep their old chapters. Delete the book and add it again to get the new split.
