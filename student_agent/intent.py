"""
意图路由：将意图列表映射到具体的处理函数
支持多意图拆分 → 按优先级逐个执行 → 聚合结果
"""

from .config import INTENT_CONFIDENCE_THRESHOLD

# ============================================================
#  意图优先级（数字越小越先处理）
# ============================================================

INTENT_PRIORITY = {
    "mental": 1,       # 情绪安全第一
    "leave": 2,        # 行政服务
    "feedback": 3,     # 投诉反馈
    "academic": 4,     # 学业查询
    "progress": 5,     # 进度查询
    "nl2sql": 6,       # 数据查询
    "life_guide": 7,   # 生活指南
    "upgrade": 8,      # 增值转化
    "chat": 9,         # 闲聊兜底
}

# ============================================================
#  意图描述（供 Agent 回复时引用）
# ============================================================

INTENT_NAMES = {
    "leave": "行政服务-请假",
    "mental": "心理关怀",
    "feedback": "售后反馈",
    "academic": "学业考务",
    "progress": "进度追踪",
    "life_guide": "生活支持",
    "upgrade": "增值转化",
    "nl2sql": "数据查询",
    "chat": "日常闲聊",
}


def sort_by_priority(intents: list[dict]) -> list[dict]:
    """按优先级排序意图列表"""
    return sorted(intents, key=lambda x: INTENT_PRIORITY.get(x["intent"], 99))


def filter_low_confidence(intents: list[dict]) -> list[dict]:
    """过滤低置信度意图，低于阈值的降级为 chat"""
    result = []
    has_high = False
    for item in intents:
        if item["confidence"] >= INTENT_CONFIDENCE_THRESHOLD:
            result.append(item)
            has_high = True

    if not has_high and intents:
        # 全部低置信度 → 保留最高那个，标记为 chat
        best = max(intents, key=lambda x: x.get("confidence", 0))
        best["intent"] = "chat"
        result = [best]

    return result


def is_multi_intent(intents: list[dict]) -> bool:
    """是否多意图（chat 不算）"""
    business = [i for i in intents if i["intent"] != "chat"]
    return len(business) > 1


def format_intent_summary(intents: list[dict]) -> str:
    """生成意图摘要（调试/日志用）"""
    parts = []
    for item in intents:
        name = INTENT_NAMES.get(item["intent"], item["intent"])
        conf = item.get("confidence", 0)
        parts.append(f"{name}({conf:.0%})")
    return " → ".join(parts)
