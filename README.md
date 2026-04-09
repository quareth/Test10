# Test10 — Sitemap scraper (DWEMR sample)

This repository is a **reference implementation** of a small full-stack app—a **sitemap-driven scraper** with scheduling, jobs, and a web UI—produced as part of a delivery run using **DWEMR** (a multi-agent planning and implementation workflow for Claude).

## About this repo

The **application source** here matches what was built during that workflow: FastAPI backend, React (Vite) frontend, SQLite storage, and Docker-based deployment. It is published **essentially as delivered**, with only **light housekeeping** before going public:

- **Omitted from version control:** local **DWEMR** state (`.dwemr/`) and **Claude** project config (`.claude/`), which are environment- and session-specific and not part of the runnable product.
- **No functional rewrites** were made for the sake of this upload—the goal is to show a realistic example of “what shipped” from a DWEMR-guided build.

If you are evaluating DWEMR, this tree is meant to illustrate the kind of structured output (layout, tests, deployment notes) you can expect from that process—not a polished product release.

## Quick start

See **[DEPLOY.md](./DEPLOY.md)** for Docker Compose setup, environment variables, and creating the first user.

```bash
docker compose up --build -d
```

The app is served on **http://localhost:8000** by default.

## Layout

| Path | Role |
|------|------|
| `backend/` | FastAPI app, scraping pipeline, scheduler, auth |
| `frontend/` | React UI |
| `Dockerfile`, `docker-compose.yml` | Container deployment |
| `DEPLOY.md` | Deployment and operations notes |
| `docs/` | Project runbooks and wave roadmap (from planning) |

## License

No `LICENSE` file is included.
