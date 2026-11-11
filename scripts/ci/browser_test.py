"""CI browser test: drive the real UI with Playwright (Chromium) against --browser mode.

Starts `python -m desktop.app --browser` with an empty library (server log → --out),
then: search "frankenstein" → Add → wait for chapter 1 → Start → play → seek near the
end of chapter 1 → auto-advance to chapter 2 → progress saved → reload → Continue →
resumes in chapter 2 within a few seconds. Screenshots of every view go to --out.

Usage: python scripts/ci/browser_test.py --library <empty dir> --out ci-out
Set PLAYWRIGHT_CHROMIUM_EXECUTABLE to use a specific Chromium binary (local runs).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:5000"
RESUME_TOLERANCE_SEC = 5
NETWORK_ATTEMPTS = 3


class Failure(Exception):
    pass


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def api(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for(description: str, check, timeout: float, interval: float = 1.0):
    """Poll ``check()`` until it returns something truthy; raise Failure on timeout."""
    deadline = time.monotonic() + timeout
    while True:
        value = check()
        if value:
            return value
        if time.monotonic() > deadline:
            raise Failure(f"Timed out after {timeout:.0f} s waiting for {description}")
        time.sleep(interval)


def start_server(library: Path, log_path: Path) -> subprocess.Popen:
    env = dict(os.environ, TINBOOK_LIBRARY_DIR=str(library.resolve()), PYTHONUNBUFFERED="1")
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "desktop.app", "--browser"],
        cwd=ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT,
    )

    def healthy():
        if process.poll() is not None:
            raise Failure(f"Server exited with code {process.returncode}; see {log_path.name}")
        try:
            return api("/api/health")
        except OSError:
            return None

    health = wait_for("the server to start", healthy, timeout=60)
    log(f"Server up: {json.dumps(health['env'])}")
    return process


def audio_state(page: Page) -> dict:
    return page.evaluate(
        """() => { const a = document.getElementById('audio');
        return {paused: a.paused, time: a.currentTime, duration: a.duration, src: a.currentSrc,
                error: a.error && a.error.code,
                chapter: document.getElementById('p-chapter-num').textContent,
                message: document.getElementById('p-message').hidden ? '' : document.getElementById('p-message').textContent}; }"""
    )


def playing_in(page: Page, chapter_number: int, min_time: float = 0.5):
    s = audio_state(page)
    if s["error"]:
        raise Failure(f"Audio element error {s['error']} ({s['src']})")
    ok = (not s["paused"]) and s["time"] >= min_time and s["chapter"].startswith(f"Chapter {chapter_number} of")
    return s if ok else None


def run(page: Page, out: Path) -> None:
    shots = out / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)

    def shot(name: str) -> None:
        page.screenshot(path=str(shots / f"{name}.png"), full_page=True)
        log(f"Screenshot {name}.png")

    page.goto(BASE + "/")
    page.wait_for_selector("#library-empty:not([hidden])", timeout=30_000)
    shot("01-library-empty")

    # Search (network: retried).
    page.click("#tab-search")
    result = None
    for attempt in range(1, NETWORK_ATTEMPTS + 1):
        page.fill("#search-input", "frankenstein")
        page.press("#search-input", "Enter")
        try:
            page.wait_for_function(
                "() => { const s = document.getElementById('search-status').textContent;"
                " return s && !s.startsWith('Searching'); }",
                timeout=90_000,
            )
        except Exception:
            pass
        status = page.text_content("#search-status")
        result = page.query_selector('#search-results li[data-gid="84"]')
        log(f"Search attempt {attempt}: {status!r}, Frankenstein (84) found: {result is not None}")
        if result:
            break
        time.sleep(10 * attempt)
    if not result:
        raise Failure("Search did not return Frankenstein (84)")
    shot("02-search-results")

    # Add (network: retried if the server reports an error).
    book_id = None
    for attempt in range(1, NETWORK_ATTEMPTS + 1):
        page.click('#search-results li[data-gid="84"] button')
        try:
            page.wait_for_selector('#book-list li[data-book-id^="84-"]', timeout=120_000)
            book_id = page.get_attribute('#book-list li[data-book-id^="84-"]', "data-book-id")
            break
        except Exception:
            error = page.text_content('#search-results li[data-gid="84"] .result-error')
            log(f"Add attempt {attempt} failed: {error!r}")
            time.sleep(10 * attempt)
    if not book_id:
        raise Failure("Adding Frankenstein failed")
    book = api(f"/api/books/{book_id}")
    log(f"Added {book_id}: {len(book['chapters'])} chapters; 1: {book['chapters'][0]['title']}; 2: {book['chapters'][1]['title']}")
    shot("03-library-generating")

    # Wait for chapter 1 audio.
    started = time.monotonic()
    wait_for("chapter 1 to be generated",
             lambda: api(f"/api/books/{book_id}")["chapters"][0]["audio_url"], timeout=900, interval=3)
    log(f"Chapter 1 generated after {time.monotonic() - started:.0f} s")
    page.wait_for_function(
        f"() => document.querySelector('#book-list li[data-book-id=\"{book_id}\"]').textContent.match(/[1-9]\\d*\\/\\d+ chapters/)",
        timeout=30_000,
    )
    shot("04-library-chapter1-ready")

    # Start → plays chapter 1.
    card_button = f'#book-list li[data-book-id="{book_id}"] .card-foot button'
    log(f"Library button says {page.text_content(card_button)!r}; clicking it")
    page.click(card_button)
    page.wait_for_selector("#player:not([hidden])", timeout=15_000)
    try:
        s = wait_for("chapter 1 to play", lambda: playing_in(page, 1), timeout=15)
    except Failure:
        log(f"Not playing yet ({audio_state(page)}); pressing Play")
        page.click("#p-play")
        s = wait_for("chapter 1 to play", lambda: playing_in(page, 1), timeout=30)
    log(f"Playing chapter 1: {s['time']:.1f} / {s['duration']:.1f} s")
    shot("05-player-chapter1")

    # Seek near the end with the seek bar → auto-advance to chapter 2.
    target = max(int(s["duration"]) - 4, 0)
    page.evaluate(
        "(t) => { const s = document.getElementById('p-seek'); s.value = String(t);"
        " s.dispatchEvent(new Event('input')); s.dispatchEvent(new Event('change')); }",
        target,
    )
    log(f"Seeked to {target} s")
    waiting_shot = False

    def advanced():
        nonlocal waiting_shot
        st = playing_in(page, 2)
        if not st and not waiting_shot and audio_state(page)["message"].startswith("Waiting"):
            log("Player is waiting for chapter 2 (still generating)")
            shot("06-player-waiting-for-chapter2")
            waiting_shot = True
        return st

    s = wait_for("auto-advance to chapter 2", advanced, timeout=900, interval=1)
    log(f"Auto-advanced: {s['chapter']} playing at {s['time']:.1f} s")
    time.sleep(7)  # longer than the 5 s save interval
    s = audio_state(page)
    shot("07-player-chapter2")

    # Progress saved on the server.
    progress = api(f"/api/books/{book_id}/progress")
    log(f"Saved progress: {progress}")
    if progress["chapter_index"] != 1 or progress["position_sec"] <= 0:
        raise Failure(f"Progress not saved for chapter 2: {progress}")

    # Reload → Continue → resumes in chapter 2 near the same position.
    before = audio_state(page)["time"]
    log(f"Reloading at chapter 2, {before:.1f} s")
    page.reload()
    page.wait_for_selector(f'#book-list li[data-book-id="{book_id}"]', timeout=30_000)
    saved = api(f"/api/books/{book_id}/progress")
    log(f"Progress after reload: {saved}")
    label = page.text_content(card_button)
    shot("08-library-after-reload")
    if label != "Continue":
        raise Failure(f"Expected a Continue button after reload, got {label!r}")
    page.click(card_button)
    s = wait_for("playback to resume in chapter 2", lambda: playing_in(page, 2, min_time=0.1), timeout=30)
    drift = abs(s["time"] - before)
    log(f"Resumed: {s['chapter']} at {s['time']:.1f} s (was {before:.1f} s, difference {drift:.1f} s)")
    shot("09-player-resumed")
    if drift > RESUME_TOLERANCE_SEC:
        raise Failure(f"Resumed {drift:.1f} s away from where playback stopped (limit {RESUME_TOLERANCE_SEC} s)")

    page.click("#p-play")  # pause → final save
    page.click("#p-chapters summary")
    shot("10-player-chapter-list")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    args.library.mkdir(parents=True, exist_ok=True)

    server = start_server(args.library, args.out / "server.log")
    console = (args.out / "browser-console.log").open("w", encoding="utf-8")
    code = 1
    try:
        with sync_playwright() as p:
            launch = {"args": ["--autoplay-policy=no-user-gesture-required"]}
            if os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"):
                launch["executable_path"] = os.environ["PLAYWRIGHT_CHROMIUM_EXECUTABLE"]
            browser = p.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 420, "height": 720})
            page.on("console", lambda m: console.write(f"{m.type}: {m.text}\n"))
            page.on("pageerror", lambda e: console.write(f"pageerror: {e}\n"))
            try:
                run(page, args.out)
                log("PASS")
                code = 0
            except Exception as error:
                log(f"FAIL: {error}")
                try:
                    log(f"Audio state at failure: {audio_state(page)}")
                except Exception:
                    pass
                try:
                    page.screenshot(path=str(args.out / "screenshots" / "99-failure.png"), full_page=True)
                except Exception:
                    pass
            browser.close()
    finally:
        console.close()
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return code


if __name__ == "__main__":
    sys.exit(main())
