# Tinbook — Product Requirements Document

**Owner:** Kayden · **Status:** Phase 1 ready to build · **Last updated:** Sept 2026

## 1. Summary
Tinbook turns free public-domain books from Project Gutenberg into audiobooks using Piper, an open-source offline text-to-speech engine. It ships in two phases:

1. **Desktop app (Phase 1):** a small Windows app for searching, converting, and listening to books in the background while coding.
2. **Pocket device (Phase 2):** a Raspberry Pi Zero 2 WH in an Altoids tin with a 2" screen and 4 buttons that plays those audiobooks to AirPods on walks.

The desktop app is also the device's "sync station": it generates the audio (the PC is far faster than the Pi) and copies finished books to the device over USB.

## 2. Goals
- Listen to any English Gutenberg book as an audiobook, for free, fully offline after download.
- Resume exactly where you left off, on either the PC or the device.
- Build a pocket device for ~$110 that's simple to use one-handed and safe in a pocket.
- Learning: Python, Flask, Linux, Raspberry Pi hardware, multi-agent AI development.

## 3. Non-goals (v1)
- Reading text on screen (no e-reader mode).
- Non-Gutenberg or DRM books, EPUB import from other sources.
- Non-English books (Piper supports other languages; revisit later).
- Cloud sync, accounts, mobile app.
- Generating audio on the Pi.

## 4. Users & core flows
**User:** Kayden (single user, Windows 10/11 PC, AirPods).

**Flow A — Add a book (desktop):** search "crime and punishment" → pick result → Add → book appears in library as "Generating 0/39 chapters" → chapter 1 becomes playable as soon as it's done, rest continue in background.

**Flow B — Listen (desktop):** open book → resumes at saved chapter/position → play/pause, ±30s, prev/next chapter, speed → auto-advances chapters → progress saved continuously.

**Flow C — Sync to device:** on device choose Menu → Sync mode → plug device into PC → desktop app shows "Tinbook connected" → Send book(s) → progress syncs both ways (newest wins) → eject on device.

**Flow D — Listen on a walk (device):** open tin → hold X to wake → pick book with Up/Down → Select → plays to AirPods → close lid → pocket.

## 5. Functional requirements

### Phase 1 — Desktop
| ID | Requirement |
|---|---|
| D-1 | Search Gutenberg by title/author (English only) via Gutendex. Show title, author, download count. |
| D-2 | Add a book: download plain text, strip Gutenberg header/footer and license, clean for speech, split into chapters. |
| D-3 | Generate one `.opus` file per chapter with Piper in a background queue, in chapter order. One book generates at a time; others wait in queue. |
| D-4 | A chapter is playable as soon as its audio exists. Library shows per-book status and chapter progress (e.g. 12/39). |
| D-5 | Generation survives app restarts: on launch, unfinished books resume from the first missing chapter. |
| D-6 | Player: play/pause, back 30s, forward 30s, previous/next chapter, chapter list, speed 0.75×–2.0× in 0.25 steps. |
| D-7 | Auto-advance to next chapter. If it isn't generated yet, show "Waiting for chapter N…" and start it automatically once ready. |
| D-8 | Progress (chapter + position + speed) saves every 5s during playback, on pause, on chapter change, and on window close. |
| D-9 | Keyboard: Space = play/pause, ← / → = ∓30s. Windows media keys via the Media Session API where supported. |
| D-10 | Delete a book (removes its folder). Regenerate a book (new voice). |
| D-11 | Settings: choose Piper voice from installed voices; default `en_US-lessac-medium`. |
| D-12 | Small window (~420×720), playback continues when minimized. |
| D-13 | `--browser` mode serves the same UI on `0.0.0.0:5000` (for Replit and debugging). |

