"""
NL2SQL 服务
使用 LongCat-2.0 大模型将自然语言问题转换为可执行的 SQL 语句，
并在安全限制下执行、返回结果。
"""
import time
from openai import OpenAI
from study_abroad_agent.config import config
from study_abroad_agent.database import get_db, TABLE_SCHEMAS, db
from study_abroad_agent.utils.logger import logger

# 客户端在首次请求时延迟初始化
_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.LONGCAT_API_KEY,
            base_url=config.LONGCAT_BASE_URL,
        )
    return _client


def _build_prompt(question: str) -> str:
    """拼接给大模型的 prompt，包含表结构与约束。"""
    schemas = "\n\n".join(TABLE_SCHEMAS.values())
    return f"""你是一个 MySQL 数据库助手。请根据下面给出的表结构，将用户提出的自然语言问题转换为**一条**可执行的 MySQL SELECT 语句。

要求：
1. 只输出纯 SQL，不要任何解释、注释、Markdown、反引号或额外文本；
2. SQL 必须是**只读**的（仅允许使用 SELECT / WITH...SELECT），严禁包含 DROP、TRUNCATE、DELETE、UPDATE、INSERT、ALTER、CREATE 等写操作；
3. 只允许查询 user_profiles、courses、consultations 这三张表；
4. 字符串值请使用单引号；
5. 结果行数限定不超过 {config.NL2SQL_MAX_ROWS}，请在合适的时候使用 LIMIT；
6. 表名和列名严格按下面的建表语句，不要使用不存在的列。

建表语句：
{schemas}

用户问题：{question}
SQL："""


def _validate_sql(sql: str) -> None:
    """基础安全校验：只允许 SELECT / WITH 开头。不通过则抛出 ValueError。"""
    if not sql:
        raise ValueError("模型未生成 SQL")
    cleaned = sql.strip().rstrip(";").strip()
    lowered = cleaned.lower()
    if lowered.startswith(("select", "with")):
        return
    forbidden = [
        "drop ", "truncate ", "delete ", "update ", "insert ",
        "alter ", "create ", "replace ", "grant ", "revoke ",
    ]
    for kw in forbidden:
        if kw in lowered:
            raise ValueError(
                f"禁止执行非只读语句，检测到关键字 '{kw.strip()}'。"
            )
    raise ValueError("仅允许以 SELECT 或 WITH 开头的只读查询语句。")


def run_nl2sql(question: str, include_sql: bool = False) -> dict:
    """
    主入口：自然语言 → SQL → 执行 → 结果字典。
    """
    prompt = _build_prompt(question)

    client = _get_client()
    logger.info("[NL2SQL] 问题: %s", question)

    t0 = time.time()
    resp = client.chat.completions.create(
        model=config.LONGCAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是一个严谨的 MySQL SQL 生成助手，只输出符合要求的纯 SQL 语句。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    raw_sql = (resp.choices[0].message.content or "").strip()
    logger.info("[NL2SQL] 原始输出: %s", raw_sql)

    # 清洗：去掉可能的 Markdown 围栏和末尾分号
    sql = raw_sql
    if sql.startswith("```"):
        # 去掉 ```sql / ``` 围栏
        lines = sql.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        sql = "\n".join(lines).strip()
    sql = sql.rstrip(";").strip()

    _validate_sql(sql)
    logger.info("[NL2SQL] 即将执行: %s", sql)

    rows = db.query(sql)
    row_count = len(rows)
    elapsed_ms = (time.time() - t0) * 1000

    result = {
        "question": question,
        "rows": rows,
        "row_count": row_count,
        "elapsed_ms": round(elapsed_ms, 2),
    }
    if include_sql:
        result["sql"] = sql
    logger.info("[NL2SQL] 完成 -> %d 行, %.1f ms", row_count, elapsed_ms)
    return result
