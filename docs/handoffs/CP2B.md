# CP2B handoff — Claude Code
## Done
- **`desktop/templates/index.html`, `desktop/static/app.js`, `desktop/static/style.css`.** Vanilla HTML/CSS/JS with no build step. It talks only to the ARCHITECTURE §6 API.
  - It sits comfortably in a 420×720 window and still works at 360 px wide.
  - It switches between light and dark with `prefers-color-scheme`.
  - The HTML uses no Jinja syntax, so CP2A can serve it with either `render_template("index.html")` or `send_file`. Assets load from `/static/…`.
- **Tabs:** Library, Search and Player. They follow the ARIA tab pattern, so ← / → move between tabs.
- **Library:**
  - Each book card shows the title, the author (Gutendex's "Last, First" is shown as "First Last"), and a status pill: Ready, Generating, `Queued · #n` (taken from `/api/jobs`) or Error.
  - Below that it shows `12/39 chapters`, plus `· working on 13` for the book being generated, then "% listened" with a thin bar.
  - **% listened** is weighted by chapter word counts, because those are known before any audio exists. It reaches 100% only when `finished` is true.
  - The button reads Start, Continue, Listen again, or Open player (for the book already open).
  - A book with status `error` shows its `error` text.
  - There is an empty state with a "Find a book" button.
- **Polling:** `/api/books` and `/api/jobs` are refreshed every 3 s while any book is `queued` or `generating`, or the player is waiting for a chapter. Polling also continues while the server can't be reached or the first load hasn't succeeded. Otherwise it stops.
  - Cards are only rebuilt when the data changes, so keyboard focus and hover aren't lost every 3 s.
- **Search:**
  - Enter or the Search button runs a search.
  - Each result shows the title, author and download count.
  - A result with no `text_url` gets a disabled "No text version" button.
  - A book already in the library gets a disabled "In library" button.
  - "Add" shows a spinner with "Adding…" during `POST /api/books`, then jumps to the Library. Errors from the server's `{"error"}` appear under that result.
  - "More results" loads `page=2, 3…`. An empty page or an error past the last page is treated as the end.
  - Stale responses from an earlier search are ignored.
- **Player:**
  - Shows the title, author, "Chapter n of N" and the chapter title.
  - Seek bar with elapsed and remaining time.
  - Buttons: play/pause, −30 / +30, previous / next chapter.
  - Speed selector: 0.75, 1, 1.25, 1.5, 1.75, 2. A saved speed outside that list snaps to the nearest one.
  - A collapsible chapter list shows each chapter's duration, or Pending, Generating… or Failed. Clicking a chapter jumps to it.
  - −30 stops at 0:00. +30 past the end goes to the next chapter.
- **Resume (task 5):** opening a book does the following:
  1. Fetches `GET /api/books/<id>` and `GET /api/books/<id>/progress`.
  2. Sets `playbackRate`. It sets `defaultPlaybackRate` too, so the speed survives chapter changes.
  3. Seeks to `position_sec` after `loadedmetadata`, and only then starts playback, so you never hear a blip from 0:00.
  - A book marked `finished` starts again from chapter 1.
- **D-7 auto-advance:**
  - When a chapter ends, the next one starts.
  - If the next chapter has no `audio_url` yet, the player shows "Waiting for chapter N…" and starts it automatically once a poll shows it's ready.
  - If generation failed instead, the player says so.
  - When the last chapter ends, the book is saved with `finished: true` and the player shows "You finished this book."
- **D-8 progress saves:**
  - Saves run every 5 s during playback, on pause, on chapter change, on speed change, and on `visibilitychange` → hidden. On `pagehide` / `beforeunload` it sends a `fetch(..., {keepalive: true})` instead.
  - Saves run strictly in order, one at a time, so a "pause then ended" pair always lands in the right order.
  - A save is skipped when nothing has changed since the last one. A book sitting paused never bumps `updated_at`. This matters for Phase 2: the newest-wins device sync shouldn't lose to an idle desktop.
- **Mini player:** a now-playing bar at the bottom of Library and Search, with play/pause. Click it to open the Player.
- **Book disappears:** if a book is deleted while it's open, the player closes with a message. If its audio disappears (regenerate), the player switches to the waiting state.
- **`window.tinbook.saveProgress()`:** a hook for the desktop shell to force a save before closing (see Notes).
- **No mocks committed.** I tested against a throwaway Flask mock of §6 plus a Playwright script, both kept outside the repo. 32 checks passed:
  - resume position and speed;
  - saves every 5 s, a single save on pause, and no saves while paused;
  - −30 / +30 edge cases, speed saving, and the chapter list;
  - finished at the end of the book;
  - auto-advance into a chapter that isn't generated yet: it waits, then starts by itself;
  - reloading the page resumes within 5 s;
  - the mini player;
  - search: "No text version", HTML escaping, Add → Library, "In library", load more, and the error message.

  The repo's `pytest` suite is unchanged and passes (319).

## How to test
After CP2A is merged, on Windows from the repo root:
```
python -m desktop.app
```
1. **Search** tab: type `frankenstein`, press Enter. You should see results with download counts.
2. Click **Add** on *Frankenstein* (id 84). The button spins for a few seconds, then the Library shows the book as **Generating · 0/N chapters**, and the count goes up every few seconds.
3. Once it's 1 or more, click **Start**. Chapter 1 plays. Try ±30, the speed setting and the chapter list.
4. Drag to near the end of chapter 1. It should move on to chapter 2 by itself, or show "Waiting for chapter 2…" and start it once it's generated.
5. Note the time, close the window, then run `python -m desktop.app` again and click **Continue**. Playback should pick up within 5 s of where you stopped, at the same speed.
6. Dark mode: switch Windows to dark mode and the app follows.

Browser mode works too: `python -m desktop.app --browser`, then open http://127.0.0.1:5000.

## Not done / known issues
- **Not run against the real CP2A server or in WebView2 yet.** I built it against the §6 contract and tested in headless Chromium, the same engine as WebView2. CP3 covers the real run.
- **Keyboard shortcuts (D-9) and the Media Session API are not done.** They belong to CP4A. Space and Enter work only on a focused button.
- **Saving on window close depends on the shell.** WebView2 may not fire `beforeunload` when pywebview closes the window. The 5 s save interval already keeps the loss under 5 s (the acceptance criterion). For an exact save, CP2A/CP3 should call the hook below.
- −30 does not go back into the previous chapter. It stops at 0:00 of the current one. "Previous chapter" always goes to the previous chapter; it never restarts the current one.

## Contract change requests
- None.

## New dependencies needed
- None.

## Notes for the next agent
- **CP2A, things the frontend relies on:**
  - `BookView.chapters[i].audio_url` is null until that chapter's audio exists. The player treats null as "not generated yet".
  - `BookView.progress` and `chapters_done` are present.
  - `PUT /progress` accepts `{chapter_index, position_sec, speed, finished}` and returns the saved `Progress`.
  - Errors come back as `{"error": "..."}` with a 4xx/5xx status, and the message is shown to the user as-is.
  - For `.opus`, pass `mimetype="audio/ogg"` to `send_file`. On Windows, Python's `mimetypes` reads the registry and may guess wrong.
  - `conditional=True` is required, or seeking breaks.
- **CP2A / CP3, window close:** before the window closes, call the hook:
  ```python
  def on_closing():
      window.evaluate_js("window.tinbook && window.tinbook.saveProgress()")
  window.events.closing += on_closing
  ```
  It returns a Promise that resolves after the PUT. pywebview 5 should wait for it; if it doesn't, the 5 s interval still covers it.
- **CP4A:**
  - The player functions are inside one IIFE in `app.js`. For shortcuts and Media Session, add handlers inside it that call `togglePlay()`, `skip(±30)` and `goToChapter()`.
  - Add `<div id="settings-root">` to the Library section and `<script src="/static/settings.js">` after `app.js`.
- **CP4B:** after a regenerate or delete, calling a refresh is enough. The player already handles a book or audio file disappearing. To trigger it from `settings.js`, CP4A can expose a refresh function on `window.tinbook`.
