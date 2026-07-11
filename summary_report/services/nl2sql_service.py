"""
NL2SQL 通用服务：SQL 生成 → 安全校验 → 执行 → 结果润色。

这是整个报告系统的核心编排层。四个具体报告服务与通用 nl2sql
接口都通过本类（或本模块的便捷函数）完成完整的"问题→报告"流程。
"""

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from summary_report.core.config import MAX_ROWS_FOR_POLISH, REPORT_MAX_CHARS
from summary_report.core.db import execute_sql, fetch_db_schema
from summary_report.core.llm import call_llm
from summary_report.core.logger import get_logger
from summary_report.core.security import validate_sql_list
from summary_report.core.sql_semantics import (
    auto_fix_sql_group_by,
    validate_sql_semantics,
)
from summary_report.utils.common import clean_sql_list, remove_markdown_json_wrappers

logger = get_logger(__name__)

# 真实库结构缓存：避免每条 SQL 请求都查 information_schema。
# 结构在进程生命周期内基本稳定，首次使用时加载一次即可。
_db_schema_cache: Dict[str, Set[str]] | None = None


def _load_db_schema() -> Dict[str, Set[str]] | None:
    """
    加载真实数据库表-列结构（带进程内缓存）。

    Returns:
        {table: {col, ...}, ...} 或 None（查询失败时降级为 schema 文本解析）。
    """
    global _db_schema_cache
    if _db_schema_cache is not None:
        return _db_schema_cache
    try:
        _db_schema_cache = fetch_db_schema()
        logger.info(
            "[NL2SQL] 加载真实库结构: %d 张表", len(_db_schema_cache)
        )
    except Exception as exc:
        # 查不到真实库结构时降级为 schema 文本解析，不中断查询流程
        logger.warning("[NL2SQL] 加载真实库结构失败(%s)，降级为 schema 文本解析", exc)
        # 用空 dict 作为标记避免反复查询失败
        _db_schema_cache = {}
    return _db_schema_cache


def render_db_schema_prompt(db_schema: Dict[str, Set[str]]) -> str:
    """
    将真实数据库结构渲染为 LLM 可读的 schema 描述文本。

    输出格式示例：

        以下是当前数据库的真实表结构（共来自 information_schema）：

        1. table_name
           - col1
           - col2
           - ...

    仅包含列名（不推断类型），因为 LLM 主要需要准确的表名/列名来生成 SQL。
    """
    if not db_schema:
        return "（未能加载数据库表结构）"

    lines = ["以下是当前数据库的真实表结构（来自 information_schema）：", ""]
    for tbl in sorted(db_schema):
        lines.append(f"{tbl}")
        for col in sorted(db_schema[tbl]):
            lines.append(f"  - {col}")
        lines.append("")
    return "\n".join(lines)


def filter_db_schema_by_tables(
    db_schema: Dict[str, Set[str]],
    table_whitelist: Set[str],
) -> Dict[str, Set[str]]:
    """
    按表名白名单过滤真实库结构，仅保留指定表。

    Args:
        db_schema:       完整库结构 {table: {col, ...}, ...}。
        table_whitelist: 需要保留的表名集合（大小写不敏感）。

    Returns:
        过滤后的 {table: {col, ...}, ...}，仅包含白名单中的表。
    """
    whitelist_lower = {t.lower() for t in table_whitelist}
    return {
        tbl: cols
        for tbl, cols in db_schema.items()
        if tbl.lower() in whitelist_lower
    }


def build_complaint_schema() -> str:
    """构建投诉处理周报的动态 schema（基于真实库结构过滤）。"""
    db_schema = _load_db_schema()
    if not db_schema:
        from summary_report.constants.schema_complaint import COMPLAINT_SCHEMA
        return COMPLAINT_SCHEMA

    whitelist = {
        "student_complaint",
        "student_feedback_ticket",
        "account",
    }
    filtered = filter_db_schema_by_tables(db_schema, whitelist)
    if not filtered:
        from summary_report.constants.schema_complaint import COMPLAINT_SCHEMA
        return COMPLAINT_SCHEMA

    return render_db_schema_prompt(filtered)


def build_mental_schema() -> str:
    """构建学生心理健康周报的动态 schema（基于真实库结构过滤）。"""
    db_schema = _load_db_schema()
    if not db_schema:
        from summary_report.constants.schema_mental import MENTAL_SCHEMA
        return MENTAL_SCHEMA

    whitelist = {
        "student_psych_record",
        "student_psych_profile",
        "student_mental_alert",
        "student_psych_alert",
        "student_mental_profile",
    }
    filtered = filter_db_schema_by_tables(db_schema, whitelist)
    if not filtered:
        from summary_report.constants.schema_mental import MENTAL_SCHEMA
        return MENTAL_SCHEMA

    return render_db_schema_prompt(filtered)


