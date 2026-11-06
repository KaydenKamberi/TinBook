# Architecture & Contracts

> **Everything in this file is a contract.** Agents implement it exactly. Changes go through a "Contract change request" in a handoff note and are only applied by Claude Code in an integration checkpoint.
>
> CP3 (Nov 2026) added Voice options (§9) and Start from a chapter (§10) for Wave 4. Items marked **(CP4x)** are contracts whose implementation lands in that Wave 4 checkpoint; until then the code has stubs with the exact signatures.

## 1. Repository layout
```
tinbook/
├── AGENTS.md  CLAUDE.md  replit.md  README.md  .gitignore  .gitattributes
├── requirements.txt            # desktop + dev deps (CP0; kokoro-onnx added in CP3)
├── requirements-device.txt     # Pi deps (CP5)
├── config.json                 # defaults, committed (CP0)
├── core/                       # shared by desktop AND device — pure Python, no UI
│   ├── __init__.py
│   ├── config.py               # CP0
│   ├── models.py               # CP0 (+ "skipped", CP3)
│   ├── gutenberg.py            # CP1B (+ catalog fallback)
│   ├── text_cleaner.py         # CP1C
│   ├── chapters.py             # CP1C
│   ├── progress.py             # CP1C
│   ├── library.py              # CP1B
│   ├── tts.py                  # CP1A; multi-engine in CP4A
│   ├── tts_kokoro.py           # Kokoro engine (CP4A)
│   ├── voices.py               # voice IDs, catalog, downloads, previews (CP3 + CP4A)
│   ├── voice_catalog.json      # curated voice catalog (CP3; maintained by CP4A)
│   ├── jobs.py                 # CP1A; priority in CP4B
│   └── pipeline.py             # CP2A; start-from-chapter in CP4B
├── desktop/
│   ├── __init__.py
│   ├── app.py                  # pywebview launcher (CP2A; close-save CP3)
│   ├── server.py               # Flask API (CP2A; Wave 4 routes CP4C)
│   ├── settings.py             # config.local.json read/update (CP4C)
│   ├── device_sync.py          # Send-to-Tinbook over USB (CP6C)
│   ├── templates/index.html    # CP2B, CP4B
│   └── static/                 # app.js, style.css, any new .js/.css (CP2B, CP4B)
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
│   ├── download_voice.py       # CP0; any voice ID in CP4A
│   ├── verify_voice_catalog.py # CP4A
│   ├── smoke_test.py           # CP0; + Kokoro in CP4A
│   ├── check_real_books.py     # CP3
│   ├── run.bat                 # CP2C
│   └── pi/
│       ├── setup.sh            # CP5
│       ├── make_library_image.sh  # CP5
│       └── tinbook.service     # CP7
├── tests/
│   ├── conftest.py             # shared opt-in fixtures (CP4D)
│   ├── fixtures/               # sample texts (CP1C)
│   └── test_*.py
├── voices/                     # gitignored; see §9.2 for the layout
├── library/                    # gitignored; generated books (§4)
└── docs/
```

## 2. Configuration (`core/config.py`)
```python
@dataclass(frozen=True)
class Config:
    root_dir: Path            # repo root
    library_dir: Path         # default: <root>/library
    voices_dir: Path          # default: <root>/voices
    default_voice: str        # "en_US-lessac-medium"; any voice ID (§9.1). The app saves the last-used voice here (§9.5)
    audio_format: str         # "opus" (fallback "mp3")
    audio_bitrate: str        # "32k" for opus, "48k" for mp3
    host: str                 # "127.0.0.1"
    port: int                 # 0 = pick a free port (desktop window); 5000 in --browser mode
    user_agent: str           # "Tinbook/0.1 (personal audiobook project)"
    http_timeout: int         # 20 (seconds)

def get_config() -> Config: ...
```
Load order (later wins): built-in defaults → `config.json` (committed) → `config.local.json` (gitignored) → environment variables `TINBOOK_LIBRARY_DIR`, `TINBOOK_VOICES_DIR`, `TINBOOK_DEFAULT_VOICE`, `TINBOOK_PORT`. Cache the result (`functools.lru_cache`). Create `library_dir` and `voices_dir` if missing. Code that writes `config.local.json` must call `get_config.cache_clear()` afterwards.

