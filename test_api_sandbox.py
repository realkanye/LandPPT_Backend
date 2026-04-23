"""
Sandbox integration test — runs the FastAPI app with an in-memory MongoDB
(mongomock_motor) and exercises key API endpoints.

Usage:
    cd /home/user/LandPPT_Backend
    .venv/bin/python test_api_sandbox.py
"""

import os, sys, asyncio, json

# ── 1. Environment ──────────────────────────────────────────────────────────
os.environ.setdefault("MONGODB_URL", "mock://localhost/landppt")
os.environ.setdefault("SECRET_KEY", "test-secret-key-sandbox")
os.environ.setdefault("DISABLE_AUTH", "true")
os.environ.setdefault("RELOAD", "false")
os.environ.setdefault("WORKERS", "1")
os.environ.setdefault("LANDPPT_ENABLE_API_DOCS", "true")
os.environ.setdefault("CACHE_BACKEND", "memory")   # skip Valkey
os.environ.setdefault("DEFAULT_AI_PROVIDER", "openai")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# ── 2. Patch mongomock so Beanie's list_collection_names works ───────────────
import mongomock.database as _mdb
_orig_lcn = _mdb.Database.list_collection_names
def _patched_lcn(self, session=None, **kwargs):
    return _orig_lcn(self, session=session)
_mdb.Database.list_collection_names = _patched_lcn

# ── 3. Patch database.py to use AsyncMongoMockClient instead of real Motor ──
import mongomock_motor
import landppt.database.database as _db_module

async def _mock_init_db():
    from beanie import init_beanie
    from landppt.database.mongo_models import (
        ProjectDocument, SlideDocument, ProjectVersionDocument,
        GlobalMasterTemplateDocument, CounterDocument, UserConfigDocument,
    )
    client = mongomock_motor.AsyncMongoMockClient()
    database = client["landppt"]
    await init_beanie(
        database=database,
        document_models=[
            ProjectDocument, SlideDocument, ProjectVersionDocument,
            GlobalMasterTemplateDocument, CounterDocument, UserConfigDocument,
        ],
    )
    print("  [mock] init_beanie OK (in-memory MongoDB)")

_db_module.init_db = _mock_init_db

# ── 4. Import app ────────────────────────────────────────────────────────────
from landppt.main_api import app

# ── 5. Run tests ─────────────────────────────────────────────────────────────
import httpx
from httpx import ASGITransport

PASS = []
FAIL = []

def ok(name, detail=""):
    PASS.append(name)
    print(f"  ✓  {name}" + (f"  — {detail}" if detail else ""))

def fail(name, detail=""):
    FAIL.append(name)
    print(f"  ✗  {name}" + (f"  — {detail}" if detail else ""))


async def run_tests():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:

        # ── GET /health ──────────────────────────────────────────────────────
        r = await client.get("/health")
        if r.status_code == 200 and r.json().get("status") == "healthy":
            ok("GET /health", r.json().get("status"))
        else:
            fail("GET /health", f"status={r.status_code} body={r.text[:80]}")

        # ── GET /docs (OpenAPI UI) ───────────────────────────────────────────
        r = await client.get("/docs")
        if r.status_code == 200:
            ok("GET /docs", "OpenAPI UI reachable")
        else:
            fail("GET /docs", f"status={r.status_code}")

        # ── GET /openapi.json ────────────────────────────────────────────────
        r = await client.get("/openapi.json")
        if r.status_code == 200:
            spec = r.json()
            route_count = len(spec.get("paths", {}))
            ok("GET /openapi.json", f"{route_count} routes exposed")
        else:
            fail("GET /openapi.json", f"status={r.status_code}")

        # ── GET /v1/projects (list projects — should be empty) ───────────────
        r = await client.get("/v1/projects")
        if r.status_code == 200:
            body = r.json()
            project_count = len(body) if isinstance(body, list) else body.get("total", "?")
            ok("GET /v1/projects", f"total={project_count}")
        else:
            fail("GET /v1/projects", f"status={r.status_code} body={r.text[:120]}")

        # ── POST /v1/projects (create project) ───────────────────────────────
        payload = {
            "title": "沙箱测试项目",
            "scenario": "business",
            "topic": "MongoDB 迁移测试",
            "requirements": "验证 MongoDB 数据层是否正常工作",
        }
        r = await client.post("/v1/projects", json=payload)
        project_id = None
        if r.status_code in (200, 201):
            body = r.json()
            project_id = body.get("project_id") or body.get("id")
            ok("POST /v1/projects", f"project_id={project_id}")
        else:
            fail("POST /v1/projects", f"status={r.status_code} body={r.text[:200]}")

        # ── GET /v1/projects/{id} (retrieve project) ─────────────────────────
        if project_id:
            r = await client.get(f"/v1/projects/{project_id}")
            if r.status_code == 200:
                body = r.json()
                ok("GET /v1/projects/{id}", f"title={body.get('title','?')}")
            else:
                fail("GET /v1/projects/{id}", f"status={r.status_code} body={r.text[:120]}")

        # ── GET /v1/templates (global master templates) ──────────────────────
        r = await client.get("/v1/templates")
        if r.status_code in (200, 404):
            ok("GET /v1/templates", f"status={r.status_code}")
        else:
            fail("GET /v1/templates", f"status={r.status_code} body={r.text[:120]}")

        # ── GET /v1/config (user config) ─────────────────────────────────────
        r = await client.get("/v1/config")
        if r.status_code in (200, 404):
            ok("GET /v1/config", f"status={r.status_code}")
        else:
            fail("GET /v1/config", f"status={r.status_code} body={r.text[:120]}")

        # ── DELETE /v1/projects/{id} ─────────────────────────────────────────
        if project_id:
            r = await client.delete(f"/v1/projects/{project_id}")
            if r.status_code in (200, 204):
                ok("DELETE /v1/projects/{id}", "project deleted")
            else:
                fail("DELETE /v1/projects/{id}", f"status={r.status_code} body={r.text[:120]}")

        # ── GET /v1/projects after delete (should be empty again) ────────────
        r = await client.get("/v1/projects")
        if r.status_code == 200:
            body = r.json()
            count = len(body) if isinstance(body, list) else body.get("total", "?")
            ok("GET /v1/projects (after delete)", f"total={count}")
        else:
            fail("GET /v1/projects (after delete)", f"status={r.status_code}")


async def main():
    print("\n" + "=" * 60)
    print(" LandPPT 沙箱集成测试 (mongomock in-memory MongoDB)")
    print("=" * 60)

    # Manually trigger startup
    print("\n[启动] 初始化应用...\n")
    await app.router.startup()

    print("\n[测试] 执行接口测试...\n")
    try:
        await run_tests()
    finally:
        await app.router.shutdown()

    print("\n" + "=" * 60)
    print(f" 结果：{len(PASS)} 通过 / {len(FAIL)} 失败")
    if FAIL:
        print(f" 失败项：{', '.join(FAIL)}")
    print("=" * 60 + "\n")
    return len(FAIL)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
