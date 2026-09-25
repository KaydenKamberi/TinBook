# AGENTS.md — Read this before doing anything

You are one of three AI agents building **Tinbook** in parallel. The human (Kayden) assigns you one checkpoint at a time. Other agents are working on other checkpoints **at the same time, on other branches**. The rules below exist so we don't break each other's work.

## 1. What Tinbook is (30-second version)
- Search Project Gutenberg → download plain text → clean it → split into chapters → Piper TTS turns each chapter into an `.opus` file → play it back with saved progress.
- **Phase 1:** desktop app (Windows, Flask + pywebview, vanilla HTML/CSS/JS frontend).
- **Phase 2:** Raspberry Pi Zero 2 WH pocket device (2" screen, 4 buttons, Bluetooth audio) that plays books prepared by the desktop app.
- Full details: `docs/PRD.md`. Contracts: `docs/ARCHITECTURE.md`. Tasks: `docs/CHECKPOINTS.md`.

## 2. Required reading order
1. `AGENTS.md` (this file)
2. `docs/ARCHITECTURE.md` — the contracts. **These are law.**
3. Your checkpoint in `docs/CHECKPOINTS.md`
4. Handoff notes in `docs/handoffs/` for every checkpoint yours depends on
5. `docs/HARDWARE.md` — only for Phase 2 (device) checkpoints

## 3. The agent roster
| Agent | Strength | Gets |
|---|---|---|
| **Claude Code** | Strongest. Hard logic, integration, debugging, Linux/system work, code review | TTS engine, job queue, frontend, integration passes, all tricky device work |
| **Replit Agent** | Mid. Has the Replit environment, package installs, secrets, live preview | Scaffolding, env/config, API wiring, networking modules, device display |
| **Mistral (Vibe)** | Most literal. Best with tight specs and pure functions | Isolated pure-function modules, tests, scripts, docs |

If you are Mistral: follow the spec **exactly**. Do not add features, refactor other files, or "improve" contracts. When unsure, pick the simplest option that satisfies the acceptance criteria and note it in your handoff.

## 4. Hard rules
1. **Only edit files your checkpoint owns.** Each checkpoint lists "Owns" (create/edit), "Reads" (look, don't touch). Touching anything else causes merge conflicts with other agents.
2. **Never change a contract** in `docs/ARCHITECTURE.md` (function signatures, JSON schemas, API routes, folder layout). If you believe a contract is wrong, implement it as written anyway and put a **Contract change request** in your handoff. Claude Code resolves these in integration checkpoints.
3. **Branch:** `cp<id>-<agent>` in lowercase, e.g. `cp1c-mistral`. Never commit to `main`.
4. **Commits:** prefix with the checkpoint, e.g. `CP1C: add chapter splitter`.
5. **Dependencies:** `requirements.txt` is owned by CP0. If you need a new package, don't edit it — list it in your handoff under "New dependencies needed."
6. **Never commit** `library/`, `voices/`, `*.onnx`, `*.opus`, `*.wav`, `.venv/`, or anything in `.gitignore`.
7. **No secrets exist in this project.** No API keys are needed (Gutendex and Piper are free/keyless). Do not add any.
8. **Cross-platform:** core code must run on Windows 10/11 and Linux (Replit, Raspberry Pi OS). Use `pathlib`, never hardcode `C:\` or `/home/...`. Get paths from `core/config.py`.
9. Do not delete or rewrite another agent's stubs, tests, or TODOs outside your owned files.

## 5. Code style
- Python 3.11. Type hints on all public functions. Short docstrings.
- `logging` (logger per module: `log = logging.getLogger(__name__)`), not `print`, except in `scripts/`.
- Raise the module's own exception class (defined in ARCHITECTURE.md) for expected failures.
- JSON writes must be **atomic**: write to `file.tmp` then `os.replace()`. Use `core.library.write_json_atomic`.
- Tests: `pytest`, in `tests/`, no network access in tests (mock HTTP).
- Frontend: vanilla HTML/CSS/JS. No build step, no npm, no frameworks.

## 6. Definition of done (every checkpoint)
- [ ] All acceptance criteria in your checkpoint are met
- [ ] `pytest` passes (at least for your modules)
- [ ] You only changed files you own
- [ ] Handoff note written at `docs/handoffs/CP<id>.md`
- [ ] Committed and pushed to your branch

## 7. Handoff note template
Create `docs/handoffs/CP<id>.md`:
```
# CP<id> handoff — <agent name>
## Done
- bullet list of what works
## How to test
- exact commands
## Not done / known issues
## Contract change requests
- (or "None")
## New dependencies needed
- (or "None")
## Notes for the next agent
```
