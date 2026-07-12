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
from datetime import datetime
from typing import Optional

from student_agent import db
from student_agent import llm
from student_agent.config import EMOTION_ALERT_THRESHOLD

logger = logging.getLogger(__name__)

# ============================================================
# 情绪关键词库 — 分层权重 + 留学生专用 + 短语匹配 + 否定检测
# ============================================================

# ── 否定词（前置修饰，翻转极性）──
_NEGATION_WORDS = ["没有", "不是", "不算", "并非", "谈不上", "不怎么", "没那么"]

# ── 强度修饰词 ──
_INTENSIFIERS = ["非常", "特别", "超级", "太", "快要", "极其", "真的", "受不了了", "到极点了", "崩溃了"]
_WEAKENERS = ["有点", "稍微", "一点点", "还行吧", "也算", "算是", "可能", "大概"]

# ── 危机短语（完整匹配，最高优先级，直接触发高危）──
_CRITICAL_PHRASES = [
    "不想活了", "活着没意思", "想结束这一切", "我想死", "生无可恋",
    "活不下去了", "死了算了", "永远睡过去", "想消失", "不值得活着",
    "坚持不下去了", "撑不住了", "我撑不下去了", "快要崩溃了",
    "没人理解我", "没人关心我", "世界上没有我的位置", "我是累赘",
    "想自残", "想伤害自己", "我恨我自己",
]

# ── 负面情绪词（三级严重度 + 留学生专属维度）──
# 格式: {word: (weight_multiplier, dimension_hint)}
# dimension_hint: mood/anxiety/social/academic/cultural

_NEGATIVE_WEIGHTED = {}

# --- L1 轻度（权重×1）---
for _w in ["累", "烦", "无聊", "想家", "不太适应", "不习惯", "语言不太通",
           "有点难", "不太顺利", "不太好", "没太听懂", "有点贵",
           "有点紧张", "不太熟", "有点孤单", "有点想家", "有点低落",
           "不太合群", "文化有点不一样", "不太敢开口"]:
    _NEGATIVE_WEIGHTED[_w] = (1, "general")

# --- L2 中度（权重×2）---
_l2_negatives = {
    "焦虑": "anxiety", "压力大": "academic", "压力好大": "academic",
    "失眠": "mood", "睡不着": "mood", "睡不好": "mood",
    "孤独": "social", "迷茫": "mood", "崩溃": "mood",
    "烦躁": "anxiety", "害怕": "anxiety", "担心": "anxiety",
    "难过": "mood", "伤心": "mood", "失望": "mood",
    "生气": "mood", "讨厌": "mood", "痛苦": "mood",
    "紧张": "anxiety", "无助": "mood", "恐惧": "anxiety",
    "沮丧": "mood", "压抑": "mood", "委屈": "mood",
    "后悔": "mood", "疲惫": "mood", "低落": "mood",
    # 留学生专属 L2
    "挂科": "academic", "退学": "academic", "跟不上了": "academic",
    "听不懂课": "academic", "GPA掉了": "academic", "成绩下滑": "academic",
    "文化冲击": "cultural", "不适应这里": "cultural", "语言障碍": "cultural",
    "种族歧视": "cultural", "被区别对待": "cultural",
    "没朋友": "social", "融不进去": "social", "被孤立": "social",
    "没人玩": "social", "交不到朋友": "social",
    "家人不理解": "cultural", "父母施压": "cultural", "花了家里很多钱": "cultural",
    "签证出问题": "cultural", "签证焦虑": "cultural",
}
for w, dim in _l2_negatives.items():
    _NEGATIVE_WEIGHTED[w] = (2, dim)

