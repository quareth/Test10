"""Phase 6 integration tests: single-process serving and SPA catch-all.

These tests verify that the FastAPI backend serves the frontend production
build, handles SPA client-side routing via a catch-all, and keeps API routes
accessible under /api/*.

Requires: frontend/dist/ to exist (run `npm run build` in frontend/ first).
"""

from __future__ import annotations

import httpx
import pytest
import uvicorn
import asyncio
import threading
import time

from backend.main import app

_BASE = "http://127.0.0.1:8111"


@pytest.fixture(scope="module")
def live_server():
    """Start a real uvicorn server in a background thread for integration tests."""
    config = uvicorn.Config(app, host="127.0.0.1", port=8111, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    for _ in range(20):
        try:
            resp = httpx.get(f"{_BASE}/api/auth/me", timeout=1.0)
            if resp.status_code in (200, 401, 403):
                break
        except httpx.ConnectError:
            time.sleep(0.25)
    else:
        pytest.fail("Live server did not start within 5 seconds")

    yield _BASE

    server.should_exit = True
    thread.join(timeout=5)


class TestFrontendServing:
    """Backend serves the frontend production build from frontend/dist/."""

    def test_root_returns_html(self, live_server: str):
        resp = httpx.get(f"{live_server}/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "<!doctype html>" in resp.text.lower() or "<html" in resp.text.lower()

    def test_static_asset_served(self, live_server: str):
        # The CSS asset should be reachable under /assets/
        resp = httpx.get(f"{live_server}/assets/index-CrqClqZ-.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers.get("content-type", "")


class TestSPACatchAll:
    """SPA catch-all returns index.html for non-API, non-static paths."""

    def test_spa_route_targets(self, live_server: str):
        resp = httpx.get(f"{live_server}/targets/1")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_spa_route_arbitrary_path(self, live_server: str):
        resp = httpx.get(f"{live_server}/some/deep/frontend/route")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")


class TestAPIRoutePrecedence:
    """API routes take precedence over the SPA catch-all."""

    def test_auth_me_returns_401(self, live_server: str):
        resp = httpx.get(f"{live_server}/api/auth/me")
        assert resp.status_code == 401
        data = resp.json()
        assert "detail" in data

    def test_api_targets_requires_auth(self, live_server: str):
        resp = httpx.get(f"{live_server}/api/targets")
        assert resp.status_code == 401
