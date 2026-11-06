/* Tinbook desktop UI (CP2B).
 * Vanilla JS, no build step. Talks only to the HTTP API in ARCHITECTURE §6.
 * Views: Library, Search, Player. One <audio> element.
 */
"use strict";

(() => {
  const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2];
  const POLL_MS = 3000;   // library/jobs refresh while anything is generating
  const SAVE_MS = 5000;   // progress save interval during playback (PRD D-8)
  const SKIP_SEC = 30;

  const $ = (id) => document.getElementById(id);
  const audio = $("audio");

  const state = {
    view: "library",
    books: [],            // BookView[] from GET /api/books
    jobs: null,           // GET /api/jobs
    loaded: false,        // first library fetch finished
    connectionError: false,
    pollTimer: null,
    refreshing: false,
    refreshAgain: false,

    // Player
    book: null,           // BookView of the open book
    chapterIndex: 0,
    speed: 1,
    finished: false,
    pendingSeek: null,    // position to apply after loadedmetadata (or once a waited-for chapter is ready)
    waiting: false,       // the current chapter has no audio yet
    wantPlay: false,      // start playback as soon as the chapter can play
    loadedSrc: null,      // audio_url currently in the <audio> element
    audioError: false,
    dirty: false,         // position/speed/chapter changed since the last save
    dragging: false,      // user is dragging the seek bar

    // Search
    search: { query: "", page: 0, token: 0, busy: false, results: [] },
  };

  /* ---------------------------------------------------------------- helpers */

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }

  async function api(path, options = {}) {
    const opts = { ...options, headers: { Accept: "application/json", ...(options.headers || {}) } };
    if (opts.body !== undefined && typeof opts.body !== "string") {
      opts.body = JSON.stringify(opts.body);
      opts.headers["Content-Type"] = "application/json";
    }
    let res;
    try {
      res = await fetch(path, opts);
    } catch (err) {
      throw new ApiError("Can't reach the Tinbook server.", 0);
    }
    const text = await res.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (err) { data = null; }
    }
    if (!res.ok) {
      const msg = data && typeof data.error === "string" ? data.error : `Request failed (HTTP ${res.status}).`;
      throw new ApiError(msg, res.status);
    }
    return data;
  }

  const enc = encodeURIComponent;
  const bookUrl = (id) => `/api/books/${enc(id)}`;

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (key in node && typeof value !== "string") node[key] = value;
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children) {
      if (child !== null && child !== undefined && child !== false) node.append(child);
    }
    return node;
  }

  const clamp = (n, lo, hi) => Math.min(Math.max(n, lo), hi);

  function fmtTime(sec) {
    if (!Number.isFinite(sec) || sec < 0) sec = 0;
    sec = Math.floor(sec);
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = String(sec % 60).padStart(2, "0");
    return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
  }

  function fmtSpeed(x) {
    return `${Number(x).toString()}×`;
  }

  /** "Shelley, Mary Wollstonecraft" -> "Mary Wollstonecraft Shelley". */
  function displayName(name) {
    const parts = String(name).split(",");
    if (parts.length !== 2) return String(name).trim();
    const [last, first] = parts.map((p) => p.trim());
    return first ? `${first} ${last}` : last;
  }

  function displayAuthors(authors) {
    if (!Array.isArray(authors) || authors.length === 0) return "Unknown author";
    return authors.map(displayName).join(", ");
  }

  function nearestSpeed(x) {
    const n = Number(x);
    if (!Number.isFinite(n)) return 1;
    return SPEEDS.reduce((best, s) => (Math.abs(s - n) < Math.abs(best - n) ? s : best), 1);
  }

  let bannerTimer = null;

  /** Show a message under the top bar. Non-sticky messages fade after 6s. */
  function showBanner(message, { sticky = false } = {}) {
    const banner = $("banner");
    banner.textContent = message;
    banner.hidden = false;
    clearTimeout(bannerTimer);
    if (!sticky) bannerTimer = setTimeout(hideBanner, 6000);
  }

  function hideBanner() {
    clearTimeout(bannerTimer);
    $("banner").hidden = true;
  }

  /** Run `fn` only when `sig` differs from last time for `key` (keeps focus/hover stable). */
  const lastRender = new Map();
  function renderIfChanged(key, sig, fn) {
    if (lastRender.get(key) === sig) return;
    lastRender.set(key, sig);
    fn();
  }

  /* ------------------------------------------------------------------ views */

  const VIEWS = ["library", "search", "player"];

  function showView(name) {
    state.view = name;
    for (const tab of document.querySelectorAll('[role="tab"]')) {
      const on = tab.dataset.view === name;
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
    }
    for (const v of VIEWS) $(`view-${v}`).hidden = v !== name;
    if (name === "search" && !state.search.query) $("search-input").focus();
    if (name === "library") renderLibrary();
    renderMini();
  }

  function initTabs() {
    const tabs = [...document.querySelectorAll('[role="tab"]')];
    for (const tab of tabs) {
      tab.addEventListener("click", () => showView(tab.dataset.view));
      tab.addEventListener("keydown", (e) => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        const i = tabs.indexOf(tab);
        const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        next.focus();
        showView(next.dataset.view);
      });
    }
    for (const btn of document.querySelectorAll("[data-goto]")) {
      btn.addEventListener("click", () => showView(btn.dataset.goto));
    }
  }

  /* ---------------------------------------------------------------- library */

  const isBusy = (book) => book.status === "queued" || book.status === "generating";

  function chaptersDone(book) {
    if (Number.isInteger(book.chapters_done)) return book.chapters_done;
    return (book.chapters || []).filter((c) => c.status === "done").length;
  }

  /** Progress for a book: live player state for the open book, else the saved copy. */
  function progressFor(book) {
    if (state.book && state.book.id === book.id) {
      return {
        chapter_index: state.chapterIndex,
        position_sec: currentPosition(),
        finished: state.finished,
        updated_at: "live",
      };
    }
    return book.progress || null;
  }

  /** Percent listened, weighted by chapter word counts (known even before audio exists). */
  function listenedPercent(book, p) {
    if (!p) return 0;
    if (p.finished) return 100;
    const chs = book.chapters || [];
    if (chs.length === 0) return 0;
    const words = chs.map((c) => Math.max(Number(c.word_count) || 0, 0));
    const total = words.reduce((a, b) => a + b, 0);
    if (total <= 0) return 0;
    const idx = clamp(Math.trunc(Number(p.chapter_index) || 0), 0, chs.length - 1);
    let before = 0;
    for (let i = 0; i < idx; i++) before += words[i];
    const dur = Number(chs[idx].duration_sec);
    const frac = dur > 0 ? clamp((Number(p.position_sec) || 0) / dur, 0, 1) : 0;
    return clamp(Math.floor((100 * (before + frac * words[idx])) / total), 0, 99);
  }

  function statusLabel(book) {
    const jobs = state.jobs;
    if (book.status === "generating") return "Generating";
    if (book.status === "queued") {
      const pos = jobs && Array.isArray(jobs.queued) ? jobs.queued.indexOf(book.id) : -1;
      return pos >= 0 && jobs.current ? `Queued · #${pos + 1}` : "Queued";
    }
    if (book.status === "ready") return "Ready";
    if (book.status === "error") return "Error";
    return String(book.status || "Unknown");
  }

  function actionLabel(book, p) {
    if (state.book && state.book.id === book.id) return "Open player";
    if (!p || (!p.updated_at && !p.chapter_index && !p.position_sec)) return "Start";
    if (p.finished) return "Listen again";
    return "Continue";
  }

  function bookCard(book) {
    const total = (book.chapters || []).length;
    const done = chaptersDone(book);
    const p = progressFor(book);
    const pct = listenedPercent(book, p);

    let chapterText = `${done}/${total} chapters`;
    const cur = state.jobs && state.jobs.current;
    if (cur && cur.book_id === book.id && Number.isInteger(cur.chapter_index)) {
      chapterText += ` · working on ${cur.chapter_index + 1}`;
    }

    return el("li", { class: "card", "data-book-id": book.id },
      el("div", { class: "card-head" },
        el("div", { class: "card-text" },
          el("h2", { class: "card-title", text: book.title || "Untitled" }),
          el("p", { class: "card-author muted", text: displayAuthors(book.authors) }),
        ),
        el("span", { class: `pill ${book.status}`, text: statusLabel(book) }),
      ),
      el("div", { class: "card-meta" },
        el("span", { text: chapterText }),
        el("span", { text: `${pct}% listened` }),
      ),
      book.status === "error" && book.error ? el("p", { class: "card-error", text: book.error }) : null,
      el("div", { class: "card-foot" },
        el("div", { class: "bar", role: "presentation" },
          el("span", { style: `width:${pct}%` }),
        ),
        el("button", {
          type: "button",
          class: "btn primary",
          text: actionLabel(book, p),
          onclick: () => openBook(book.id, { play: !(state.book && state.book.id === book.id) }),
        }),
      ),
    );
  }

  function renderLibrary() {
    if (state.view !== "library") return;
    $("library-loading").hidden = state.loaded;
    $("library-empty").hidden = !state.loaded || state.books.length > 0;
    const sig = JSON.stringify([
      state.books,
      state.jobs,
      state.book && [state.book.id, state.chapterIndex, Math.floor(currentPosition()), state.finished],
    ]);
    renderIfChanged("library", sig, () => {
      $("book-list").replaceChildren(...state.books.map(bookCard));
    });
  }

  /* ---------------------------------------------------------------- polling */

  function needsPolling() {
    return !state.loaded || state.connectionError || state.waiting || state.books.some(isBusy);
  }

  function schedulePoll() {
    clearTimeout(state.pollTimer);
    state.pollTimer = needsPolling() ? setTimeout(refresh, POLL_MS) : null;
  }

  /** Fetch /api/books and /api/jobs, then update every view that depends on them. */
  async function refresh() {
    if (state.refreshing) {
      state.refreshAgain = true;
      return;
    }
    state.refreshing = true;
    clearTimeout(state.pollTimer);
    try {
      const [booksRes, jobsRes] = await Promise.all([api("/api/books"), api("/api/jobs")]);
      state.books = Array.isArray(booksRes && booksRes.books) ? booksRes.books : [];
      state.jobs = jobsRes || null;
      state.loaded = true;
      if (state.connectionError) hideBanner();
      state.connectionError = false;
      syncOpenBook();
    } catch (err) {
      state.connectionError = err.status === 0;
      showBanner(err.message, { sticky: state.connectionError });
    } finally {
      state.refreshing = false;
      renderLibrary();
      renderSearchButtons();
      if (state.refreshAgain) {
        state.refreshAgain = false;
        refresh();
      } else {
        schedulePoll();
      }
    }
  }

  /** Apply fresh library data to the open book (chapter statuses, deletion, waiting). */
  function syncOpenBook() {
    if (!state.book) return;
    const fresh = state.books.find((b) => b.id === state.book.id);
    if (!fresh) {
      closePlayer("This book is no longer in your library.");
      return;
    }
    state.book = fresh;
    const ch = fresh.chapters[state.chapterIndex];
    if (state.waiting && ch && ch.audio_url) {
      // D-7: the chapter we were waiting for is ready — start it.
      loadChapter(state.chapterIndex, state.pendingSeek || 0, state.wantPlay);
      return;
    }
    if (!state.waiting && ch && !ch.audio_url && state.loadedSrc) {
      // Audio disappeared (e.g. regenerate): wait for the new file.
      loadChapter(state.chapterIndex, currentPosition(), isPlaying() || state.wantPlay);
      return;
    }
    renderPlayer();
    renderChapterList();
  }

  /* ----------------------------------------------------------------- search */

  async function runSearch(query, page) {
    const s = state.search;
    const token = ++s.token;
    s.busy = true;
    $("search-more").hidden = true;
    $("search-status").textContent = page === 1 ? "Searching…" : "Loading more…";
    if (page === 1) {
      s.results = [];
      $("search-results").replaceChildren();
    }
    let results;
    try {
      const data = await api(`/api/search?q=${enc(query)}&page=${page}`);
      results = Array.isArray(data && data.results) ? data.results : [];
    } catch (err) {
      if (token !== s.token) return;
      s.busy = false;
      if (page > 1) {
        // Gutendex answers past the last page with an error: treat it as the end.
        $("search-status").textContent = `${s.results.length} results · no more results.`;
      } else {
        $("search-status").textContent = err.message;
      }
      return;
    }
    if (token !== s.token) return;   // a newer search started meanwhile
    s.busy = false;
    s.query = query;
    s.page = page;
    s.results = s.results.concat(results);
    const list = $("search-results");
    for (const r of results) list.append(resultItem(r));
    if (s.results.length === 0) {
      $("search-status").textContent = `No books found for “${query}”.`;
    } else if (results.length === 0) {
      $("search-status").textContent = `${s.results.length} results · no more results.`;
    } else {
      $("search-status").textContent = `${s.results.length} results`;
      $("search-more").hidden = false;
    }
  }

  const inLibrary = (gid) => state.books.some((b) => b.gutenberg_id === gid);

  function resultItem(r) {
    const downloads = Number(r.download_count) || 0;
    const sub = `${displayAuthors(r.authors)} · ${downloads.toLocaleString()} downloads`;
    const btn = el("button", { type: "button", class: "btn primary" });
    const errLine = el("p", { class: "result-error", hidden: true });
    const li = el("li", { class: "result", "data-gid": String(r.gutenberg_id) },
      el("div", { class: "result-text" },
        el("p", { class: "result-title", text: r.title || "Untitled" }),
        el("p", { class: "result-sub", text: sub }),
        errLine,
      ),
      btn,
    );
    li._result = r;
    li._btn = btn;
    btn.addEventListener("click", () => addBook(r, btn, errLine));
    setResultButton(li);
    return li;
  }

  function setResultButton(li) {
    const r = li._result;
    const btn = li._btn;
    if (btn.classList.contains("busy")) return;
    if (!r.text_url) {
      btn.disabled = true;
      btn.className = "btn";
      btn.textContent = "No text version";
    } else if (inLibrary(r.gutenberg_id)) {
      btn.disabled = true;
      btn.className = "btn";
      btn.textContent = "In library";
    } else {
      btn.disabled = false;
      btn.className = "btn primary";
      btn.textContent = "Add";
    }
  }

  function renderSearchButtons() {
    for (const li of $("search-results").children) setResultButton(li);
  }

  async function addBook(r, btn, errLine) {
    btn.disabled = true;
    btn.classList.add("busy");
    btn.replaceChildren(el("span", { class: "spinner", "aria-hidden": "true" }), "Adding…");
    errLine.hidden = true;
    try {
      const book = await api("/api/books", {
        method: "POST",
        body: { gutenberg_id: r.gutenberg_id, voice: null },
      });
      if (book && book.id) {
        state.books = [book, ...state.books.filter((b) => b.id !== book.id)];
      }
      btn.classList.remove("busy");
      setResultButton(btn.parentElement);
      showView("library");
      refresh();
    } catch (err) {
      btn.classList.remove("busy");
      setResultButton(btn.parentElement);
      errLine.textContent = err.message;
      errLine.hidden = false;
    }
  }

  function initSearch() {
    $("search-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const q = $("search-input").value.trim();
      if (!q) {
        $("search-input").focus();
        return;
      }
      runSearch(q, 1);
    });
    $("search-more").addEventListener("click", () => {
      if (!state.search.busy && state.search.query) runSearch(state.search.query, state.search.page + 1);
    });
  }

  /* ----------------------------------------------------------------- player */

  const isPlaying = () => !audio.paused && !audio.ended;

  function chapterDuration() {
    if (Number.isFinite(audio.duration) && audio.duration > 0 && state.loadedSrc && !state.waiting) {
      return audio.duration;
    }
    const ch = state.book && state.book.chapters[state.chapterIndex];
    return ch && Number(ch.duration_sec) > 0 ? Number(ch.duration_sec) : 0;
  }

  function currentPosition() {
    if (state.pendingSeek !== null) return state.pendingSeek;
    if (state.waiting || !state.loadedSrc || audio.readyState < 1) return 0;
    return Number.isFinite(audio.currentTime) ? audio.currentTime : 0;
  }

  function setRate(speed) {
    audio.defaultPlaybackRate = speed;   // survives src changes
    audio.playbackRate = speed;
  }

  function resetAudio() {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    state.loadedSrc = null;
  }

  async function openBook(id, { play = false } = {}) {
    if (state.book && state.book.id === id) {
      showView("player");
      if (play && !isPlaying()) playAudio();
      return;
    }
    let book;
    let progress;
    try {
      [book, progress] = await Promise.all([api(bookUrl(id)), api(`${bookUrl(id)}/progress`)]);
    } catch (err) {
      showBanner(err.message);
      return;
    }
    if (state.book) {
      saveProgress();         // the old book's live position, queued before anything else
      resetAudio();
    }
    state.book = book;
    state.audioError = false;
    state.dirty = false;
    state.speed = nearestSpeed(progress && progress.speed);
    setRate(state.speed);
    $("p-speed").value = String(state.speed);

    const count = book.chapters.length;
    let idx = clamp(Math.trunc(Number(progress && progress.chapter_index) || 0), 0, Math.max(count - 1, 0));
    let pos = Math.max(Number(progress && progress.position_sec) || 0, 0);
    state.finished = Boolean(progress && progress.finished);
    if (state.finished) {
      // Finished books start over from the beginning ("Listen again").
      idx = 0;
      pos = 0;
    }
    showView("player");
    renderChapterList();
    if (count === 0) {
      state.waiting = false;
      renderPlayer();
      return;
    }
    loadChapter(idx, pos, play);
  }

  function closePlayer(message) {
    resetAudio();
    state.book = null;
    state.waiting = false;
    state.wantPlay = false;
    state.pendingSeek = null;
    state.dirty = false;
    renderPlayer();
    renderChapterList();
    if (message) showBanner(message);
  }

  /** Point the player at a chapter. Plays when ready if `autoplay`. */
  function loadChapter(index, startSec = 0, autoplay = false) {
    const ch = state.book.chapters[index];
    state.chapterIndex = index;
    state.wantPlay = autoplay;
    state.audioError = false;
    state.pendingSeek = startSec > 0 ? startSec : null;

    if (!ch || !ch.audio_url) {
      state.waiting = true;
      if (state.loadedSrc) resetAudio();
      renderPlayer();
      renderChapterList();
      schedulePoll();
      return;
    }

    state.waiting = false;
    if (state.loadedSrc !== ch.audio_url) {
      state.loadedSrc = ch.audio_url;
      audio.src = ch.audio_url;      // loadedmetadata applies pendingSeek, then plays if wanted
      setRate(state.speed);
    } else if (audio.readyState >= 1) {
      state.pendingSeek = startSec;
      applyPendingSeek();
    }
    renderPlayer();
    renderChapterList();
    if (autoplay) playAudio();
  }

  function applyPendingSeek() {
    if (state.pendingSeek === null) return;
    const d = chapterDuration();
    const t = d > 0 ? clamp(state.pendingSeek, 0, Math.max(d - 1, 0)) : state.pendingSeek;
    state.pendingSeek = null;
    try {
      audio.currentTime = t;
    } catch (err) {
      /* ignore: some engines reject seeks before data; position stays 0 */
    }
  }

  function playAudio() {
    state.wantPlay = true;
    if (state.audioError && state.book) {
      state.loadedSrc = null;
      loadChapter(state.chapterIndex, currentPosition(), true);
      return;
    }
    // Wait for loadedmetadata so a resume never plays a blip from 0:00.
    if (state.waiting || !state.loadedSrc || audio.readyState < 1) {
      renderPlayer();
      return;
    }
    if (state.finished) state.finished = false;
    const p = audio.play();
    if (p && typeof p.catch === "function") {
      p.catch((err) => {
        if (err && err.name === "AbortError") return;   // src changed mid-start
        state.wantPlay = false;
        renderPlayer();
      });
    }
  }

  function pauseAudio() {
    state.wantPlay = false;
    audio.pause();
    renderPlayer();
  }

  function togglePlay() {
    if (!state.book) return;
    if (isPlaying() || (state.wantPlay && (state.waiting || audio.readyState < 1))) pauseAudio();
    else playAudio();
  }

  function goToChapter(index, autoplay) {
    if (!state.book) return;
    const count = state.book.chapters.length;
    if (index < 0 || index >= count) return;
    state.finished = false;
    loadChapter(index, 0, autoplay);
    markDirty();
    saveProgress();   // D-8: on chapter change
  }

  function skip(delta) {
    if (!state.book || state.waiting || !state.loadedSrc) return;
    const d = chapterDuration();
    const t = currentPosition() + delta;
    if (d > 0 && t >= d) {
      if (state.chapterIndex + 1 < state.book.chapters.length) {
        goToChapter(state.chapterIndex + 1, isPlaying() || state.wantPlay);
      } else {
        seekTo(d);
      }
      return;
    }
    seekTo(Math.max(t, 0));
  }

  function seekTo(t) {
    if (state.waiting || !state.loadedSrc) return;
    if (audio.readyState < 1) {
      state.pendingSeek = t;
    } else {
      audio.currentTime = t;
    }
    markDirty();
    renderTimes();
  }

  function markDirty() {
    if (state.book) state.dirty = true;
  }

  /* --------------------------------------------------------------- progress */

  let saveChain = Promise.resolve();

  function progressBody() {
    return {
      chapter_index: state.chapterIndex,
      position_sec: Math.round(currentPosition() * 10) / 10,
      speed: state.speed,
      finished: state.finished,
    };
  }

  function applySavedProgress(bookId, saved) {
    const b = state.books.find((x) => x.id === bookId);
    if (b && saved) b.progress = saved;
  }

  /** Save progress if anything changed. Saves run one at a time, in order. */
  function saveProgress() {
    if (!state.book || !state.dirty) return saveChain;
    const id = state.book.id;
    const body = progressBody();
    state.dirty = false;
    saveChain = saveChain.then(() =>
      api(`${bookUrl(id)}/progress`, { method: "PUT", body })
        .then((saved) => applySavedProgress(id, saved))
        .catch((err) => {
          console.warn("Tinbook: progress save failed:", err.message);
          if (state.book && state.book.id === id) state.dirty = true;   // retry on the next tick
        }),
    );
    return saveChain;
  }

  /** Fire-and-forget save that survives page unload. */
  function saveOnUnload() {
    if (!state.book || !state.dirty) return;
    state.dirty = false;
    try {
      fetch(`${bookUrl(state.book.id)}/progress`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(progressBody()),
        keepalive: true,
      });
    } catch (err) {
      /* nothing more we can do while unloading */
    }
  }

  /* -------------------------------------------------------------- rendering */

  function setPlayButton(btn, playing) {
    btn.classList.toggle("playing", playing);
    const label = playing ? "Pause" : "Play";
    btn.setAttribute("aria-label", label);
    btn.title = label;
  }

  function playerMessage() {
    const book = state.book;
    const n = state.chapterIndex + 1;
    if (book.chapters.length === 0) return { cls: "error", text: "This book has no chapters." };
    const ch = book.chapters[state.chapterIndex];
    if (state.audioError) return { cls: "error", text: `Couldn't play chapter ${n}. Press play to try again.` };
    if (state.waiting) {
      if (ch && ch.status === "error") {
        return { cls: "error", text: `Chapter ${n} couldn't be generated.${book.error ? ` ${book.error}` : ""}` };
      }
      if (book.status === "error") {
        return { cls: "error", text: `Chapter ${n} isn't available: generation stopped with an error.` };
      }
      return { cls: "waiting", text: `Waiting for chapter ${n}…` };
    }
    if (state.finished) return { cls: "done", text: "You finished this book." };
    return null;
  }

  function renderTimes() {
    if (!state.book) return;
    const d = chapterDuration();
    const seek = $("p-seek");
    const t = state.dragging ? Number(seek.value) : currentPosition();
    if (!state.dragging) {
      seek.max = String(Math.max(Math.floor(d), 0));
      seek.value = String(Math.floor(t));
    }
    $("p-elapsed").textContent = fmtTime(t);
    $("p-remaining").textContent = `−${fmtTime(Math.max(d - t, 0))}`;
  }

  function renderPlayer() {
    const hasBook = Boolean(state.book);
    $("player-empty").hidden = hasBook;
    $("player").hidden = !hasBook;
    renderMini();
    if (!hasBook) return;

    const book = state.book;
    const count = book.chapters.length;
    const ch = book.chapters[state.chapterIndex];
    $("p-book-title").textContent = book.title || "Untitled";
    $("p-book-author").textContent = displayAuthors(book.authors);
    $("p-chapter-num").textContent = count ? `Chapter ${state.chapterIndex + 1} of ${count}` : "";
    $("p-chapter-title").textContent = ch ? ch.title : "";

    const msg = playerMessage();
    const msgEl = $("p-message");
    msgEl.hidden = !msg;
    if (msg) {
      msgEl.className = `p-message ${msg.cls}`;
      msgEl.textContent = msg.text;
    }

    const playable = !state.waiting && Boolean(state.loadedSrc);
    $("p-seek").disabled = !playable;
    $("p-back").disabled = !playable;
    $("p-fwd").disabled = !playable;
    $("p-prev").disabled = state.chapterIndex <= 0;
    $("p-next").disabled = state.chapterIndex >= count - 1;
    $("p-play").disabled = count === 0;
    setPlayButton($("p-play"), isPlaying() || (state.wantPlay && !state.audioError));
    renderTimes();
  }

  function chapterStatusText(ch, i) {
    const cur = state.jobs && state.jobs.current;
    if (ch.status === "done") return { cls: "", text: ch.duration_sec ? fmtTime(ch.duration_sec) : "Ready" };
    if (ch.status === "error") return { cls: "error", text: "Failed" };
    if (cur && state.book && cur.book_id === state.book.id && cur.chapter_index === i) {
      return { cls: "generating", text: "Generating…" };
    }
    return { cls: "", text: "Pending" };
  }

  function renderChapterList() {
    const list = $("p-chapter-list");
    if (!state.book) {
      lastRender.delete("chapters");
      list.replaceChildren();
      return;
    }
    const chs = state.book.chapters;
    $("p-chapter-count").textContent = `· ${chaptersDone(state.book)}/${chs.length} ready`;
    const cur = state.jobs && state.jobs.current;
    const sig = JSON.stringify([state.book.id, state.chapterIndex, chs, cur && [cur.book_id, cur.chapter_index]]);
    renderIfChanged("chapters", sig, () => list.replaceChildren(...chs.map((ch, i) => {
      const st = chapterStatusText(ch, i);
      return el("li", {},
        el("button", {
          type: "button",
          "aria-current": i === state.chapterIndex ? "true" : null,
          onclick: () => goToChapter(i, isPlaying() || state.wantPlay || ch.status === "done"),
        },
          el("span", { class: "ch-num", text: String(i + 1) }),
          el("span", { class: "ch-title", text: ch.title }),
          el("span", { class: `ch-status ${st.cls}`, text: st.text }),
        ),
      );
    })));
  }

  function renderMini() {
    const show = Boolean(state.book) && state.view !== "player";
    $("mini").hidden = !show;
    if (!show) return;
    const ch = state.book.chapters[state.chapterIndex];
    $("mini-chapter").textContent = state.waiting
      ? `Waiting for chapter ${state.chapterIndex + 1}…`
      : (ch ? ch.title : "");
    $("mini-book").textContent = state.book.title || "";
    setPlayButton($("mini-play"), isPlaying() || (state.wantPlay && !state.audioError));
  }

  /* ----------------------------------------------------------------- events */

  function initPlayer() {
    const speed = $("p-speed");
    for (const s of SPEEDS) speed.append(el("option", { value: String(s), text: fmtSpeed(s) }));
    speed.value = "1";
    speed.addEventListener("change", () => {
      state.speed = nearestSpeed(speed.value);
      setRate(state.speed);
      markDirty();
      saveProgress();
    });

    $("p-play").addEventListener("click", togglePlay);
    $("mini-play").addEventListener("click", togglePlay);
    $("mini-open").addEventListener("click", () => showView("player"));
    $("p-back").addEventListener("click", () => skip(-SKIP_SEC));
    $("p-fwd").addEventListener("click", () => skip(SKIP_SEC));
    $("p-prev").addEventListener("click", () => goToChapter(state.chapterIndex - 1, isPlaying() || state.wantPlay));
    $("p-next").addEventListener("click", () => goToChapter(state.chapterIndex + 1, isPlaying() || state.wantPlay));

    const seek = $("p-seek");
    seek.addEventListener("input", () => {
      state.dragging = true;
      renderTimes();
    });
    seek.addEventListener("change", () => {
      state.dragging = false;
      seekTo(Number(seek.value));
    });

    $("p-chapters").addEventListener("toggle", (e) => {
      if (!e.target.open) return;
      const current = $("p-chapter-list").querySelector('[aria-current="true"]');
      if (current) current.scrollIntoView({ block: "nearest" });
    });

    audio.addEventListener("loadedmetadata", () => {
      setRate(state.speed);
      applyPendingSeek();
      renderPlayer();
      if (state.wantPlay) playAudio();
    });

    audio.addEventListener("timeupdate", () => {
      if (isPlaying()) markDirty();
      renderTimes();
    });

    audio.addEventListener("durationchange", renderTimes);
    audio.addEventListener("seeked", renderTimes);

    audio.addEventListener("play", () => {
      if (state.finished) {
        state.finished = false;
        markDirty();
      }
      renderPlayer();
    });

    audio.addEventListener("playing", () => {
      state.wantPlay = false;
      renderPlayer();
    });

    audio.addEventListener("pause", () => {
      // D-8: save on pause. (Also fires just before "ended".)
      if (!state.loadedSrc) return;   // src cleared on purpose (switching/closing books)
      markDirty();
      saveProgress();
      renderPlayer();
      renderLibrary();
    });

    audio.addEventListener("ended", () => {
      if (!state.book) return;
      const next = state.chapterIndex + 1;
      if (next < state.book.chapters.length) {
        goToChapter(next, true);   // D-7: auto-advance (waits if not generated yet)
      } else {
        state.finished = true;
        state.wantPlay = false;
        markDirty();
        saveProgress();
        renderPlayer();
      }
    });

    audio.addEventListener("error", () => {
      if (!state.loadedSrc) return;   // cleared src on purpose
      state.audioError = true;
      state.wantPlay = false;
      renderPlayer();
      refresh();   // the file may have been removed; refresh decides whether to wait
    });

    // D-8: every 5s during playback.
    setInterval(() => {
      if (isPlaying()) saveProgress();
    }, SAVE_MS);

    // D-8: on window close / hide.
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") saveProgress();
    });
    window.addEventListener("pagehide", saveOnUnload);
    window.addEventListener("beforeunload", saveOnUnload);
  }

  /* ------------------------------------------------------------------- boot */

  // Hook for the desktop shell: pywebview can call this before closing the window.
  window.tinbook = {
    saveProgress: () => {
      markDirty();
      return saveProgress().then(() => true);
    },
  };

  $("banner").addEventListener("click", hideBanner);
  initTabs();
  initSearch();
  initPlayer();
  renderPlayer();
  showView("library");
  refresh();
})();