# --- L3 重度（权重×3）---
_l3_negatives = {
    "绝望": "mood", "无望": "mood", "快撑不住了": "mood",
    "我撑不下去了": "mood", "快要疯了": "mood", "精神崩溃": "mood",
    "极度焦虑": "anxiety", "恐慌": "anxiety", "心悸": "anxiety",
    "完全孤立": "social", "没人可以说话": "social", "与世隔绝": "social",
    "读不下去了": "academic", "毕不了业": "academic",
    "适应不了": "cultural", "完全无法融入": "cultural", "格格不入": "cultural",
}
for w, dim in _l3_negatives.items():
    _NEGATIVE_WEIGHTED[w] = (3, dim)

# ── 积极信号词（二级强度）──
_WEAK_POSITIVE = ["还好", "还行", "OK", "ok", "过得去", "凑合", "一般般", "就那样", "马马虎虎"]
_STRONG_POSITIVE = [
    "开心", "高兴", "喜欢", "很棒", "很好", "真好", "好棒", "不错", "顺利", "感谢", "谢谢", "期待",
    "兴奋", "成功", "通过", "录取", "offer", "优秀", "加油", "恭喜", "太棒了",
    "交到朋友", "有进步", "进步很大", "适应了", "习惯了", "有意思",
    "nice", "great", "awesome", "happy", "love", "wonderful", "fantastic",
]


def _has_negation_before(content: str, pos: int, window: int = 5) -> bool:
    """检测关键词前面是否有否定词（在 window 个字符内）"""
    before = content[max(0, pos - window):pos]
    for nw in _NEGATION_WORDS:
        if nw in before:
            return True
    return False


def _get_intensity_modifier(content: str, kw_pos: int, keyword_len: int, window: int = 8) -> float:
    """检测关键词附近是否有强度修饰词，返回 0.5~1.5 的系数"""
    start = max(0, kw_pos - window)
    end = min(len(content), kw_pos + keyword_len + window)
    nearby = content[start:end]
    for w in _INTENSIFIERS:
        if w in nearby:
            return 1.5
    for w in _WEAKENERS:
        if w in nearby:
            return 0.5
    return 1.0


