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
        _client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=config.LLM_TIMEOUT,
        )
    return _client


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
