"""
大模型调用封装

基于 OpenAI 兼容协议（通义百练 DashScope），提供统一的
``call_llm`` 入口，屏蔽底层客户端差异。

实例化放在模块顶层，全局复用，避免每次请求重复创建连接。
"""

from openai import OpenAI

from summary_report.core.config import DASHSCOPE_API_KEY, LLM_BASE_URL, LLM_MODEL
from summary_report.core.logger import get_logger

logger = get_logger(__name__)

# 全局单例客户端，复用连接池
_client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=LLM_BASE_URL)


def call_llm(prompt: str, model: str = LLM_MODEL) -> str:
    """
    调用 LLM 并返回生成文本。

    Args:
        prompt: 发送给模型的完整提示词。
        model:  模型名称，默认使用配置中的 LLM_MODEL。

    Returns:
        模型返回的文本内容。

    Raises:
        Exception: 调用失败时向上抛出原始异常，并记录错误日志。
    """
    logger.debug("调用 LLM, model=%s, prompt长度=%d", model, len(prompt))
    try:
        completion = _client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = completion.choices[0].message.content or ""
        return content
    except Exception as exc:
        logger.error("LLM 调用失败: %s", exc, exc_info=True)
        raise