def analyze_emotion_keywords(content: str) -> dict:
    """
    服务端本地情绪分析 — 分层关键词检测 + 留学生专项。
    作为 LLM 情绪分析的兜底/补充方案。

    参数:
        content: 学生消息文本

    返回:
        {
          "tag": str, "score": int(0-100),
          "dimensions": {mood, anxiety, social, academic, cultural},
          "flags": {suicide_risk, self_harm, hopelessness, social_withdrawal,
                    sleep_issue, panic_attack, eating_issue},
          "keywords": list, "severity_note": str, "method": "keyword"
        }
    """
    content = content.lower()  # 大小写不敏感匹配
    keywords = []
    tag = "正常"
    score = 75  # 中性偏积极
    flags = {
        "suicide_risk": False, "self_harm": False, "hopelessness": False,
        "social_withdrawal": False, "sleep_issue": False, "panic_attack": False,
        "eating_issue": False,
    }
    dimensions = {"mood": 25, "anxiety": 25, "social": 25, "academic": 25, "cultural": 25}
    severity_note = ""

    # ================================================
    # 优先级 1：危机短语匹配（绕过所有否定检测）
    # ================================================
    for phrase in _CRITICAL_PHRASES:
        if phrase in content:
            keywords.append(phrase)
            score = 5
            tag = "高危"
            flags["suicide_risk"] = True
            flags["hopelessness"] = True
            dimensions = {"mood": 90, "anxiety": 80, "social": 60, "academic": 50, "cultural": 50}
            severity_note = f"关键词引擎检测到危机短语：{phrase}"
            return {
                "tag": tag,
                "score": score,
                "dimensions": dimensions,
                "flags": flags,
                "keywords": [phrase],
                "severity_note": severity_note,
                "method": "keyword",
            }

    # ================================================
    # 优先级 2：分层负面词匹配 + 否定检测 + 强度修饰
    # ================================================
    weighted_neg_hits = []  # [(word, weight, dimension_hint, position)]
    weighted_pos_hits = []

    for word, (weight, dim_hint) in _NEGATIVE_WEIGHTED.items():
        idx = content.find(word)
        if idx >= 0:
            # 否定检测
            if _has_negation_before(content, idx):
                continue  # "没有不开心" → 跳过
            intensity = _get_intensity_modifier(content, idx, len(word))
            weighted_neg_hits.append((word, weight * intensity, dim_hint, idx))

    for word in _STRONG_POSITIVE:
        idx = content.find(word)
        if idx >= 0:
            if _has_negation_before(content, idx):
                continue
            weighted_pos_hits.append((word, 2.0, idx))

    for word in _WEAK_POSITIVE:
        idx = content.find(word)
        if idx >= 0:
            if _has_negation_before(content, idx):
                continue
            weighted_pos_hits.append((word, 0.5, idx))

    # ================================================
    # 优先级 3：专项风险信号检测
    # ================================================
    _sleep_words = ["失眠", "睡不着", "睡不好", "噩梦", "嗜睡", "睡眠"]
    _panic_words = ["心慌", "胸闷", "喘不过气", "濒死感", "手脚发麻", "头晕目眩"]
    _eating_words = ["吃不下", "暴食", "没胃口", "体重骤降", "厌食"]
    _social_words = ["没朋友", "融不进去", "被孤立", "没人玩", "不出门", "不回复消息", "躲着"]
    _hopeless_words = ["绝望", "无望", "看不到希望", "永远好不起来", "不会好了"]

    for w in _sleep_words:
        if w in content:
            flags["sleep_issue"] = True
            keywords.append(w)
            break
    for w in _panic_words:
        if w in content:
            flags["panic_attack"] = True
            keywords.append(w)
            break
    for w in _eating_words:
        if w in content:
            flags["eating_issue"] = True
            keywords.append(w)
            break
    for w in _social_words:
        if w in content:
            flags["social_withdrawal"] = True
            keywords.append(w)
            break
    for w in _hopeless_words:
        if w in content:
            flags["hopelessness"] = True
            keywords.append(w)
            break

    # ================================================
    # 综合评分
    # ================================================
    if weighted_neg_hits:
        # 取加权分最高的前 5 个负面词
        weighted_neg_hits.sort(key=lambda x: x[1], reverse=True)
        top_neg = weighted_neg_hits[:5]
        keywords.extend([w for w, _, _, _ in top_neg])

        # 计算总分：基准 75 - 加权负面分累计
        total_neg_weight = sum(w for _, w, _, _ in weighted_neg_hits)
        score = max(5, 75 - min(70, int(total_neg_weight * 10)))

        # 确定主情绪标签
        if flags.get("suicide_risk"):
            tag = "高危"
        elif flags.get("hopelessness"):
            tag = "低落"
        elif any("焦虑" in w or "紧张" in w or "害怕" in w or "恐慌" in w for w, _, _, _ in top_neg):
            tag = "焦虑"
        elif any("孤独" in w or "没朋友" in w or "孤立" in w for w, _, _, _ in top_neg):
            tag = "孤独"
        elif any("想家" in w or "文化" in w or "不适应" in w for w, _, _, _ in top_neg):
            tag = "适应困难"
        elif any("挂科" in w or "退学" in w or "跟不上" in w for w, _, _, _ in top_neg):
            tag = "焦虑"
        else:
            tag = "低落"

        # 聚合维度分
        dim_accum = {"mood": 25, "anxiety": 25, "social": 25, "academic": 25, "cultural": 25}
        dim_counts = {"mood": 0, "anxiety": 0, "social": 0, "academic": 0, "cultural": 0}
        for _, wgt, dim_hint, _ in weighted_neg_hits:
            if dim_hint != "general":
                dim_accum[dim_hint] += wgt * 15
                dim_counts[dim_hint] += 1
            else:
                # general 关键词均匀分布到各维度
                for d in dim_accum:
                    dim_accum[d] += wgt * 5
        for d in dim_accum:
            if dim_counts[d] > 0:
                dim_accum[d] = min(95, dim_accum[d])
            else:
                dim_accum[d] = max(25, dim_accum[d] - 5)
        dimensions = dim_accum
    else:
        keywords = [w for w, _, _ in weighted_pos_hits[:5]]

    # 积极信号提升分数
    if weighted_pos_hits and not weighted_neg_hits:
        pos_boost = sum(w for _, w, _ in weighted_pos_hits[:3])
        score = min(100, 75 + int(pos_boost * 8))
        tag = "积极"

    # 混合信号
    if weighted_neg_hits and weighted_pos_hits:
        score = min(70, max(20, score))

    # 去重 keywords
    keywords = list(dict.fromkeys(keywords))[:8]

    # 生成 severity_note
    if score <= 30:
        severity_note = "关键词检测到多个负面信号，风险偏高"
    elif score <= 60:
        severity_note = "关键词检测到部分负面信号，需关注"
    elif score >= 80:
        severity_note = "关键词检测以积极信号为主"
    else:
        severity_note = "关键词检测结果正常"

    return {
        "tag": tag,
        "score": score,
        "dimensions": dimensions,
        "flags": flags,
        "keywords": keywords,
        "severity_note": severity_note,
        "method": "keyword",
    }