def generate_sql(
    question: str,
    schema: str,
    extra_instruction: str = "",
) -> List[str]:
    """
    使用 LLM 将自然语言问题转换为 SQL 语句数组。

    当真实库结构可用时，优先用真实库结构（information_schema）渲染 schema
    提示词，避免静态 schema 文本过时导致 LLM 生成引用不存在列的 SQL。

    Args:
        question:         用户自然语言问题。
        schema:           该报告对应的表结构描述（作为 fallback）。
        extra_instruction: 额外的生成指令（如维度建议），追加到提示词末尾。

    Returns:
        SQL 字符串列表。

    Raises:
        ValueError: LLM 未生成有效 SQL 时抛出。
    """
    # 优先用真实库结构替换过时的静态 schema 文本
    db_schema = _load_db_schema()
    if db_schema:
        schema_text = render_db_schema_prompt(db_schema)
    else:
        schema_text = schema

    prompt = f"""
你是一个 MySQL 专家。根据用户的问题、数据库表结构，生成对应的 SQL 查询语句。

数据库表结构：
{schema_text}

用户问题：{question}

{extra_instruction}

要求：
1. 只返回 JSON 格式的 SQL 字符串数组，不要任何解释、不要 markdown 代码块标记
2. 严格使用上述表结构中定义的字段名和表名，不要凭空编造字段
3. 涉及多表查询时使用 JOIN 关联，并写清楚 ON 条件
4. 聚合查询使用 GROUP BY
5. 如果有日期范围筛选，使用 BETWEEN 或 >= <=
6. 如果有同环比计算，使用子查询或窗口函数
7. 返回格式：["SELECT ... FROM ...", "SELECT ... FROM ..."]

JSON 格式示例：
["SELECT st.name, s.score FROM students st JOIN scores s ON st.id = s.student_id WHERE st.name = '张三'"]
"""
    raw = call_llm(prompt)
    text = remove_markdown_json_wrappers(raw)

    try:
        sql_list = json.loads(text)
    except json.JSONDecodeError:
        # 容错：可能是被包了一层字符串
        sql_list = [text.strip().strip('"').strip("'")]

    if isinstance(sql_list, str):
        sql_list = [sql_list]

    sql_list = clean_sql_list(sql_list)
    if not sql_list:
        raise ValueError("LLM 未生成有效的 SQL 语句")
    return sql_list


def _format_results_for_polish(all_results: List[Dict[str, Any]]) -> str:
    """将执行结果格式化为可读文本，供 LLM 润色使用。"""
    parts: List[str] = []
    for i, res in enumerate(all_results):
        if res["type"] == "SELECT":
            part = f"查询{i + 1} [{res['count']}条记录]:\n"
            part += f"SQL: {res['sql']}\n"
            part += f"列: {res['columns']}\n"
            rows = res["rows"]
            if rows:
                for row in rows[:MAX_ROWS_FOR_POLISH]:
                    part += f"  {list(row.values()) if isinstance(row, dict) else row}\n"
                if res["count"] > MAX_ROWS_FOR_POLISH:
                    part += f"  ...(共{res['count']}条,仅展示前{MAX_ROWS_FOR_POLISH}条)\n"
            else:
                part += "  (无结果)\n"
            parts.append(part)
        else:
            parts.append(
                f"操作{i + 1}: {res['type']} - 影响{res['affected_rows']}行\nSQL: {res['sql']}"
            )
    return "\n".join(parts)


def polish_report(
    question: str,
    all_results: List[Dict[str, Any]],
    report_context: str = "",
) -> str:
    """
    使用 LLM 将原始查询结果润色为专业报告。

    Args:
        question:      原始用户问题（帮助 LLM 理解意图）。
        all_results:   execute_sql 返回的结果列表。
        report_context: 报告背景描述，引导 LLM 输出对应业务口吻。

    Returns:
        润色后的报告文本。
    """
    formatted = _format_results_for_polish(all_results)
    prompt = f"""
你是一个专业的数据分析师和报告撰写助手。根据用户的问题、查询的数据结果，生成一份专业、详细的分析报告。

报告背景：
{report_context}

用户问题：{question}

数据查询结果：
{formatted}

要求：
1. 用专业的报告格式回答，包含标题、分点、数据支撑
2. 先给出核心结论（1-2句话概括）
3. 然后分维度详细分析数据
4. 对于有趋势的数据，指出变化方向和关键节点
5. 对于有异常的数据，标注风险点和关注事项
6. 最后给出可落地的建议
7. 不要解释SQL语句或技术细节
8. 字数控制在 {REPORT_MAX_CHARS} 字以内，保持简洁有力
9. 如果有同环比数据，明确指出增长/下降幅度
"""
    return call_llm(prompt).strip()


