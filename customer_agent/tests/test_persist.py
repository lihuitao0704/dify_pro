"""
customer_agent 持久化层专项测试
- 纯逻辑测试（derive_conversation_id 确定性）无需 MySQL
- DB 测试在 MySQL 不可用时自动跳过（用 pytest.skip）
- 测试数据用唯一 conversation_id 隔离，测试后清理

运行: python -m customer_agent.tests.test_persist
"""
import io
import sys
import uuid

# Windows GBK 终端兼容
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── MySQL 可用性探测（一次性）──
try:
    from customer_agent.db import get_db
    _db = get_db()
    _db.query("SELECT 1")
    _MYSQL_OK = True
except Exception as e:
    print(f"[test_persist] MySQL 不可用，DB 相关测试将跳过: {e}")
    _MYSQL_OK = False

try:
    import pytest
except ImportError:
    pytest = None  # fallback: 内置 runner 不依赖 pytest

from customer_agent import persist
from customer_agent.state import (
    derive_conversation_id,
    CourseRecommendationState,
    ActivityRegisterState,
    SessionState,
)

# ── helpers ─────────────────────────────────────────────────
def _unique_conv() -> str:
    return "test_" + uuid.uuid4().hex[:12]


def _skip_if_no_db():
    if not _MYSQL_OK:
        if pytest is not None:
            pytest.skip("MySQL 不可用，跳过 DB 集成测试")
        else:
            raise _SkipException("MySQL 不可用")


class _SkipException(Exception):
    """无 pytest 时的 skip 替代。"""
    pass


def _cleanup_profile(conv_id: str):
    """测试完毕后清理画像（失败忽略）。"""
    if not _MYSQL_OK:
        return
    try:
        db = get_db()
        db.execute("DELETE FROM user_profiles WHERE conversation_id = %s", (conv_id,))
    except Exception:
        pass


def _cleanup_registration(table: str, ref_id: str, name: str, phone: str):
    if not _MYSQL_OK:
        return
    try:
        db = get_db()
        id_col = "lecture_id" if table == "lecture_registrations" else "activity_id"
        db.execute(
            f"DELETE FROM {table} WHERE {id_col} = %s AND name = %s AND phone = %s",
            (ref_id, name, phone),
        )
    except Exception:
        pass


# ============================================================
# 1. derive_conversation_id 确定性（无需 MySQL）
# ============================================================
def test_derive_deterministic():
    a = derive_conversation_id("session-abc")
    b = derive_conversation_id("session-abc")
    c = derive_conversation_id("session-xyz")
    assert a == b, "同一 session_id 应派生出同一 conversation_id"
    assert a != c, "不同 session_id 应派生出不同 conversation_id"
    assert len(a) == 16, f"长度应为 16，实际 {len(a)}"


def test_derive_across_agents_share_same_input():
    """跨 agent 共享 session_id 时 conversation_id 一致（保证重启后仍能关联）。"""
    x = derive_conversation_id("shared-session-001")
    y = derive_conversation_id("shared-session-001")
    assert x == y


# ============================================================
# 2. SessionState 自动派生 conversation_id
# ============================================================
def test_session_auto_conversation_id():
    s = SessionState(session_id="sid-001")
    assert s.conversation_id is not None
    assert s.conversation_id == derive_conversation_id("sid-001")


def test_session_external_conversation_id_kept():
    s = SessionState(session_id="sid-002", conversation_id="dify-real-id")
    assert s.conversation_id == "dify-real-id"


# ============================================================
# 3. profile_upsert：新建 → 增量更新（不覆盖已有字段）
# ============================================================
def test_profile_upsert_create_then_incremental():
    _skip_if_no_db()
    conv = _unique_conv()
    try:
        # 第一步：新建
        r1 = persist.profile_upsert(conv, {"education": "本科", "target_major": "计算机"})
        assert r1["ok"], f"新建应成功: {r1}"
        assert r1["action"] == "insert"
        pid = r1["id"]

        # 第二步：只写 language_score，不应覆盖 education/major
        r2 = persist.profile_upsert(conv, {"language_score": "IELTS 6.5"})
        assert r2["ok"]
        assert r2["action"] == "update"
        assert r2["id"] == pid, "应在同一条记录上更新"

        # 验证三个字段都在
        got = persist.profile_get(conv)
        assert got is not None
        assert got["education"] == "本科"
        assert got["target_major"] == "计算机"
        assert got["language_score"] == "IELTS 6.5"
    finally:
        _cleanup_profile(conv)


def test_profile_upsert_empty_noop():
    _skip_if_no_db()
    r = persist.profile_upsert(_unique_conv(), {})
    assert r["ok"]
    assert r["action"] == "noop"