def merge_emotion_results(llm_result: dict, keyword_result: dict) -> dict:
    """
    融合 LLM 情感分析和关键词分析结果。
    LLM 结果优先（含多维度数据），关键词结果补充 flags / context_tags。

    参数:
        llm_result:     LLM analyze_emotion 返回结果（可能含 dimensions/flags/stage）
        keyword_result: 本地关键词分析结果（含 dimensions/flags/method）

    返回:
        融合后的完整情绪分析结果 dict
    """
    # ── LLM 在线 → 以 LLM 为准，关键词补充 flags 和 keywords ──
    if llm_result and llm_result.get("emotion"):
        merged = dict(llm_result)

        # 确保核心字段存在
        merged.setdefault("risk_score", 0)
        merged.setdefault("risk_level", "low")
        merged.setdefault("needs_alert", False)
        merged.setdefault("emotion", "正常")
        merged.setdefault("stage", "stable")
        merged.setdefault("dimensions", {"mood": 25, "anxiety": 25, "social": 25, "academic": 25, "cultural": 25})
        merged.setdefault("flags", {
            "suicide_risk": False, "self_harm": False, "hopelessness": False,
            "social_withdrawal": False, "sleep_issue": False, "panic_attack": False,
            "eating_issue": False,
        })
        merged.setdefault("protective", {})
        merged.setdefault("context_tags", [])
        merged.setdefault("severity_note", "")

        # 关键词补充：合并 keywords（去重）
        llm_kw = set(merged.get("keywords") or [])
        kw_kw = set(keyword_result.get("keywords") or [])
        merged["keywords"] = list(llm_kw | kw_kw)[:8]

        # 关键词补充：flags 取 OR（任一引擎检测到就标 true）
        kw_flags = keyword_result.get("flags", {})
        for flag_key in merged["flags"]:
            if kw_flags.get(flag_key):
                merged["flags"][flag_key] = True

        # 关键词补充：context_tags 合并去重
        kw_tags = keyword_result.get("context_tags") or keyword_result.get("keywords") or []
        merged["context_tags"] = list(set(merged.get("context_tags", []) + kw_tags))[:6]

        # 如果 LLM 没有给出 dimensions 但 keyword 有 → 用 keyword 的作为下限
        if not merged.get("dimensions") or all(v == 25 for v in merged["dimensions"].values()):
            kw_dims = keyword_result.get("dimensions", {})
            if kw_dims and any(v != 25 for v in kw_dims.values()):
                merged["dimensions"] = kw_dims

        # 确保 needs_alert 考虑 suicide_risk 和 hopelessness
        flags = merged.get("flags", {})
        if flags.get("suicide_risk") and not merged.get("needs_alert"):
            merged["needs_alert"] = True
            merged["alert_reason"] = merged.get("alert_reason") or "检测到自杀风险信号"
        if flags.get("hopelessness") and merged.get("risk_score", 0) >= 50 and not merged.get("needs_alert"):
            merged["needs_alert"] = True
            merged["alert_reason"] = merged.get("alert_reason") or "检测到绝望感信号且风险分>=50"

        return merged

    # ── LLM 不可用 → 用关键词结果转换为兼容格式 ──
    tag = keyword_result.get("tag", "正常")
    score = keyword_result.get("score", 75)
    keyword_risk = 100 - score  # 反转：关键词 score=积极分, risk_score=风险分

    if score <= 20:
        risk_level = "critical"
    elif score <= 40:
        risk_level = "high"
    elif score <= 60:
        risk_level = "medium"
    else:
        risk_level = "low"

    kw_flags = keyword_result.get("flags", {})
    needs_alert = (
        keyword_risk >= EMOTION_ALERT_THRESHOLD
        or kw_flags.get("suicide_risk", False)
        or (kw_flags.get("hopelessness", False) and keyword_risk >= 50)
    )

    alert_reason = ""
    if kw_flags.get("suicide_risk"):
        alert_reason = "关键词检测到自杀风险信号"
    elif kw_flags.get("hopelessness"):
        alert_reason = "关键词检测到绝望感信号"
    elif needs_alert:
        alert_reason = f"关键词检测风险分 {keyword_risk} >= {EMOTION_ALERT_THRESHOLD}"

    # 阶段估算
    if kw_flags.get("suicide_risk"):
        stage = "crisis"
    elif keyword_risk >= 60:
        stage = "warning"
    elif keyword_risk >= 35:
        stage = "fluctuating"
    else:
        stage = "stable"

    return {
        "emotion": tag,
        "risk_score": keyword_risk,
        "risk_level": risk_level,
        "stage": stage,
        "dimensions": keyword_result.get("dimensions", {"mood": 25, "anxiety": 25, "social": 25, "academic": 25, "cultural": 25}),
        "flags": kw_flags,
        "protective": {"has_support": False, "has_coping": False, "seeking_help": False, "future_oriented": False},
        "context_tags": [],
        "keywords": keyword_result.get("keywords", []),
        "severity_note": keyword_result.get("severity_note", ""),
        "needs_alert": needs_alert,
        "alert_reason": alert_reason,
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
    # 插入后再查一次确认；如果失败则返回构造的 dict
    return db.query_one(
        "SELECT * FROM mental_health_profile WHERE student_id = %s",
        (student_id,)
    ) or dict(default_data)


def update_profile(
    student_id: int,
    emotion: dict,
    user_msg: str,
) -> dict:
    """
    更新学生心理画像（mental_health_profile）。

    计算逻辑：
      - 追加当前情绪到 emotion_history（保留最近30条，含多维度数据）
      - 更新连续负面天数（consecutive_negative_days）
      - 更新负面关键词累计次数
      - 存储当前阶段（stage）

    参数:
        student_id: 学生ID
        emotion:    情绪分析结果（完整 dict，含 dimensions/flags/stage）
        user_msg:   当前学生消息（用于存储触发内容）

    返回:
        更新后的 mental_health_profile 行 dict
    """
    profile = get_or_create_profile(student_id)

    risk_score = emotion.get("risk_score", 0)
    risk_level = emotion.get("risk_level", "low")

    # 解析已有 emotion_history
    emotion_history = json.loads(profile.get("emotion_history", "[]") or "[]")

    # 追加当前情绪记录（含多维度数据）
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "emotion": emotion.get("emotion", ""),
        "score": risk_score,
        "stage": emotion.get("stage", "stable"),
        "dimensions": emotion.get("dimensions", {}),
        "flags": emotion.get("flags", {}),
        "trigger": user_msg[:100],
    }
    emotion_history.append(entry)
    emotion_history = emotion_history[-30:]  # 保留最近30条

    # 计算连续负面天数 / 关键词次数
    is_negative = risk_level not in ("low", "normal")
    new_cons = (profile.get("consecutive_negative_days") or 0) + 1 if is_negative else 0
    old_neg = profile.get("negative_keywords_count") or 0
    new_neg = old_neg + (1 if is_negative else 0)

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
    # 检查今天是否已有 pending 预警
    existing = db.query_one(
        """SELECT id, risk_level FROM mental_health_alert
           WHERE student_id = %s AND follow_up_status = 'pending'
           AND DATE(created_at) = CURDATE()""",
        (student_id,)
    )
    if existing:
        _severity = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        new_sev = _severity.get(emotion.get("risk_level", "high"), 1)
        old_sev = _severity.get(existing.get("risk_level", "medium"), 1)
        if new_sev <= old_sev:
            logger.info("今日已有同级或更高级预警(id=%s)，跳过重复创建", existing["id"])
            return None
        else:
            # 升级：将旧预警标记为 resolved，创建新的更高级预警
            logger.warning("⚠️ 预警升级：%s → %s, student=%d",
                           existing["risk_level"], emotion.get("risk_level"), student_id)
            db.update("mental_health_alert", {"id": existing["id"]},
                      {"follow_up_status": "resolved",
                       "action_taken": f"自动升级为 {emotion.get('risk_level')} 预警"})

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
        "critical": "\n\n🚨 我非常担心你。如果你有伤害自己的想法，请立即联系你所在学校的心理咨询中心或紧急求助热线——你不是一个人，有人愿意帮助你。",
        "high": "\n\n💙 我有些担心你。如果你愿意，可以和信任的老师或朋友聊聊，你不是一个人在面对这些。",
        "medium": "\n\n💪 听起来你最近压力不小，照顾好自己，需要的话我随时在～",
    }
    return care_map.get(risk_level, "")


