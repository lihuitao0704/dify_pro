"""
情绪分析服务 — 情绪检测、心理画像管理、预警触发

融合两套方案：
  1. LLM 分析（优先）：调用 llm.analyze_emotion() 进行深度语义理解
  2. 关键词兜底（student_sgent 模式）：本地关键词库快速检测

包含三部分业务逻辑：
  - 学生消息情绪分析 & 关键词检测
  - 心理画像（mental_health_profile）增/改/查
  - 心理预警（mental_health_alert）创建与查重
"""

import json
import logging
from datetime import datetime, date
from typing import Optional

from student_agent import db
from student_agent import llm
from student_agent.config import EMOTION_ALERT_THRESHOLD

logger = logging.getLogger(__name__)

# ============================================================
# 情绪关键词库（服务端兜底分析用，student_sgent 迁移）
# ============================================================

_POSITIVE_WORDS = [
    "开心", "高兴", "喜欢", "棒", "好", "不错", "顺利", "感谢", "谢谢", "期待",
    "兴奋", "成功", "通过", "录取", "offer", "优秀", "加油", "恭喜", "太棒了",
    "nice", "great", "awesome", "happy", "love", "wonderful", "fantastic",
]

_NEGATIVE_WORDS = [
    "焦虑", "担心", "害怕", "压力", "烦", "累", "难过", "伤心", "生气", "讨厌",
    "无聊", "失望", "痛苦", "崩溃", "失眠", "睡不着", "紧张", "烦躁", "无助", "孤独",
    "迷茫", "恐惧", "疲惫", "委屈", "后悔", "愤怒", "沮丧", "低落", "想家",
]

_CRITICAL_WORDS = [
    "绝望", "轻生", "自杀", "不想活", "死了算了", "自残", "伤害自己", "不想活了",
    "活不下去", "生无可恋", "活着没意思",
]


def analyze_emotion_keywords(content: str) -> dict:
    """
    服务端本地情绪分析 — 关键词检测。
    作为 LLM 情绪分析的兜底/补充方案。

    参数:
        content: 学生消息文本

    返回:
        {"tag": str, "score": int(0-100), "keywords": list}
          - tag:      情绪标签（正常/焦虑/低落/孤独/积极/高危等）
          - score:    情绪分值（0=极负面, 100=极正面, 默认75中性偏积极）
          - keywords: 触发关键词列表（前5个）
    """
    keywords = []
    tag = "正常"
    score = 75  # 中性偏积极

    # 高危词优先检测
    for w in _CRITICAL_WORDS:
        if w in content:
            keywords.append(w)
            score = 10
            tag = "高危"
            break

    if tag != "高危":
        neg_found = [w for w in _NEGATIVE_WORDS if w in content]
        pos_found = [w for w in _POSITIVE_WORDS if w in content]

        if neg_found:
            keywords = neg_found
            score = 30
            tag = "焦虑"
        if pos_found and tag == "正常":
            # 仅在无负面情绪时标记为积极
            keywords.extend(pos_found)
            score = 85
            tag = "积极"
        elif pos_found and tag == "焦虑":
            # 混杂情绪：记录正面词但不改变主情绪
            keywords.extend(pos_found)
            score = 45  # 中和一点

    return {
        "tag": tag,
        "score": score,
        "keywords": keywords[:5],
    }


def merge_emotion_results(llm_result: dict, keyword_result: dict) -> dict:
    """
    融合 LLM 情感分析和关键词分析结果。
    LLM 结果优先，关键词结果作为字段补充。

    参数:
        llm_result:     LLM analyze_emotion 返回结果
        keyword_result: 本地关键词分析结果

    返回:
        融合后的情绪分析结果 dict
    """
    # 如果 LLM 在线并返回有效结果，以 LLM 为准
    if llm_result and llm_result.get("emotion"):
        merged = dict(llm_result)
        # 补充 keyword 字段（LLM 可能不返回）
        if not merged.get("keywords") and keyword_result.get("keywords"):
            merged["keywords"] = keyword_result["keywords"]
        # 确保关键字段存在
        merged.setdefault("risk_score", 0)
        merged.setdefault("risk_level", "low")
        merged.setdefault("needs_alert", False)
        merged.setdefault("emotion", "正常")
        return merged

    # LLM 不可用或无效 → 用关键词结果转换为兼容格式
    tag = keyword_result.get("tag", "正常")
    score = keyword_result.get("score", 75)

    if score <= 20:
        risk_level = "critical"
    elif score <= 40:
        risk_level = "high"
    elif score <= 60:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "emotion": tag,
        "risk_score": 100 - score,  # 反转：0=无风险, 100=高危
        "risk_level": risk_level,
        "keywords": keyword_result.get("keywords", []),
        "needs_alert": (100 - score) >= EMOTION_ALERT_THRESHOLD,
        "alert_reason": f"关键词检测：{', '.join(keyword_result.get('keywords', []))}" if keyword_result.get("keywords") else "",
        "response_guide": "",
    }


