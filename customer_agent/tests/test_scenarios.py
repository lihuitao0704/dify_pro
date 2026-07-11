"""
7场景 E2E 测试
直接运行: python -m customer_agent.tests.test_scenarios
"""
import sys
import io
# Windows GBK 终端兼容
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def run_tests():
    from customer_agent.agent import process_message

    test_cases = [
        # ── 1. 公司信息咨询 ──
        {"name": "公司背景", "input": "你们机构是做什么的？成立多久了？"},
        {"name": "校区分布", "input": "你们校区在哪里？有北京的校区吗？"},
        {"name": "成功案例", "input": "你们有什么成功案例能说说吗？"},

        # ── 2. 业务查询 ──
        {"name": "留学业务", "input": "你们留学申请服务都包含什么？"},
        {"name": "语培业务", "input": "有什么语言培训课程？"},
        {"name": "背景提升", "input": "有背景提升项目吗？"},

        # ── 3. 政策查询 ──
        {"name": "德国APS", "input": "去德国留学APS是什么要求？"},
        {"name": "新加坡签证", "input": "新加坡学生签证怎么办理？"},
        {"name": "语言要求", "input": "申请新加坡大学雅思要多少分？"},

        # ── 4. 课程推荐 ──
        {"name": "推荐德国", "input": "我本科车辆工程，GPA3.3，想去德国读硕士"},
        {"name": "推荐新加坡", "input": "雅思6.5，预算20万，推荐新加坡什么项目"},
        {"name": "不完整背景", "input": "帮我推荐留学的"},

        # ── 5. 活动报名 ──
        {"name": "查活动", "input": "最近有什么留学讲座或活动吗？"},
        {"name": "查讲座", "input": "有新加坡留学相关的分享会吗？"},
        {"name": "报名", "input": "帮我报名升学规划讲座，姓名张三，手机13800138000"},

        # ── 6. FAQ ──
        {"name": "申请流程", "input": "申请流程是什么？"},
        {"name": "费用问题", "input": "你们服务费用多少钱？"},
        {"name": "退费政策", "input": "如果不去留学了 能退费吗？"},

        # ── 7. 闲聊 ──
        {"name": "打招呼", "input": "你好 在吗？"},
        {"name": "感谢", "input": "谢谢你的解答"},
        {"name": "无厘头", "input": "你觉得今天天气怎么样？"},

        # ── 复合意图 ──
        {"name": "推荐+活动", "input": "帮我推荐德国留学项目，顺便报名下周的讲座"},
        {"name": "公司+费用", "input": "介绍一下你们机构 顺便问下留学费用"},

        # ── 围栏外 ──
        {"name": "法律问题", "input": "我要起诉你们机构"},
        {"name": "医疗咨询", "input": "我头痛三天了吃什么药好？"},
    ]

    print("=" * 60)
    print("  客服Agent 7场景 E2E 测试")
    print("=" * 60)

    pass_count = 0
    fail_count = 0

    for tc in test_cases:
        try:
            result = process_message(tc["input"])
            reply = result["reply"]
            intents = [i["intent"] for i in result["intents"]]
            status = "[PASS]" if reply and len(reply) < 600 else "[WARN]"

            print(f"\n{status} [{tc['name']}] \"{tc['input']}\"")
            print(f"   意图: {intents}")
            print(f"   回复 ({len(reply)}字): {reply[:150]}{'...' if len(reply)>150 else ''}")

            if reply:
                pass_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"\n[FAIL] [{tc['name']}] \"{tc['input']}\"")
            print(f"   异常: {e}")
            fail_count += 1

    print("\n" + "=" * 60)
    print(f"结果: {pass_count} 通过 / {fail_count} 失败 / {len(test_cases)} 总用例")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
