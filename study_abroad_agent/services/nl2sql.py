"""
NL2SQL 服务
使用 LongCat-2.0 大模型将自然语言问题转换为可执行的 SQL 语句，
并在安全限制下执行、返回结果。
模型自动判断意图：查询 (SELECT) 或新增 (INSERT)。
"""
import re
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


_WRITE_FORBIDDEN = [
    "drop ", "truncate ", "delete ", "update ", "alter ",
    "create ", "replace ", "grant ", "revoke ",
]


def _build_prompt(question: str) -> str:
    """拼接给大模型的 prompt，包含表结构与约束。模型自动判断生成 SELECT 或 INSERT。"""
    schemas = "\n\n".join(TABLE_SCHEMAS.values())
    tables = ", ".join(config.NL2SQL_ALLOWED_TABLES)

    return f"""你是一个 MySQL 专家。根据用户的问题、数据库表结构和业务规则，自动判断意图并生成对应的 SQL 语句。

数据库表结构：
{schemas}

允许操作的表：{tables}

用户问题：{question}

要求：
1. 只返回纯 SQL 语句，不要任何解释、注释、Markdown 代码块、反引号或额外文本
2. 根据意图自动生成合适的 SQL：
   - 查询类（查询、搜索、列出、查看、有哪些、统计、帮我找）→ 生成 SELECT 语句
   - 新增类（新增、添加、插入、创建、记录、录入）→ 生成 INSERT 语句
3. SELECT 语句要求：
   - 只读查询，仅允许 SELECT / WITH...SELECT
   - 结果行数限定不超过 {config.NL2SQL_MAX_ROWS}，适时使用 LIMIT
   - 字符串值使用单引号
4. INSERT 语句要求：
   - 纯 INSERT，禁止包含 SELECT、WITH 等任何其他关键字
   - 禁止多条语句（语句内不允许分号）
   - 不要给自增主键 id 赋值，让数据库自动生成
   - 用户未提及的列不出现在 INSERT 中（使用默认值）
   - 字符串值使用单引号包裹，数值和 NULL 不加引号
5. 使用正确的表名和列名，不要使用不存在的列
6. 表名或列名含特殊字符时可用反引号包裹

SQL："""


def _extract_insert_table(sql: str) -> str:
    """从 INSERT 语句中提取表名（去除反引号）。"""
    m = re.match(r"insert\s+into\s+`?([a-zA-Z0-9_\-]+)`?", sql, re.IGNORECASE)
    if not m:
        raise ValueError("无法解析 INSERT 语句中的表名，仅允许向白名单表插入。")
    return m.group(1)


def _validate_sql(sql: str) -> str:
    """安全校验，自动判断 SQL 类型。返回 'query' 或 'insert'。不通过则抛出 ValueError。"""
    if not sql:
        raise ValueError("模型未生成 SQL")

    cleaned = sql.strip().rstrip(";").strip()
    lowered = cleaned.lower()

    if lowered.startswith("insert into"):
        _validate_insert(cleaned)
        return "insert"

    # 默认为 query
    _validate_query(cleaned)
    return "query"


def _validate_query(sql: str) -> None:
    """只读校验：只允许 SELECT / WITH 开头。"""
    cleaned = sql.strip().rstrip(";").strip()
    lowered = cleaned.lower()
    if lowered.startswith(("select", "with")):
        return
    for kw in _WRITE_FORBIDDEN:
        if kw in lowered:
            raise ValueError(f"禁止执行非只读语句，检测到关键字 '{kw.strip()}'。")
    raise ValueError("仅允许以 SELECT 或 WITH 开头的只读查询语句。")


def _validate_insert(sql: str) -> None:
    """INSERT 校验：单条 INSERT、表名在白名单、无禁用关键字、无多条语句。"""
    cleaned = sql.strip()
    # 禁止多条语句：剥离首尾空白后，若语句内部仍含分号则拒绝。
    if ";" in cleaned.strip(";").strip():
        raise ValueError("禁止一次执行多条语句（语句内不允许出现分号）。")
    cleaned = cleaned.rstrip(";").strip()
    lowered = cleaned.lower()

    if not lowered.startswith("insert into"):
        raise ValueError("INSERT 操作必须以 'INSERT INTO' 开头。")

    # 完整关键字禁令：SELECT/WITH 也禁掉，防止 INSERT ... SELECT 绕过。
    forbidden = ["select", "with"] + _WRITE_FORBIDDEN
    for kw in forbidden:
        if kw in lowered:
            raise ValueError(
                f"INSERT 语句中禁止出现 '{kw.strip()}'，仅允许单条纯 INSERT。"
            )

    # 表名白名单
    table = _extract_insert_table(cleaned)
    if table not in set(config.NL2SQL_ALLOWED_TABLES):
        raise ValueError(
            f"不允许向表 '{table}' 插入数据，仅允许：{config.NL2SQL_ALLOWED_TABLES}。"
        )


def run_nl2sql(question: str, include_sql: bool = False) -> dict:
    """
    主入口：自然语言 → SQL → 执行 → 结果字典。
    模型自动判断意图（query 走只读 SELECT；insert 走 INSERT，受 NL2SQL_ALLOW_WRITE 控制）。
    """
    prompt = _build_prompt(question)
    system_content = (
        "你是一个严谨的 MySQL 助手，根据用户问题自动判断是查询还是新增，只输出符合要求的纯 SQL 语句。"
    )

    client = _get_client()
    logger.info("[NL2SQL] 问题: %s", question)

    t0 = time.time()
    resp = client.chat.completions.create(
        model=config.LONGCAT_MODEL,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    raw_sql = (resp.choices[0].message.content or "").strip()
    logger.info("[NL2SQL] 原始输出: %s", raw_sql)

    # 清洗：去掉可能的 Markdown 围栏
    sql = raw_sql
    if sql.startswith("```"):
        lines = sql.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        sql = "\n".join(lines).strip()
    sql = sql.rstrip(";").strip()

    intent = _validate_sql(sql)
    logger.info("[NL2SQL] 自动判定意图: %s | 即将执行: %s", intent, sql)

    if intent == "insert" and not config.NL2SQL_ALLOW_WRITE:
        raise ValueError(
            "NL2SQL 写入功能未开启（config.NL2SQL_ALLOW_WRITE=False），"
            "如需启用请将其设为 True。"
        )

    result = {
        "question": question,
        "action": intent,
        "sql": sql if include_sql else None,
    }

    if intent == "insert":
        inserted_id = int(db.execute(sql) or 0)
        result["inserted_id"] = inserted_id
        result["affected_rows"] = 1 if inserted_id else 0
        elapsed_ms = (time.time() - t0) * 1000
        result["elapsed_ms"] = round(elapsed_ms, 2)
        logger.info("[NL2SQL] 完成 -> insert_id=%d, %.1f ms", inserted_id, elapsed_ms)
    else:
        rows = db.query(sql)
        row_count = len(rows)
        elapsed_ms = (time.time() - t0) * 1000
        result["rows"] = rows
        result["row_count"] = row_count
        result["elapsed_ms"] = round(elapsed_ms, 2)
        logger.info("[NL2SQL] 完成 -> %d 行, %.1f ms", row_count, elapsed_ms)

    return result
