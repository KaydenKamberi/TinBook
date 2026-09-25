# Architecture & Contracts

> **Everything in this file is a contract.** Agents implement it exactly. Changes go through a "Contract change request" in a handoff note and are only applied by Claude Code in an integration checkpoint.

## 1. Repository layout
```
tinbook/
├── AGENTS.md  CLAUDE.md  replit.md  README.md  .gitignore
├── requirements.txt            # desktop + dev deps (CP0)
├── requirements-device.txt     # Pi deps (CP5)
├── config.json                 # defaults, committed (CP0)
├── core/                       # shared by desktop AND device — pure Python, no UI
│   ├── __init__.py
│   ├── config.py               # CP0
│   ├── models.py               # CP0
│   ├── gutenberg.py            # CP1B
│   ├── text_cleaner.py         # CP1C
│   ├── chapters.py             # CP1C
│   ├── progress.py             # CP1C
│   ├── library.py              # CP1B
│   ├── tts.py                  # CP1A
│   ├── jobs.py                 # CP1A
│   └── pipeline.py             # CP2A
├── desktop/
│   ├── __init__.py
│   ├── app.py                  # pywebview launcher (CP0 stub, CP2A real)
│   ├── server.py               # Flask API (CP2A)
│   ├── device_sync.py          # Send-to-Tinbook over USB (CP6C)
│   ├── templates/index.html    # CP2B
│   └── static/
│       ├── app.js  style.css   # CP2B
│       └── settings.js         # CP4B
├── device/                     # Phase 2, runs on the Pi only
│   ├── __init__.py
│   ├── main.py                 # app loop / state machine (CP7)
│   ├── display.py              # screen rendering (CP6B)
│   ├── buttons.py              # button events (CP6B)
│   ├── player.py               # mpv wrapper (CP6A)
│   ├── bluetooth.py            # bluetoothctl wrapper (CP6A)
│   ├── power.py                # PiSugar client (CP6C)
│   └── usb_sync.py             # USB gadget switching (CP7)
├── scripts/
│   ├── download_voice.py       # CP0
│   ├── smoke_test.py           # CP0
│   ├── run.bat                 # CP2C
│   └── pi/
│       ├── setup.sh            # CP5
│       ├── make_library_image.sh  # CP5
│       └── tinbook.service     # CP7
├── tests/
│   ├── fixtures/               # sample texts (CP1C)
│   └── test_*.py
├── voices/                     # gitignored; Piper .onnx + .onnx.json
├── library/                    # gitignored; generated books
└── docs/
```

## 2. Configuration (`core/config.py`)
```python
@dataclass(frozen=True)
class Config:
    root_dir: Path            # repo root
    library_dir: Path         # default: <root>/library
    voices_dir: Path          # default: <root>/voices
    default_voice: str        # "en_US-lessac-medium"
    audio_format: str         # "opus" (fallback "mp3")
    audio_bitrate: str        # "32k" for opus, "48k" for mp3
    host: str                 # "127.0.0.1"
    port: int                 # 0 = pick a free port (desktop window); 5000 in --browser mode
    user_agent: str           # "Tinbook/0.1 (personal audiobook project)"
    http_timeout: int         # 20 (seconds)

def get_config() -> Config: ...
```
Load order (later wins): built-in defaults → `config.json` (committed) → `config.local.json` (gitignored) → environment variables `TINBOOK_LIBRARY_DIR`, `TINBOOK_VOICES_DIR`, `TINBOOK_DEFAULT_VOICE`, `TINBOOK_PORT`. Cache the result (`functools.lru_cache`). Create `library_dir` and `voices_dir` if missing.