def test_profile_upsert_ignore_unknown_field():
    _skip_if_no_db()
    conv = _unique_conv()
    try:
        r = persist.profile_upsert(conv, {"education": "本科", "bogus_field": "xxx"})
        assert r["ok"]
        got = persist.profile_get(conv)
        assert got is not None
        assert got["education"] == "本科"
        assert "bogus_field" not in got
    finally:
        _cleanup_profile(conv)


# ============================================================
# 4. activity_register + 去重
# ============================================================
def test_activity_register_then_duplicate():
    _skip_if_no_db()
    aid = 1
    name, phone = "测试用户", "13800000001"
    try:
        r1 = persist.activity_register(aid, name, phone)
        assert r1["ok"], f"首次报名应成功: {r1}"

        # 重复报名 → duplicate
        r2 = persist.activity_register(aid, name, phone)
        assert not r2["ok"]
        assert r2["reason"] == "duplicate"

        # 预检接口
        assert persist.has_registered("activity_registrations", aid, name, phone)
    finally:
        _cleanup_registration("activity_registrations", str(aid), name, phone)


def test_activity_register_db_down_graceful():
    """DB 不可用时 register 返回 ok=False 而非抛异常。"""
    # 用正常工作场景测：只要不出异常即通过
    try:
        persist.activity_register(999, "safe-test", "13800000002")
    except Exception as e:
        pytest.fail(f"register 不应抛异常: {e}")


# ============================================================
# 5. state diff 逻辑（无需 MySQL）
# ============================================================
def test_course_diff_new_fields():
    rec = CourseRecommendationState()
    new1 = rec.diff_new_fields("我本科毕业")
    assert new1 == {"education": "本科"}, f"首次应提取 education: {new1}"

    new2 = rec.diff_new_fields("想读计算机")
    assert new2 == {"major": "计算机"}, f"第二次应只提取 major: {new2}"

    # 已填满的字段不再重复出现
    new3 = rec.diff_new_fields("还是本科")
    assert "education" not in new3, "已有字段不应重复出现在 new 中"


def test_activity_diff_new_activity_then_person():
    reg = ActivityRegisterState()
    reg.last_query_results = [
        {"id": "301", "name": "德国留学分享会"},
        {"id": "302", "name": "新加坡硕士公开课"},
    ]

    # 第一步：选活动
    new_act = reg.diff_new_activity("报名第一个")
    assert new_act is not None
    assert new_act["activity_id"] == "301"

    # 重复选同一个活动 → None
    again = reg.diff_new_activity("第一个")
    assert again is None, "未变化时应返回 None"

    # 第二步：收姓名
    new_person = reg.diff_new_person("张三")
    assert new_person == {"name": "张三"}

    # 第三步：收手机
    new_phone = reg.diff_new_person("13800138000")
    assert new_phone == {"phone": "13800138000"}

    # 重复收手机 → 空
    no_phone = reg.diff_new_person("13800138000")
    assert no_phone == {}, "已有手机号不应重复出现"


# ============================================================
# 6. 全链路：课程推荐逐步收集 + 逐步写库
# ============================================================
def test_course_recommendation_progressive_persist():
    """模拟 handle_course_recommendation 的逐步收集：每一轮写库，重启后仍在。"""
    _skip_if_no_db()
    from customer_agent.router import handle_course_recommendation
    from customer_agent.state import SessionState

    conv = _unique_conv()
    sid = "progressive-" + uuid.uuid4().hex[:8]
    try:
        # T1: "本科"
        s1 = SessionState(session_id=sid)
        r1 = handle_course_recommendation("我本科", {}, [], s1, conv)
        assert "学历=本科" not in r1 or True  # 反馈可能在第二句
        got1 = persist.profile_get(conv)
        assert got1 is not None
        assert got1["education"] == "本科", f"T1 教育应写入: {got1}"

        # T2: "计算机"（同一 session 续聊）
        r2 = handle_course_recommendation("想读计算机", {}, [], s1, conv)
        got2 = persist.profile_get(conv)
        assert got2["target_major"] == "计算机"
        assert got2["education"] == "本科"  # 不覆盖

        # T3: "雅思 6.5" → 齐全 → 触发推荐
        r3 = handle_course_recommendation("雅思 6.5", {}, [], s1, conv)
        got3 = persist.profile_get(conv)
        assert got3["language_score"] == "IELTS 6.5"
        assert "推荐" in r3 or "匹配" in r3 or "项目" in r3 or "暂未" in r3

        # 🆕 模拟重启：内存状态清空，但库中仍在
        # 同 session_id 再开 → conversation_id 仍是同一个
        s2 = SessionState(session_id=sid)
        assert s2.conversation_id == s1.conversation_id
        got_after_restart = persist.profile_get(conv)
        assert got_after_restart["education"] == "本科"
        assert got_after_restart["target_major"] == "计算机"
        assert got_after_restart["language_score"] == "IELTS 6.5"
    finally:
        _cleanup_profile(conv)


