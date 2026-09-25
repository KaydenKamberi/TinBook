# replit.md

Read `AGENTS.md` first — it is the source of truth for all agents on this repo.

You are **Replit Agent**. Notes for this environment:
- pywebview cannot open a window in Replit. Run the app with `python -m desktop.app --browser`, which serves Flask on `0.0.0.0:5000` for the preview pane.
- You own environment setup (CP0): `requirements.txt`, `.replit`/Nix config if needed, `scripts/download_voice.py`. If Piper or ffmpeg needs a system package on Replit, set it up here and document it in your handoff.
- No secrets are needed for this project. Do not add any.
- Work on your checkpoint's branch only; don't push to `main`.