## 3. Data models (`core/models.py`)
All dataclasses have `to_dict() -> dict` and `@classmethod from_dict(d: dict)`. Unknown keys in `from_dict` are ignored.
```python
@dataclass
class SearchResult:
    gutenberg_id: int
    title: str
    authors: list[str]        # e.g. ["Dostoyevsky, Fyodor"]
    language: str             # "en"
    download_count: int
    text_url: str | None      # plain-text URL, None if no plain text available

ChapterStatus = Literal["pending", "done", "error"]
BookStatus = Literal["queued", "generating", "ready", "error"]

@dataclass
class Chapter:
    index: int                # 0-based
    title: str
    word_count: int
    status: ChapterStatus = "pending"
    duration_sec: float | None = None
    # derived, not stored: text file = text/{index:03d}.txt ; audio = audio/{index:03d}.{ext}

@dataclass
class Book:
    id: str                   # "{gutenberg_id}-{slug}"  e.g. "2554-crime-and-punishment"
    gutenberg_id: int
    title: str
    authors: list[str]
    voice: str
    audio_format: str         # "opus" | "mp3"
    status: BookStatus
    chapters: list[Chapter]
    added_at: str             # ISO 8601 UTC
    error: str | None = None
    schema_version: int = 1
    # helpers:
    def chapters_done(self) -> int: ...
    def total_duration_sec(self) -> float: ...   # sum of known durations

@dataclass
class Progress:
    chapter_index: int = 0
    position_sec: float = 0.0
    speed: float = 1.0
    finished: bool = False
    updated_at: str = ""      # ISO 8601 UTC; "" means never saved
```
**Slug rule:** lowercase title, keep `[a-z0-9]`, collapse everything else to single `-`, strip `-` from ends, max 40 chars (cut at last `-` before 40 if possible). Implemented as `models.slugify(title: str) -> str`.
**Time helper:** `models.now_iso() -> str` returns UTC like `2026-09-24T18:03:11Z`.

## 4. Library folder format (shared by desktop & device)
```
library/
└── 2554-crime-and-punishment/
    ├── book.json        # Book.to_dict()
    ├── progress.json    # Progress.to_dict()  (missing = default Progress)
    ├── raw.txt          # original download (desktop only, not synced)
    ├── text/000.txt …   # cleaned chapter text (desktop only, not synced)
    └── audio/000.opus … # chapter audio
```
Device copy contains only `book.json`, `progress.json`, `audio/`.

## 5. Module contracts

### `core/gutenberg.py` (CP1B)
```python
class GutenbergError(Exception): ...
def search(query: str, page: int = 1) -> list[SearchResult]
def get_metadata(gutenberg_id: int) -> SearchResult
def download_text(gutenberg_id: int) -> str     # raw UTF-8 text
```
- Gutendex: `GET https://gutendex.com/books/?search=<q>&languages=en&page=<n>`; single: `GET https://gutendex.com/books/<id>/`.
- `text_url` priority from `formats`: key starting with `text/plain; charset=utf-8` → `text/plain; charset=us-ascii` → any key starting with `text/plain`. Skip URLs ending in `.zip`.
- Send `User-Agent` from config; use `http_timeout`. Decode bytes as UTF-8 with `errors="replace"`.
- Results whose `text_url` is None are still returned (UI shows them disabled).

### `core/text_cleaner.py` (CP1C)
```python
def strip_gutenberg_boilerplate(raw: str) -> str
def clean_for_speech(text: str) -> str
def clean(raw: str) -> str      # = clean_for_speech(strip_gutenberg_boilerplate(raw))
```
See CP1C in CHECKPOINTS.md for exact rules.

### `core/chapters.py` (CP1C)
```python
def split_chapters(text: str) -> list[tuple[str, str]]   # [(title, chapter_text), ...], never empty
```
See CP1C for exact rules.

### `core/progress.py` (CP1C)
```python
def load_progress(book_dir: Path) -> Progress          # default Progress() if file missing/corrupt
def save_progress(book_dir: Path, progress: Progress) -> Progress   # sets updated_at=now_iso(), atomic write, returns saved copy
def newer(a: Progress, b: Progress) -> Progress        # the one with the later updated_at ("" is oldest); tie -> a
```
Note: takes a `book_dir` Path (not a book id) so it works on desktop and device with no config dependency. Uses `core.library.write_json_atomic` — if CP1B isn't merged yet, implement a private `_write_json_atomic` with identical behavior.

### `core/library.py` (CP1B)
```python
class LibraryError(Exception): ...
def write_json_atomic(path: Path, data: dict) -> None   # writes path.tmp then os.replace; utf-8, indent=2
def book_dir(book_id: str) -> Path
def create_book(meta: SearchResult, raw_text: str, chapters: list[tuple[str, str]], voice: str, audio_format: str) -> Book
    # creates folder, raw.txt, text/NNN.txt, book.json (status "queued"). Raises LibraryError if it already exists.
def list_books() -> list[Book]          # sorted by added_at desc; skips folders with unreadable book.json (log warning)
def get_book(book_id: str) -> Book      # raises LibraryError if missing
def save_book(book: Book) -> None       # atomic
def delete_book(book_id: str) -> None
def chapter_text_path(book_id: str, index: int) -> Path
def chapter_audio_path(book_id: str, index: int, audio_format: str) -> Path
```

