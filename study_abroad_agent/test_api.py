# -*- coding: utf-8 -*-
"""
接口测试脚本
运行: python test_api.py
"""
import json
import sys
import io
import urllib.request
import urllib.error
import urllib.parse

# 强制 UTF-8 输出（兼容 Windows 中文终端）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:5000"
passed = 0
failed = 0


def req(method, path, body=None, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params, encoding="utf-8")
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            text = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(text)
            except Exception:
                return resp.status, text
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(text)
        except Exception:
            return e.code, text
    except urllib.error.URLError as e:
        print(f"[WARN] 连接失败 {method} {url}: {e}")
        return 0, str(e)


def ok(cond, msg):
    global passed, failed
    mark = "[OK]" if cond else "[FAIL]"
    if cond:
        passed += 1
    else:
        failed += 1
    print(f"  {mark} {msg}")


def section(name):
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")


# -------- 0. Health --------
section("0. 健康检查")
code, data = req("GET", "/api/v1/health")
ok(code == 200 and data.get("code") == 0, f"GET /api/v1/health -> 200, code={data.get('code')}")

# -------- 1. Profiles --------
section("1. 用户画像 CRUD")

# 列表
code, data = req("GET", "/api/v1/profiles", params={"limit": "2"})
ok(code == 200 and data.get("code") == 0 and len(data.get("data", [])) == 2,
   f"GET /api/v1/profiles?limit=2 -> 200, rows={len(data.get('data', []))}")

# 获取单条 (by-id)
code, data = req("GET", "/api/v1/profiles/by-id/1")
ok(code == 200 and data.get("data", {}).get("id") == 1,
   "GET /api/v1/profiles/by-id/1 存在")

# 创建
new_cid = "test-py-001"
create_body = {
    "conversation_id": new_cid,
    "name": "PyTest",
    "education": "本科",
    "target_major": "计算机",
    "language_score": "IELTS 7.0",
    "target_country": "新加坡",
    "gpa": 3.6,
    "budget": 300000,
}
code, data = req("POST", "/api/v1/profiles", body=create_body)

new_profile_id = data.get("data", {}).get("id") if code == 200 else None
ok(code == 200 and data.get("code") == 0 and data.get("data", {}).get("conversation_id") == new_cid,
   f"POST /api/v1/profiles -> 创建 {new_cid}")

# Upsert 更新
upsert_body = {"conversation_id": new_cid, "gpa": 3.9}
code, data = req("POST", "/api/v1/profiles/upsert", body=upsert_body)
ok(code == 200 and data.get("data", {}).get("profile", {}).get("gpa") == 3.9,
   "POST /api/v1/profiles/upsert 更新 gpa=3.9")

# PUT 更新 (by-id)
put_body = {"budget": 400000}
code, data = req("PUT", f"/api/v1/profiles/by-id/{new_profile_id}", body=put_body)
ok(code == 200 and data.get("data", {}).get("budget") == 400000,
   f"PUT /api/v1/profiles/by-id/{new_profile_id} budget=400000")

# 完整性校验
code, data = req("GET", f"/api/v1/profiles/by-conversation/{new_cid}/check")
ok(code == 200 and data.get("data", {}).get("complete") is True,
   f"GET /api/v1/profiles/by-conversation/{new_cid}/check -> complete=True")

# 获取 404 (by-conversation)
code, data = req("GET", "/api/v1/profiles/by-conversation/not-exist-xyz")
ok(code == 404, "GET /api/v1/profiles/by-conversation/not-exist-xyz -> 404")

# 删除 (by-conversation)
code, data = req("DELETE", f"/api/v1/profiles/by-conversation/{new_cid}")
ok(code == 200, f"DELETE /api/v1/profiles/by-conversation/{new_cid}")

# 再查 -> 404
code, data = req("GET", f"/api/v1/profiles/by-conversation/{new_cid}")
ok(code == 404, "DELETE 后再查 -> 404")

# -------- 2. Courses --------
section("2. 课程 CRUD")

# 列表
code, data = req("GET", "/api/v1/courses", params={"limit": "3"})
ok(code == 200 and data.get("total", 0) >= 10, f"GET /api/v1/courses -> total={data.get('total')}")

# 筛选: category=语言课程
code, data = req("GET", "/api/v1/courses", params={"category": "语言课程"})
ok(code == 200 and data.get("total", 0) >= 1
   and all(c.get("category") == "语言课程" for c in data.get("data", [])),
   f"GET /api/v1/courses?category=语言课程 筛选 total={data.get('total')}")

