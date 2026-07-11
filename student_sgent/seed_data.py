"""
测试数据初始化脚本

用法：
    python seed_data.py
    python seed_data.py --force   （跳过确认，直接执行）

安全机制：
    - 默认需要交互确认，防止误运行清空生产数据
    - --force 参数用于 CI/CD 等自动化场景
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# 防御性 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services import student_service as svc

SID = 1  # 测试学生ID
SESSION_ID = "sess_test_001"


def cleanup_old_data():
    """清理旧测试数据（事务包裹，失败自动回滚）"""
    from models import get_session
    from sqlalchemy import text
    with get_session() as session:
        tables = [
            "risk_interventions", "feedback_tickets", "student_applications",
            "study_intentions", "deadline_reminders", "academic_schedules",
            "conversation_messages", "conversation_sessions",
            "emotion_profile_snapshots",
        ]
        for t in tables:
            session.execute(text(f"DELETE FROM `{t}`"))
        # commit 由 get_session 上下文管理器自动处理
    print("旧数据已清理")


def seed():
    """初始化测试数据"""
    # 1. 创建会话
    svc.create_session(SID, SESSION_ID)
    print(f"会话: {SESSION_ID}")

    # 2. 添加测试消息（含情绪数据）
    messages = [
        ("我今天考试通过了，太开心了！", "积极", 85, ["开心", "通过"]),
        ("最近失眠很严重，压力太大了", "焦虑", 30, ["失眠", "压力"]),
        ("老师，我的签证材料什么时候能发？等了两周了", "焦虑", 40, []),
        ("收到曼彻斯特的offer了！感谢老师！", "积极", 90, ["offer", "感谢"]),
        ("课程安排查询", None, None, []),
    ]
    for content, tag, score, kw in messages:
        svc.add_message(SESSION_ID, "user", content,
                        emotion_tag=tag, emotion_score=score,
                        trigger_keywords=kw or None)
        svc.add_message(SESSION_ID, "assistant",
                        f"收到您的消息：{content[:20]}...")

    # 3. 创建日程
    now = datetime.now()
    svc.create_academic_schedule(SID, "雅思冲刺班", now + timedelta(hours=2),
                                  schedule_type="course",
                                  end_time=now + timedelta(hours=4),
                                  location="线上-Zoom")
    svc.create_academic_schedule(SID, "期中考试", now + timedelta(days=3),
                                  schedule_type="exam",
                                  end_time=now + timedelta(days=3, hours=2))

    # 4. 创建DDL提醒
    svc.create_deadline_reminder("曼彻斯特大学申请截止", now + timedelta(days=14),
                                   deadline_type="application", student_id=SID,
                                   reminder_days=[7, 3, 1])
    svc.create_deadline_reminder("签证材料提交DDL", now + timedelta(days=5),
                                   deadline_type="visa", student_id=SID,
                                   reminder_days=[3, 1])

    # 5. 升学意向
    svc.create_study_intention(SID, "英国", "曼彻斯特大学", "计算机科学",
                                "硕士", "2027-09", "30-50万", "雅思6.5", priority=0)
    svc.create_study_intention(SID, "澳大利亚", "悉尼大学", "数据科学",
                                "硕士", "2027-09", "40-60万", "雅思7.0", priority=1)

    # 6. 申请进度
    svc.create_student_application(SID, "曼彻斯特大学", target_country="英国",
                                     target_major="计算机科学",
                                     stage="under_review",
                                     progress_detail="材料已提交，等待审核",
                                     deadline=now + timedelta(days=14),
                                     next_action="准备补充材料")

    # 7. 投诉工单
    svc.create_feedback_ticket(SID, "签证材料拖延，请尽快处理",
                                ticket_type="complaint",
                                category="签证办理",
                                title="签证材料迟迟未发",
                                priority="high")
    svc.create_feedback_ticket(SID, "建议增加周末答疑时段",
                                ticket_type="suggestion",
                                category="其他",
                                priority="low")

    # 8. 心理预警（含风险标签）
    svc.create_risk_intervention(SID, "连续多日情绪评分低于30分，学生表现出焦虑和失眠症状",
                                  risk_level="high")
    svc.create_risk_intervention(SID, "学生提到签证拖延带来的压力",
                                  risk_level="medium",
                                  risk_tags=["签证焦虑", "时间压力"])


if __name__ == "__main__":
    # --force / -f 跳过确认
    force = "--force" in sys.argv or "-f" in sys.argv

    if not force:
        print("=" * 60)
        print("[WARN] 此脚本将清空 hambaki_3 库中全部学生模块表数据！")
        print("=" * 60)
        print(f"将删除并重新初始化以下表的数据：")
        print("  conversation_sessions, conversation_messages,")
        print("  emotion_profile_snapshots, risk_interventions,")
        print("  feedback_tickets, academic_schedules,")
        print("  deadline_reminders, study_intentions,")
        print("  student_applications")
        print()
        confirm = input("确认继续？(yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            print("已取消。")
            sys.exit(0)

    cleanup_old_data()
    seed()

    print("""
========================================
测试数据初始化完成！

学生ID: 1
测试会话: sess_test_001
消息: 10 条 (含情绪数据)
日程: 2 条
DDL: 2 条
升学意向: 2 条
申请进度: 1 条
工单: 2 条
预警: 2 条（含风险标签）

启动: uvicorn main:app --port 8000
访问: http://localhost:8000
Token: dev-token（在页面顶部输入）
========================================
""")
