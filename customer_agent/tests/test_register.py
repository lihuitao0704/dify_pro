"""
activity_register 多轮收集专项测试
验证 ActivityRegisterState + handle_activity_register 的端到端流程。

直接运行: python -m customer_agent.tests.test_register
"""
import sys
import io

# Windows GBK 终端兼容
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ============================================================
# 1. ActivityRegisterState 单元测试
# ============================================================
def test_register_state():
    from customer_agent.state import ActivityRegisterState

    print("\n" + "=" * 60)
    print("  ActivityRegisterState 单元测试")
    print("=" * 60)

    # ── 测试 is_ready ──
    reg = ActivityRegisterState()
    assert not reg.is_ready(), "空状态不应 ready"

    reg.name = "张三"
    assert not reg.is_ready(), "仅姓名不应 ready"

    reg.phone = "13800138000"
    assert not reg.is_ready(), "姓名+手机但无活动，不应 ready"

    reg.activity_id = "101"
    assert reg.is_ready(), "姓名+手机+activity_id 后应 ready"

    # ── 测试 next_missing_field 顺序 ──
    reg2 = ActivityRegisterState()
    assert reg2.next_missing_field() == "activity_select"
    reg2.activity_id = "101"
    assert reg2.next_missing_field() == "name"
    reg2.name = "李四"
    assert reg2.next_missing_field() == "phone"
    reg2.phone = "13900139000"
    assert reg2.next_missing_field() is None

    # ── 测试 fill_from_message ──
    reg3 = ActivityRegisterState()
    reg3.fill_from_message("我叫王五，手机 13700137000")
    assert reg3.name == "王五", f"姓名识别错误: {reg3.name}"
    assert reg3.phone == "13700137000", f"手机识别错误: {reg3.phone}"

    reg4 = ActivityRegisterState()
    reg4.fill_from_message("赵六 13600136000")
    assert reg4.name == "赵六", f"独立姓名识别错误: {reg4.name}"
    assert reg4.phone == "13600136000", f"独立手机识别错误: {reg4.phone}"

    # ── 测试 resolve_index ──
    reg5 = ActivityRegisterState()
    reg5.last_query_results = [
        {"id": "201", "name": "德国留学分享会"},
        {"id": "202", "name": "新加坡硕士公开课"},
        {"id": "203", "name": "雅思备考讲座"},
    ]
    assert reg5.resolve_index("报名第一个")
    assert reg5.activity_id == "201", f"activity_id 错误: {reg5.activity_id}"
    assert reg5.activity_name == "德国留学分享会"

    reg6 = ActivityRegisterState()
    reg6.last_query_results = reg5.last_query_results
    assert reg6.resolve_index("我要第2个")
    assert reg6.activity_id == "202"

    reg7 = ActivityRegisterState()
    reg7.last_query_results = reg5.last_query_results
    assert not reg7.resolve_index("随便看看"), "不匹配时应返回 False"

    # ── 测试 resolve_name ──
    reg8 = ActivityRegisterState()
    reg8.last_query_results = reg5.last_query_results
    assert reg8.resolve_name("报名新加坡硕士公开课")
    assert reg8.activity_id == "202"
    assert reg8.activity_name == "新加坡硕士公开课"

    print("[PASS] ActivityRegisterState 单元测试全部通过 ✓")


