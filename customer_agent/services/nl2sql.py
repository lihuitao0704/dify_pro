"""
统一 NL2SQL 引擎

合并自:
  - study_abroad_agent/services/nl2sql.py              (安全校验 + 自动意图判断)
  - Event & Lecture Registration/Event_Lecture.py      (讲座/活动/报名相关 schema)

覆盖 7 张表:
  - user_profiles / courses / consultations           (留学业务)
  - lectures / activities                              (活动讲座)
  - lecture_registrations / activity_registrations     (报名记录)

特性:
  - 采用 LongCat-2.0 (OpenAI 兼容) 大模型
  - 自动识别 query (SELECT) 与 insert (INSERT) 意图
  - 严格白名单校验、单条语句、禁多条
  - 写操作受 config.NL2SQL_ALLOW_WRITE 开关控制
  - 可选 polished 模式：返回自然语言润色回答 (活动讲座场景)
"""
import re
import time
import logging
from typing import Optional
from openai import OpenAI

from customer_agent.config import config

log = logging.getLogger(__name__)

# 客户端延迟初始化（线程安全由 GIL+模块级变量保证首次正确性）
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )
    return _client


# 写操作关键字黑名单 (用于 query 校验)
_WRITE_FORBIDDEN = [
    "drop ", "truncate ", "delete ", "update ", "alter ",
    "create ", "replace ", "grant ", "revoke ",
]


def _build_prompt(question: str) -> str:
    """拼接给大模型的 prompt，包含 7 张表结构与约束。"""
    from customer_agent.schemas import TABLE_SCHEMAS  # 延迟加载，避免循环
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
   - 查询类（查询、搜索、列出、查看、有哪些、统计、帮我找、有没有）→ 生成 SELECT 语句
   - 新增类（新增、添加、插入、创建、记录、录入、报名、预约）→ 生成 INSERT 语句
3. SELECT 语句要求：
   - 只读查询，仅允许 SELECT / WITH...SELECT
   - 结果行数限定不超过 {config.NL2SQL_MAX_ROWS}，适时使用 LIMIT
   - 字符串值使用单引号
4. INSERT 语句要求：
   - 纯 INSERT，禁止包含 SELECT、WITH 等任何其他关键字
   - 禁止多条语句（语句内不允许分号）
   - 不要给自增主键 id 赋值，让数据库自动生成
   - 用户未提及的列不出现在 INSERT 中（使用默认值）
   - 字符串值使用单引号包裹，数值和 NULL 不加反引号
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
    if ";" in cleaned.strip(";").strip():
        raise ValueError("禁止一次执行多条语句（语句内不允许出现分号）。")
    cleaned = cleaned.rstrip(";").strip()
    lowered = cleaned.lower()

    if not lowered.startswith("insert into"):
        raise ValueError("INSERT 操作必须以 'INSERT INTO' 开头。")

    forbidden = ["select", "with"] + _WRITE_FORBIDDEN
    for kw in forbidden:
        if kw in lowered:
            raise ValueError(
                f"INSERT 语句中禁止出现 '{kw.strip()}'，仅允许单条纯 INSERT。"
            )

    table = _extract_insert_table(cleaned)
    if table not in set(config.NL2SQL_ALLOWED_TABLES):
        raise ValueError(
            f"不允许向表 '{table}' 插入数据，仅允许：{config.NL2SQL_ALLOWED_TABLES}。"
        )


def _build_polished(question: str, sql: str, rows) -> str:
    """对查询结果做自然语言润色 (活动讲座场景)。LLM 不可用时返回简单拼接。"""
    try:
        client = _get_client()
        content = f"用户问题：{question}\nSQL：{sql}\n查询结果：{rows}\n请用简洁自然的中文回答用户的问题。"
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是一个客服助手，根据查询结果用简洁自然中文回答。"},
                {"role": "user", "content": content},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        log.warning("[NL2SQL] polished 失败: %s", e)
        return ""


