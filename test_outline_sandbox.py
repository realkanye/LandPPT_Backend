"""
大纲生成任务测试 — mock LLM，走完整数据库 + 业务逻辑链路
"""
import os, sys, asyncio, json
from unittest.mock import AsyncMock, patch

# ── 环境 ──────────────────────────────────────────────────────────────────────
os.environ.setdefault("MONGODB_URL", "mock://localhost/landppt")
os.environ.setdefault("SECRET_KEY", "test-secret-key-sandbox")
os.environ.setdefault("DISABLE_AUTH", "true")
os.environ.setdefault("CACHE_BACKEND", "memory")
os.environ.setdefault("DEFAULT_AI_PROVIDER", "openai")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# ── patch mongomock ───────────────────────────────────────────────────────────
import mongomock.database as _mdb
_orig = _mdb.Database.list_collection_names
def _p(self, session=None, **kw): return _orig(self, session=session)
_mdb.Database.list_collection_names = _p

# ── patch database.py → AsyncMongoMockClient ─────────────────────────────────
import mongomock_motor
import landppt.database.database as _db_module

async def _mock_init_db():
    from beanie import init_beanie
    from landppt.database.mongo_models import (
        ProjectDocument, SlideDocument, ProjectVersionDocument,
        GlobalMasterTemplateDocument, CounterDocument, UserConfigDocument,
    )
    client = mongomock_motor.AsyncMongoMockClient()
    await init_beanie(
        database=client["landppt"],
        document_models=[
            ProjectDocument, SlideDocument, ProjectVersionDocument,
            GlobalMasterTemplateDocument, CounterDocument, UserConfigDocument,
        ],
    )

_db_module.init_db = _mock_init_db

# ── 模拟 LLM 返回的大纲 JSON ──────────────────────────────────────────────────
MOCK_OUTLINE_JSON = json.dumps({
    "title": "MongoDB 数据库迁移实践",
    "slides": [
        {
            "id": 1, "type": "title",
            "title": "MongoDB 数据库迁移实践",
            "subtitle": "从 PostgreSQL 到 MongoDB 的完整迁移方案",
            "content": ""
        },
        {
            "id": 2, "type": "content",
            "title": "迁移背景与目标",
            "content": "• 原系统基于 PostgreSQL + SQLAlchemy\n• 目标：切换至 MongoDB + Beanie ODM\n• 提升文档存储灵活性与横向扩展能力"
        },
        {
            "id": 3, "type": "content",
            "title": "核心迁移步骤",
            "content": "• 数据模型重新设计（文档模型）\n• 代码层全量切换（repositories / service）\n• 兼容层保障平滑过渡"
        },
        {
            "id": 4, "type": "content",
            "title": "测试与验证",
            "content": "• 单元测试：mongomock 内存数据库\n• 集成测试：FastAPI + httpx\n• 13/13 接口全部通过"
        },
        {
            "id": 5, "type": "thankyou",
            "title": "谢谢",
            "subtitle": "感谢聆听",
            "content": ""
        }
    ],
    "metadata": {"total_slides": 5}
}, ensure_ascii=False)


# ── LLM 响应 mock 对象 ────────────────────────────────────────────────────────
class _FakeLLMResponse:
    def __init__(self):
        self.content = MOCK_OUTLINE_JSON
        self.model = "gpt-4o-mock"
        self.usage = type("U", (), {"total_tokens": 512})()


# ── 从 app 导入 ───────────────────────────────────────────────────────────────
from landppt.main_api import app
import httpx
from httpx import ASGITransport


async def main():
    print("\n" + "=" * 60)
    print(" 大纲生成任务测试（LLM mock）")
    print("=" * 60)

    # 启动应用（初始化 DB、导入模板）
    print("\n[1] 启动应用 ...\n")
    await app.router.startup()

    # patch LLM 调用：委托链最终落在 EnhancedPPTService._text_completion_for_role
    target = "landppt.services.enhanced_ppt_service.EnhancedPPTService._text_completion_for_role"

    with patch(target, new=AsyncMock(return_value=_FakeLLMResponse())):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            timeout=30,
        ) as client:

            # ── 步骤 1：提交大纲生成 ──────────────────────────────────────────
            print("[2] POST /outline/generate\n")
            payload = {
                "scenario": "business",
                "topic":    "MongoDB 数据库迁移实践",
                "requirements": "包含迁移背景、步骤、测试验证三个核心部分，共5页",
                "language": "zh",
                "network_mode": False,
            }
            r = await client.post("/outline/generate", json=payload)
            print(f"    HTTP {r.status_code}")

            if r.status_code == 200:
                body = r.json()
                outline = body.get("outline", {})
                slides  = outline.get("slides", [])
                print(f"    ✓ 生成成功")
                print(f"    标题：{outline.get('title', '?')}")
                print(f"    幻灯片数：{len(slides)}")
                print()
                for i, s in enumerate(slides, 1):
                    title   = s.get("title", "?")
                    stype   = s.get("type", "?")
                    content = (s.get("content") or "").replace("\n", " ")[:60]
                    print(f"    [{i}] [{stype:8}] {title}")
                    if content:
                        print(f"         {content}")

                # ── 步骤 2：用同一 topic 通过 v1 创建完整项目任务 ─────────────
                print(f"\n[3] POST /v1/presentations（以同一 topic 提交异步任务）\n")
                r2 = await client.post("/v1/presentations", json={
                    "title":    "MongoDB 迁移 PPT",
                    "scenario": "business",
                    "topic":    "MongoDB 数据库迁移实践",
                })
                print(f"    HTTP {r2.status_code}")
                if r2.status_code in (200, 201, 202):
                    b2 = r2.json()
                    job_id     = b2.get("job_id")
                    project_id = b2.get("project_id")
                    print(f"    ✓ 任务已提交")
                    print(f"    job_id     : {job_id}")
                    print(f"    project_id : {project_id}")

                    # ── 步骤 3：查询任务状态 ───────────────────────────────────
                    print(f"\n[4] GET /v1/jobs/{job_id}\n")
                    r3 = await client.get(f"/v1/jobs/{job_id}")
                    print(f"    HTTP {r3.status_code}")
                    if r3.status_code == 200:
                        b3 = r3.json()
                        print(f"    ✓ 任务状态: {b3.get('status')}")
                        print(f"    进度:       {b3.get('progress', 0):.0%}")
                        print(f"    消息:       {b3.get('message', '-')[:60]}")
                else:
                    print(f"    ✗ 失败: {r2.text[:200]}")

            else:
                print(f"    ✗ 失败: {r.text[:300]}")

    await app.router.shutdown()
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