## 3. Data models (`core/models.py`)
All dataclasses have `to_dict() -> dict` and `@classmethod from_dict(d: dict)`. Unknown keys in `from_dict` are ignored. `Book.from_dict` treats a missing `chapters` key as `[]`.
```python
@dataclass
class SearchResult:
    gutenberg_id: int
    title: str
    authors: list[str]        # e.g. ["Dostoyevsky, Fyodor"]
    language: str             # "en"
    download_count: int
    text_url: str | None      # plain-text URL, None if no plain text available

ChapterStatus = Literal["pending", "done", "error", "skipped"]   # "skipped" added in CP3 (§10)
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
    voice: str                # voice ID (§9.1). New books store the canonical "engine:name"; older plain names stay valid
    audio_format: str         # "opus" | "mp3"
    status: BookStatus        # "ready" = every chapter is "done" or "skipped" (is_complete())
    chapters: list[Chapter]
    added_at: str             # ISO 8601 UTC
    error: str | None = None
    schema_version: int = 1
    # helpers:
    def chapters_done(self) -> int: ...          # chapters with status "done"
    def chapters_skipped(self) -> int: ...       # chapters with status "skipped" (CP3)
    def is_complete(self) -> bool: ...           # every chapter "done" or "skipped" (CP3)
    def total_duration_sec(self) -> float: ...   # sum of known durations

@dataclass
class Progress:
    chapter_index: int = 0
    position_sec: float = 0.0
    speed: float = 1.0
    finished: bool = False
    updated_at: str = ""      # ISO 8601 UTC; "" means never saved
```
**Slug rule:** transliterate to ASCII first (Unicode NFKD, drop combining marks, so `é` → `e`), lowercase, keep `[a-z0-9]`, collapse everything else to single `-`, strip `-` from ends, max 40 chars (cut at the last `-` at or before position 40 if possible, so a word ending exactly at 40 is kept; otherwise hard-cut at 40). If the result is empty, return `"book"`. Implemented as `models.slugify(title: str) -> str`.
**Time helper:** `models.now_iso() -> str` returns UTC like `2026-09-24T18:03:11Z`.

## 4. Library folder format (shared by desktop & device)
```
library/
├── 2554-crime-and-punishment/
│   ├── book.json        # Book.to_dict()
│   ├── progress.json    # Progress.to_dict()  (missing = default Progress)
│   ├── raw.txt          # original download (desktop only, not synced)
│   ├── text/000.txt …   # cleaned chapter text (desktop only, not synced)
│   └── audio/000.opus … # chapter audio (none for "skipped" or not-yet-generated chapters)
├── pg_catalog.csv       # Gutenberg catalog cache (§5 gutenberg fallback; desktop only)
└── .cache/84.txt        # downloaded text waiting to be added (§10.2; desktop only)
```
Device copy contains only `book.json`, `progress.json`, `audio/`. **Any folder whose name starts with `.` is never a book** (`list_books` skips it silently); files at the top level are ignored.

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
- Send `User-Agent` from config. Gutendex requests use a timeout of `min(8, http_timeout)` seconds so the fallback starts quickly; gutenberg.org requests use `http_timeout`. Decode bytes as UTF-8 with `errors="replace"`.
- Results whose `text_url` is None are still returned (UI shows them disabled).
- **Fallback when Gutendex fails** (timeout, connection error, non-200, invalid JSON/metadata):
  - `download_text`: download `https://www.gutenberg.org/cache/epub/<id>/pg<id>.txt` directly. Also tried if Gutendex works but its `text_url` download fails. A 404 there means "no plain-text download".
  - `search` / `get_metadata`: use Project Gutenberg's catalog `https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv`, cached at `<library_dir>/pg_catalog.csv` (written via `.tmp` + `os.replace`, only after it parses). Re-downloaded when older than 7 days; if that refresh fails, the old copy is used (refresh retried at most every 10 min). Parsed once per process and kept in memory until the file changes.
  - Catalog search: English only (`Language` contains `en`); every query word (case- and accent-insensitive) must appear in title + authors. Order: exact title, title starts with query, title contains query, all words in title, author-only match; then books with text before audio; then lowest ID. 32 results per page (as Gutendex).
  - Catalog → `SearchResult`: `download_count=0`; `authors` = `Authors` entries without a `[Role]` (translators etc.), life dates removed (`"Dostoyevsky, Fyodor, 1821-1881"` → `"Dostoyevsky, Fyodor"`); `text_url` = the direct URL above if `Type` is `Text`, else None. `get_metadata` returns any language; unknown IDs raise `GutenbergError`.
  - Exception: a Gutendex 404 for `search` with `page > 1` means "past the last page", so `search` returns `[]` and does not use the catalog (no catalog results mixed into later pages).
  - After Gutendex times out, is unreachable or returns 5xx, it is skipped for 60 s (straight to the fallback). 404s do not pause it.
  - If the fallback also fails, raise `GutenbergError` mentioning both failures (stated once if both failed with the same message).

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
See CP1C for exact rules. Deterministic: the same text always gives the same chapters (§10.2 relies on it).

