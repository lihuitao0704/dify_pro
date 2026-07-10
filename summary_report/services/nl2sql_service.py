"""
NL2SQL 通用服务：SQL 生成 → 安全校验 → 执行 → 结果润色。

这是整个报告系统的核心编排层。四个具体报告服务与通用 nl2sql
接口都通过本类（或本模块的便捷函数）完成完整的"问题→报告"流程。
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from summary_report.core.config import MAX_ROWS_FOR_POLISH, REPORT_MAX_CHARS
from summary_report.core.db import execute_sql
from summary_report.core.llm import call_llm
from summary_report.core.logger import get_logger
from summary_report.core.security import validate_sql_list
from summary_report.utils.common import clean_sql_list, remove_markdown_json_wrappers

logger = get_logger(__name__)


def generate_sql(
    question: str,
    schema: str,
    extra_instruction: str = "",
) -> List[str]:
    """
    使用 LLM 将自然语言问题转换为 SQL 语句数组。

    Args:
        question:         用户自然语言问题。
        schema:           该报告对应的表结构描述。
        extra_instruction: 额外的生成指令（如维度建议），追加到提示词末尾。

    Returns:
        SQL 字符串列表。

    Raises:
        ValueError: LLM 未生成有效 SQL 时抛出。
    """
    prompt = f"""
你是一个 MySQL 专家。根据用户的问题、数据库表结构，生成对应的 SQL 查询语句。

数据库表结构：
{schema}

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


def run_nl2sql_pipeline(
    question: str,
    schema: str,
    report_context: str = "",
    extra_instruction: str = "",
    skip_security: bool = False,
) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """
    端到端执行：生成 SQL → (安全校验) → 执行 → 润色，返回三元组。

    Args:
        question:         用户问题。
        schema:           表结构提示。
        report_context:   润色用报告背景。
        extra_instruction: 给 SQL 生成器的额外维度建议。
        skip_security:    是否跳过只读校验（仅接口层显式开启）。

    Returns:
        (sql_list, results, answer) 三元组。

    Raises:
        ValueError:        SQL 生成失败。
        Exception:        执行/润色失败时透传。
    """
    logger.info("[NL2SQL] 用户问题: %s", question)

    sql_list = generate_sql(question, schema, extra_instruction)
    logger.info("[NL2SQL] 生成 %d 条SQL", len(sql_list))

    if not skip_security:
        # 默认做只读校验，防止幻觉输出写入语句
        validate_sql_list(sql_list)

    results = execute_sql(sql_list)
    logger.info("[NL2SQL] 执行完成, 共 %d 组结果", len(results))

    answer = polish_report(question, results, report_context)
    logger.info("[NL2SQL] 润色完成, 长约 %d 字", len(answer))

    return sql_list, results, answer
