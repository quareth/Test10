from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.auth.routes import router as auth_router
from backend.config import settings
from backend.database import init_db
from backend.routes.jobs import router as jobs_router
from backend.routes.schedules import router as schedules_router
from backend.routes.targets import router as targets_router
from backend.scheduler import init_scheduler, shutdown_scheduler

# Resolve the frontend dist directory relative to the project root.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialise database and scheduler on startup."""
    await init_db()
    await init_scheduler()
    try:
        yield
    finally:
        await shutdown_scheduler()


app = FastAPI(title="Sitemap Scraper", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(targets_router)
app.include_router(jobs_router)
app.include_router(schedules_router)

# ---------------------------------------------------------------------------
# Serve the frontend production build (SPA)
# ---------------------------------------------------------------------------
# Mount static assets only when the frontend has been built.  The catch-all
# route below returns index.html for any non-API, non-static path so that
# client-side routing works correctly.
# ---------------------------------------------------------------------------

if _FRONTEND_DIST.is_dir():
    # Mount static assets (JS, CSS, images, etc.) under /assets so they are
    # served directly without hitting the catch-all.
    _assets_dir = _FRONTEND_DIST / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="static-assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def _spa_catch_all(request: Request, full_path: str) -> FileResponse:
        """Return index.html for any path not matched by API routes or static mounts.

        This enables SPA client-side routing: paths like ``/targets/1`` are
        resolved by the frontend router rather than producing a server 404.
        """
        # If the requested path maps to an existing file in dist (e.g. favicon,
        # manifest, robots.txt), serve that file directly.
        candidate = _FRONTEND_DIST / full_path
        if candidate.is_file() and _FRONTEND_DIST in candidate.resolve().parents:
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