### Phase 2 — Device
| ID | Requirement |
|---|---|
| P-1 | Boots straight into the Tinbook app (systemd service). |
| P-2 | Library screen: list of ready books with author and % complete. |
| P-3 | Now Playing screen: book, chapter title, progress bar, elapsed/remaining, speed, battery %, Bluetooth status. |
| P-4 | Buttons (see HARDWARE.md §5 for mapping): Up/Down/Select/Back plus hold actions for chapter skip and menu. |
| P-5 | Bluetooth: scan, pair, connect from the menu; remember last device and auto-reconnect on boot/playback. |
| P-6 | Screen sleeps after 20s idle. While asleep, buttons are locked; holding X for 1.5s wakes it. |
| P-7 | Sync mode: stops playback, exposes the library to the PC as a USB drive labeled `TINBOOK`; "Eject" returns to normal. |
| P-8 | Battery % from PiSugar 3 on screen; warn at 15%; save progress and shut down cleanly at 5%. |
| P-9 | Progress saved every 10s, on pause, and on shutdown. Same `progress.json` format as desktop. |
| P-10 | Power saving: Wi-Fi off during playback (also prevents Bluetooth audio stutter on the shared radio), backlight off when idle, CPU governor `powersave`. |

## 6. Non-functional requirements
- **Offline:** after a book is downloaded, nothing needs internet.
- **Storage:** Opus mono 32 kbps ≈ 14 MB/hour. A 20-hour book ≈ 290 MB. 16 GB device library ≈ 50 long books or 100+ average ones.
- **Generation speed:** depends on the PC. Expect roughly 5–20× faster than real time on a modern laptop CPU, so a 20-hour book may take 1–4 hours total. Target: chapter 1 playable within ~2 minutes of clicking Add.
- **Battery (device):** estimated 3–5 hours of Bluetooth playback on the 1200 mAh PiSugar 3. Measure in CP8.
- **Reliability:** no corrupted JSON on crash (atomic writes); regenerate any missing/partial chapter file.
- **Etiquette:** identify with a User-Agent; don't bulk-scrape Gutenberg; cache downloaded text.

## 7. Tech stack
| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Desktop shell | pywebview (Edge WebView2 on Windows) |
| Backend | Flask (JSON API + serves static frontend) |
| Frontend | Vanilla HTML/CSS/JS, HTML5 `<audio>` |
| Book source | Gutendex API (`https://gutendex.com/books/`) → gutenberg.org plain-text files |
| TTS | Piper (`piper-tts` pip package), ONNX voices from `rhasspy/piper-voices` on Hugging Face |
| Encoding | ffmpeg (via `imageio-ffmpeg`, fallback to system ffmpeg) → Opus 32 kbps mono |
| Device OS | Raspberry Pi OS Lite 64-bit (latest offered by Raspberry Pi Imager) |
| Device display | Pimoroni `displayhatmini` library + Pillow |
| Device audio | mpv → PipeWire (Bluetooth A2DP) |
| Device battery | PiSugar power manager (`pisugar-server`) |
| Device sync | Linux USB gadget `g_mass_storage` with a FAT32 image labeled `TINBOOK` |

## 8. Phases & milestones
See `docs/CHECKPOINTS.md` for the full plan with owners and parallel waves.
- **Phase 1:** CP0 → Wave 1 (CP1A/B/C) → Wave 2 (CP2A/B/C) → CP3 integration → Wave 4 polish (CP4A/B/C). **Milestone:** Kayden listens to a Gutenberg book on his PC while coding.
- **Phase 2:** CP5 Pi setup → Wave 6 (CP6A/B/C) → CP7 device app → CP8 hardware & field test. **Milestone:** a full walk listening from the tin.

## 9. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Piper wheel issues on Windows | CP0 smoke test on Windows first. Fallback: Piper standalone binary via subprocess (tts.py supports both). |
| Bundled ffmpeg lacks libopus | Detect at startup; fallback to system ffmpeg; last resort MP3 48 kbps (config `audio_format`). |
| Chapter detection fails on odd books | Size-based fallback splitting (never fails, just less pretty titles). |
| Gutendex slow or down | Timeouts + clear error message. Downloaded books are cached locally. |
| Bluetooth audio stutters on Pi Zero 2 W | Wi-Fi off during playback (shared radio). |
| Parts don't fit in Altoids tin (depth) | Stack is ~17 mm + PiSugar board. Measure before cutting; fallback: deeper tin or 3D-printed case. |
| Battery life shorter than hoped | Software power saving; later swap to larger flat LiPo if it fits. |
| Parallel agents conflicting | Strict file ownership + frozen contracts + handoffs (AGENTS.md). |

## 10. Future ideas (not v1)
- Sleep timer, bookmarks, multiple voices per book.
- Wi-Fi sync as an alternative to USB.
- Non-English books with matching Piper voices.
- Scroll-wheel (rotary encoder) and hardware hold switch.