### `core/progress.py` (CP1C)
```python
def load_progress(book_dir: Path) -> Progress          # default Progress() if file missing/corrupt (bad JSON, non-UTF-8, not an object); bad field types -> that field's default
def save_progress(book_dir: Path, progress: Progress) -> Progress   # sets updated_at=now_iso(), atomic write, returns a new saved copy (the argument is not modified)
def newer(a: Progress, b: Progress) -> Progress        # the one with the later updated_at ("" is oldest); tie -> a
```
Takes a `book_dir` Path (not a book id) so it works on desktop and device. Writes through `core.library.write_json_atomic` (CP3). `save_progress` raises `LibraryError` if `book_dir` does not exist — it never recreates a deleted book's folder.

### `core/library.py` (CP1B)
```python
class LibraryError(Exception): ...
def write_json_atomic(path: Path, data: dict) -> None   # writes path.tmp then os.replace; utf-8, indent=2
def book_dir(book_id: str) -> Path
def create_book(meta: SearchResult, raw_text: str, chapters: list[tuple[str, str]], voice: str, audio_format: str) -> Book
    # creates folder, raw.txt, text/NNN.txt, book.json (status "queued", chapters "pending"). Raises LibraryError if it already exists.
def list_books() -> list[Book]          # sorted by added_at desc; skips dot-folders silently and folders with unreadable book.json (log warning)
def get_book(book_id: str) -> Book      # raises LibraryError if missing or invalid (accepts chapter status "skipped")
def save_book(book: Book) -> None       # atomic
def delete_book(book_id: str) -> None
def chapter_text_path(book_id: str, index: int) -> Path
def chapter_audio_path(book_id: str, index: int, audio_format: str) -> Path
```

### `core/tts.py` (CP1A; multi-engine CP4A)
```python
class TTSError(Exception): ...
def list_voices() -> list[str]          # canonical IDs of installed voices = voices.installed_voice_ids() (CP3)
def synthesize_to_file(text: str, out_path: Path, voice: str, audio_format: str, bitrate: str) -> float
    # voice: any voice ID (§9.1), plain names mean Piper. Dispatches to the engine (Kokoro: CP4A).
    # returns duration in seconds. Writes to out_path.part then renames, so partial files never look complete.
    # Must be safe to call from two threads at once (job worker + voice preview).
def check_environment() -> dict
    # {"piper": bool, "kokoro": bool (CP4A), "ffmpeg": str|None, "opus": bool, "mp3": bool, "voices": [canonical ids]}
```
`"mp3"` (CP3) says whether the found ffmpeg can encode the mp3 fallback.

### `core/jobs.py` (CP1A; priority CP4B)
```python
class JobQueue:
    def start(self) -> None             # starts ONE daemon worker thread; re-enqueues books with status queued/generating
    def enqueue(self, book_id: str) -> None
    def prioritize(self, book_id: str, chapter_index: int) -> None   # (CP4B) §10.4
    def status(self) -> dict            # {"current": {"book_id", "chapter_index", "chapters_done", "chapters_total"} | None, "queued": [book_id, ...]}
    def stop(self) -> None
def get_queue() -> JobQueue             # process-wide singleton
```
Worker: for each chapter where status is not "done"/"skipped" or the audio file is missing (never "skipped" ones) → synthesize → set status/duration → `save_book` after **every** chapter. Order: from the book's cursor (§10.4; default 0), in order, wrapping around. Book status: `generating` while running, `ready` when `is_complete()`, `error` (with message) if a chapter fails twice, if the book's `audio_format` is unsupported, or if the worker hits any unexpected exception (CP3: a book is never left stuck in queued/generating). Reload the book from disk before each save (the API may have changed it).

