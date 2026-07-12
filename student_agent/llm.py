"""
LLM 能力层：对话 / 意图识别 / 情绪分析 / NL2SQL / 摘要 / 话术生成
可插拔：DeepSeek / Qwen / LongCat / OpenAI 等 OpenAI 兼容 API
"""

import json
import os
import logging
import re
from openai import OpenAI
from .config import LLM_CONFIG

logger = logging.getLogger(__name__)

# ============================================================
#  LLM 客户端
# ============================================================

_client: OpenAI | None = None
_online: bool | None = None


class LLMError(Exception):
    """LLM 调用失败异常"""


class LLMOfflineError(LLMError):
    """LLM 不可用（无 API Key 或网络不通）"""


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
    """基础对话，失败时抛出 LLMOfflineError"""
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
    except LLMError:
        raise
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        raise LLMOfflineError(f"LLM 调用失败: {e}") from e


def chat_stream(messages: list[dict], system_prompt: str = "", temperature: float = 0.7):
    """流式对话生成器，逐个 yield token 字符串"""
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    try:
        client = get_client()
        stream = client.chat.completions.create(
            model=LLM_CONFIG["model"],
            messages=full_messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except LLMError:
        raise
    except Exception as e:
        logger.error("LLM 流式调用失败: %s", e)
        raise LLMOfflineError(f"LLM 流式调用失败: {e}") from e


def chat_json(messages: list[dict], system_prompt: str = "", temperature: float = 0.3) -> dict | list:
    """对话并要求返回 JSON。LLM 不可用时抛出 LLMOfflineError"""
    raw = chat(messages, system_prompt, temperature)
    raw = raw.strip()
    # 提取第一个 JSON 代码块（可能前面有解释文字）
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        raw = m.group(1).strip()
    else:
        # 没有代码块标记：尝试提取最外层 { } 或 [ ]
        brack_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw)
        if brack_match:
            raw = brack_match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("LLM 返回非 JSON: %.200s", raw)
        raise LLMError(f"LLM 返回了无法解析的内容") from e


# ============================================================
#  意图识别
# ============================================================

INTENT_SYSTEM_PROMPT = """你是学生智能助手的意图识别模块。分析学生消息，识别所有意图。

9种意图类型：
1. leave       - 请假相关（想请假、请病假、请事假、查请假状态）
2. mental      - 心理情绪表达（焦虑、压力、孤独、难过、想家、失眠）
3. feedback    - 投诉/建议/反馈（不满意、投诉、提建议、有问题要反馈）
4. academic    - 学业考务（查考试、DDL、论文截止、选课、成绩查询、查分数）
5. progress    - 申请进度（留学申请到哪一步、offer状态、签证进度）
6. life_guide  - 海外生活指南（看病、租房、交通、银行卡、医保、紧急求助、活动、讲座）
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
                messages.append({"role": "system", "content": f"最近对话上下文。重要规则：如果当前消息看起来像是对上一轮的追问/继续（比如上一轮聊升学，这一轮说怎么联系/有没有项目/多少钱），意图必须跟上一轮保持一致：\n{ctx_text}"})
        messages.append({"role": "user", "content": user_msg})

        try:
            result = chat_json(messages, INTENT_SYSTEM_PROMPT)
            if isinstance(result, dict):
                result = [result]
            result.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            return result
        except Exception as e:
            logger.warning("意图识别降级至关键词模式: %s", e)

    # ── 降级：关键词匹配 ──
    return _keyword_intent(user_msg)


def _keyword_intent(user_msg: str) -> list[dict]:
    """关键词意图匹配（离线兜底）"""
    KEYWORD_MAP = [
        (["请假", "请个假", "休假", "病假", "事假"], "leave"),
        (["压力", "焦虑", "孤独", "难过", "想家", "失眠", "崩溃", "绝望", "累死了", "好累", "烦躁"], "mental"),
        (["投诉", "反馈", "建议改善", "不满意", "报修", "没人管", "太差"], "feedback"),
        (["考试", "DDL", "deadline", "论文", "截止", "选课", "成绩", "考务", "日程", "分数", "绩点", "gpa", "GPA"], "academic"),
        (["申请进度", "offer", "签证", "到哪一步", "流程走到"], "progress"),
        (["看病", "医院", "医保", "租房", "交通", "银行卡", "电话卡", "大使馆", "紧急", "活动", "讲座", "分享会", "见面会", "社团", "课程", "项目", "专业", "培训"], "life_guide"),
        (["读博", "读硕", "深造", "升学", "学历提升", "再读", "预约顾问", "联系顾问", "怎么申请", "有没有", "推荐"], "upgrade"),
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

EMOTION_PROMPT = """你是留学生心理健康评估专家。基于学生消息和情绪历史，进行多维度心理状态评估。