def run_nl2sql(
    question: str,
    include_sql: bool = False,
    polish: bool = False,
) -> dict:
    """
    主入口：自然语言 → SQL → 执行 → 结果字典。

    参数:
      question:    自然语言问题
      include_sql: 是否在响应中返回 SQL
      polish:      是否返回自然语言润色回答 (活动讲座场景)

    返回 dict:
      - question / action ("query"|"insert") / sql
      - query  → rows / row_count / elapsed_ms [+ polished?]
      - insert → inserted_id / affected_rows / elapsed_ms
    """
    from customer_agent.db import get_db

    prompt = _build_prompt(question)
    system_content = (
        "你是一个严谨的 MySQL 助手，根据用户问题自动判断是查询还是新增，"
        "只输出符合要求的纯 SQL 语句。"
    )

    client = _get_client()
    log.info("[NL2SQL] 问题: %s", question)

    t0 = time.time()
    resp = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    raw_sql = (resp.choices[0].message.content or "").strip()
    log.info("[NL2SQL] 原始输出: %s", raw_sql)

    sql = raw_sql
    if sql.startswith("```"):
        lines = sql.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        sql = "\n".join(lines).strip()
    sql = sql.rstrip(";").strip()

    intent = _validate_sql(sql)
    log.info("[NL2SQL] 自动判定意图: %s | 即将执行: %s", intent, sql)

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

    db = get_db()
    if intent == "insert":
        inserted_id = int(db.execute(sql) or 0)
        result["inserted_id"] = inserted_id
        result["affected_rows"] = 1 if inserted_id else 0
        elapsed_ms = (time.time() - t0) * 1000
        result["elapsed_ms"] = round(elapsed_ms, 2)
        log.info("[NL2SQL] 完成 -> insert_id=%d, %.1f ms", inserted_id, elapsed_ms)
    else:
        rows = db.query(sql)
        row_count = len(rows)
        elapsed_ms = (time.time() - t0) * 1000
        result["rows"] = rows
        result["row_count"] = row_count
        result["elapsed_ms"] = round(elapsed_ms, 2)
        if polish:
            result["polished"] = _build_polished(question, sql, rows)
        log.info("[NL2SQL] 完成 -> %d 行, %.1f ms", row_count, elapsed_ms)

    return result


def ensure_unique_constraints():
    """
    启动时确保所有业务表的唯一约束存在 (防重复插入的数据库层兜底)。
    合并自 Event_Lecture._ensure_unique_constraints。
    """
    from customer_agent.db import get_db
    constraints = [
        ("lecture_registrations", "uk_lecture_reg", "( lecture_id, name, phone )"),
        ("activity_registrations", "uk_activity_reg", "( activity_id, name, phone )"),
        ("lectures", "uk_lectures", "( title, event_time )"),
        ("activities", "uk_activities", "( title, event_time )"),
    ]
    db = get_db()
    for table, cname, cols in constraints:
        try:
            row = db.query_one(
                "SELECT COUNT(*) AS c FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND CONSTRAINT_NAME = %s",
                (table, cname),
            )
            if row and row["c"] > 0:
                continue
            try:
                db.execute(f"ALTER TABLE {table} ADD CONSTRAINT {cname} UNIQUE {cols}")
            except Exception:
                _deduplicate_table(db, table)
                db.execute(f"ALTER TABLE {table} ADD CONSTRAINT {cname} UNIQUE {cols}")
        except Exception as e:
            log.warning("[NL2SQL] 唯一约束检查失败 %s/%s: %s", table, cname, e)


def _deduplicate_table(db, table: str):
    """按各表业务键去重，保留第一条，删除后续重复行。"""
    dedupe_sql = {
        "lecture_registrations": "DELETE t1 FROM lecture_registrations t1 "
        "INNER JOIN lecture_registrations t2 WHERE t1.registration_id > t2.registration_id "
        "AND t1.lecture_id = t2.lecture_id AND t1.name = t2.name AND t1.phone = t2.phone",
        "activity_registrations": "DELETE t1 FROM activity_registrations t1 "
        "INNER JOIN activity_registrations t2 WHERE t1.registration_id > t2.registration_id "
        "AND t1.activity_id = t2.activity_id AND t1.name = t2.name AND t1.phone = t2.phone",
        "lectures": "DELETE t1 FROM lectures t1 INNER JOIN lectures t2 "
        "WHERE t1.lecture_id > t2.lecture_id AND t1.title = t2.title "
        "AND t1.event_time = t2.event_time",
        "activities": "DELETE t1 FROM activities t1 INNER JOIN activities t2 "
        "WHERE t1.activity_id > t2.activity_id AND t1.title = t2.title "
        "AND t1.event_time = t2.event_time",
    }
    sql = dedupe_sql.get(table)
    if sql:
        try:
            db.execute(sql)
        except Exception as e:
            log.warning("[NL2SQL] 去重失败 %s: %s", table, e)
