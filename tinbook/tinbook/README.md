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