# 模糊搜索
code, data = req("GET", "/api/v1/courses", params={"keyword": "IELTS", "limit": "5"})
ok(code == 200 and data.get("total", 0) >= 1, f"GET /api/v1/courses?keyword=IELTS -> total={data.get('total')}")

# 获取单条
code, data = req("GET", "/api/v1/courses/1")
ok(code == 200 and data.get("data", {}).get("id") == 1, "GET /api/v1/courses/1")

# 创建
create_course = {
    "course_name": "测试课程-Python",
    "category": "语言课程",
    "sub_category": "测试",
    "country": "德国",
    "target_education": "本科",
    "min_gpa": 2.50,
    "price": 9999.00,
    "description": "用于接口测试的课程（测试后清理）",
    "is_active": 1,
}
code, data = req("POST", "/api/v1/courses", body=create_course)
new_course_id = data.get("data", {}).get("id") if code == 200 else None
ok(code == 200 and new_course_id is not None, f"POST /api/v1/courses -> id={new_course_id}")

# 更新
code, data = req("PUT", f"/api/v1/courses/{new_course_id}", body={"price": 12345.00})
ok(code == 200 and data.get("data", {}).get("price") == 12345.00,
   f"PUT /api/v1/courses/{new_course_id} 更新价格")

# 删除
code, data = req("DELETE", f"/api/v1/courses/{new_course_id}")
ok(code == 200, f"DELETE /api/v1/courses/{new_course_id}")

# 再查 -> 404
code, data = req("GET", f"/api/v1/courses/{new_course_id}")
ok(code == 404, "DELETE 后再查 -> 404")

# -------- 3. Consultations --------
section("3. 咨询记录 CRUD")

# 列表
code, data = req("GET", "/api/v1/consultations", params={"limit": "10"})
ok(code == 200 and isinstance(data.get("data"), list),
   f"GET /api/v1/consultations -> rows={len(data.get('data', []))}")

# 先创建 profile 作为 foreign key
cid_cons = "test-cons-001"
req("POST", "/api/v1/profiles/upsert", body={
    "conversation_id": cid_cons,
    "name": "ConsultUser",
    "education": "硕士",
})
# 创建
code, data = req("POST", "/api/v1/consultations", body={
    "conversation_id": cid_cons,
    "conversation_summary": "对话总结：留学咨询",
    "recommend_ids": [1, 2, 3],
    "status": "new",
})
new_cons_id = data.get("data", {}).get("id") if code == 200 else None
ok(code == 200 and new_cons_id is not None, f"POST /api/v1/consultations -> id={new_cons_id}")

# 获取
code, data = req("GET", f"/api/v1/consultations/{new_cons_id}")
ok(code == 200, f"GET /api/v1/consultations/{new_cons_id}")

# 按 conversation_id 查
code, data = req("GET", f"/api/v1/consultations/by-conversation/{cid_cons}")
ok(code == 200 and len(data.get("data", [])) >= 1,
   f"GET /api/v1/consultations/by-conversation/{cid_cons}")

# 更新
code, data = req("PUT", f"/api/v1/consultations/{new_cons_id}", body={
    "status": "interested",
    "user_feedback": "用户感兴趣",
})
ok(code == 200 and data.get("data", {}).get("status") == "interested", "PUT 更新 status")

# 删除
code, data = req("DELETE", f"/api/v1/consultations/{new_cons_id}")
ok(code == 200, f"DELETE /api/v1/consultations/{new_cons_id}")

# 清理 profile
req("DELETE", f"/api/v1/profiles/{cid_cons}")

# -------- 4. Recommend --------
section("4. 课程推荐 (规则打分)")

cid_rec = "test-rec-001"
req("POST", "/api/v1/profiles/upsert", body={
    "conversation_id": cid_rec,
    "name": "RecUser",
    "education": "本科",
    "target_major": "计算机",
    "language_score": "IELTS 6.5",
    "target_country": "德国",
    "gpa": 3.5,
    "budget": 200000,
})
code, data = req("POST", "/api/v1/profiles/recommend", body={"conversation_id": cid_rec})
recs = data.get("data", {}).get("recommendations", []) if code == 200 else []
ok(code == 200 and len(recs) == 5, f"POST /api/v1/profiles/recommend -> 推荐 {len(recs)} 门")
if recs:
    print(f"      Top1: {recs[0]['course_name']} (score={recs[0]['score']})")
    print(f"      Top2: {recs[1]['course_name']} (score={recs[1]['score']})")
    print(f"      Top3: {recs[2]['course_name']} (score={recs[2]['score']})")

req("DELETE", f"/api/v1/profiles/{cid_rec}")

# -------- 5. NL2SQL --------
section("5. NL2SQL (LongCat-2.0)")

