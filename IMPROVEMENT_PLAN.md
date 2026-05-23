# Daily Edge — Improvement Plan

This plan covers the work remaining after the correctness/security/threading
fixes already merged to `claude/newsletter-charts-app-8Hw41`. Items are ordered
by value: Phase 1 unblocks clean install and confident changes; later phases are
structural cleanup.

## Status of prior work (done)

- SyntaxError in `chart_engine.py`, `FINANCE_DB` env var, structured logging
- `threading.Lock` around `newsletter_engine._CACHE` and `scanner._fetch_status`
- CORS origin restriction, `rsi_period` parse guard, `127.0.0.1` default bind
- `pd.read_html` timeout, parallel `compute_scanner` + feature loop
- Chart.js instance cleanup (no more leak on filter/sort), duplicate
  `showChartArea()` removed, narrow `ruff` config + CI guard

---

## Phase 1 — Correctness & installability (do first)

### 1.1 Drop the hard `ta` dependency
- **Why:** `ta` fails to build in a clean container; it blocked launching the
  app locally. RSI/KAMA/MACD/CCI/Bollinger already exist in `indicators.py`.
- **What:** Rewrite `scanner._scan_one` to import indicator helpers from
  `indicators.py` instead of `ta`. Remove `ta` from `requirements.txt`.
- **Bonus:** Collapses the 4× duplication of RSI/KAMA (newsletter_engine,
  scanner, features, indicators) into a single source of truth.
- **Effort:** 1–2 hours.

### 1.2 Harden `data_fetcher` against metadata failures
- **Why:** A yfinance `.info` (name/sector) failure currently aborts the whole
  OHLCV download.
- **What:** Isolate the metadata lookup so a failure logs a warning and the
  price bars still persist. Price history and metadata become independent.
- **Effort:** ~30 min.

### 1.3 Add a test suite (currently zero tests)
- **Why:** CI lints but runs no tests; pure-function logic is unguarded.
- **What:** `tests/` with pytest covering deterministic functions:
  - `indicators.py`: `_rsi`, `_kama`, `_macd`, `_bollinger` vs. fixtures
  - `newsletter_engine.py`: `engineer_features` / `score_and_select` shape +
    edge cases (empty df, <30 bars)
  - `scanner.py`: `_compute_tf` returns the expected keys
  - Seed an isolated SQLite DB via the `FINANCE_DB` env var.
- **Effort:** ~half day. Activates the CI test step already scaffolded.

---

## Phase 2 — Resolve the two-pipeline split

### 2.1 Decide the fate of the orphaned CLI pipeline
- **Problem:** The repo carries a second, unused newsletter pipeline
  (`newsletter_generator.py`, `story_selector.py`, `features.py`,
  `nl_cache.py`, `nl_fetcher.py`, `subtitle_generator.py`, `universe.py`,
  parts of `chart_engine.py`) that the Flask app never calls. It's dead code
  that looks live.
- **Option A — Wire it in:** Have `newsletter_engine.compute_newsletter_data`
  delegate to `features.engineer_all_features` + `story_selector.select_stories`,
  bridging `finance.db` and `daily_edge_cache.db`.
- **Option B — Remove it:** Delete the dead modules if the Flask
  `newsletter_engine` is the canonical path.
- **Effort:** ~half day either way. Recommend deciding explicitly.

---

## Phase 3 — Structural cleanup (lower urgency)

### 3.1 Split `app.py` into Flask Blueprints
- symbols / data / indicators / scanner / newsletter blueprints. Navigability
  only; no behavior change. ~2 hours.

### 3.2 Frontend modularization
- `scripts/app.js` relies on global functions; HTML still has inline `onclick=`.
  Convert to ES modules + `addEventListener`. Do only if the frontend keeps
  growing.

### 3.3 Housekeeping
- Add `.python-version`.
- Fix README claims about `run_newsletter.py` (depends on the Phase 2 decision).
- Verify `Dockerfile` / `docker-compose.yml` boot now that `FINANCE_DB` is wired.

---

## Recommended order

1. **1.1 Drop `ta`** — quick, removes a real install blocker.
2. **1.2 Fetch hardening** — quick, prevents data-loss on metadata errors.
3. **1.3 Tests** — locks in everything above.
4. **2.1 Pipeline decision** — removes the biggest source of confusion.
5. Phase 3 as capacity allows.