def get_or_create_profile(student_id: int) -> dict:
    """
    获取学生心理画像；不存在则创建默认画像。

    参数:
        student_id: 学生ID

    返回:
        mental_health_profile 行 dict（含所有字段）
    """
    profile = db.query_one(
        "SELECT * FROM mental_health_profile WHERE student_id = %s",
        (student_id,)
    )
    if profile:
        return profile

    # 创建默认画像
    default_data = {
        "student_id": student_id,
        "current_emotion": "正常",
        "risk_score": 0,
        "risk_level": "low",
        "emotion_history": "[]",
        "negative_keywords_count": 0,
        "consecutive_negative_days": 0,
        "last_conversation": "",
        "last_assessment_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    db.insert("mental_health_profile", default_data)
    return db.query_one(
        "SELECT * FROM mental_health_profile WHERE student_id = %s",
        (student_id,)
    )


def update_profile(
    student_id: int,
    emotion: dict,
    user_msg: str,
) -> dict:
    """
    更新学生心理画像（mental_health_profile）。

    计算逻辑：
      - 追加当前情绪到 emotion_history（保留最近30条）
      - 更新连续负面天数（consecutive_negative_days）
      - 更新负面关键词累计次数

    参数:
        student_id: 学生ID
        emotion:    情绪分析结果 {emotion, risk_score, risk_level, ...}
        user_msg:   当前学生消息（用于存储触发内容）

    返回:
        更新后的 mental_health_profile 行 dict
    """
    profile = get_or_create_profile(student_id)

    risk_score = emotion.get("risk_score", 0)
    risk_level = emotion.get("risk_level", "low")

    # 解析已有 emotion_history
    emotion_history = json.loads(profile.get("emotion_history", "[]") or "[]")

    # 追加当前情绪记录
    emotion_history.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "emotion": emotion.get("emotion", ""),
        "score": risk_score,
        "trigger": user_msg[:100],
    })
    emotion_history = emotion_history[-30:]  # 保留最近30条

    # 计算连续负面天数
    if risk_level not in ("low",):
        new_cons = (profile.get("consecutive_negative_days") or 0) + 1
    else:
        new_cons = 0

    # 累计负面关键词次数
    old_neg = profile.get("negative_keywords_count") or 0
    new_neg = old_neg + (1 if risk_level not in ("low", "normal") else 0)

    upsert_data = {
        "current_emotion": emotion.get("emotion", "正常"),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "emotion_history": json.dumps(emotion_history, ensure_ascii=False),
        "negative_keywords_count": new_neg,
        "consecutive_negative_days": new_cons,
        "last_conversation": user_msg[:500],
        "last_assessment_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 判断是 insert 还是 update
    existing = db.query_one(
        "SELECT id FROM mental_health_profile WHERE student_id = %s",
        (student_id,)
    )
    if existing:
        db.update("mental_health_profile", {"student_id": student_id}, upsert_data)
    else:
        upsert_data["student_id"] = student_id
        db.insert("mental_health_profile", upsert_data)

    return db.query_one(
        "SELECT * FROM mental_health_profile WHERE student_id = %s",
        (student_id,)
    )


def create_alert(
    student_id: int,
    emotion: dict,
    user_msg: str,
) -> Optional[int]:
    """
    创建心理预警记录（mental_health_alert）。

    幂等规则：同学生今天内已有同风险等级的 pending 预警则不重复创建。
    创建成功后会标记画像的 teacher_notified = 1。

    参数:
        student_id: 学生ID
        emotion:    情绪分析结果
        user_msg:   触发预警的学生消息

    返回:
        预警记录ID（如果创建了）；None（如果已存在今天的不重复预警）
    """
    # 检查今天是否已有同等级 pending 预警
    existing = db.query_one(
        """SELECT id FROM mental_health_alert
           WHERE student_id = %s AND follow_up_status = 'pending'
           AND DATE(created_at) = CURDATE()""",
        (student_id,)
    )
    if existing:
        logger.info("今日已有预警记录(id=%s)，跳过重复创建", existing["id"])
        return None

    alert_id = db.insert("mental_health_alert", {
        "student_id": student_id,
        "trigger_reason": emotion.get("alert_reason", f"风险评分 {emotion.get('risk_score', 0)}"),
        "risk_level": emotion.get("risk_level", "high"),
        "alert_content": user_msg[:500],
        "emotion_label": emotion.get("emotion", ""),
        "risk_score": emotion.get("risk_score", 0),
        "follow_up_status": "pending",
    })

    # 标记画像已通知老师
    db.update(
        "mental_health_profile",
        {"student_id": student_id},
        {"teacher_notified": 1},
    )

    logger.info("已创建心理预警: student=%d, alert_id=%s, risk_level=%s",
                student_id, alert_id, emotion.get("risk_level"))
    return alert_id


def get_care_text(risk_level: str) -> str:
    """
    根据风险等级生成关怀话术文本。

    参数:
        risk_level: "low" / "medium" / "high" / "critical"

    返回:
        关怀文本（空字符串表示无需额外关怀）
    """
    care_map = {
        "high": "\n\n💙 我有些担心你。如果你愿意，可以和信任的老师或朋友聊聊，你不是一个人在面对这些。",
        "critical": "\n\n💙 我有些担心你。如果你愿意，可以和信任的老师或朋友聊聊，你不是一个人在面对这些。",
        "medium": "\n\n💪 听起来你最近压力不小，照顾好自己，需要的话我随时在～",
    }
    return care_map.get(risk_level, "")


def analyze_and_update(student_id: int, emotion: dict, user_msg: str) -> str:
    """
    完整情绪处理流水线：更新画像 → 预警判断 → 返回关怀文本。

    此为 agent.py _handle_emotion_update 的替代实现。

    参数:
        student_id: 学生ID
        emotion:    情绪分析结果（来自 LLM 或关键词兜底）
        user_msg:   学生原始消息

    返回:
        关怀文本（追加到最终回复中）；空字符串表示无额外关怀
    """
    risk_score = emotion.get("risk_score", 0)
    risk_level = emotion.get("risk_level", "low")

    # 更新心理画像
    update_profile(student_id, emotion, user_msg)

    # 高危 → 触发预警
    if risk_score >= EMOTION_ALERT_THRESHOLD and emotion.get("needs_alert"):
        create_alert(student_id, emotion, user_msg)

    # 返回关怀文本
    return get_care_text(risk_level)


# ============================================================
# 心理关怀回复（场景：mental）
# ============================================================

MENTAL_RESPONSES = {
    "压力大": "听你说压力很大……留学确实不容易，课程、论文、生活都压在肩上。你已经很努力了 💪 要不要聊聊具体是什么让你压力最大？",
    "焦虑": "焦虑的时候，试着深呼吸几次 🫁 你愿意和我说说是哪方面让你焦虑吗？学业？申请？还是生活上的事？",
    "孤独": "一个人在国外确实容易感到孤独……很多留学生都经历过这个阶段。你有没有想过参加一些社团活动，或者和班上的同学约个饭？哪怕只是走出门散散步，心情也会不一样～",
    "难过": "💙 我在听。有些时候不需要解决方案，只需要有个人愿意听。你想说什么都可以～",
    "想家": "想家是最正常不过的事了。有没有试过和家人视频？哪怕只是看看家里的猫🐱。",
}


def get_mental_response(emotion_type: str, message: str) -> str:
    """
    根据情绪类型返回心理关怀回复。

    参数:
        emotion_type: 意图识别中的 emotion 参数
        message:      学生原始消息（用于关键词匹配）

    返回:
        关怀回复文本
    """
    for key, resp in MENTAL_RESPONSES.items():
        if key in emotion_type or key in message:
            return resp
    return "我听到了。留学路上有起有落，每一步都是在往前走。需要的话，随时可以找我聊聊 🌿"


def handle_mental(student_id: int, message: str, params: dict, context: list) -> str:
    """
    处理心理关怀意图（完整 handler）。

    参数:
        student_id: 学生ID
        message:    学生消息
        params:     意图参数（含 emotion 等）
        context:    对话上下文

    返回:
        回复文本
    """
    emotion_type = params.get("emotion", "")
    return get_mental_response(emotion_type, message)
