"""
enterprise_agent/todo_scheduler.py — 主动待办推送
定时检测待处理事项，通过API通知相关员工

使用: 在 main.py 的 startup 事件中调用 start_scheduler()
"""
import logging
import threading
import time
from datetime import datetime
from enterprise_agent.database import SessionLocal
from sqlalchemy import text

logger = logging.getLogger("enterprise_agent.scheduler")

_check_interval = 300  # 默认每5分钟扫描一次
_running = False
_thread = None


def scan_pending_todos():
    """扫描所有待处理事项，返回按用户分组的待办统计"""
    db = SessionLocal()
    try:
        todos = []

        # 1. 待审批请假
        leaves = db.execute(text(
            "SELECT COUNT(*) AS cnt FROM leave_application WHERE status=0"
        )).fetchone()
        if leaves and leaves.cnt > 0:
            todos.append({
                "type": "leave_approval",
                "title": f"待审批请假",
                "count": leaves.cnt,
                "message": f"您有 {leaves.cnt} 条请假申请待审批",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        # 2. 待处理投诉
        complaints = db.execute(text(
            "SELECT COUNT(*) AS cnt FROM student_complaint WHERE handle_status='待处理'"
        )).fetchone()
        if complaints and complaints.cnt > 0:
            todos.append({
                "type": "complaint",
                "title": f"待处理投诉",
                "count": complaints.cnt,
                "message": f"有 {complaints.cnt} 条投诉待处理",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        # 3. 待跟进意向客户
        customers = db.execute(text(
            "SELECT COUNT(*) AS cnt FROM intention_customer WHERE current_status='意向中'"
        )).fetchone()
        if customers and customers.cnt > 0:
            todos.append({
                "type": "customer_followup",
                "title": f"待跟进客户",
                "count": customers.cnt,
                "message": f"有 {customers.cnt} 个意向客户待跟进",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        # 4. 处理中投诉
        in_progress = db.execute(text(
            "SELECT COUNT(*) AS cnt FROM student_complaint WHERE handle_status='处理中'"
        )).fetchone()
        if in_progress and in_progress.cnt > 0:
            todos.append({
                "type": "complaint_in_progress",
                "title": f"处理中的投诉",
                "count": in_progress.cnt,
                "message": f"有 {in_progress.cnt} 条投诉正在处理中，请关注进度",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        return todos
    except Exception as e:
        logger.error(f"扫描待办失败: {e}")
        return []
    finally:
        db.close()


def _scan_loop():
    """后台扫描循环"""
    global _running
    logger.info("待办推送调度器已启动，扫描间隔: %ds", _check_interval)
    while _running:
        try:
            todos = scan_pending_todos()
            if todos:
                count = sum(t.get("count", 0) for t in todos)
                logger.info("待办扫描: 发现 %d 类待办，共 %d 条", len(todos), count)
                for t in todos:
                    logger.info("  - %s: %d 条", t["title"], t["count"])
        except Exception as e:
            logger.error("待办扫描异常: %s", e)
        time.sleep(_check_interval)


def start_scheduler(interval: int = 300):
    """启动待办推送调度器"""
    global _running, _thread, _check_interval
    if _running:
        return
    _check_interval = interval
    _running = True
    _thread = threading.Thread(target=_scan_loop, daemon=True)
    _thread.start()


def stop_scheduler():
    """停止调度器"""
    global _running
    _running = False
    logger.info("待办推送调度器已停止")


def get_pending_summary() -> list:
    """获取当前待办摘要（供API调用）"""
    return scan_pending_todos()