### `core/tts.py` (CP1A)
```python
class TTSError(Exception): ...
def list_voices() -> list[str]          # voice names found in voices_dir (e.g. "en_US-lessac-medium")
def synthesize_to_file(text: str, out_path: Path, voice: str, audio_format: str, bitrate: str) -> float
    # returns duration in seconds. Writes to out_path.part then renames, so partial files never look complete.
def check_environment() -> dict         # {"piper": bool, "ffmpeg": str|None, "opus": bool, "voices": [...]} for smoke tests/UI
```

### `core/jobs.py` (CP1A)
```python
class JobQueue:
    def start(self) -> None             # starts ONE daemon worker thread; re-enqueues books with status queued/generating
    def enqueue(self, book_id: str) -> None
    def status(self) -> dict            # {"current": {"book_id", "chapter_index", "chapters_done", "chapters_total"} | None, "queued": [book_id, ...]}
    def stop(self) -> None
def get_queue() -> JobQueue             # process-wide singleton
```
Worker: for each chapter in order where status != "done" or audio file missing → synthesize → set status/duration → `save_book` after **every** chapter. Book status: `generating` while running, `ready` when all done, `error` (with message) if a chapter fails twice. Reload the book from disk before each save (the API may have changed it).

### `core/pipeline.py` (CP2A)
```python
def add_book(gutenberg_id: int, voice: str | None = None) -> Book
    # get_metadata → download_text → clean → split_chapters → create_book → get_queue().enqueue
def regenerate_book(book_id: str, voice: str) -> Book   # delete audio/, reset chapters to pending, set voice, enqueue
```

## 6. Desktop HTTP API (`desktop/server.py`, CP2A)
All JSON. Errors: HTTP 4xx/5xx with `{"error": "message"}`.

| Method & path | Body / query | Returns |
|---|---|---|
| `GET /` | | `index.html` |
| `GET /api/health` | | `{"ok": true, "env": check_environment()}` |
| `GET /api/search` | `?q=...&page=1` | `{"results": [SearchResult...]}` |
| `GET /api/books` | | `{"books": [BookView...]}` |
| `POST /api/books` | `{"gutenberg_id": 2554, "voice": null}` | `BookView` (201) |
| `GET /api/books/<id>` | | `BookView` |
| `DELETE /api/books/<id>` | | `{"ok": true}` |
| `POST /api/books/<id>/regenerate` | `{"voice": "..."}` | `BookView` |
| `GET /api/books/<id>/chapters/<n>/audio` | | audio file (`send_file`, `conditional=True` for Range/seek support); 404 if not generated |
| `GET /api/books/<id>/progress` | | `Progress` |
| `PUT /api/books/<id>/progress` | `Progress` fields | saved `Progress` |
| `GET /api/jobs` | | `JobQueue.status()` |
| `GET /api/voices` | | `{"voices": [...], "default": "..."}` |
| `PUT /api/settings` | `{"default_voice": "..."}` | saved settings; writes `config.local.json` and clears config cache (CP4B) |
| `GET /api/device` | | `{"connected": bool, "path": str|None}` (CP6C) |
| `POST /api/device/sync` | `{"book_ids": [...]}` or `{"all": true}` | sync report (CP6C) |

`BookView` = `Book.to_dict()` plus `"progress": Progress`, `"chapters_done": int`, and each chapter gets `"audio_url"` (or null).

## 7. Frontend (CP2B)
Single page, three views toggled by tabs: **Library**, **Search**, **Player**. Polls `/api/books` and `/api/jobs` every 3s while any book is generating. One `<audio>` element. Talks only to the API above.

## 8. Device (Phase 2) — overview
- Library lives at `/mnt/tinbook/library/` inside a FAT32 image (`/home/tinbook/tinbook.img`, label `TINBOOK`), loop-mounted in normal mode, exported via `g_mass_storage` in sync mode.
- `TINBOOK_LIBRARY_DIR=/mnt/tinbook/library` so `core/models.py` + `core/progress.py` work unchanged.
- The desktop only syncs books whose status is `ready`. The device lists every book folder it finds and loads it with `Book.from_dict`.
- Detailed hardware, pins and button mapping: `docs/HARDWARE.md`.