### `core/pipeline.py` (CP2A; start-from-chapter CP4B)
```python
class BookAlreadyExists(LibraryError): ...     # same book added twice (also the loser of a simultaneous add) -> HTTP 409
def add_book(gutenberg_id: int, voice: str | None = None, start_chapter: int = 0) -> Book
    # voice None -> config.default_voice. Raises TTSError if the voice ID is invalid or not installed (before any download).
    # Stores the canonical voice ID. (cached text or) download_text → clean → split_chapters → create_book → §10.3 → enqueue
def regenerate_book(book_id: str, voice: str) -> Book
    # delete audio/, chapters "done"/"error"/"pending" -> "pending" ("skipped" stay skipped), durations None,
    # set voice (canonical) and audio_format = config.audio_format, status "queued", error None, save, enqueue. Keeps progress.
def preview_book(gutenberg_id: int) -> dict          # (CP4B) §10.2
def generate_chapter(book_id: str, index: int) -> Book   # (CP4B) §10.4
def generate_skipped(book_id: str) -> Book           # (CP4B) §10.4
```
`add_book` raises `ValueError` for a bad `gutenberg_id` or `start_chapter`.

### `core/voices.py` (CP3 + CP4A)
See §9.4.

## 6. Desktop HTTP API (`desktop/server.py`, CP2A; Wave 4 routes CP4C)
All JSON. Errors: HTTP 4xx/5xx with `{"error": "message"}`. Status codes: 400 bad input (`ValueError`, `TTSError`, invalid voice ID), 404 unknown book/chapter/voice/route, 409 conflict (duplicate book, voice state), 502 Gutenberg unreachable (`GutenbergError`), 503 frontend missing, 500 anything unexpected (logged).

| Method & path | Body / query | Returns |
|---|---|---|
| `GET /` | | `index.html` |
| `GET /api/health` | | `{"ok": true, "env": check_environment()}` |
| `GET /api/search` | `?q=...&page=1` (q required) | `{"results": [SearchResult...]}` |
| `GET /api/preview/<int:gutenberg_id>` | | `BookPreview` (§10.2) **(CP4C)** |
| `GET /api/books` | | `{"books": [BookView...]}` |
| `POST /api/books` | `{"gutenberg_id": 2554, "voice": null, "start_chapter": 0}` (`start_chapter` optional, **CP4C**) | `BookView` (201). On success with a non-null voice, saves it as `default_voice` (§9.5) **(CP4C)** |
| `GET /api/books/<id>` | | `BookView` |
| `DELETE /api/books/<id>` | | `{"ok": true}` |
| `POST /api/books/<id>/regenerate` | `{"voice": "..."}` | `BookView`; saves the voice as `default_voice` **(CP4C)** |
| `POST /api/books/<id>/chapters/<int:n>/generate` | | `BookView` (§10.4) **(CP4C)**; 404 if no chapter n |
| `POST /api/books/<id>/generate-skipped` | | `BookView` (§10.4) **(CP4C)** |
| `GET /api/books/<id>/chapters/<n>/audio` | | audio file (`send_file`, `conditional=True` for Range/seek support; `audio/ogg` or `audio/mpeg`); 404 if not generated |
| `GET /api/books/<id>/progress` | | `Progress` |
| `PUT /api/books/<id>/progress` | `Progress` fields (partial allowed; `updated_at` ignored) | saved `Progress` |
| `GET /api/jobs` | | `JobQueue.status()` |
| `GET /api/voices` | | **(CP4C, changed)** `{"voices": [VoiceView...], "default": "<canonical id>", "engines": {"piper": bool, "kokoro": bool}}` |
| `POST /api/voices/<voice_id>/download` | | `VoiceView`: 202 while downloading, 200 if already installed **(CP4C)** |
| `DELETE /api/voices/<voice_id>` | | `{"ok": true, "removed": [voice ids]}` **(CP4C)** |
| `GET /api/voices/<voice_id>/preview` | | audio file (`conditional=True`) **(CP4C)** |
| `PUT /api/settings` | `{"default_voice": "..."}` | `{"default_voice": "<canonical id>"}`; 400 if not installed. Writes `config.local.json` (via `desktop/settings.py`, §9.5) |
| `GET /api/device` | | `{"connected": bool, "path": str\|None}` (CP6C) |
| `POST /api/device/sync` | `{"book_ids": [...]}` or `{"all": true}` | sync report (CP6C) |

