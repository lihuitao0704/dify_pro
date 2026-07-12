"""
定时提醒服务：扫描学业日程，DDL 临近时自动推送提醒
使用 APScheduler 后台调度
"""

from datetime import datetime, timedelta
from . import db as _db

# ============================================================
#  提醒核心逻辑
# ============================================================

def scan_and_remind() -> list[dict]:
    """扫描学业DDL + 增值转化意向，发送提醒。返回本次发送的提醒列表"""
    sent = []
    sent.extend(_scan_academic_reminders())
    sent.extend(_scan_upgrade_reminders())
    return sent


def _scan_academic_reminders() -> list[dict]:
    """扫描学业日程，DDL临近时推送"""
    now = datetime.now()
    sent = []

    schedules = _db.query(
        """SELECT id, student_id, event_type, title, course_name, deadline, priority,
                  reminder_24h_sent, reminder_3d_sent, reminder_7d_sent
           FROM academic_schedule
           WHERE status = 'upcoming' AND deadline > NOW()
           ORDER BY deadline ASC"""
    )

    for s in schedules:
        deadline = s["deadline"]
        if isinstance(deadline, str):
            try:
                deadline = datetime.strptime(deadline[:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, IndexError):
                continue
        hours_left = (deadline - now).total_seconds() / 3600
        days_left = hours_left / 24

        remind_type = None
        update_field = None

        if hours_left <= 24 and not s["reminder_24h_sent"]:
            remind_type = "DDL提醒（24小时内）"
            update_field = "reminder_24h_sent"
        elif days_left <= 3 and not s["reminder_3d_sent"]:
            remind_type = "DDL提醒（3天内）"
            update_field = "reminder_3d_sent"
        elif days_left <= 7 and not s["reminder_7d_sent"]:
            remind_type = "DDL提醒（7天内）"
            update_field = "reminder_7d_sent"

        if remind_type and update_field:
            msg = _build_academic_msg(s, days_left, hours_left)
            _db.insert("reminder_log", {
                "student_id": s["student_id"],
                "schedule_id": s["id"],
                "remind_type": remind_type,
                "remind_channel": "agent",
                "message": msg,
            })
            _db.update("academic_schedule", {"id": s["id"]}, {update_field: 1})
            sent.append({"student_id": s["student_id"], "schedule_id": s["id"], "message": msg})

    return sent


def _scan_upgrade_reminders() -> list[dict]:
    """扫描升学意向表，对未转化学生定时推送推销内容"""
    sent = []

    interests = _db.query(
        """SELECT id, student_id, interest_degree, interest_country,
                  recommendation_text, conversion_status, contacted_at
           FROM upgrade_interest
           WHERE conversion_status IN ('identified', 'contacted', 'interested')
           ORDER BY created_at DESC"""
    )

    for i in interests:
        sid = i["student_id"]
        uid = i["id"]
        status = i["conversion_status"]

        # 查最近一次升学推送
        last_remind = _db.query_one(
            """SELECT id, sent_at FROM reminder_log
               WHERE student_id = %s AND remind_type LIKE '%%升学%%'
               ORDER BY sent_at DESC LIMIT 1""",
            (sid,)
        )

        should_push = False
        if status == "identified" and not last_remind:
            should_push = True
        elif status == "contacted" and (not last_remind or _days_since(last_remind["sent_at"]) >= 7):
            should_push = True
        elif status == "interested" and (not last_remind or _days_since(last_remind["sent_at"]) >= 3):
            should_push = True

        if should_push:
            # 生成推销文案
            degree = i["interest_degree"] or "升学"
            country = i["interest_country"] or ""
            msg = _build_upgrade_msg(degree, country, i["recommendation_text"], status)

            _db.insert("reminder_log", {
                "student_id": sid,
                "remind_type": f"升学推送-{status}",
                "remind_channel": "agent",
                "message": msg,
            })

            # 首次推 → 更新状态为 contacted
            if status == "identified":
                _db.update("upgrade_interest", {"id": uid}, {
                    "conversion_status": "contacted",
                    "contacted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })

            sent.append({"student_id": sid, "schedule_id": None, "message": msg})

    return sent


def _days_since(dt) -> int:
    """距今天数"""
    if isinstance(dt, str):
        try:
            dt = datetime.strptime(dt[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, IndexError):
            return 999
    try:
        return (datetime.now() - dt).days
    except TypeError:
        return 999


def _build_academic_msg(s: dict, days_left: float, hours_left: float) -> str:
    icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.get("priority", "medium"), "📅")
    if hours_left <= 24:
        time_text = f"还剩 {hours_left:.0f} 小时"
    else:
        time_text = f"还剩 {days_left:.0f} 天"
    return (
        f"{icon} 学业提醒\n"
        f"📝 {s['title']}{'（' + s['course_name'] + '）' if s.get('course_name') else ''}\n"
        f"⏰ 截止时间：{str(s['deadline'])[:16]}\n"
        f"⏳ {time_text}\n"
        f"加油，你可以的！💪"
    )


def _build_upgrade_msg(degree: str, country: str, recommendation: str, status: str) -> str:
    prefix = {"identified": "🎓 升学推荐", "contacted": "💡 再次推荐", "interested": "🎯 专属方案"}
    title = prefix.get(status, "🎓 升学推荐")
    country_text = f" | {country}" if country else ""
    rec = recommendation[:200] if recommendation else f"关于{degree}深造，我们整理了最新项目和申请方案。"
    return (
        f"{title}\n"
        f"📚 {degree}{country_text}\n"
        f"📋 {rec}\n"
        f"感兴趣的话随时找我聊聊～"
    )


def get_pending_reminders(student_id: int) -> list[dict]:
    """获取某学生的未读提醒"""
    return _db.query(
        """SELECT id, remind_type, message, sent_at, is_read
           FROM reminder_log
           WHERE student_id = %s AND is_read = 0
           ORDER BY sent_at DESC LIMIT 20""",
        (student_id,)
    )


def mark_read(reminder_id: int):
    """标记提醒为已读"""
    _db.update("reminder_log", {"id": reminder_id}, {"is_read": 1})


# ============================================================
#  APScheduler 集成（可选）
# ============================================================

_scheduler = None


def start_scheduler():
    """启动定时调度器（每小时检查一次）"""
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(scan_and_remind, "interval", hours=1, id="reminder_scan")
        _scheduler.start()
        print("[Reminder] 定时提醒调度器已启动（每小时检查一次）")
    except ImportError:
        print("[Reminder] APScheduler 未安装，跳过定时调度（手动调用 scan_and_remind() 仍可用）")
    except Exception as e:
        print(f"[Reminder] 调度器启动失败: {e}")


def stop_scheduler():
    """停止定时调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        print("[Reminder] 调度器已停止")
