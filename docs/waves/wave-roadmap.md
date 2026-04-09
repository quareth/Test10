# Wave Roadmap -- Sitemap Scraper Web App

App-wide wave breakdown owned by product-manager.

## App boundary

A deployed web application for a small team that scrapes documentation sites via sitemap discovery, converts HTML pages to Markdown, and stores indexed results for download. Purpose: feed RAG pipelines and AI platforms with clean Markdown knowledge.

## Wave overview

| Wave | Title | Goal | Status |
|------|-------|------|--------|
| wave-1 | Core Scraping App | Deliver a working web app with auth, dashboard, on-demand scraping, both indexing modes, downloads, and historical storage | complete |
| wave-2 | Scheduled Indexing and Deployment | Add recurring scrape schedules, background job execution, and production deployment configuration | complete |

## Wave 1: Core Scraping App

**Goal:** Deliver a complete, usable web application that a small team can use to scrape documentation sites on demand, convert HTML to Markdown, choose an indexing mode, download results, and access historical snapshots.

**Scope:**
- User authentication (small-team login, not public registration)
- Dashboard showing scrape targets, job status, and historical results
- Add a target website URL and trigger a scrape
- Sitemap discovery from a root URL
- HTML scraping of all pages found in the sitemap
- HTML-to-Markdown conversion producing clean, readable Markdown
- Two indexing modes: bulk (single concatenated file) and structured (separate files preserving site path hierarchy)
- Download indexed content (individual files or zip archive)
- Persistent historical storage of all past indexed results with re-download

**Acceptance shape:**
- A user can log in, add a URL, trigger a scrape, see results on the dashboard, choose bulk or structured output, and download the result
- Past results are stored and re-downloadable
- The app runs as a web server (not just CLI or scripts)

**Why first:** This is the complete core product. Without it, nothing else matters. Scheduling is an enhancement on top of a working scraping tool.

## Wave 2: Scheduled Indexing and Deployment

**Goal:** Add recurring scrape schedules so content stays fresh automatically, and prepare the application for production deployment.

**Scope:**
- Define recurring scrape schedules from the dashboard (per target)
- Background job runner that executes scheduled scrapes automatically
- Automatic storage of scheduled scrape results as new historical snapshots
- Dashboard updates showing schedule status and next-run info
- Production deployment configuration and documentation
- Any polish or fixes discovered during wave-1 delivery

**Acceptance shape:**
- A user can set a schedule for a target and the system scrapes it automatically at the defined interval
- Scheduled results appear in history and are downloadable like on-demand results
- The app can be deployed to a server (not localhost-only)

**Dependencies:** wave-1 complete

**Why second:** Scheduling builds on top of the working scrape-and-download flow. Deployment config is best done once the app shape is stable.

## Sequencing notes

- Wave 1 is self-contained and delivers a usable product on its own.
- Wave 2 is additive. If wave 1 is the only wave delivered, the user still has a functional tool (just without automation).
- Tech choices made in wave 1 (framework, database, storage) carry forward into wave 2. Planning specialists should document those choices clearly.

## Decision log

- 2026-04-08: Wave-1 selected as initial active wave.
- 2026-04-09: Wave-1 completed (29 tasks, 6 phases, 90+ tests). Wave-2 activated. Rationale: the user's onboarding clarification explicitly includes scheduled/recurring scraping and deployed hosting as MVP requirements, so wave-2 is not an enhancement but part of the stated product scope.
- 2026-04-09: Wave-2 completed (18 tasks, 4 phases, 130 tests). ALL WAVES COMPLETE. App delivery done.

---
Last updated: 2026-04-09
