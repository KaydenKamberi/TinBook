# CP2A handoff — Replit Agent

## Done
- Implemented `core/pipeline.py`: metadata and text download, cleaning, chapter splitting, atomic library creation, and queue submission. Voice defaults come from config; missing voices are rejected before download.
- Regeneration validates the voice before deleting audio, resets chapter status/durations and book errors, saves metadata, and re-enqueues the book. Text and playback progress are preserved.
- Implemented every Phase 1 route in ARCHITECTURE §6, including settings persistence. Device routes are not implemented; they remain CP6C.
- `BookView` includes serialized progress, `chapters_done`, and per-chapter `audio_url` or null. Audio uses conditional `send_file`, with Opus/MP3 content types and Range support.
- API validation covers JSON bodies, positive book IDs and page numbers, installed voices, chapter bounds, finite playback positions/speeds, and boolean completion. Expected failures and unknown routes/methods return JSON errors.
- `create_app()` starts the process-wide queue once per app creation. Browser mode binds `0.0.0.0:5000` without a reloader. Desktop mode uses a free loopback port, a daemon server thread, and the exact 420×720 window / 360×560 minimum size. Both modes stop the queue on exit; desktop mode also closes the HTTP server.
- Added `tests/test_server.py` with Flask test-client tests, real cleaning/splitting/storage/progress behavior, mocked network and queue, Range requests, settings, error cases, and launcher shutdown/window tests.
- Full repository suite: **384 passed**.
- The running Replit workflow was restarted and `/api/health` verified visually and over HTTPS: HTTP 200, Piper available, ffmpeg available, libopus available, and the default voice installed.
- A separate bounded real-audio integration check used a temporary library and controlled text. Only Gutenberg metadata/text retrieval was mocked; the actual pipeline, queue, Piper, ffmpeg, storage, and audio endpoint ran. POST returned 201, generation was observed, the book reached `ready`, and `Range: bytes=0-100` returned HTTP 206 with 101 bytes and `Content-Range: bytes 0-100/99552`. Audio began with `OggS`; duration was about 24.78 seconds. The temporary library was removed after the queue stopped.
- Edited only `desktop/server.py`, `desktop/app.py`, `core/pipeline.py`, `tests/test_server.py`, and this required handoff. No frontend, Gutenberg fallback, dependency, or Replit configuration files were edited.

## How to test
From the repository root:

```bash
python -m pytest -q
python -m pytest -q tests/test_server.py
python -m desktop.app --browser
```

With the Replit workflow running:

```bash
curl "https://$REPLIT_DEV_DOMAIN/api/health"
curl "https://$REPLIT_DEV_DOMAIN/api/search?q=frankenstein"
curl -H "Content-Type: application/json" \
  -d '{"gutenberg_id":84}' "https://$REPLIT_DEV_DOMAIN/api/books"
curl "https://$REPLIT_DEV_DOMAIN/api/jobs"
# Substitute the ID returned by POST; wait until chapter 0 audio exists.
curl -i -r 0-100 \
  "https://$REPLIT_DEV_DOMAIN/api/books/BOOK_ID/chapters/0/audio"
```

Download the voice first if it is missing:

```bash
python scripts/download_voice.py en_US-lessac-medium
```

On Windows, run `python -m desktop.app` for the native window.

### Live Gutendex check
On 2026-11-05 America/Los_Angeles (2026-11-06 UTC), the actual existing Gutenberg client was called without modifications or network mocks:

1. `search("crime and punishment")` succeeded. **2554 was result #1.** First three results:
   - **2554 — Crime and Punishment**, Dostoyevsky, Fyodor; English; download count 62172; text URL `https://www.gutenberg.org/ebooks/2554.txt.utf-8`.
   - **58700 — Crimes and Punishments: Including a New Translation of Beccaria's 'Dei Delitti e delle Pene'**, Farrer, James Anson; English; download count 1401; text URL `https://www.gutenberg.org/ebooks/58700.txt.utf-8`.
   - **53814 — A searchlight on Germany: Germany's Blunders, Crimes and Punishment**, Hornaday, William T. (William Temple); English; download count 490; text URL `https://www.gutenberg.org/ebooks/53814.txt.utf-8`.
2. The first `download_text(2554)` attempt timed out. A subsequent call using the unchanged configured timeout **succeeded**, returning **1,177,953 characters**, and `"*** START OF" in text` was **True**.
3. Later live browser-API requests for `/api/search?q=frankenstein` and `POST /api/books` with ID 84 timed out upstream and correctly returned JSON HTTP 502. No book was created by the failed POST.

The requested CP1B live search/download recheck therefore passed on retry, but upstream availability remains intermittent.

## Not done / known issues
- The CP2B frontend has not been merged into this branch: no `index.html`, `app.js`, or `style.css` is present here. `/` returns an explicit JSON HTTP 503 explaining that CP2B must be merged; it does not render a fabricated replacement UI. Flask is wired to the standard `desktop/templates/` and `desktop/static/` locations.
- The full live Frankenstein acceptance sequence could not finish because of the upstream timeouts noted above. Tests cover its API behavior, and the separate real-Piper check verifies generation and Range serving, but that controlled-text check is not presented as a successful live Gutenberg download of Frankenstein.
- The actual Windows GUI was not opened in Replit. Binding, dimensions, daemon-thread setup, and cleanup were tested with mocked pywebview/server objects.
- No fallback was added to `core/gutenberg.py`; another agent owns that change.

## Contract change requests
- None. `pipeline.BookAlreadyExists` is an additional `LibraryError` subclass used to return HTTP 409 without changing the contracted public function signatures.

## New dependencies needed
- None.

## Notes for the next agent
- Merge CP2B to supply the real template/static assets. No production UI mocks were added.
- Settings API support is included because CP2A requires every Phase 1 route; CP4B can add its settings UI against `PUT /api/settings`. Existing local settings are preserved, writes are atomic, and the config cache is cleared.
- `GET /api/voices` returns `{"voices": [...], "default": "..."}`. Install the selected voice before adding/regenerating a book.
- Progress PUT supports partial updates, preserves omitted values, and stamps server time instead of trusting client `updated_at`.
- The queue is stored in `app.extensions["tinbook_queue"]` for launcher shutdown. Library deletion needs no queue stop; the Wave 1 worker handles deletion.
- The branch was created from updated `origin/main` after all three Wave 1 branches were merged. Its intended push target is `cp2a-replit`, never `main`.