## 评估对象背景
中国留学生，在海外求学。常见压力源：学业难度、语言障碍、文化冲击、社交孤立、经济压力、家庭期望、签证焦虑、身份认同困惑。

## 一、情绪标签（选一个最准确的）
正常 / 焦虑 / 低落 / 孤独 / 适应困难 / 积极 / 愤怒 / 自我否定 / 思乡 / 疲惫 / 迷茫

## 二、五维度评分（每项 0-100，分数越高问题越严重）

| 维度 | 0-20 正常 | 21-40 轻度 | 41-60 中度 | 61-80 重度 | 81-100 极重 |
|------|----------|-----------|-----------|-----------|------------|
| **mood** 情绪基调 | 积极愉快 | 偶尔低落 | 持续低落、兴趣减退 | 明显抑郁、快感缺失 | 绝望、情感麻木 |
| **anxiety** 焦虑水平 | 放松平静 | 偶尔紧张 | 持续担忧、影响专注 | 严重焦虑、躯体化（心慌/手抖） | 恐慌发作、失控感 |
| **social** 社交连接 | 人际关系良好 | 偶尔感到孤单 | 社交减少、缺乏归属 | 明显孤立、回避社交 | 完全与社会脱节 |
| **academic** 学业压力 | 游刃有余 | 有一定压力 | 压力明显、担心挂科 | 不堪重负、想退学 | 学业崩溃、已放弃 |
| **cultural** 文化适应 | 融入当地 | 有些不适应 | 文化冲击明显、思乡 | 严重不适应、想回国 | 完全无法适应、敌视环境 |

评分原则：
- 基于学生原话推断，不要臆测
- 没有提到的维度给中间偏低的分数（25-35），不要给 0
- 有明确证据的维度才给高分
- 同时考虑情绪历史的演变趋势

## 三、阶段判定
- `stable` — 情绪平稳，无明显困扰
- `adapting` — 正在适应新环境，有轻度不适但属于正常范围
- `fluctuating` — 情绪有起伏，时好时坏，需要关注但整体可控
- `warning` — 持续恶化趋势，多维度亮红灯，需主动干预
- `crisis` — 当前处于心理危机状态，需立即介入

判定时请结合历史数据：如果连续多天负面 → 至少 `warning`；如果出现自杀意念 → 直接 `crisis`。

## 四、专项风险信号（true/false，必须谨慎判定）
- `suicide_risk` — **任何涉及死亡意愿/自杀/不想活的表达**（包括间接表达如"想消失""永远睡过去""不值得活着"）。最重要的一票，一旦触及必须标注 true
- `self_harm` — 自伤行为描述（割伤/撞墙/不吃饭惩罚自己等）
- `hopelessness` — 表达绝望/无助/看不到希望/觉得永远好不起来
- `social_withdrawal` — 明显回避社交/不出门/不回复消息
- `sleep_issue` — 提到失眠/噩梦/嗜睡/睡眠质量差
- `panic_attack` — 描述心慌/胸闷/呼吸困难/濒死感等惊恐症状
- `eating_issue` — 提到吃不下/暴食/体重骤变

## 五、保护因素（true/false，积极信号）
- `has_support` — 提到有家人/朋友/老师可以依靠
- `has_coping` — 有自己的应对方式（运动/音乐/写日记/兴趣爱好）
- `seeking_help` — 主动求助意愿（想找老师聊聊/想寻求帮助）
- `future_oriented` — 对未来有期待/正在做计划/提到目标

