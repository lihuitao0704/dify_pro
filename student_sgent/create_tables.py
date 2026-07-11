"""
数据库建表脚本

用法：
    python create_tables.py
    python -m create_tables   （从任意路径）

注意：
    - 仅创建 hambaki_3 库中学生的 9 张表
    - 不会影响 test 库或其他模块的表
    - 使用了 checkfirst=True，已存在的表不会重复创建
"""

import sys
from pathlib import Path

# 防御性 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import text

from models import Base, get_session, get_engine
from models.student import (
    ConversationSession,
    ConversationMessage,
    EmotionProfileSnapshot,
    RiskIntervention,
    FeedbackTicket,
    AcademicSchedule,
    DeadlineReminder,
    StudyIntention,
    StudentApplication,
)


def create_all_tables():
    """在 hambaki_3 库中创建全部 9 张学生模块表"""
    engine = get_engine()

    print("=" * 60)
    print("开始创建学生模块表（数据库：hambaki_3）")
    print("=" * 60)

    # 显示将要创建的表
    table_names = sorted(Base.metadata.tables.keys())
    print(f"\n待创建的表（共 {len(table_names)} 张）：")
    for i, name in enumerate(table_names, 1):
        print(f"  {i}. {name}")

    print("\n正在创建...")
    Base.metadata.create_all(engine, checkfirst=True)
    print("建表完成！\n")

    # 验证表是否创建成功
    with get_session() as session:
        for name in table_names:
            result = session.execute(
                text(f"SELECT COUNT(*) FROM `{name}`")
            ).scalar()
            print(f"  OK  {name} -- {result} rows")

    print(f"\nTotal: {len(table_names)} tables ready.")


if __name__ == "__main__":
    create_all_tables()
