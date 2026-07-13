"""
LLM 能力层：通用对话 / JSON对话 / 结果润色
底层调用 LongCat-2.0（OpenAI 兼容协议）
"""

import json
import re
import time
from openai import OpenAI
from customer_agent.config import config

_client = None
_online = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        # 超时从 config 取（默认 8s 太短，config 已上调到 20s）；
        # max_retries=0 避免超时被 SDK 多次重试放大总耗时（8s×3 → 25s）。
        # 连接失败/429 仍由 SDK 内置重试兜底，这里只禁用读超时重试。
        _client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=config.LLM_TIMEOUT,
            max_retries=0,
        )
    return _client


def _invalidate_client():
    """供配置热更新时调用，下次 get_client() 重建连接。"""
    global _client
    _client = None


def is_online() -> bool:
    global _online
    if _online is None:
        key = config.LLM_API_KEY
        _online = bool(key and key not in ("", "your-api-key-here", "sk-xxx"))
    return _online


def chat(messages: list, system_prompt: str = "", temperature: float = 0.7) -> str:
    """基础对话"""
    full = []
    if system_prompt:
        full.append({"role": "system", "content": system_prompt})
    full.extend(messages)

    try:
        resp = get_client().chat.completions.create(
            model=config.LLM_MODEL,
            messages=full,
            temperature=temperature,
            max_tokens=1024,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        print(f"[LLM] 调用失败: {e}")
        return ""  # 返回空串，由调用方判断降级


def chat_json(messages: list, system_prompt: str = "", temperature: float = 0.3):
    """对话并要求返回 JSON"""
    raw = chat(messages, system_prompt, temperature)
    if raw == "[OFFLINE]":
        raise RuntimeError("LLM offline")
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    return json.loads(raw)


def polish(user_msg: str, raw_data: dict, context_hint: str = "") -> str:
    """把结构化数据润色为自然语言回复"""
    data_text = json.dumps(raw_data, ensure_ascii=False, default=str)[:2000]

    system = (
        "你是留学机构的客服助理。把下面的数据润色成一段友好自然的中文回复。\n"
        f"{context_hint}\n"
        "要求：不超过280字，不出现JSON/SQL/数据库等技术词汇，不要加前缀说明。"
    )
    prompt = (
        f"用户提问：「{user_msg}」\n"
        f"数据：{data_text}\n\n"
        "请润色为自然语言回复："
    )
    try:
        return chat([{"role": "user", "content": prompt}], system, temperature=0.6)
    except Exception:
        # 降级：返回数据的摘要
        return f"查询到 {len(raw_data)} 条相关记录，如需详细解答请继续提问～"



def agent_reply(user_msg: str, context: list, extra_instruction: str = "",
                 temperature: float = 0.7) -> str:
    """带人设的Agent回复，LLM离线时返回空串（调用方负责兜底）"""
    from customer_agent.persona import CUSTOMER_SERVICE_PERSONA
    system = CUSTOMER_SERVICE_PERSONA
    if extra_instruction:
        system += f"\n\n额外要求：{extra_instruction}"
    msgs = list(context[-10:]) + [{"role": "user", "content": user_msg}]
    result = chat(msgs, system, temperature=temperature)
    return result if result else ""


# ── 轻量化 FAQ/检索改写（无人设 prompt，降低 token、提升速度）────────────────
# 人设 prompt ~1500 字，FAQ 改写根本不需要身份/业务能力/话术示例，只保留
# "禁止原样输出"这一核心约束即可。实测 6-7s 而非 25s 超时。
_REWRITE_SYSTEM = (
    "你是留学机构的客服助理。参考材料来自内部知识库/FAQ，"
    "请用自己的话重新组织成一段自然、简洁的中文回答：\n"
    "· 直接回答结论，不整段照搬材料原文\n"
    "· 金额/时间/数字必须精确到材料中的数字，没有就不写\n"
    "· 材料没覆盖时，诚实告知可联系顾问获取详细信息\n"
    "· 不超过 280 字，不出现 JSON/SQL 等技术词汇"
)

# FAQ 改写结果缓存 {cache_key: polished_text}，避免同题重复调 LLM
_rewrite_cache: dict = {}


def rewrite_retrieval(user_msg: str, docs: list, style: str = "faq",
                      use_cache: bool = True) -> str:
    """轻量改写入口：无人设 prompt，仅用检索材料 + 风格规则。

    Args:
        user_msg:   用户原始问题
        docs:       检索得到的材料片段 list[str]
        style:      改写风格 ("faq" | "company_info" | "company_service" | "study_policy")
        use_cache:  是否启用结果缓存（默认开启）

    Returns:
        LLM 改写后的自然语言；LLM 不可用时返回 "" (调用方负责兜底)
    """
    cache_key = None
    if use_cache and docs:
        cache_key = style + "::" + str(hash(user_msg + "\n".join(docs)))
        cached = _rewrite_cache.get(cache_key)
        if cached is not None:
            return cached

    ctx_text = "\n\n".join(docs)
    # 风格细化规则（只追加风格差异部分，保持 system 精简）
    style_tip = ""
    if style == "company_info":
        style_tip = "融合成一段有温度的公司介绍，像聊天一样自然。"
    elif style == "company_service":
        style_tip = "具体说明服务项目，可增加业务名、适合人群、价格区间。"
    elif style == "study_policy":
        style_tip = "按维度（语言要求/院校门槛/签证/就业）分点说明。"
    # else: faq 用默认规则即可

    prompt = (
        f"参考材料:\n{ctx_text}\n\n"
        f"用户问题:「{user_msg}」\n"
        f"{style_tip}"
    )
    result = chat(
        [{"role": "user", "content": prompt}],
        _REWRITE_SYSTEM,
        temperature=0.5,
    )
    if result and cache_key is not None:
        # 限制缓存条目数，避免内存膨胀
        if len(_rewrite_cache) > 500:
            _rewrite_cache.clear()
        _rewrite_cache[cache_key] = result
    return result if result else ""


def clear_rewrite_cache():
    """供知识库重载后调用，避免改写用的是过期材料。"""
    _rewrite_cache.clear()