## 六、留学生情境标签（可多选，无则空数组）
可选：`学业压力` `语言障碍` `文化冲突` `社交孤立` `经济压力` `家庭期望` `签证焦虑` `身份困惑` `歧视经历` `思乡` `职业迷茫`

## 七、综合风险评分
- `risk_score`（0-100）：综合五维度 + 风险信号得出的整体风险分
- `risk_level`：low(0-30) / medium(31-60) / high(61-80) / critical(81-100)
- 有 `suicide_risk` 时 risk_score 至少 85，risk_level 至少 critical
- 有 `hopelessness` 时 risk_score 至少 60

## 八、预警与引导
- `needs_alert`：risk_score >= 70 或 suicide_risk == true 或 hopelessness == true 且 risk_score >= 50
- `alert_reason`：简短说明触发了哪个预警条件
- `severity_note`：50 字以内的综合判断（如"学业压力是主因，有社交退缩但无自伤风险，保护因素较好"）
- `response_guide`：给 AI 助手的回复策略建议（如何共情、引导什么话题、应避免什么）

## 输出格式
严格返回以下 JSON（不要 markdown 代码块标记）：
{
  "emotion": "焦虑",
  "risk_score": 55,
  "risk_level": "medium",
  "stage": "fluctuating",
  "dimensions": {"mood": 40, "anxiety": 70, "social": 50, "academic": 65, "cultural": 55},
  "flags": {"suicide_risk": false, "self_harm": false, "hopelessness": false, "social_withdrawal": true, "sleep_issue": true, "panic_attack": false, "eating_issue": false},
  "protective": {"has_support": true, "has_coping": false, "seeking_help": true, "future_oriented": true},
  "context_tags": ["学业压力"],
  "keywords": ["失眠", "跟不上", "听不懂"],
  "severity_note": "焦虑主要来自学业压力，有社交退缩迹象，但主动求助是积极信号",
  "needs_alert": false,
  "alert_reason": "",
  "response_guide": "先共情学业困难，肯定主动沟通的勇气，引导使用学校学习中心资源，避免空洞安慰"
}"""


def analyze_emotion(user_msg: str, history_emotions: list = None) -> dict:
    """情绪分析 → {emotion, risk_score, risk_level, keywords, needs_alert, ...}"""
    messages = [{"role": "user", "content": user_msg}]
    if history_emotions:
        hist = json.dumps(history_emotions, ensure_ascii=False)
        messages.insert(0, {"role": "system", "content": f"学生近期情绪历史：{hist}"})

    try:
        return chat_json(messages, EMOTION_PROMPT)
    except Exception:
        logger.warning("LLM 情绪分析失败，降级至关键词引擎")
        return {}  # 空 dict → merge_emotion_results 走关键词分支


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
        # 安全检查：禁止非 SELECT 操作和多语句注入
        dangerous = ["DROP", "DELETE", "ALTER", "TRUNCATE", "UPDATE", "INSERT",
                     "CREATE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "LOAD", "INTO"]
        upper = raw.upper()
        for word in dangerous:
            # 匹配独立单词（不是列名/表名的一部分）
            if re.search(rf"\b{word}\b", upper):
                return f"-- 安全限制：不允许 {word} 操作"
        # 检查多语句注入（分号后面有非空内容）
        parts = [p.strip() for p in raw.split(";")]
        non_empty = [p for p in parts if p]
        if len(non_empty) > 1:
            return "-- 安全限制：不允许执行多条SQL"
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


def agent_chat_stream(user_msg: str, context: list[dict], extra_instruction: str = ""):
    """流式 Agent 人格化回复"""
    system = AGENT_PERSONA
    if extra_instruction:
        system += f"\n\n本次回复额外要求：{extra_instruction}"
    messages = list(context[-10:]) + [{"role": "user", "content": user_msg}]
    yield from chat_stream(messages, system, temperature=0.7)