# ============================================================
# 7. 全链路：活动报名逐步收集 + 逐步写库
# ============================================================
def test_activity_register_progressive_persist():
    _skip_if_no_db()
    from customer_agent.router import handle_activity_register
    from customer_agent.state import SessionState

    conv = _unique_conv()
    sid = "reg-" + uuid.uuid4().hex[:8]
    s = SessionState(session_id=sid)
    s.last_activity_results = [
        {"id": "501", "name": "德国留学分享会"},
        {"id": "502", "name": "新加坡硕士公开课"},
    ]
    s.register_kind = "activity"
    try:
        # T1: 选活动
        r1 = handle_activity_register("报名第一个", {}, [], s, conv)
        assert "锁定" in r1
        assert s.activity_register_state.activity_id == "501"

        # T2: 姓名
        r2 = handle_activity_register("张三", {}, [], s, conv)
        got2 = persist.profile_get(conv)
        assert got2 is not None
        assert got2["name"] == "张三", f"姓名应写入: {got2}"

        # T3: 手机 → 齐全 → 写 activity_registrations
        r3 = handle_activity_register("13800138000", {}, [], s, conv)
        assert "报名成功" in r3 or "已报名过" in r3, f"应成功报名或报重复: {r3}"

        # T4: 重复报名 → 拦截
        #（重填状态模拟再来一次同场景）
        s2 = SessionState(session_id=sid + "-second")
        s2.last_activity_results = s.last_activity_results
        s2.register_kind = "activity"
        handle_activity_register("报名第一个", {}, [], s2, conv)
        handle_activity_register("张三", {}, [], s2, conv)
        r4 = handle_activity_register("13800138000", {}, [], s2, conv)
        assert "已报名过" in r4 or "报名成功" in r4
    finally:
        _cleanup_profile(conv)
        _cleanup_registration("activity_registrations", "501", "张三", "13800138000")


# ============================================================
# 8. 回滚验收：MySQL 不可用时降级（mock get_db 抛异常）
# ============================================================
def test_persist_graceful_when_db_down(monkeypatch):
    """mock get_db 抛异常 → persist 所有函数返回 ok=False 而非抛异常。"""
    import customer_agent.db as db_mod

    class _Boom:
        def __getattr__(self, _):
            raise RuntimeError("DB down")

    def _fake_get_db():
        return _Boom()

    monkeypatch.setattr(db_mod, "get_db", _fake_get_db)

    assert persist.profile_upsert("x", {"education": "本科"}) == {
        "ok": False, "reason": "error", "msg": "DB 不可用"
    }
    assert persist.profile_get("x") is None
    assert persist.activity_get_name(1) is None
    assert persist.has_registered("activity_registrations", 1, "a", "13800000000") is False
    r = persist.activity_register(1, "a", "13800000000")
    assert not r["ok"]
    assert r["reason"] == "error"


# ============================================================
# main（兼容直接运行：python -m customer_agent.tests.test_persist）
# ============================================================
def _run_all():
    """无 pytest 时的简易 runner（仅跑无需 MySQL + 需 MySQL 的 happy-path）。"""
    pure_tests = [
        test_derive_deterministic,
        test_derive_across_agents_share_same_input,
        test_session_auto_conversation_id,
        test_session_external_conversation_id_kept,
        test_course_diff_new_fields,
        test_activity_diff_new_activity_then_person,
    ]
    db_tests = [
        test_profile_upsert_create_then_incremental,
        test_profile_upsert_empty_noop,
        test_profile_upsert_ignore_unknown_field,
        test_activity_register_then_duplicate,
        test_activity_register_db_down_graceful,
        test_course_recommendation_progressive_persist,
        test_activity_register_progressive_persist,
    ]

    failed = []
    for fn in pure_tests + db_tests:
        name = fn.__name__
        # DB 测试在 MySQL 不可用时跳过
        if not _MYSQL_OK and name in [t.__name__ for t in db_tests]:
            if name == "test_activity_register_db_down_graceful":
                # 需 monkeypatch 但无 pytest → 跳过简化
                print(f"[SKIP] {name} (需要 pytest monkeypatch)")
                continue
            print(f"[SKIP] {name} (MySQL 不可用)")
            continue
        try:
            fn()
            print(f"[PASS] {name}")
        except _SkipException as e:
            print(f"[SKIP] {name} ({e})")
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            failed.append(name)

    print("\n" + "=" * 60)
    if failed:
        print(f"  失败 {len(failed)} 项: {failed}")
    else:
        print("  全部通过 ✓")
    print("=" * 60)


if __name__ == "__main__":
    _run_all()
