"""
LLM 能力层：对话 / 意图识别 / 情绪分析 / NL2SQL / 摘要 / 话术生成
可插拔：DeepSeek / Qwen / LongCat / OpenAI 等 OpenAI 兼容 API
"""

import json
import os
import re
from openai import OpenAI
from .config import LLM_CONFIG

# ============================================================
#  LLM 客户端
# ============================================================

_client: OpenAI | None = None
_online: bool | None = None


def is_online() -> bool:
    """检测 LLM API 是否可用"""
    global _online
    if _online is None:
        key = os.getenv("LLM_API_KEY", LLM_CONFIG.get("api_key", ""))
        if not key or key in ("sk-your-api-key-here", "your-api-key-here", ""):
            _online = False
        else:
            _online = True  # 有 key 就当在线，调用时再报错
    return _online


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
        )
    return _client


def chat(messages: list[dict], system_prompt: str = "", temperature: float = 0.7) -> str:
    """基础对话，失败时返回 OFFLINE 标记"""
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=LLM_CONFIG["model"],
            messages=full_messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[LLM] 调用失败: {e}")
        return "[OFFLINE]"


def chat_json(messages: list[dict], system_prompt: str = "", temperature: float = 0.3) -> dict | list:
    """对话并要求返回 JSON"""
    raw = chat(messages, system_prompt, temperature)
    if raw == "[OFFLINE]":
        raise RuntimeError("LLM offline")
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ============================================================
#  意图识别
# ============================================================

INTENT_SYSTEM_PROMPT = """你是学生智能助手的意图识别模块。分析学生消息，识别所有意图。

9种意图类型：
1. leave       - 请假相关（想请假、请病假、请事假、查请假状态）
2. mental      - 心理情绪表达（焦虑、压力、孤独、难过、想家、失眠）
3. feedback    - 投诉/建议/反馈（不满意、投诉、提建议、有问题要反馈）
4. academic    - 学业考务（查考试、DDL、论文截止、选课、成绩查询）
5. progress    - 申请进度（留学申请到哪一步、offer状态、签证进度）
6. life_guide  - 海外生活指南（看病、租房、交通、银行卡、医保、紧急求助）
7. upgrade     - 升学意向（想读硕、想读博、继续深造、学历提升）
8. nl2sql      - 数据查询（查我的记录、统计、我的xxx有多少）
9. chat        - 日常闲聊（打招呼、感谢、天气、其他非业务对话）

一条消息可能包含多个意图。请提取每个意图的参数。

返回格式：
[
  {"intent": "leave", "confidence": 0.95, "params": {"leave_type": "病假", "duration": "2天"}},
  {"intent": "mental", "confidence": 0.8, "params": {"emotion": "压力大"}}
]

只返回 JSON 数组。如果只有一个意图，数组长度就是1。"""


def classify_intent(user_msg: str, context: list[dict] = None) -> list[dict]:
    """意图分类：LLM优先，失败降级关键词规则"""
    if is_online():
        messages = []
        if context:
            recent = [m for m in context[-6:] if m.get("role") in ("user", "assistant")]
            if recent:
                ctx_text = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in recent])
                messages.append({"role": "system", "content": f"最近对话上下文：\n{ctx_text}"})
        messages.append({"role": "user", "content": user_msg})

        try:
            result = chat_json(messages, INTENT_SYSTEM_PROMPT)
            if isinstance(result, dict):
                result = [result]
            result.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            return result
        except Exception as e:
            print(f"[LLM] 意图识别降级至关键词模式: {e}")

    # ── 降级：关键词匹配 ──
    return _keyword_intent(user_msg)


def _keyword_intent(user_msg: str) -> list[dict]:
    """关键词意图匹配（离线兜底）"""
    KEYWORD_MAP = [
        (["请假", "请个假", "休假", "病假", "事假"], "leave"),
        (["压力", "焦虑", "孤独", "难过", "想家", "失眠", "崩溃", "绝望", "累死了", "好累", "烦躁"], "mental"),
        (["投诉", "反馈", "建议改善", "不满意", "报修", "没人管", "太差"], "feedback"),
        (["考试", "DDL", "deadline", "论文", "截止", "选课", "成绩", "考务", "日程"], "academic"),
        (["申请进度", "offer", "签证", "到哪一步", "流程走到"], "progress"),
        (["看病", "医院", "医保", "租房", "交通", "银行卡", "电话卡", "大使馆", "紧急"], "life_guide"),
        (["读博", "读硕", "深造", "升学", "学历提升", "再读"], "upgrade"),
        (["查", "记录", "统计", "有多少", "帮我看看", "显示"], "nl2sql"),
    ]
    matched = []
    for keywords, intent in KEYWORD_MAP:
        for kw in keywords:
            if kw in user_msg:
                matched.append({"intent": intent, "confidence": 0.85, "params": {}})
                break
    if not matched:
        matched.append({"intent": "chat", "confidence": 0.6, "params": {}})
    return matched


# ============================================================
#  情绪分析
# ============================================================

EMOTION_PROMPT = """你是学生心理状态评估专家。分析学生消息中的情绪信号，评估心理健康风险。

情绪标签（选一个）：正常、焦虑、低落、孤独、适应困难、积极、愤怒、自我否定

风险评分规则（0-100）：
- 0-20: 正常/积极，无负面信号
- 21-40: 轻度不适，短暂负面情绪
- 41-60: 中度困扰，持续负面情绪，影响日常生活
- 61-80: 高度风险，表达强烈痛苦/绝望/自我否定
- 81-100: 危急，有自伤/伤人倾向

风险等级：low(0-30) / medium(31-60) / high(61-80) / critical(81-100)

返回 JSON：
{
  "emotion": "焦虑",
  "risk_score": 45,
  "risk_level": "medium",
  "keywords": ["失眠", "压力大", "睡不着"],
  "needs_alert": false,
  "alert_reason": "",
  "response_guide": "给予共情，询问是否需要和老师聊聊"
}

needs_alert 为 true 当 risk_score >= 70。
response_guide 是给 Agent 回复时的情绪引导建议。"""