def analyze_and_update(student_id: int, emotion: dict, user_msg: str) -> str:
    """
    完整情绪处理流水线：更新画像 → 多条件预警判断 → 返回关怀文本。

    预警条件（满足任一即触发）：
      1. risk_score >= EMOTION_ALERT_THRESHOLD（默认70）且 needs_alert
      2. flags.suicide_risk == true（无条件触发）
      3. flags.hopelessness == true 且 risk_score >= 50
      4. stage == "crisis"
      5. 连续负面天数 >= 7

    参数:
        student_id: 学生ID
        emotion:    情绪分析结果（完整版，含 dimensions/flags/stage）
        user_msg:   学生原始消息

    返回:
        关怀文本（追加到最终回复中）；空字符串表示无额外关怀
    """
    risk_score = emotion.get("risk_score", 0)
    risk_level = emotion.get("risk_level", "low")
    flags = emotion.get("flags", {})
    stage = emotion.get("stage", "stable")

    # 更新心理画像
    profile = update_profile(student_id, emotion, user_msg)

    # ── 多条件预警判断 ──
    should_alert = False

    # 条件1：标准阈值
    if risk_score >= EMOTION_ALERT_THRESHOLD and emotion.get("needs_alert"):
        should_alert = True
        logger.info("预警触发：risk_score=%d >= %d", risk_score, EMOTION_ALERT_THRESHOLD)

    # 条件2：自杀风险（无条件触发）
    if flags.get("suicide_risk"):
        should_alert = True
        logger.warning("⚠️ 预警触发：检测到自杀风险信号！student=%d", student_id)

    # 条件3：绝望感 + 中度以上风险
    if flags.get("hopelessness") and risk_score >= 50:
        should_alert = True
        logger.warning("⚠️ 预警触发：绝望感信号 + risk_score=%d", risk_score)

    # 条件4：危机阶段
    if stage == "crisis":
        should_alert = True
        logger.warning("⚠️ 预警触发：阶段判定为 crisis")

    # 条件5：连续 7 天负面
    cons_days = profile.get("consecutive_negative_days", 0) if profile else 0
    if cons_days >= 7:
        should_alert = True
        logger.warning("⚠️ 预警触发：连续负面天数=%d", cons_days)

    if should_alert:
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