# ============================================================
# 2. 端到端多轮对话测试（模拟 handle_activity_register 调用链）
# ============================================================
def test_register_e2e():
    """
    模拟完整的多轮报名对话:
      T1: 用户查活动 → 展示活动列表，缓存
      T2: 报名第一个 → lock + 发现缺姓名/手机 → 追问姓名
      T3: 张三 → 缺手机 → 追问手机
      T4: 13800138000 → 齐全 → 调 event_register
    """
    from customer_agent.state import SessionState, ActivityRegisterState

    print("\n" + "=" * 60)
    print("  activity_register 端到端多轮对话测试")
    print("=" * 60)

    sess = SessionState(session_id="test-001")
    sess.register_kind = "activity"   # 测试活动报名（非讲座）

    # ── T1: 模拟查活动后缓存 3 条活动结果 ──
    sess.last_activity_results = [
        {"id": "101", "name": "德国留学分享会", "date": "2026-07-18"},
        {"id": "102", "name": "新加坡硕士公开课", "date": "2026-07-20"},
        {"id": "103", "name": "雅思备考讲座", "date": "2026-07-22"},
    ]
    print(f"\n[T1] 查活动 → 缓存 {len(sess.last_activity_results)} 条结果")
    assert len(sess.last_activity_results) == 3
    assert not sess.has_active_flow(), "T1 查完活动后不应有活跃 flow"

    # ── T2: 用户说"报名第一个"──
    from customer_agent.router import handle_activity_register
    reply2 = handle_activity_register(
        "报名第一个", {}, sess.get_context(), sess, "0"
    )
    print(f"\n[T2] 用户: '报名第一个'")
    print(f"     回复: {reply2}")
    assert sess.has_active_flow(), "T2 应进入 activity_register 流程"
    assert sess.current_intent == "activity_register"
    reg = sess.activity_register_state
    assert reg is not None
    assert reg.activity_id == "101", f"应选中第一个活动 id=101, 实际={reg.activity_id}"
    assert reg.name == "", "T2 不应识别到姓名"
    assert not reg.is_ready(), "T2 不应 ready"
    assert "怎么称呼" in reply2 or "姓名" in reply2, "T2 应追问姓名"

    # ── T3: 用户说"张三"──
    reply3 = handle_activity_register(
        "张三", {}, sess.get_context(), sess, "0"
    )
    print(f"\n[T3] 用户: '张三'")
    print(f"     回复: {reply3}")
    assert sess.has_active_flow(), "T3 仍应锁定流程"
    assert reg.name == "张三", f"姓名应=张三, 实际={reg.name}"
    assert not reg.is_ready(), "T3 仍不应 ready"
    assert "手机" in reply3 or "联系" in reply3, "T3 应追问手机号"

    # ── T4: 用户说手机号 → 齐全 → 调 event_register ──
    # （因为 event_register 真实调接口可能失败，这里只验证 is_ready 状态和状态清空）
    reg.phone = "13800138000"   # 模拟收集到手机
    assert reg.is_ready(), "T4 参数齐全后 is_ready 应为 True"

    # 直接调用 event_register，若接口不可用也验证解锁逻辑
    reply4 = handle_activity_register(
        "13800138000", {}, sess.get_context(), sess, "0"
    )
    print(f"\n[T4] 用户: '13800138000'")
    print(f"     回复: {reply4}")
    assert not sess.has_active_flow(), "T4 完成后应解锁"
    assert sess.current_intent is None, "T4 完成后 current_intent 应为 None"
    assert sess.activity_register_state is None, "T4 完成后状态应清空"

    print("\n[PASS] activity_register 端到端多轮对话测试通过 ✓")


# ============================================================
# 3. SessionState.has_active_flow 集成测试
# ============================================================
def test_active_flow():
    from customer_agent.state import SessionState

    print("\n" + "=" * 60)
    print("  SessionState.has_active_flow 集成测试")
    print("=" * 60)

    sess = SessionState(session_id="test-002")
    assert not sess.has_active_flow(), "初始状态无活跃 flow"

    # 锁 course_recommendation
    sess.lock_intent("course_recommendation")
    assert sess.has_active_flow(), "锁定 course_recommendation 后应有活跃 flow"
    sess.unlock_intent()
    assert not sess.has_active_flow(), "解锁后应无活跃 flow"

    # 锁 activity_register
    sess.lock_intent("activity_register")
    assert sess.has_active_flow(), "锁定 activity_register 后应有活跃 flow"

    # 清除子状态但保留锁定意图（异常场景）
    sess.activity_register_state = None
    assert not sess.has_active_flow(), "清除子状态后应无活跃 flow"

    # 锁 chat（非业务流程）
    sess.lock_intent("chat")
    # lock_intent 对 chat 不创建子状态
    # has_active_flow 只识别 course_recommendation / activity_register
    assert not sess.has_active_flow(), "锁定 chat 不产生活跃 flow"
    sess.unlock_intent()

    print("[PASS] SessionState.has_active_flow 集成测试通过 ✓")


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  activity_register 专项测试套件")
    print("=" * 60)

    test_register_state()
    test_active_flow()
    test_register_e2e()

    print("\n" + "=" * 60)
    print("  所有测试全部通过 ✓")
    print("=" * 60)
