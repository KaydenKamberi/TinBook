# Gutenberg fallback handoff — Claude Code

Branch: `gutenberg-fallback-claude` (from `main`). Fixes Gutendex timeouts/503s blocking search, metadata and downloads.

## Done
- `core/gutenberg.py` tries Gutendex first, with a timeout of `min(8, http_timeout)` seconds (was 20).
- **`download_text`**: if Gutendex fails, downloads `https://www.gutenberg.org/cache/epub/<id>/pg<id>.txt` directly. It also tries that URL if Gutendex works but its own `text_url` download fails. A 404 gives "no plain-text download available".
- **`search` / `get_metadata`**: if Gutendex fails (timeout, connection error, non-200, bad JSON/metadata), they use Project Gutenberg's `pg_catalog.csv`:
  - Downloaded once to `<library_dir>/pg_catalog.csv`, re-downloaded when older than 7 days. Written to `.tmp` and swapped in only after it parses, so a bad or cut-off download never replaces a good copy.
  - If a refresh fails but an old copy exists, the old copy is used. The refresh is retried at most every 10 minutes.
  - Parsed once per process (~1 s for ~75k rows) and kept in memory. Each search after that takes ~10 ms.
  - Search: English only. Every query word must appear in the title or authors (case- and accent-insensitive). Ranking: exact title → title starts with the query → title contains it → all words in title → author-only match. Within each rank, text books come before audio, then lowest ID. 32 results per page.
  - Results: `download_count=0`. Authors exclude `[Translator]`/`[Editor]` entries and have life dates removed. `text_url` is the direct cache URL for `Type == Text`, otherwise None.
- After Gutendex times out, is unreachable or returns 5xx, it is skipped for 60 s. So `pipeline.add_book` (which calls `get_metadata` and then `download_text`) waits 8 s once, not twice. 404s don't trigger the skip.
- If both Gutendex and the fallback fail, `GutenbergError` mentions both failures.
- All §5 signatures are unchanged. Updated the `core/gutenberg.py` section of `docs/ARCHITECTURE.md` to describe the fallback.
- Tests: new `tests/test_gutenberg_fallback.py` (34 tests, all HTTP mocked via `responses`) covers each fallback path, caching, refresh, stale copy, bad downloads, pagination, English-only, and the 8 s timeout. In `tests/test_library.py` (existing CP1B gutenberg tests), I only added a fixture that resets module state, and changed the timeout test to expect 8 s. `pytest`: 353 passed.

## How to test
From the repo root (Windows cmd or PowerShell):
```
python -m pytest -q
```
Live check that **forces** the fallback (points Gutendex at a dead host). The first run downloads the catalog to `library\pg_catalog.csv`:
```
python -c "from core import gutenberg as g; g._BASE_URL='https://gutendex.invalid/books/'; r=g.search('crime and punishment'); print([(x.gutenberg_id, x.title) for x in r[:3]]); print(g.get_metadata(2554)); t=g.download_text(2554); print(len(t), '*** START OF' in t)"
```
Expected: 2554 "Crime and Punishment" first in the list, metadata for 2554 with `text_url='https://www.gutenberg.org/cache/epub/2554/pg2554.txt'`, then a large character count and `True`. Running it a second time should be faster because the catalog is cached.

Normal path (Gutendex up or down, either should work now):
```
python -c "from core import gutenberg as g; print([(x.gutenberg_id, x.title) for x in g.search('crime and punishment')[:3]])"
```

## Not done / known issues
- Not live-tested: this sandbox can't reach gutendex.com or gutenberg.org. The CSV parser reads columns by header name (`Text#`, `Type`, `Title`, `Language`, `Authors`). If the real file lacks them, the error is "unexpected format".
- Catalog results have no popularity data, so ranking differs from Gutendex (which sorts by downloads). The lowest ID is usually the main edition.
- On a slow connection, the first fallback search waits for the catalog download (~15 MB) to finish.

## Contract change requests
- Applied in this branch (requested by Kayden): Gutendex timeout is `min(8, http_timeout)` instead of `http_timeout`. Fallback behavior is documented in ARCHITECTURE §5 `core/gutenberg.py`. No signature, schema, route or folder changes. The only new file in the library folder is `pg_catalog.csv` (plus a transient `pg_catalog.csv.tmp`), and `list_books` already ignores files.

## New dependencies needed
- None.

## Notes for the next agent
- Module state for tests: `_gutendex_skip_until`, `_catalog_retry_at`, `_catalog_cache`. Reset all three in an autouse fixture (see either gutenberg test file), or a Gutendex failure in one test makes later tests skip Gutendex.
- The CP1B handoff's live acceptance check (first three results for "crime and punishment") can now be run even while Gutendex is down.

---

# Update after the Wave 2 review — Claude Code
Kayden approved this branch's edits outside CP1B ownership: `core/gutenberg.py`, `tests/test_library.py`, and ARCHITECTURE §5.

## Changed
- **Merged `origin/cp2c-mistral`** into this branch, so `tests/test_gutenberg.py` (CP2C) is here. Before this, merging both into `main` made 14 of its tests fail:
  - 13 failed because of leaked module state. `test_search_timeout_raises` started the 60 s Gutendex pause, and the tests after it skipped Gutendex.
  - 1 failed because download behaviour changed (see the 404 test below).
- **`tests/test_gutenberg.py`:**
  - Added the same autouse `reset_gutenberg_state` fixture as `tests/test_library.py`.
  - `test_download_text_http_404_raises` now also registers a 404 for the direct `https://www.gutenberg.org/cache/epub/84/pg84.txt` URL. It expects "no plain-text download" and checks that all three URLs are requested in order.
- **`core/gutenberg.py`, `search()`:** a Gutendex **404 on page > 1** now returns `[]` instead of falling back to the catalog. Gutendex answers 404 for a page past the last one. Before this fix, "More results" could append catalog results (duplicates or unrelated books) after the real Gutendex results. A 404 on page 1, and any outage on any page, still fall back as before. ARCHITECTURE §5 is updated to match.
- **`tests/test_gutenberg_fallback.py`:** 4 new tests (38 total):
  - a 404 past the last page returns `[]` and never downloads the catalog (this test fails without the fix);
  - a 404 on page 1 still uses the catalog;
  - a later page still falls back during a 503 or timeout.
- Full suite: **386 passed**.

## Known issue (unchanged)
- If Gutendex goes down between page 1 and page 2, page 2 comes from the catalog, whose ranking differs, so results can repeat. The frontend (CP2B) drops duplicate IDs when it appends "More results".
