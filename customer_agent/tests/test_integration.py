"""
集成验证（确定性，主要验证状态机+API结构，最小化对慢 LLM 的依赖）
直接运行: python -m customer_agent.tests.test_integration
"""
import sys
import io
# Windows GBK 终端兼容
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from fastapi.testclient import TestClient
from customer_agent.main import app
from customer_agent.state import get_session

c = TestClient(app)
results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    flag = "PASS" if cond else "FAIL"
    print(f"[{flag}] {name} {('- ' + detail) if detail else ''}")


# ── 1. 基础健康 ───────────────────────────────────────────────
check("GET /health", c.get("/health").status_code == 200)

r = c.get("/admin/kb-status")
check("KB loaded", r.json()["loaded"] and r.json()["chunks"] > 0,
      f"chunks={r.json()['chunks']}")

r = c.get("/admin/project-status")
check("project-status Phase3",
      r.json()["phase"] == "Phase 3" and r.json()["overall_pct"] > 0,
      f"overall={r.json()['overall_pct']}%")

# ── 2. session 记忆：同 session_id 调用多次后历史累积 ─────────
sid = "smoke-session"
c.post("/chat", json={"message": "你好", "session_id": sid})
c.post("/chat", json={"message": "德国留学", "session_id": sid})
c.post("/chat", json={"message": "推荐项目", "session_id": sid})
sess = get_session(sid)
check("session 记忆累积(6条历史)", len(sess.history) == 6,
      f"history_len={len(sess.history)}")

# ── 3. 意图锁定 + 续写：推荐流程逐步追问 ─────────────────────
sid2 = "smoke-recommend"
r1 = c.post("/chat", json={"message": "帮我推荐留学", "session_id": sid2})
sess2 = get_session(sid2)
check("推荐流程: 第1轮锁定",
      sess2.has_active_flow()
      and sess2.current_intent == "course_recommendation",
      f"locked={sess2.current_intent}")

r2 = c.post("/chat", json={"message": "本科学历", "session_id": sid2})
sess2 = get_session(sid2)
check("推荐流程: 第2轮记住学历",
      sess2.course_recommendation_state
      and sess2.course_recommendation_state.education == "本科",
      f"ed={sess2.course_recommendation_state.education if sess2.course_recommendation_state else None}")

r3 = c.post("/chat", json={"message": "计算机专业", "session_id": sid2})
r4 = c.post("/chat", json={"message": "雅思6.5", "session_id": sid2})
sess2 = get_session(sid2)
check("推荐流程: 收集齐后解锁",
      not sess2.has_active_flow(),
      f"locked={sess2.current_intent}")

# ── 4. 全部 /api/v1/* CRUD 返回正确结构 ─────────────────────
r = c.get("/api/v1/courses", params={"limit": 1})
check("courses 结构", r.json().get("code") == 0 and "data" in r.json())

r = c.get("/api/v1/events/lectures", params={"limit": 1})
check("lectures 结构", r.json().get("code") == 0 and "data" in r.json())

r = c.get("/api/v1/events/activities", params={"limit": 1})
check("activities 结构", r.json().get("code") == 0 and "data" in r.json())

r = c.get("/api/v1/profiles", params={"limit": 1})
check("profiles 结构", r.json().get("code") == 0 and "data" in r.json())

r = c.get("/api/v1/consultations", params={"limit": 1})
check("consultations 结构", r.json().get("code") == 0 and "data" in r.json())

# ── 5. 创建后查询一致性 ─────────────────────────────────────
r = c.post("/api/v1/courses", json={
    "course_name": "_smoke_test", "category": "语言课程",
    "country": "德国", "price": 1})
check("course 创建", r.json().get("code") == 0 and r.json().get("data"))
new_id = r.json()["data"]["id"]
r = c.get(f"/api/v1/courses/{new_id}")
check("course 按id查询",
      r.status_code == 200 and r.json()["data"]["id"] == new_id)
c.delete(f"/api/v1/courses/{new_id}")

# ── 6. profile upsert 一致性 ─────────────────────────────────
r = c.post("/api/v1/profiles/upsert",
           json={"conversation_id": "_smoke_ctx", "name": "烟雾测",
                 "education": "本科"})
check("profile upsert", r.json().get("code") == 0)
r = c.get("/api/v1/profiles/by-conversation/_smoke_ctx")
check("profile 查询",
      r.status_code == 200 and (r.json().get("total") or 0) >= 1)

# ── 7. 活动查询 NL2SQL 降级路径（LLM 失败时直查 DB）────────
r = c.post("/chat", json={"message": "最近有什么讲座"})
check("活动查询(降级路径可用)",
      r.status_code == 200 and r.json().get("reply"))

# ── 汇总 ─────────────────────────────────────────────────
fails = [item for item in results if not item[1]]
print("\n" + "=" * 55)
print(f"总计: {len(results)} 项, 通过: {len(results)-len(fails)}, 失败: {len(fails)}")
if fails:
    print("--- 失败项 ---")
    for f in fails:
        print(" ", f[0], "-", f[2])
print("=" * 55)

# 清理烟雾测试数据
from customer_agent.db import get_db
db = get_db()
db.execute("DELETE FROM courses WHERE course_name = %s", ("_smoke_test",))
db.execute("DELETE FROM user_profiles WHERE conversation_id = %s",
           ("_smoke_ctx",))