def analyze_emotion(user_msg: str, history_emotions: list = None) -> dict:
    """情绪分析 → {emotion, risk_score, risk_level, keywords, needs_alert, ...}"""
    messages = [{"role": "user", "content": user_msg}]
    if history_emotions:
        hist = json.dumps(history_emotions, ensure_ascii=False)
        messages.insert(0, {"role": "system", "content": f"学生近期情绪历史：{hist}"})

    try:
        return chat_json(messages, EMOTION_PROMPT)
    except Exception:
        return {
            "emotion": "正常", "risk_score": 0, "risk_level": "low",
            "keywords": [], "needs_alert": False, "alert_reason": "",
            "response_guide": "正常回复",
        }


# ============================================================
#  智能摘要
# ============================================================

SUMMARY_PROMPT = """你是一个工单摘要生成器。将学生的长篇反馈/投诉提炼为简洁的工单摘要。

要求：
1. 50-150字
2. 包含：问题类型、核心诉求、紧急程度
3. 只返回摘要文本，不要其他内容"""


def summarize(long_text: str) -> str:
    """长篇投诉 → 工单摘要"""
    try:
        return chat([{"role": "user", "content": long_text}], SUMMARY_PROMPT, temperature=0.3)
    except Exception:
        return long_text[:150]


# ============================================================
#  分类
# ============================================================

CATEGORY_PROMPT = """将学生反馈分类到以下类别之一：
签证办理 / 院校申请 / 生活服务 / 教学质量 / 其他

只返回类别名称。"""


def classify_category(content: str) -> str:
    """投诉内容 → 工单分类"""
    try:
        result = chat([{"role": "user", "content": content}], CATEGORY_PROMPT, temperature=0.1)
        return result.strip()
    except Exception:
        return "其他"


# ============================================================
#  NL2SQL
# ============================================================

def generate_sql(question: str, schema_text: str) -> str:
    """自然语言 → SQL"""
    prompt = f"""你是 MySQL 专家。根据表结构和用户问题，生成一条 SQL。

表结构：
{schema_text}

用户问题：{question}

要求：
1. 只生成 SELECT 语句（安全限制）
2. 使用 student_id 过滤时注意关联正确的表
3. 如果问"我的xxx"，用 student_id = 提问者的ID
4. 只返回纯 SQL 语句，不要解释
"""
    try:
        raw = chat([{"role": "user", "content": prompt}], temperature=0.1)
        raw = raw.strip()
        raw = re.sub(r"^```(?:sql)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.rstrip(";")
        # 安全检查
        dangerous = ["DROP", "DELETE", "ALTER", "TRUNCATE", "UPDATE", "INSERT"]
        for word in dangerous:
            if raw.upper().startswith(word):
                return f"-- 安全限制：不允许 {word} 操作"
        return raw
    except Exception as e:
        return f"-- SQL生成失败: {e}"


def polish_answer(question: str, sql: str, data: list[dict]) -> str:
    """查询结果 → 自然语言回答"""
    if not data:
        return "没有查到相关记录～"

    prompt = f"""你是友好的学生助手。将查询结果转成自然语言回答。

用户问题：{question}
SQL: {sql}
结果（前20条）：{json.dumps(data[:20], ensure_ascii=False, default=str)}

要求：简洁口语化，200字以内，不说技术细节。"""
    try:
        return chat([{"role": "user", "content": prompt}], temperature=0.5)
    except Exception:
        return f"查到 {len(data)} 条记录"


# ============================================================
#  营销话术生成
# ============================================================

RECOMMEND_PROMPT = """你是留学顾问。根据学生画像生成个性化升学推荐话术。

要求：
1. 200-400字
2. 包含：学生背景点评、推荐项目、申请条件、下一步建议
3. 语气温暖专业，不夸张
"""


def generate_recommendation(student_profile: dict) -> str:
    """学生画像 → 个性化推荐话术"""
    profile_text = json.dumps(student_profile, ensure_ascii=False)
    try:
        return chat([{"role": "user", "content": f"学生画像：{profile_text}"}], RECOMMEND_PROMPT, temperature=0.7)
    except Exception:
        return "根据你的背景，我们有多项升学项目适合你，请联系顾问获取详细方案。"


# ============================================================
#  Agent 闲聊回复
# ============================================================

AGENT_PERSONA = """你是"小留同学"，一个温暖、专业、偶尔可爱的留学助手。

人设：
- 称呼学生为"同学"或"你"
- 语气亲切但不做作，专业但不冰冷
- 学生表达负面情绪时先共情，再引导
- 适当使用 emoji（每2-3条消息1-2个）
- 业务操作完成后清晰告知结果和下一步

禁止：
- 编造信息（不知道就说不知道，帮学生查）
- 超出留学服务范围的建议（法律/医疗诊断等）
- 长篇大论（回复控制在 300 字以内）"""


def agent_chat(user_msg: str, context: list[dict], extra_instruction: str = "") -> str:
    """Agent 人格化回复"""
    system = AGENT_PERSONA
    if extra_instruction:
        system += f"\n\n本次回复额外要求：{extra_instruction}"
    messages = list(context[-10:]) + [{"role": "user", "content": user_msg}]
    return chat(messages, system, temperature=0.7)
