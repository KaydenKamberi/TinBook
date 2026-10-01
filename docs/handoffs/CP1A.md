# CP1A handoff — Claude Code
## Done
- **`core/tts.py`** follows ARCHITECTURE §5: `TTSError`, `list_voices()`, `synthesize_to_file()`, `check_environment()`.
  - Each `PiperVoice` is loaded once per voice name and cached (thread-safe).
  - The pipeline is text → WAV in a temp dir → ffmpeg → `out_path.part` → `os.replace` to `out_path`. If synthesis fails, the `.part` file is deleted and any existing complete file is left untouched.
  - The text goes to Piper one paragraph at a time (split on blank lines, hard wraps joined), and every chunk is streamed into the same WAV, so memory stays flat on long chapters. Paragraphs get a 0.4 s pause between them.
  - Duration is the WAV frame count divided by the sample rate.
  - ffmpeg is detected once (cached). Candidates are tried in order, bundled `imageio-ffmpeg` first, then `ffmpeg` on PATH. The first one whose `ffmpeg -hide_banner -encoders` output lists `libopus` is used. If none has it, `check_environment()["opus"]` is `False`, and asking for `opus` raises a `TTSError` that explains how to switch to mp3.
  - Two formats are supported: `opus` (`libopus`, `-f opus`) and `mp3` (`libmp3lame`, `-f mp3`), both encoded as mono at the bitrate passed in.
  - **Engine fallback:** if `from piper import PiperVoice` fails, the module runs a `piper` executable from PATH as `piper --model X.onnx --config X.onnx.json --output_raw`. It sends one paragraph per stdin line and streams the raw int16 output into the WAV. The sample rate comes from the voice's `.onnx.json`. Both the standalone binary and the piper-tts CLI accept these flags.
  - Any Piper, onnxruntime or OS failure is wrapped in `TTSError`.
- **`core/jobs.py`** follows ARCHITECTURE §5: `JobQueue` (`start`, `enqueue`, `status`, `stop`) and `get_queue()`, a process-wide singleton.
  - There is one daemon worker thread. `start()` is safe to call twice. It re-enqueues books whose status is `queued` or `generating`, oldest `added_at` first.
  - Chapters are processed in order. A chapter gets generated if its status is not `done` or its audio file is missing.
  - The book is saved after every chapter. It is reloaded from disk before every save, so changes made by the API in the meantime are kept.
  - Book status moves from `generating` to `ready`. If a chapter fails twice, that chapter is marked `error` and the book becomes `error` with a message like `"Chapter 2 (Chapter II) failed twice: …"`. The worker then moves on to the next book.
  - If an `error` book is enqueued again, its failed chapter is retried.
  - **Delete during generation:** after a chapter finishes, the book is reloaded. If it no longer exists, the new audio file is removed and the emptied folders are cleaned up, so a deleted book is never resurrected.
  - **Regenerate during generation:** if the voice or format changed during a chapter, that chapter is redone with the new settings. `enqueue()` on the book currently generating queues it again, so a late regenerate is never missed.
  - `stop()` lets the current chapter finish, then the worker exits. It waits at most 2 seconds. The book stays `generating`, so the next `start()` resumes it.
  - Bitrate: if the book's format matches `config.audio_format`, `config.audio_bitrate` is used. Otherwise the default for the book's format is used (`opus` → `32k`, `mp3` → `48k`).
- **Tests:** `tests/test_tts.py` (19) and `tests/test_jobs.py` (19). Piper, ffmpeg and `core.library` are all faked, so there is no network and no real synthesis. Full suite: **67 passed**. The threaded tests passed 40 runs in a row with no flakes.

## How to test
```
pip install -r requirements.txt
pytest -q
```
Steps I ran here: Piper was faked because the voice download is blocked in my sandbox, but ffmpeg was the real bundled one.
- A 3-chapter book produced 3 valid files: Ogg Opus, mono, 48 kHz, about 40 kb/s. `book.json` ended `ready`, and the durations matched ffprobe.
- I `kill -9`'d the process in the middle of chapter 3 of 5. On restart it resumed at chapter 3 and finished `ready`.

**Kayden: real-voice check on Windows** (after CP1B is merged, because it needs the real `core/library.py`). Run `python`, then paste:
```python
from core import library, jobs
from core.config import get_config
from core.models import SearchResult
c = get_config()
meta = SearchResult(999999, "Tinbook Test", ["Test"], "en", 0, None)
chapters = [("One", "Hello from chapter one."), ("Two", "This is chapter two.\n\nIt has two paragraphs."), ("Three", "And this is chapter three.")]
book = library.create_book(meta, "raw", chapters, c.default_voice, c.audio_format)
jobs.JobQueue()._process_book(book.id)
b = library.get_book(book.id); print(b.status, [(ch.status, round(ch.duration_sec, 1)) for ch in b.chapters])
print(library.book_dir(book.id))
```
You should see `ready [('done', …), ('done', …), ('done', …)]`. The folder it prints should contain `audio/000.opus` through `002.opus`, and each file should play. Delete that folder afterwards.

## Not done / known issues
- **Not tested with a real Piper voice.** Hugging Face is blocked in my sandbox. The Piper calls match the API recorded in the CP0 handoff (`PiperVoice.load` and `synthesize()` yielding `AudioChunk`s), and the Windows smoke test already passed with them. The real-voice check above covers the rest.
- **The `piper` executable fallback was only tested against a fake process.** To install it, if the pip package ever breaks: download `piper_windows_amd64.zip` (or `piper_linux_x86_64.tar.gz`) from https://github.com/rhasspy/piper/releases (release `2023.11.14-2`), unzip it, add the `piper` folder to PATH, and check that `piper --help` runs. The same `.onnx` voices work with it.
- **A failing chapter stops its book,** at the first chapter that fails twice. Later chapters are not attempted. This keeps chapters strictly in order (PRD D-3) and makes the error obvious.
- **No progress inside a chapter.** `status()` reports chapter-level progress only.

## Contract change requests
- Optional: add `"mp3": bool` to `check_environment()` so the UI can say whether the mp3 fallback would work. I didn't add it, to keep the contract exact.

## New dependencies needed
- None

## Notes for the next agent
- **CP1B (`library.py`).** `jobs` relies on these behaviours:
  - `get_book` raises `LibraryError` when the book is missing.
  - `list_books` skips unreadable books instead of raising; `start()` calls it.
  - `chapter_audio_path` / `chapter_text_path` only build paths and don't create folders. `tts` creates `audio/` itself.
  - `save_book` is atomic.
- **CP2A.**
  - Call `get_queue().start()` once, at app creation.
  - `pipeline.regenerate_book` should delete `audio/`, reset the chapters to `pending`, set the voice and status `queued`, save, then `enqueue`. This is safe even while that book is generating.
  - `DELETE /api/books/<id>` needs no queue call. The worker notices the deletion and cleans up after itself.
  - Call `get_queue().stop()` on window close.
- **CP2B.** `GET /api/jobs` returns `{"current": {"book_id", "chapter_index", "chapters_done", "chapters_total"} | None, "queued": [...]}`. `chapter_index` is `None` for a moment at the start and end of a book.
- **Tests that touch config:** call `get_config.cache_clear()`, and also `tts._detect_ffmpeg.cache_clear()` and `tts._voice_cache.clear()` if they use `tts`.
