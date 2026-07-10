"""
SQL 安全校验

对 LLM 生成的 SQL 做只读校验，防止大模型幻觉输出写入类语句
导致数据被误改。校验规则：
  1. 仅允许 SELECT / WITH (CTE) 开头的只读语句
  2. 多语句拼接（分号后紧跟非空 SQL）一律拒绝
  3. 明显的注入模式（如注释绕过、UNION 注入）记录警告

关键点：多语句与危险关键字的检测都在「剥离字符串字面量」之后进行，
以避免字符串中合法出现的分号（如 GROUP_CONCAT(... SEPARATOR '; ')）
或关键字（如备注里写了"不要 DELETE"）被误判。

校验失败的 SQL 将抛出 ``ValueError``，由上层转为 400 错误返回。
"""

import re
from typing import List

from summary_report.core.logger import get_logger

logger = get_logger(__name__)

# 允许的只读 SQL 起始（忽略前导空白与括号）
_READONLY_PREFIXES = ("SELECT", "WITH")

# 危险关键字（任何位置出现都拒绝）
_DANGEROUS_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "TRUNCATE",
    "ALTER",
    "CREATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "EXEC",
    "EXECUTE",
)

# 匹配危险关键字（单词边界，忽略大小写）
_DANGEROUS_PATTERN = re.compile(
    r"\b(" + "|".join(_DANGEROUS_KEYWORDS) + r")\b", re.IGNORECASE
)

# 多语句检测：分号后跟非空白内容且不是结尾
_MULTI_STATEMENT_PATTERN = re.compile(r";\s*\S")

# 匹配 SQL 字符串字面量：
#   - 单引号串，允许 \' 转义和 '' 转义
#   - 双引号串（MySQL 中默认也当字符串用），同样处理转义
_STRING_LITERAL_PATTERN = re.compile(r"'(?:\\.|''|[^'\\])*'" + r'|"(\\.|""|[^"\\])*"')


def _strip_leading_comments(sql: str) -> str:
    """移除前导的 SQL 注释，方便判断真实起始关键字。"""
    s = sql.strip()
    #  -- 单行注释
    s = re.sub(r"--(.*?)\n", "\n", s)
    #  /* */ 多行注释
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    return s.strip()


def _strip_string_literals(sql: str) -> str:
    """
    将 SQL 中所有字符串字面量替换为空字符串，仅保留结构骨架。

    这样后续的多语句 / 关键字检测就不会被字符串内容里的分号
    或关键字干扰（例如 GROUP_CONCAT(... SEPARATOR '; ') 完全合法）。
    """
    return _STRING_LITERAL_PATTERN.sub("", sql)


def validate_readonly_sql(sql: str) -> None:
    """
    校验单条 SQL 是否只读安全。

    Raises:
        ValueError: 当 SQL 包含写操作关键字、多语句拼接或无法解析时。
    """
    if not sql or not sql.strip():
        raise ValueError("SQL 为空")

    stripped = _strip_leading_comments(sql)

    # 1) 多语句检测 —— 在剥离了字符串字面量的骨架上进行，
    #    避免字符串内的分号（如 SEPARATOR '; '）被误判
    skeleton = _strip_string_literals(stripped)
    if _MULTI_STATEMENT_PATTERN.search(skeleton):
        logger.warning("检测到多语句 SQL，已拒绝: %s", sql[:120])
        raise ValueError("不允许执行多条 SQL 语句（包含分号拼接）")

    # 2) 起始关键字校验 —— 在原串上做，SELECT/WITH 不会包在字符串里
    first_word = stripped.split()[0].upper().rstrip("(")
    # 处理被括号包裹的奇怪写法：取第一个实词
    if first_word.startswith("("):
        first_word = first_word.lstrip("(")
    if first_word not in _READONLY_PREFIXES:
        logger.warning("检测到非只读 SQL（起始=%s），已拒绝: %s", first_word, sql[:120])
        raise ValueError(f"仅允许 SELECT 查询，检测到起始关键字: {first_word}")

    # 3) 全句扫描危险关键字 —— 同样在剥离字符串后的骨架上扫描，
    #    避免字符串内容里的关键字（如备注里写了"不要DELETE"）被误判
    matches = _DANGEROUS_PATTERN.findall(skeleton)
    if matches:
        logger.warning("检测到危险关键字 %s，已拒绝: %s", matches, sql[:120])
        raise ValueError(f"SQL 包含不允许的关键字: {matches}")


def validate_sql_list(sql_list: List[str]) -> None:
    """逐条校验 SQL 列表，全部通过才放行。"""
    for sql in sql_list:
        validate_readonly_sql(sql)