def _regenerate_sql_with_feedback(
    question: str,
    schema: str,
    bad_sql_list: List[str],
    error_message: str,
) -> List[str]:
    """
    将校验失败的 SQL 和错误原因反馈给 LLM，要求其修正后重新生成。

    与 generate_sql 一样，优先使用真实库结构渲染 schema，避免 LLM 持续
    根据过时的 schema 文本思考。

    Returns:
        修正后的 SQL 字符串列表。

    Raises:
        ValueError: LLM 仍未生成有效 SQL 时抛出。
    """
    db_schema = _load_db_schema()
    schema_text = render_db_schema_prompt(db_schema) if db_schema else schema

    bad_sql_block = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(bad_sql_list))
    prompt = f"""
你是一个 MySQL 专家。刚才你为以下问题生成的 SQL 语句在校验时发现了错误，请根据错误原因修正后重新生成。

用户问题：{question}

数据库表结构：
{schema_text}

刚才生成的有问题的 SQL：
{bad_sql_block}

校验错误原因：
{error_message}

请修正上述错误，重新生成正确的 SQL 语句数组。
要求：
1. 只返回 JSON 格式的 SQL 字符串数组，不要任何解释、不要 markdown 代码块标记
2. 严格遵循校验错误原因中的提示进行修正
3. 严格使用上述表结构中真实存在的字段名和表名
4. 返回格式：["SELECT ... FROM ...", "SELECT ... FROM ..."]
"""
    raw = call_llm(prompt)
    text = remove_markdown_json_wrappers(raw)

    try:
        sql_list = json.loads(text)
    except json.JSONDecodeError:
        sql_list = [text.strip().strip('"').strip("'")]

    if isinstance(sql_list, str):
        sql_list = [sql_list]

    sql_list = clean_sql_list(sql_list)
    if not sql_list:
        raise ValueError("LLM 修正后仍未生成有效的 SQL 语句")
    return sql_list


def run_nl2sql_pipeline(
    question: str,
    schema: str,
    report_context: str = "",
    extra_instruction: str = "",
    skip_security: bool = False,
    max_retries: int = 2,
) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """
    端到端执行：生成 SQL → 校验 → (失败则反馈重试) → 执行 → 润色，返回三元组。

    重试机制覆盖两道失败场景：
      1. 语义校验失败（表不存在 / 列不属于表 / 缺 GROUP BY）→ 反馈错误给 LLM 修正；
      2. SQL 执行报错（如 MySQL Unknown column）→ 将 DB 错误反馈给 LLM 修正。

    Args:
        question:          用户问题。
        schema:            表结构提示。
        report_context:    润色用报告背景。
        extra_instruction: 给 SQL 生成器的额外维度建议。
        skip_security:     是否跳过只读校验（仅接口层显式开启）。
        max_retries:        最大重试次数（每次将错误反馈给 LLM 修正）。

    Returns:
        (sql_list, results, answer) 三元组。

    Raises:
        ValueError:        SQL 生成失败或重试后仍无法通过校验/执行。
        Exception:        润色失败时透传。
    """
    logger.info("[NL2SQL] 用户问题: %s", question)

    sql_list = generate_sql(question, schema, extra_instruction)
    logger.info("[NL2SQL] 生成 %d 条SQL", len(sql_list))

    if not skip_security:
        # 默认做只读校验，防止幻觉输出写入语句
        validate_sql_list(sql_list)

    db_schema = _load_db_schema()
    last_error: Exception | None = None
    results: List[Dict[str, Any]] | None = None

    for attempt in range(1, max_retries + 1):
        # ── 关卡 0：自动修复 GROUP BY（程序化，无需 LLM）──────
        sql_list, group_by_fixed = auto_fix_sql_group_by(sql_list)
        if group_by_fixed:
            logger.info("[NL2SQL] 自动修复 GROUP BY 完成，重新校验")
            if not skip_security:
                validate_sql_list(sql_list)

        # ── 关卡 1：语义校验 ──────────────────────────────────
        try:
            validate_sql_semantics(sql_list, schema, db_schema=db_schema)
        except ValueError as exc:
            last_error = exc
            logger.warning(
                "[NL2SQL] 语义校验失败(第%d/%d): %s",
                attempt, max_retries, str(exc)[:100],
            )
            if attempt < max_retries:
                sql_list = _regenerate_sql_with_feedback(
                    question, schema, sql_list, str(exc)
                )
                if not skip_security:
                    validate_sql_list(sql_list)
                continue
            break  # 重试耗尽

        # ── 关卡 2：SQL 执行 ──────────────────────────────────
        try:
            results = execute_sql(sql_list)
            break  # 执行成功
        except ValueError as exc:
            last_error = exc
            logger.warning(
                "[NL2SQL] SQL 执行失败(第%d/%d): %s",
                attempt, max_retries, str(exc)[:100],
            )
            if attempt < max_retries:
                sql_list = _regenerate_sql_with_feedback(
                    question, schema, sql_list, str(exc)
                )
                if not skip_security:
                    validate_sql_list(sql_list)
                continue

    if results is None:
        raise ValueError(
            f"SQL 在重试 {max_retries} 次后仍无法通过校验/执行: {last_error}"
        )

    logger.info("[NL2SQL] 执行完成, 共 %d 组结果", len(results))

    answer = polish_report(question, results, report_context)
    logger.info("[NL2SQL] 润色完成, 长约 %d 字", len(answer))

    return sql_list, results, answer