- `BookView` = `Book.to_dict()` plus `"progress": Progress`, `"chapters_done": int`, `"chapters_skipped": int` **(CP4C)**, and each chapter gets `"audio_url"` (or null).
- `VoiceView` = `VoiceInfo.to_dict()` plus `"download": DownloadState.to_dict() | null` (this voice's pack, from `voices.download_states()`).
- `<voice_id>` in a path is any voice ID, URL-encoded (`kokoro%3Aaf_heart`). Voice routes check in this order: `normalize_voice_id` fails → 400; `get_voice` raises `VoiceError` → 404; the action raises `VoiceError` (not installed, already downloading, …) → 409.

## 7. Frontend (CP2B; Wave 4 changes CP4B)
Single page. Views: **Library**, **Search**, **Player**, plus a **Voices** screen (CP4B). Polls `/api/books` and `/api/jobs` every 3 s while any book is generating or the player is waiting for a chapter that can still arrive; polls `/api/voices` every 1 s while a voice download runs. One `<audio>` element for books (previews use their own `Audio` object and pause the book). Talks only to the API above. Exposes `window.tinbook.saveProgress()` (returns a Promise) for the desktop shell's close handler (`desktop/app.py`, CP3).

## 8. Device (Phase 2) — overview
- Library lives at `/mnt/tinbook/library/` inside a FAT32 image (`/home/tinbook/tinbook.img`, label `TINBOOK`), loop-mounted in normal mode, exported via `g_mass_storage` in sync mode.
- `TINBOOK_LIBRARY_DIR=/mnt/tinbook/library` so `core/models.py` + `core/progress.py` work unchanged.
- The desktop only syncs books whose status is `ready` (every chapter done or skipped). It copies the audio files that exist. The device lists every book folder it finds and loads it with `Book.from_dict`.
- **Skipped chapters are absent, not missing** (PRD P-11): on the device a chapter is playable only if its status is `"done"` and its audio file exists. Next/previous and auto-advance skip over the others; lists show them as "not generated"; if `progress.chapter_index` points at one, the device moves to the next playable chapter. Sync (CP6C) never reports a skipped chapter as missing or as an error.
- Detailed hardware, pins and button mapping: `docs/HARDWARE.md`.

## 9. Voices (Feature A: Piper + Kokoro)

### 9.1 Voice IDs
- Canonical form: `"<engine>:<name>"`, engine `piper` or `kokoro`. Examples: `"piper:en_US-ryan-high"`, `"kokoro:af_heart"`.
- Piper names match `[a-z]{2,3}_[A-Z]{2}-[a-z0-9_]+-[a-z0-9_]+` (language_REGION-speaker-quality). Kokoro names match `[a-z]{2}_[a-z]+` (first letter = language: `a` American, `b` British; second = gender `f`/`m`).
- A plain name without `:` is a Piper name (`"en_US-lessac-medium"` = `"piper:en_US-lessac-medium"`). Books and settings saved before CP3 keep working unchanged.
- Case-sensitive, no whitespace trimming. Anything else raises `VoiceError`.
- `voices.parse_voice_id(id) -> (engine, name)` and `voices.normalize_voice_id(id) -> str` (CP3). The API always returns canonical IDs. New books store canonical IDs.

### 9.2 Engines and files on disk
```
voices/
├── en_US-lessac-medium.onnx  en_US-lessac-medium.onnx.json   # Piper: two files per voice (unchanged layout)
├── kokoro/kokoro-v1.0.onnx  kokoro/voices-v1.0.bin           # Kokoro: one pack shared by every Kokoro voice
└── previews/<engine>_<name>.opus|mp3                         # cached preview samples (§9.4)
```
- **Piper** (`piper-tts`, unchanged): 22.05 kHz voices, one model per voice.
- **Kokoro** (CP4A, `core/tts_kokoro.py`): package **`kokoro-onnx>=0.6,<0.7`** (import `kokoro_onnx`; MIT; the Kokoro-82M model is Apache-2.0). ONNX Runtime on CPU, **no PyTorch**. Verified in CP3: 0.6.1 resolves together with `piper-tts 1.8.0` (shared `onnxruntime 1.31.1`, `numpy 2.5.x`); Python 3.10–3.13; `espeakng-loader` ships espeak-ng for `win_amd64`, so Windows needs no separate espeak install; upstream CI runs on `windows-2022`.
  - Model files from GitHub release `model-files-v1.1`: `kokoro-v1.0.onnx` (fp32, 325,505,369 bytes) and `voices-v1.0.bin` (28,214,398 bytes; 54 voices, 28 of them English). Sizes and SHA-256 are in the catalog (measured in CP3). fp32 is used because the release notes give int8 a spectral correlation of only 0.916 against fp32; fp16 (0.999, 164 MB) is a possible later option once its CPU speed is measured.
  - Use: one cached `Kokoro(str(model_path), str(voices_bin_path))` per process (loading is slow), guarded by a lock. `samples, rate = kokoro.create(paragraph, voice=name, speed=1.0, lang=lang)` returns float32 samples in [-1, 1] at `rate` = 24000. `lang` = `"en-us"` for names starting with `a`, `"en-gb"` for `b`.
  - Like Piper: one paragraph per call, written into one mono 16-bit WAV at the engine's rate (float → int16: clip to [-1, 1], × 32767), 0.4 s silence between paragraphs, then the existing ffmpeg step. Duration = frames / rate.
  - If `import kokoro_onnx` fails: `check_environment()["kokoro"] = False`, and synthesizing a Kokoro voice raises `TTSError("Kokoro is not installed. Run: pip install -r requirements.txt")`. Piper keeps working.
  - Not verified in CP3 (the sandbox blocked running the model): real synthesis speed on Kayden's CPU. CP4A measures it if it can; Kayden's smoke test does.

### 9.3 Catalog file (`core/voice_catalog.json`)
```json
{
  "schema_version": 1,
  "_notes": ["free text, ignored by code"],
  "packs": {
    "piper:en_US-ryan-high": {"engine": "piper", "files": [
      {"path": "en_US-ryan-high.onnx", "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx",
       "size_bytes": 121000000, "sha256": null, "verified": false},
      {"path": "en_US-ryan-high.onnx.json", "url": "…/en_US-ryan-high.onnx.json", "size_bytes": 5000, "sha256": null, "verified": false}]},
    "kokoro-v1.0": {"engine": "kokoro", "files": [
      {"path": "kokoro/kokoro-v1.0.onnx", "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx",
       "size_bytes": 325505369, "sha256": "beb0d184…", "verified": true}, {"path": "kokoro/voices-v1.0.bin", "…": "…"}]}
  },
  "voices": [
    {"id": "kokoro:af_heart", "engine": "kokoro", "pack": "kokoro-v1.0", "name": "Heart", "gender": "female",
     "accent": "American", "quality": "Kokoro · grade A · best-rated Kokoro voice", "recommended": true}
  ]
}
```
Rules (tested by CP4D):
1. `schema_version` is `1`; `packs` is an object; `voices` is a non-empty list.
2. Every voice has exactly the keys `id, engine, pack, name, gender, accent, quality, recommended`.
3. `id` is canonical (`normalize_voice_id(id) == id`) and its engine equals `engine`; ids are unique.
4. `pack` is a key of `packs`, and that pack's `engine` equals the voice's `engine`.
5. `gender` is `"female"` or `"male"`; `name`, `accent`, `quality` are non-empty strings; `recommended` is a bool.
6. A Piper voice's pack key equals its `id`, and its files are exactly `<name>.onnx` and `<name>.onnx.json` with URLs `https://huggingface.co/rhasspy/piper-voices/resolve/main/<lang>/<lang_REGION>/<speaker>/<quality>/<file>`.
7. Every Kokoro voice uses pack `kokoro-v1.0`, whose files are exactly `kokoro/kokoro-v1.0.onnx` and `kokoro/voices-v1.0.bin`.
8. Every file has exactly the keys `path, url, size_bytes, sha256, verified`; `path` is relative (no leading `/`, no `\`, no `..` part); `url` starts with `https://`; `size_bytes` is a positive int; `sha256` is null or 64 lowercase hex characters; `verified` is a bool, and `verified: true` requires a `sha256`.
9. Every pack is used by at least one voice.
10. Each engine has at least one `recommended` voice.
11. `config.json`'s `default_voice`, normalized, is a catalog voice.

`size_bytes` is for display; downloads report progress from `Content-Length` and check `sha256` when it isn't null. Piper sizes are estimates (`verified: false`) until Kayden runs `scripts/verify_voice_catalog.py --write` (CP4A); huggingface.co is blocked in the cloud sandboxes.

Curated in CP3: Piper — Lessac (medium, high), Ryan (high), LJ (high), Amy, Joe, HFC Female, HFC Male (US); Alba (Scottish), Cori (high), Northern English Male, Jenny (UK). Kokoro — af_heart (A), af_bella (A-), af_nicole (B-), af_aoede, af_kore, af_sarah, am_michael, am_fenrir, am_puck (C+), bf_emma (B-), bf_isabella, bm_george, bm_fable (C). Kokoro grades are from hexgrad/Kokoro-82M `VOICES.md` (`af_heart` = A confirmed online in CP3; the rest to re-check in CP4A).

### 9.4 `core/voices.py`
```python
ENGINES = ("piper", "kokoro")
CATALOG_PATH: Path                        # core/voice_catalog.json
class VoiceError(Exception): ...

# CP3 (implemented)
def parse_voice_id(voice_id: str) -> tuple[str, str]
def normalize_voice_id(voice_id: str) -> str
def load_catalog() -> dict                # parsed catalog file (deep copy)
def pack_files(voice_id: str) -> list[Path]   # absolute paths the voice needs; VoiceError for a Kokoro voice not in the catalog
def is_installed(voice_id: str) -> bool   # all pack files exist; False (never raises) for invalid IDs
def installed_voice_ids() -> list[str]    # sorted canonical IDs: Piper files on disk (catalogued or not) + catalogued Kokoro voices whose pack exists

@dataclass
class VoiceInfo:                          # to_dict() -> dict
    id: str; engine: str; name: str; gender: str; accent: str; quality: str
    pack: str; size_bytes: int; installed: bool; recommended: bool; in_catalog: bool

@dataclass
class DownloadState:                      # to_dict() -> dict
    pack: str
    state: Literal["downloading", "done", "error"]
    bytes_done: int
    bytes_total: int                      # 0 while unknown
    error: str | None = None

# CP4A (stubs until then)
def catalog() -> list[VoiceInfo]
def get_voice(voice_id: str) -> VoiceInfo
def start_download(voice_id: str) -> DownloadState
def download_states() -> dict[str, DownloadState]   # keyed by pack
def delete_voice(voice_id: str) -> list[str]
def preview_file(voice_id: str) -> Path
```
- `catalog()`: every catalog voice in file order, then installed Piper voices that aren't in the catalog (`name` = the Piper name, `gender`/`accent`/`quality` = `""`, `pack` = the voice id, `size_bytes` = the two files' size on disk, `recommended` False, `in_catalog` False). `size_bytes` = sum of the pack's `size_bytes`. `installed` = `is_installed(id)`.
- `get_voice(id)`: accepts plain or canonical IDs; the catalog entry or the uncatalogued installed Piper voice; otherwise `VoiceError`.
- `start_download(id)`: downloads the voice's **pack** in a background daemon thread (one thread per pack; a second call while it runs returns the running state). Already installed → `DownloadState(pack, "done", total, total)` and nothing is downloaded. Each missing file streams to `<file>.part` (`User-Agent` from config, `http_timeout` per read), then is checked against `sha256` (if not null) and `os.replace`d into place; files already present are skipped (so a retry resumes per file). `bytes_total` = sum of `Content-Length` (catalog `size_bytes` when a header is missing). Any failure → state `"error"` with a readable message; the `.part` file is deleted; finished files are kept. Uncatalogued voices can't be downloaded (`VoiceError`).
- `download_states()`: every pack download started in this process, finished ones included, until the process exits.
- `delete_voice(id)`: `VoiceError` if the voice isn't installed or its pack is downloading. Deletes the pack's files and the cached previews of every voice using that pack; returns their IDs, sorted (for Kokoro: all catalogued Kokoro voices). Books are untouched: a book whose voice was deleted fails its next chapter with "Voice is not installed" (status `error`) until it's regenerated with another voice. Deleting the default voice is allowed.
- `preview_file(id)`: `VoiceError` if not installed. Returns `voices_dir/previews/<engine>_<name>.<audio_format>`; on first use synthesizes `PREVIEW_TEXT.format(name=<display name>)` with `tts.synthesize_to_file` (config format and bitrate). `PREVIEW_TEXT = "Hi, I'm {name}. It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife."`

### 9.5 Last-used voice and settings (`desktop/settings.py`, CP4C)
```python
class SettingsError(Exception): ...
def read_local_settings() -> dict                 # {} if config.local.json is missing; SettingsError if unreadable or not a JSON object
def update_local_settings(changes: dict) -> dict  # merge into config.local.json (library.write_json_atomic), get_config.cache_clear(), return the merged dict
```
- The only Wave 4 key is `default_voice` (canonical ID). The server sets it after a successful `POST /api/books` with a non-null `voice`, after `POST …/regenerate`, and on `PUT /api/settings`. A settings write failure never fails the add/regenerate itself (log a warning).
- The add-book dialog preselects `GET /api/voices` → `default`; if that voice isn't installed, the first installed voice.
- `TINBOOK_DEFAULT_VOICE`, if set, still wins over `config.local.json` (documented; the remembered choice then has no effect).

## 10. Start from a chapter (Feature B)

### 10.1 Statuses
- Chapter status `"skipped"`: the user chose to start after it. The worker never generates a skipped chapter. It becomes `"pending"` only through `generate_chapter` / `generate_skipped` (or never).
- Book status `"ready"` = `is_complete()`: every chapter is `"done"` or `"skipped"`. `regenerate_book` leaves skipped chapters skipped.
- BookView adds `chapters_skipped`. Library cards show "12/39 chapters · 5 skipped".

### 10.2 Preview before adding (`pipeline.preview_book`, CP4B)
```json
{"gutenberg_id": 84, "title": "Frankenstein; Or, The Modern Prometheus", "authors": ["Shelley, Mary Wollstonecraft"],
 "chapters": [{"index": 0, "title": "Opening — … — Letter 1", "word_count": 1450}, {"index": 1, "title": "Letter 2", "word_count": 920}]}
```
- `get_metadata` + `download_text`, then `clean` + `split_chapters`. Raises `GutenbergError` / `ValueError` like `add_book`.
- The raw text is cached at `<library_dir>/.cache/<gutenberg_id>.txt` (write `.tmp`, then `os.replace`). `add_book` uses a cache file younger than 24 h instead of downloading again (so the chapter indexes match what the user saw), and deletes it after the book is created. Both functions delete cache files older than 24 h.

### 10.3 Adding with a start chapter (`pipeline.add_book`, CP4B)
- `start_chapter` must be an `int` with `0 <= start_chapter < len(chapters)` (else `ValueError`, HTTP 400). `bool` is not accepted.
- After `create_book`: chapters with index `< start_chapter` get status `"skipped"` (saved before enqueueing); if `start_chapter > 0`, `progress.json` is saved with `chapter_index = start_chapter`, position 0, so the player opens there. Then enqueue as usual.

### 10.4 Generating on request and priority (`pipeline` + `jobs`, CP4B)
- `generate_chapter(book_id, index)`: `LibraryError` if the book is missing; `IndexError` if `index` is out of range (HTTP 404). If the chapter is `"done"` and its audio exists, nothing changes (returns the book). Otherwise: a `"skipped"`/`"error"` chapter becomes `"pending"`; if the book isn't `"generating"`, status `"queued"` and `error` None; save; `get_queue().prioritize(book_id, index)`.
- `generate_skipped(book_id)`: every `"skipped"` chapter → `"pending"`; if any changed and the book isn't generating, status `"queued"`; save; `enqueue(book_id)`. Generation order follows the book's cursor.
- `JobQueue.prioritize(book_id, chapter_index)`:
  - The chapter being synthesized is never interrupted. After it is saved, the worker's **next** chapter is the prioritized one, even if it belongs to another book. The interrupted book goes back to the front of the queue, right after the prioritized book.
  - Each book has a cursor (default 0). The worker picks the first chapter needing audio at index ≥ cursor, then wraps around to earlier ones. `prioritize` sets the book's cursor to `chapter_index`. So the jumped-to chapter comes first, then later chapters in order, then any earlier missing ones (skipped chapters are never picked).
  - A newer `prioritize` replaces an older one. A chapter that doesn't need audio is ignored (the book just continues). Cursors live in memory only (after a restart, generation starts from the first missing chapter).
- Player (CP4B): whenever it needs a chapter whose `audio_url` is null — a jump (previous/next, chapter list, +30 past the end) or auto-advance — it calls `POST /api/books/<id>/chapters/<n>/generate` once for that chapter, then shows "Generating chapter N…" and starts it when ready (D-7). The chapter list shows skipped chapters as "Skipped" with a **Generate** button, and a **Generate all skipped (N)** button when N > 0.
