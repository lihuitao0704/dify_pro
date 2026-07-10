"""
通用工具函数。

收集跨模块复用的纯函数，不依赖任何业务上下文。
"""

from typing import List


def remove_markdown_json_wrappers(text: str) -> str:
    """
    移除 LLM 常见的 ```json ... ``` 代码块包装。

    很多兼容 OpenAI 协议的模型在"返回 JSON"时会额外包裹 markdown
    代码块标记，这里做一层容错剥离。
    """
    text = text.strip()
    if text.startswith("```"):
        # 去掉首行 ```json 或 ```
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        # 去掉末尾 ```
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def clean_sql_list(sql_list: List[str]) -> List[str]:
    """
    清洗 LLM 返回的 SQL 列表：去空白、去空串。

    某些模型会返回带前后引号的单个 JSON 字符串，这里按字符串
    形式兜底保留，交由调用方判断。
    """
    return [s.strip() for s in sql_list if s and s.strip()]
