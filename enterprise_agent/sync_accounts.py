"""
企业智能助手 - 账户同步脚本
从 employee 表和 student 表同步到 account 表，已有账号跳过

同步规则：
- employee 表中：通过 department.manager_id 判断是否为管理者
  - 如果 emp_id 在 department.manager_id 中出现 → user_type = '管理者'
  - 否则 → user_type = '员工'
- student 表中 → user_type = '学员'
"""
import sys
import os
import logging

# 确保模块可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from sqlalchemy import text

from enterprise_agent.database import SessionLocal, engine
from enterprise_agent.models import Account, Employee, Student, Department

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sync_accounts")


def sync_accounts():
    """
    同步账户主流程
    从 employee 表和 student 表同步到 account 表
    """
    stats = {
        "total_employees": 0,
        "total_students": 0,
        "skipped_employees": 0,
        "skipped_students": 0,
        "created_employees": 0,
        "created_managers": 0,
        "created_students": 0,
        "errors": 0,
    }

    db = SessionLocal()
    try:
        # ===== Step 1: 收集所有部门负责人ID（管理者） =====
        manager_ids = set()
        departments = db.query(Department).filter(
            Department.status == 1,
            Department.manager_id.isnot(None),
        ).all()

        for dept in departments:
            manager_ids.add(dept.manager_id)

        logger.info(f"发现 {len(manager_ids)} 位部门负责人（管理者）")

        # ===== Step 2: 同步 employee → account =====
        employees = db.query(Employee).filter(Employee.status == 1).all()
        stats["total_employees"] = len(employees)
        logger.info(f"员工表共 {len(employees)} 条在职记录")

        for emp in employees:
            try:
                # 用户名生成策略：优先电话，其次姓名+ID后缀
                username = emp.phone or f"{emp.emp_name}_{emp.emp_id}"
                existing = db.query(Account).filter(
                    (Account.username == username) |
                    ((Account.phone.isnot(None)) & (Account.phone == emp.phone) & (emp.phone.isnot(None)))
                ).first()

                if existing:
                    stats["skipped_employees"] += 1
                    logger.debug(f"  跳过已存在: {emp.emp_name}")
                    continue

                # 判断是否为管理者
                is_mgr = emp.emp_id in manager_ids
                user_type = "管理者" if is_mgr else "员工"

                import secrets
                from enterprise_agent.security import hash_password
                # 安全提示：密码仅在创建时可用，日志仅记录用户名不记录密码
                logger.info("  >>> 创建账号: %s | 用户名: %s", user_type, username)
                account = Account(
                    username=username,
                    password=hashed_pwd,
                    real_name=emp.emp_name,
                    user_type=user_type,
                    dept_id=emp.dept_id,
                    student_id=None,
                    phone=emp.phone,
                    email=emp.email,
                    status=1,
                    create_time=datetime.now(),
                    update_time=datetime.now(),
                )
                db.add(account)
                db.flush()

                if is_mgr:
                    stats["created_managers"] += 1
                else:
                    stats["created_employees"] += 1

                logger.info(f"  创建{'管理者' if is_mgr else '员工'}账号: {emp.emp_name}")

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"  同步员工 {emp.emp_name} 失败: {e}")

        # ===== Step 3: 同步 student → account =====
        students = db.query(Student).all()
        stats["total_students"] = len(students)
        logger.info(f"学生表共 {len(students)} 条记录")

        for stu in students:
            try:
                # 检查是否已存在
                username = stu.name
                existing = db.query(Account).filter(
                    (Account.username == username) |
                    ((Account.phone.isnot(None)) & (Account.phone == stu.phone) & (stu.phone.isnot(None))) |
                    ((Account.student_id.isnot(None)) & (Account.student_id == stu.id))
                ).first()

                if existing:
                    stats["skipped_students"] += 1
                    logger.debug(f"  跳过已存在: {stu.name}")
                    continue

                from enterprise_agent.security import hash_password
                account = Account(
                    username=username,
                    password=hash_password("123456"),  # 默认密码（bcrypt哈希后存储）
                    real_name=stu.name,
                    user_type="学员",
                    dept_id=None,
                    student_id=stu.id,
                    phone=stu.phone,
                    email=stu.email,
                    status=1,
                    create_time=datetime.now(),
                    update_time=datetime.now(),
                )
                db.add(account)
                db.flush()

                stats["created_students"] += 1
                logger.info(f"  创建学员账号: {stu.name}")

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"  同步学生 {stu.name} 失败: {e}")

        db.commit()

        # ===== 输出统计信息 =====
        logger.info("=" * 50)
        logger.info("账户同步完成！统计信息：")
        logger.info(f"  员工总数: {stats['total_employees']}")
        logger.info(f"  已有跳过: {stats['skipped_employees']}")
        logger.info(f"  新建员工: {stats['created_employees']}")
        logger.info(f"  新建管理者: {stats['created_managers']}")
        logger.info(f"  学生总数: {stats['total_students']}")
        logger.info(f"  学生已有跳过: {stats['skipped_students']}")
        logger.info(f"  新建学员: {stats['created_students']}")
        logger.info(f"  新增账号合计: {stats['created_employees'] + stats['created_managers'] + stats['created_students']}")
        if stats["errors"] > 0:
            logger.warning(f"  错误数: {stats['errors']}")
        logger.info("=" * 50)

        return stats

    except Exception as e:
        db.rollback()
        logger.error(f"同步过程发生错误: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    """
    直接运行: python sync_accounts.py
    """
    logger.info("=" * 50)
    logger.info("企业智能助手 - 账户同步脚本")
    logger.info("=" * 50)

    stats = sync_accounts()

    total_created = stats["created_employees"] + stats["created_managers"] + stats["created_students"]
    if total_created > 0:
        logger.info("同步完成！新增 %s 个账号", total_created)
    else:
        logger.info("同步完成，没有新增账号（所有记录已存在）")

    if stats["errors"] > 0:
        logger.warning("发生 %s 个错误，请查看日志", stats["errors"])
