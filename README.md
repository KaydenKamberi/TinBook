# Tinbook

A pocket audiobook player built from free Project Gutenberg books and offline, open-source text-to-speech (Piper).

- **Phase 1 — Desktop app:** a small Windows window (Flask + pywebview). Search Gutenberg, add a book, it gets converted to audio chapter by chapter, and you listen while you work.
- **Phase 2 — The device:** a Raspberry Pi Zero 2 WH in an Altoids tin with a 2" screen and 4 buttons. It plays the same audiobooks to Bluetooth earbuds (AirPods). Books are prepared on the PC and copied over USB.

Everything runs locally. No accounts, no API keys, no cloud.

---

## For AI agents
**Read [`AGENTS.md`](AGENTS.md) first. Always.** It tells you how this repo works, what you own, and how to hand off.

## For Kayden (human)
| File | What it's for |
|---|---|
| `AGENTS.md` | Shared rules for every AI (Claude Code, Replit, Mistral) |
| `CLAUDE.md` / `replit.md` | Auto-loaded by Claude Code / Replit; they point to AGENTS.md |
| `docs/PRD.md` | What we're building and why |
| `docs/ARCHITECTURE.md` | File layout, data formats, and function contracts (the "rules of the road" that let AIs work in parallel) |
| `docs/CHECKPOINTS.md` | Every checkpoint, who owns it, what runs in parallel, and the kickoff prompt |
| `docs/HARDWARE.md` | Exact device parts + specs (AI-facing, for Phase 2) |
| `docs/PARTS_LIST.md` | Shopping list with prices (for you / Claude Cowork) |
| `docs/handoffs/` | Each AI leaves a note here when it finishes a checkpoint |

### Kickoff prompt template
Paste this into whichever AI owns the checkpoint:

```
Repo: <your GitHub URL>
Read AGENTS.md, then docs/ARCHITECTURE.md, then checkpoint CP__ in docs/CHECKPOINTS.md.
Also read any handoff notes in docs/handoffs/ that CP__ depends on.
Do CP__ only. Work on branch cp__-<agent>. Write your handoff note when done.
```

### Merge workflow
1. Each AI works on its own branch (`cp1a-claude`, `cp1b-replit`, `cp1c-mistral`, ...).
2. When all checkpoints in a wave are done, merge them into `main` in the order listed in CHECKPOINTS.md.
3. Pull `main` onto your Windows PC and test before starting the next wave.

## Running (after CP2)
Windows:
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/download_voice.py en_US-lessac-medium
python -m desktop.app
```
Replit / headless: `python -m desktop.app --browser` (serves on 0.0.0.0:5000 for the preview tab).

## CI
`.github/workflows/windows-check.yml` ("Windows check") runs on a GitHub Windows runner with Python 3.11 on every pull request to `main`, every push to `main`, and on demand. It runs `pytest`, the Piper smoke test, the real-books check, a real 2-chapter generation of *Frankenstein*, and a Playwright browser test of the UI (search → add → play → auto-advance → reload → resume).

- **Run it manually:** GitHub → **Actions** → **Windows check** → **Run workflow** → pick the branch → **Run workflow**.
- **Downloads:** open the run → **Summary** → **Artifacts** → `tinbook-windows-check` (zip): `check_real_books.txt` (says whether Gutendex or the fallback was used), `audio/*.opus` (the 2 generated chapters), `screenshots/*.png`, `server.log` and `browser-console.log`. Kept for 14 days. The run's Summary page also shows the real-books results.
- To run the browser test locally: `pip install -r requirements-dev.txt`, `python -m playwright install chromium`, then `python scripts/ci/browser_test.py --library %TEMP%\tinbook-ci-library --out %TEMP%\tinbook-ci-out` (it uses port 5000, so close any running `--browser` server first).
