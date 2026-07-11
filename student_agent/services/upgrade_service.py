"""
增值转化服务 — 升学意向识别、冷却检查、推荐话术生成

包含：
  - 升学意向记录与状态管理（upgrade_interest 表 CRUD）
  - 营销触达冷却检查（来自 education-service-api 的防骚扰模式）
  - 个性化推荐话术生成（LLM 基于学生画像）
  - 意向状态流转：identified → interested → converted / lost
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from student_agent import db
from student_agent import llm
from student_agent.config import TEACHER_AGENT_URL

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================

# 营销触达冷却天数（防骚扰，education-service-api 模式）
MARKETING_COOLDOWN_DAYS = 7

# 意向状态流转
STATUS_IDENTIFIED = "identified"
STATUS_INTERESTED = "interested"
STATUS_CONTACTED = "contacted"
STATUS_CONVERTED = "converted"
STATUS_LOST = "lost"

# 追问关键词（判断是否为上一轮的继续追问）
FOLLOWUP_KEYWORDS = [
    "预约", "联系", "报名", "怎么申请", "怎么报", "多少钱", "费用",
    "多久", "什么时候", "顾问", "一对一",
]


def check_marketing_cooldown(student_id: int) -> bool:
    """
    检查营销触达冷却期。

    来自 education-service-api 的模式：
      cooldown_start = now - timedelta(days=cooldown)
      查询 cooling 期内是否有触达记录，有则拦截

    参数:
        student_id: 学生ID

    返回:
        True = 冷却期内，不应重复触达
        False = 可触达
    """
    cooldown_start = (datetime.now() - timedelta(days=MARKETING_COOLDOWN_DAYS))\
        .strftime("%Y-%m-%d %H:%M:%S")

    recent = db.query_one(
        """SELECT id, created_at FROM upgrade_interest
           WHERE student_id = %s
             AND conversion_status IN ('identified', 'interested', 'contacted')
             AND created_at >= %s
           ORDER BY created_at DESC LIMIT 1""",
        (student_id, cooldown_start)
    )

    if recent:
        logger.info(
            "营销冷却拦截: student=%d, last_touch=%s",
            student_id, recent.get("created_at"),
        )
        return True
    return False


def get_student_profile(student_id: int) -> Optional[dict]:
    """
    获取学生信息作为推荐画像。

    参数:
        student_id: 学生ID

    返回:
        学生信息 dict（含 name/education/major/gpa/language_score/target_country 等）
    """
    return db.query_one(
        """SELECT name, education, major, gpa, language_score,
                  target_country, target_degree, target_major
           FROM student WHERE id = %s""",
        (student_id,)
    )


def get_today_interest(student_id: int) -> Optional[dict]:
    """
    查询学生今天是否已有意向记录。

    参数:
        student_id: 学生ID

    返回:
        今日意向记录或 None
    """
    return db.query_one(
        """SELECT id, conversion_status FROM upgrade_interest
           WHERE student_id = %s AND DATE(created_at) = CURDATE()
           ORDER BY id DESC LIMIT 1""",
        (student_id,)
    )


def get_latest_identified(student_id: int) -> Optional[dict]:
    """
    查询学生最新的 identified 状态意向。

    参数:
        student_id: 学生ID

    返回:
        最新意向记录或 None
    """
    return db.query_one(
        """SELECT id FROM upgrade_interest
           WHERE student_id = %s AND conversion_status = 'identified'
           ORDER BY id DESC LIMIT 1""",
        (student_id,)
    )


def create_interest(
    student_id: int,
    params: dict,
    message: str,
) -> int:
    """
    记录升学意向（当天不重复）。

    参数:
        student_id: 学生ID
        params:     意图参数（degree/country/major 等）
        message:    触发消息

    返回:
        意向记录ID
    """
    interest_id = db.insert("upgrade_interest", {
        "student_id": student_id,
        "interest_degree": params.get("degree", "硕士咨询"),
        "interest_country": params.get("country", ""),
        "interest_major": params.get("major", ""),
        "detected_source": "对话识别",
        "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "conversation_snippet": message[:300],
        "conversion_status": STATUS_IDENTIFIED,
    })

    logger.info("升学意向已记录: id=%s, student=%d", interest_id, student_id)
    return interest_id


def update_interest_status(
    interest_id: int,
    status: str,
) -> bool:
    """
    更新意向状态。

    参数:
        interest_id: 意向记录ID
        status:      新状态（interested/contacted/converted/lost）

    返回:
        是否更新成功
    """
    update_data = {"conversion_status": status}
    if status == STATUS_INTERESTED:
        update_data["contacted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    affected = db.update("upgrade_interest", {"id": interest_id}, update_data)
    return affected > 0


def is_followup(message: str, context: list) -> bool:
    """
    判断当前消息是否是对上一轮升学话题的继续追问。

    参数:
        message: 当前学生消息
        context: 对话上下文

    返回:
        True = 追问 / False = 新意向
    """
    # 检查是否包含追问关键词
    is_follow = any(kw in message for kw in FOLLOWUP_KEYWORDS) or len(message) <= 5

    if not is_follow:
        return False

    # 检查上下文是否已推送过升学信息
    prev_followup_count = sum(
        1 for m in context[-6:]
        if m.get("role") == "assistant"
        and (
            "预约留学顾问" in m.get("content", "")
            or "我可以帮你" in m.get("content", "")
        )
    )
    return prev_followup_count > 0


def handle_followup(student_id: int, context: list) -> str:
    """
    处理追问场景：学生确认了 → 更新意向状态为 interested。

    参数:
        student_id: 学生ID
        context:    对话上下文

    返回:
        回复文本
    """
    # 查询最新的 identified 记录
    latest = get_latest_identified(student_id)
    if latest:
        update_interest_status(latest["id"], STATUS_INTERESTED)

    return (
        "好的！已经为你登记了升学意向 📋\n\n"
        "升学咨询功能正在对接中，上线后会有顾问为你提供一对一规划。"
        "当前你可以先了解升学项目和专业方向，问我 新加坡有哪些硕士项目 试试～"
    )


def get_followup_prompt() -> str:
    """
    生成升学咨询引导文本。

    返回:
        引导文本
    """
    return (
        "好的！关于升学深造的具体事宜，我可以帮你：\n\n"
        "📞 预约留学顾问一对一免费咨询\n"
        "📋 获取详细的项目手册和申请条件\n"
        "📅 了解最新的申请截止日期\n\n"
        "告诉我你想了解的方向，我马上安排顾问联系你～"
    )


def generate_recommendation_text(student: dict) -> str:
    """
    基于学生画像生成个性化推荐话术。

    调用 llm.generate_recommendation()，失败时返回默认文案。

    参数:
        student: 学生信息 dict

    返回:
        推荐话术文本
    """
    try:
        profile = {
            "name": student.get("name", "同学"),
            "education": student.get("education", ""),
            "major": student.get("major", ""),
            "gpa": student.get("gpa", ""),
            "language_score": student.get("language_score", ""),
            "target_country": student.get("target_country", ""),
        }
        return llm.generate_recommendation(profile)
    except Exception as e:
        logger.warning("推荐话术生成失败: %s", e)
        return (
            f"{student.get('name', '同学')}你好！根据你的背景（"
            f"{student.get('major', '')} / GPA {student.get('gpa', '')}），"
            f"我们有多项升学项目适合你，请联系顾问获取详细方案。"
        )


def handle_upgrade(student_id: int, message: str, params: dict, context: list) -> str:
    """
    处理升学意向完整 handler。

    流程：
      1. 判断话题继承（追问/新意向）
      2. 追问 → 更新状态为 interested
      3. 新意向 → 检查冷却期 → 记录意向 → 生成推荐
      4. 返回推荐话术

    参数:
        student_id: 学生ID
        message:    学生消息
        params:     意图参数
        context:    对话上下文

    返回:
        回复文本
    """
    # ── 追问模式 ──
    if is_followup(message, context):
        return handle_followup(student_id, context)

    # ── 第一轮追问（尚未推送过升学信息） ──
    if any(kw in message for kw in FOLLOWUP_KEYWORDS) or len(message) <= 5:
        return get_followup_prompt()

    # ── 冷却检查 ──
    if check_marketing_cooldown(student_id):
        # 冷却期内不重复触达，但仍记录意向
        existing = get_today_interest(student_id)
        student = get_student_profile(student_id)

        if not existing and student:
            create_interest(student_id, params, message)

        if student:
            return generate_recommendation_text(student)
        return get_followup_prompt()

    # ── 新意向检查（当天不重复） ──
    existing = get_today_interest(student_id)
    student = get_student_profile(student_id)

    # 记录意向（当天不重复）
    if not existing:
        create_interest(student_id, params, message)

    # 生成推荐
    if student:
        recommendation = generate_recommendation_text(student)
    else:
        recommendation = "你好！根据你的情况，我们有多项升学项目适合你～"

    return (
        f"{recommendation}\n\n"
        f"💡 如果感兴趣，我可以帮你预约留学顾问做一对一咨询，为你定制专属升学方案～"
    )
