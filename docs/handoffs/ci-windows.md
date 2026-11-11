# CI (Windows check) handoff — Claude Code
Branch `ci-windows-claude`, from `main` at `50e847d` (CP3 merged). Requested by Kayden. Only new files, plus a "CI" section in `README.md`. No existing code changed.

## Done
- **`.github/workflows/windows-check.yml`** ("Windows check"): `windows-latest`, Python 3.11, pip cache. Runs on `workflow_dispatch`, pull requests to `main`, and pushes to `main`. Job timeout 30 min; every step has its own timeout; a second push to the same branch cancels the older run.
  1. `pip install -r requirements.txt -r requirements-dev.txt`, then `pytest`.
  2. `scripts/download_voice.py en_US-lessac-medium` (the `voices/` folder is cached between runs), then `scripts/smoke_test.py`.
  3. `scripts/ci/check_books.py`: runs `check_real_books.py` on 84, 2554 and 1342 and saves the report to `ci-out/check_real_books.txt`. After each book it lists every HTTP request and prints `Source:` lines (Gutendex, or `FALLBACK: …` with the catalog or direct URL), then `Gutendex: UP/DOWN`. The step passes if the books come through the fallback while Gutendex is down. The job Summary page shows these lines.
  4. `scripts/ci/e2e_generate.py`: real `pipeline.add_book(84)`. Chapters 3+ are marked `skipped` **before** the worker starts, so the real `JobQueue` (real Piper + ffmpeg) generates exactly chapters 1–2, then `queue.stop()`. Checks both `.opus` files exist, start with `OggS`, and have `duration_sec > 0`. It copies them to `ci-out/audio/` and prints the real-time factor.
  5. `scripts/ci/browser_test.py` (Playwright, Chromium, 420×720): starts `python -m desktop.app --browser` with an empty library, logging to `ci-out/server.log`. Then: search "frankenstein" → Add → wait for chapter 1 → **Start** → playing → seek bar to 4 s before the end → auto-advance to chapter 2 (screenshot of "Waiting for chapter 2…" if it shows) → the server's progress shows chapter 2 → reload → **Continue** → playing in chapter 2 within 5 s of where it was. Screenshots `01`–`10` go to `ci-out/screenshots/`; browser console messages go to `ci-out/browser-console.log`.
  6. Uploads `ci-out/` as the artifact `tinbook-windows-check` (14 days), even when a step fails.
- **Retries:** `scripts/ci/retry.py` (attempts + timeout per attempt + doubling delay) wraps pip, the voice download, the books check and `playwright install`. The e2e and browser scripts retry their own network parts (add/search, 3 tries) so they don't regenerate audio on a retry.
- **`requirements-dev.txt`** (new): `playwright>=1.47,<2`.

## How to test
- GitHub → Actions → **Windows check** → Run workflow → branch. Downloads are under the run's **Artifacts**.
- Locally (Windows): `pip install -r requirements-dev.txt`, `python -m playwright install chromium`, then e.g. `python scripts\ci\check_books.py --out %TEMP%\books.txt` or the browser test command in README → CI.
- Verified in the Linux sandbox before pushing (Gutenberg and Hugging Face are blocked here, so Gutenberg and Piper were faked in-process; a sine tone stood in for Piper's audio):
  - `e2e_generate.py` → exactly 2 Ogg files with durations, book `ready`.
  - `browser_test.py` → PASS, including the "Waiting for chapter 2…" path and a resume within 0.9 s.
  - `check_books.py` with Gutendex mocked down → `FALLBACK` lines, exit 0. With it up → `primary`.

## Not done / known issues
- Wording: a brand-new book's library button says **Start**, not Continue (`app.js` `actionLabel`). The test clicks Start first and checks for **Continue** after the reload.
- The first real Windows run is the real test of everything above (headless Chromium audio on a runner with no sound card, real Piper speed). See "First run" below.
- Local runs of the CI scripts write to whatever `--out` you give. `ci-out/` is not in `.gitignore` (I didn't edit existing files), so use a temp folder locally.
- Cost: on a private repo, Windows minutes count ×2 against the free Actions minutes. Each run is roughly 15–25 min. Pushes to `main` and every PR update trigger it.

## Contract change requests
- None. The scripts only use public `core` functions, apart from `scripts/ci/gutenberg_source.py`, which wraps the private `core.gutenberg._request` to log which URLs were used. If that function is renamed, only the source lines break.

## New dependencies needed
- `playwright` (dev/CI only), in the new `requirements-dev.txt`.

## First run
- (filled in after the first run on this branch)