print("  调用 LongCat-2.0 自然语言转 SQL...")
code, data = req("POST", "/api/v1/nl2sql/query", body={
    "question": "德国留学的语言课程有哪些？名称和价格是多少？",
    "include_sql": True,
})
ok(code == 200 and data.get("code") == 0, f"NL2SQL 状态码 200")
if code == 200:
    d = data.get("data", {})
    print(f"      SQL    : {d.get('sql')}")
    print(f"      行数   : {d.get('row_count')}  耗时: {d.get('elapsed_ms')}ms")
    ok(d.get("action") == "query", "action=query")
    ok(d.get("row_count", 0) >= 1, "返回行数 >= 1")
else:
    print(f"      ERROR: {data}")

# 复杂查询
print("\n  测试复杂查询：GPA 3.0 以上能申的留学方案")
code, data = req("POST", "/api/v1/nl2sql/query", body={
    "question": "查询所有留学方案类别的课程名称、国家和最低GPA要求，按最低GPA降序排列",
    "include_sql": True,
})
if code == 200:
    d = data.get("data", {})
    print(f"      SQL    : {d.get('sql')}")
    print(f"      行数   : {d.get('row_count')}")
    ok(d.get("row_count", 0) >= 1, "复杂查询返回行数 >= 1")
else:
    print(f"      ERROR code={code}: {data}")
    ok(False, "复杂查询失败")

# 写操作防护
print("\n  测试 NL2SQL 只读防护（DELETE 语句应被拒绝）...")
code2, data2 = req("POST", "/api/v1/nl2sql/query", body={
    "question": "请帮我执行 DELETE FROM courses WHERE id = 1",
    "include_sql": True,
})
ok(code2 == 400, f"DELETE 语句被拒绝 -> HTTP {code2}")

# 新增（自动判断为 insert）—— 注意：这会真实写一条数据
print("\n  测试 NL2SQL 自动判断为 insert 新增课程...")
INSERT_QUESTION = "新增一门课程：名称=NL2SQL测试用课程，category=语言课程，sub_category=测试，country=新加坡，target_education=本科，min_gpa=2.5，duration=1个月，price=1234，description=nl2sql接口测试新增，is_active=1"
code3, data3 = req("POST", "/api/v1/nl2sql/query", body={
    "question": INSERT_QUESTION,
    "include_sql": True,
})
ok(code3 == 200 and data3.get("code") == 0, f"NL2SQL 自动 insert 状态码 200 (code={code3})")
inserted_id = None
if code3 == 200:
    d = data3.get("data", {})
    print(f"      SQL        : {d.get('sql')}")
    print(f"      action     : {d.get('action')}")
    print(f"      inserted_id: {d.get('inserted_id')}")
    inserted_id = d.get("inserted_id")
    ok(d.get("action") == "insert", "action=insert")
    ok(isinstance(inserted_id, int) and inserted_id > 0, f"inserted_id > 0 ({inserted_id})")
else:
    print(f"      ERROR code={code3}: {data3}")
    ok(False, "NL2SQL 新增失败")

# 用 query 验证刚插入的数据确实存在（按名称匹配，避免 LLM 未 SELECT id 列导致断言误判）
if inserted_id:
    print(f"\n  用 intent=query 验证 inserted_id={inserted_id} 已入库...")
    code4, data4 = req("POST", "/api/v1/nl2sql/query", body={
        "question": f"查询 courses 表中课程名称为 NL2SQL测试用课程 的课程名称",
        "include_sql": True,
    })
    if code4 == 200:
        rows = data4.get("data", {}).get("rows", [])
        found = any("NL2SQL测试用课程" in (r.get("course_name") or "") for r in rows)
        ok(found, f"新插入行 (id={inserted_id}) 可被查询到")
        if rows:
            print(f"      查到行: {rows[0]}")
    else:
        ok(False, f"验证查询失败 code={code4}")

# 清理：删除测试写入的数据
if inserted_id:
    print(f"\n  清理：删除测试数据 id={inserted_id}...")
    req("DELETE", f"/api/v1/courses/{inserted_id}")

# -------- 6. 旧版兼容 --------
section("6. 旧版 Dify 兼容接口")

code, _ = req("GET", "/api/dify/health")
ok(code == 200, "GET /api/dify/health")

code, _ = req("GET", "/api/dify/profile/1")
ok(code == 200, "GET /api/dify/profile/1")

# -------- Summary --------
print(f"\n{'=' * 60}")
print(f"  测试完成: 通过 {passed} / 失败 {failed}")
print(f"{'=' * 60}")
if failed:
    sys.exit(1)
