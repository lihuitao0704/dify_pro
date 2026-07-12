"""
端到端测试：覆盖 7 大场景 + 多意图混合
启动 Agent 后运行：python test_e2e.py
"""

import sys
import os
import io

# 修复 Windows GBK 编码问题
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 先初始化数据库（独立测试）
from student_agent.db import init_database
init_database()

from student_agent.agent import process_message
from student_agent.reminder import scan_and_remind

PASS = 0
FAIL = 0


def test(name: str, student_id: int, message: str, expected_intents: list = None):
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"学生{student_id}: {message}")
    print("-" * 60)

    try:
        result = process_message(student_id, message)
        reply = result["reply"]
        intents = [i["intent"] for i in result.get("intents", [])]
        emotion = result.get("emotion", {})

        print(f"意图: {intents}")
        print(f"情绪: {emotion.get('emotion', 'N/A')} (风险{emotion.get('risk_score', 0)})")
        print(f"回复: {reply[:300]}...")

        if expected_intents:
            matched = any(exp in intents for exp in expected_intents)
            if matched:
                print(f"✅ 通过（期望意图: {expected_intents}，实际: {intents}）")
                PASS += 1
            else:
                print(f"⚠️ 意图不匹配（期望: {expected_intents}，实际: {intents}）")
                FAIL += 1
        else:
            PASS += 1
    except Exception as e:
        print(f"❌ 失败: {e}")
        FAIL += 1


# ============================================================
#  场景测试
# ============================================================

# 场景① 请假
test("请假提交", 1001, "我想请后天上午的事假，要去银行办事",
     expected_intents=["leave"])
test("请假查询", 1001, "帮我查一下我的请假记录",
     expected_intents=["leave", "nl2sql"])

# 场景② 心理关怀
test("心理-压力", 1004, "我觉得好孤独，来这边一个朋友都没有",
     expected_intents=["mental"])
test("心理-焦虑", 1002, "最近压力好大晚上一直失眠",
     expected_intents=["mental"])

# 场景③ 售后反馈
test("投诉提交", 1002, "宿舍空调坏了一周了报修没人来，太热了没法住",
     expected_intents=["feedback"])
test("投诉查询", 1002, "我之前反馈的问题处理进度如何",
     expected_intents=["feedback"])

# 场景④ 学业考务
test("学业查询", 1001, "我接下来有什么考试和DDL",
     expected_intents=["academic"])

# 场景⑤ 进度追踪
test("进度查询", 1001, "我的留学申请到哪一步了",
     expected_intents=["progress"])

# 场景⑥ 生活支持
test("生活指南-医疗", 1004, "新加坡看病怎么用医保",
     expected_intents=["life_guide"])
test("生活指南-租房", 1005, "新加坡租房要注意什么",
     expected_intents=["life_guide"])

# 场景⑦ 增值转化
test("升学意向", 1003, "我在想要不要继续读个博士",
     expected_intents=["upgrade"])

# 闲聊
test("闲聊", 1001, "你好呀今天天气真好",
     expected_intents=["chat"])

# 多意图混合 ⭐
test("多意图-请假+心理+学业", 1002,
     "我论文快截止了好焦虑，想请两天假调整一下",
     expected_intents=["leave", "mental", "academic"])

# NL2SQL
test("NL2SQL查询", 1001, "帮我查一下我有多少条请假记录",
     expected_intents=["nl2sql"])


# ============================================================
#  定时提醒测试
# ============================================================

print(f"\n{'='*60}")
print("测试: 定时提醒扫描")
print("-" * 60)
try:
    sent = scan_and_remind()
    print(f"发送提醒数: {len(sent)}")
    for s in sent:
        print(f"  学生{s['student_id']}: {s['message'][:80]}...")
    print(f"✅ 提醒扫描完成")
    PASS += 1
except Exception as e:
    print(f"❌ 失败: {e}")
    FAIL += 1


# ============================================================
#  结果
# ============================================================

total = PASS + FAIL
print(f"\n{'='*60}")
print(f"测试结果: {PASS}/{total} 通过"
      + (f", {FAIL} 失败" if FAIL > 0 else " 🎉 全部通过！"))
print(f"{'='*60}")

if FAIL > 0:
    sys.exit(1)
