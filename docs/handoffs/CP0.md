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