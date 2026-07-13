"""
数据库初始化校验脚本（独立可执行）。

⚠️ 不再建表。服务直接读写已有的 ``dify_pro`` 数据库。本脚本职责：
  1. 校验当前库中是否存在业务所需的全部核心表
  2. 输出每张表的行数概况，确认数据已就绪

使用方式（项目根目录）：
    python init_db.py
"""

from summary_report.core.config import DB_CONFIG
from summary_report.core.db import fetch_table_names, get_connection
from summary_report.core.logger import get_logger, setup_logging

logger = get_logger(__name__)

# 业务所需的全部核心表（顺序按模块分组，仅用于输出）
# 注意：表名必须与数据库 192.168.48.121 中的实际表名一致
REQUIRED_TABLES: list[str] = [
    # 客户经营模块
    "intention_customer",
    # 员工管理模块
    "employee_daily_report",
    # 留学业务
    "application_progress",
    "academic_deadline",
    "student_admin_service",
    "student_score",
    # 投诉工单
    "student_complaint",
    "student_feedback_ticket",
    # 心理健康
    "student_psych_record",
    "student_psych_profile",
    "student_mental_alert",
    "student_psych_alert",
    # 辅助核心表（被业务表通过 FK 引用或报告文本生成时使用）
    "department",      # 部门表（旧 schema 中曾错误命名为 organization）
    "account",         # 账户表
    "consultations",   # 咨询记录
    "user_profiles",   # 客户画像
    "courses",         # 课程表
]


def check_tables() -> bool:
    """
    执行校验。返回 True 表示全部表存在，False 表示有缺失。
    """
    logger.info("校验数据库: host=%s, database=%s", DB_CONFIG["host"], DB_CONFIG["database"])

    existing: set[str] = set(fetch_table_names())
    logger.info("当前库中共有 %d 张表", len(existing))

    missing: list[str] = []
    found: list[str] = []

    for tbl in REQUIRED_TABLES:
        if tbl in existing:
            found.append(tbl)
        else:
            missing.append(tbl)

    # ── 输出结果 ──
    print(f"\n✅ 已就绪的表 ({len(found)}/{len(REQUIRED_TABLES)}):")
    for tbl in found:
        print(f"   - {tbl}")

    if missing:
        print(f"\n❌ 缺失的表 ({len(missing)}):")
        for tbl in missing:
            print(f"   - {tbl}")

    # ── 行数概况 ──
    if found:
        print("\n📊 数据行数概况：")
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                for tbl in found:
                    cursor.execute(f"SELECT COUNT(*) AS n FROM `{tbl}`")  # noqa: S608
                    row = cursor.fetchone()
                    print(f"   - {tbl:<30s} {row['n']:>6d} 行")
        finally:
            conn.close()

    if missing:
        print(f"\n⚠️  校验未通过，共缺失 {len(missing)} 张表，请在 dify_pro 库中创建。")
        return False

    print(f"\n🎉 数据库初始化校验通过！全部 {len(REQUIRED_TABLES)} 张核心表就绪。")
    return True


if __name__ == "__main__":
    setup_logging()
    ok = check_tables()
    raise SystemExit(0 if ok else 1)
