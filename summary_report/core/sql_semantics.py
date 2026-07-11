"""
SQL 语义校验（基于 schema 的轻量级静态分析）。

在 SQL 执行前拦截两类 LLM 幻觉错误：
  1. GROUP BY 一致性：含聚合函数 (COUNT/SUM/AVG/MAX/MIN) 但缺少 GROUP BY，
     且 SELECT 列表中存在非聚合列 → 与 MySQL only_full_group_by 冲突
  2. JOIN 列归属：JOIN ... ON a.col = b.col 中，a.col 不属于 a 表 或
     b.col 不属于 b 表 → 语义错误

校验失败的 SQL 将抛出 ``ValueError``，由上层转为 400 错误并附带具体原因，
便于定位是哪条 SQL 出了问题。
"""

import re
from typing import Dict, List, Set, Tuple

from summary_report.core.logger import get_logger

logger = get_logger(__name__)

# ── 聚合函数检测 ─────────────────────────────────────────────
_AGGREGATE_FUNCS = ("COUNT", "SUM", "AVG", "MAX", "MIN")
_AGGREGATE_PATTERN = re.compile(
    r"\b(" + "|".join(_AGGREGATE_FUNCS) + r")\s*\(", re.IGNORECASE
)
_GROUP_BY_PATTERN = re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE)

# 匹配单个聚合函数调用（含嵌套括号内容），可选尾部别名。
# 用 ^...$ 锚定整个表达式：纯聚合函数（可带别名）视为已聚合。
_SINGLE_AGG_PATTERN = re.compile(
    r"^(?:COUNT|SUM|AVG|MAX|MIN)\s*\([^)]*\)"
    r"(?:\s+(?:AS\s+)?[a-zA-Z_][a-zA-Z0-9_]*)?$",
    re.IGNORECASE,
)
# 匹配 SELECT ... FROM 之间的列表达式
_SELECT_EXPR_PATTERN = re.compile(
    r"\bSELECT\s+(.*?)\s+FROM\b", re.IGNORECASE | re.DOTALL
)

# ── JOIN 解析 ────────────────────────────────────────────────
# 匹配: JOIN table [AS] alias ON cond
_JOIN_PATTERN = re.compile(
    r"\bJOIN\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?\s+ON\s+(.+?)(?=\b(?:LEFT|RIGHT|INNER|OUTER|JOIN|WHERE|GROUP|ORDER|LIMIT|HAVING|UNION)\b|$)",
    re.IGNORECASE,
)
# FROM table [AS] alias
_FROM_PATTERN = re.compile(
    r"\bFROM\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?",
    re.IGNORECASE,
)
# ON 条件中的等值连接：alias.col = alias.col
_JOIN_COND_PATTERN = re.compile(
    r"(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)", re.IGNORECASE
)


# 表头行模式："1. table_name（..." 或 "table_name（..."
# 捕获第一个紧跟在序号后、以中文/英文括号结尾前的标识符作为表名。
_TABLE_HEADER_PATTERN = re.compile(
    r"^\s*(?:\d+\.\s*)?([a-zA-Z_][a-zA-Z0-9_]*)\s*[（(]"
)

# 模块标题行（不含括号，如"一、客户经营模块"）— 不作为表头解析
_MODULE_TITLE_PATTERN = re.compile(r"^\s*[一二三四五六七八九十]+[、.]\s*")

# 分隔线（═══ 或 ---）
_SEPARATOR_PATTERN = re.compile(r"^\s*[═══\-]{3,}\s*$")

# 关联关系标题
_ASSOC_HEADER_PATTERN = re.compile(r"^\s*关联关系[:：]")


def _parse_schema_tables(schema: str) -> Dict[str, Set[str]]:
    """
    从 schema 文本中解析出每个表对应的列名集合。

    支持的格式（与 schema_*.py 及 schema_all.py 的写法一致）：

        格式 A（每列独占一行，schema_*.py 风格）：
            1. table_name（中文说明）
               - col1 TYPE, 说明
               - col2 TYPE, 说明

        格式 B（逗号分隔多行，schema_all.py 风格）：
            1. table_name（中文说明）
               - col1 TYPE PK, col2, col3,
                 col4 TYPE, col5

    解析策略：
    - 先按表头切分为若干"表区块"；
    - 在每个区块内，把所有逗号分隔的子串逐个检查：子串的开头如果是一个
      合法的 SQL 标识符，就视为一个列名（跳过 TYPE 关键字、注释等噪声）；
    - 关联关系段由 _ASSOC_HEADER_PATTERN 识别，之后的区块不再解析。

    Returns:
        {table_name_lower: {col_name_lower, ...}, ...}
    """
    tables: Dict[str, Set[str]] = {}
    current_table: str | None = None

    # SQL 类型关键字噪声：如果"列名候选"是这些词，应跳过
    _type_noise = {
        "bigint", "int", "tinyint", "smallint", "mediumint",
        "varchar", "char", "text", "longtext", "mediumtext",
        "decimal", "float", "double", "numeric",
        "date", "datetime", "timestamp", "time", "year",
        "enum", "set", "json", "blob", "binary", "varbinary",
        "pk", "fk", "key", "primary", "foreign",
        "not", "null", "default", "auto_increment",
        "unsigned", "zerofill",
    }

    for line in schema.splitlines():
        # 分隔线 → 重置当前表
        if _SEPARATOR_PATTERN.match(line):
            current_table = None
            continue

        # 关联关系标题 → 后续区块不再解析
        if _ASSOC_HEADER_PATTERN.match(line):
            current_table = None
            continue

        # 表头行：需含括号（避免误匹配模块标题"一、客户经营模块"）
        header_match = _TABLE_HEADER_PATTERN.match(line)
        if header_match and re.search(r"[（(]", line) and not _MODULE_TITLE_PATTERN.match(line):
            current_table = header_match.group(1).lower()
            tables[current_table] = set()
            continue

        # 在表区块内：解析列名（逗号分隔）
        if current_table is not None:
            # 取第一个标识符作为候选列名（去掉开头的 "- "）
            stripped = line.strip()
            if stripped.startswith("- "):
                stripped = stripped[2:]

            # 按逗号分隔，逐个提取候选列名
            for part in stripped.split(","):
                part = part.strip()
                if not part:
                    continue
                # 每个分段的第一个"单词"是列名候选
                ident_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)", part)
                if not ident_match:
                    continue
                cand = ident_match.group(1).lower()
                # 跳过类型/关键字噪声
                if cand in _type_noise:
                    continue
                # 跳过纯数字表名引用
                if cand.isdigit():
                    continue
                # 跳过带括号的表达式（如 "ENUM(...)"、"BIGINT FK→..."）
                # 取列名后紧跟的字符：如果直接是 '(' 说明不是列名
                rest = part[ident_match.end():]
                if rest.startswith("("):
                    continue
                tables[current_table].add(cand)

    return tables


def _build_alias_map(sql: str) -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
    """
    解析 SQL 中的表别名与列归属。

    Returns:
        (alias_to_table, tables_columns)
        - alias_to_table: {alias_lower: table_name_lower, ...}
        - tables_columns: {table_name_lower: {col, ...}, ...}  （从 schema 解析得到，
          需要外部传入，但这里为简化通过参数传递）
    """
    alias_to_table: Dict[str, str] = {}

    # FROM 子句
    from_match = _FROM_PATTERN.search(sql)
    if from_match:
        table = from_match.group(1).lower()
        alias = from_match.group(2).lower() if from_match.group(2) else table
        alias_to_table[alias] = table
        # 表名本身也可作为别名使用
        if table not in alias_to_table:
            alias_to_table[table] = table

    # JOIN 子句
    for m in _JOIN_PATTERN.finditer(sql):
        table = m.group(1).lower()
        alias = m.group(2).lower() if m.group(2) else table
        alias_to_table[alias] = table
        if table not in alias_to_table:
            alias_to_table[table] = table

    return alias_to_table


def _strip_string_literals(sql: str) -> str:
    """将 SQL 中的字符串字面量替换为空，避免内容干扰解析。"""
    return re.sub(r"'(?:\\.|''|[^'\\])*'" + r'|"(\\.|""|[^"\\])*"', "", sql)


def _has_non_aggregated_columns(sql: str) -> bool:
    """
    判断 SELECT 列表中是否存在不在聚合函数内的非聚合列。

    只有形如 COUNT(a), AVG(b) 的聚合表达式才视为"已聚合"；
    其他任何列表达式（含常量、列引用、含列的算术表达式等）均为"非聚合"。

    Returns:
        True: 存在至少一个非聚合列（此时必须配 GROUP BY 才能满足 only_full_group_by）
        False: 所有列表达式均为聚合函数（纯聚合查询无需 GROUP BY）
    """
    exprs = _extract_select_expressions(sql)
    if not exprs:
        return False  # 无法解析时保守返回 False，让后续执行阶段兜底

    for expr in exprs:
        stripped = expr.strip()
        # 整个表达式完全是一个聚合函数调用 → 已聚合，跳过
        if _SINGLE_AGG_PATTERN.fullmatch(stripped):
            continue
        # 表达式中嵌入了聚合函数（如 COUNT(a) + 1）也视为含聚合部分
        # 但这类表达式整体仍需 GROUP BY，所以仍视为需要 GROUP BY
        # 为简化处理：只要表达式不在聚合函数内就视为非聚合列
        return True

    return False


def check_group_by_consistency(sql: str) -> None:
    """
    检查含聚合函数的 SQL 是否正确使用 GROUP BY。

    规则（对齐 MySQL only_full_group_by）：
    - 如果 SELECT 列表中所有表达式都是聚合函数（如 SELECT COUNT(*), SUM(x)），
      则不需要 GROUP BY，直接放行；
    - 如果 SELECT 列表中存在非聚合列（如 SELECT col, COUNT(*)），则必须有
      GROUP BY 子句，否则在 only_full_group_by 模式下会报错。

    注意：含嵌套子查询的 SELECT 列表可能让正则解析出错，这类场景直接放行，
    由 SQL 执行阶段兜底（执行失败会触发 LLM 反馈重试）。

    Raises:
        ValueError: 检测到非聚合列但缺 GROUP BY。
    """
    skeleton = _strip_string_literals(sql)
    if not _AGGREGATE_PATTERN.search(skeleton):
        return  # 无聚合函数，跳过

    if _GROUP_BY_PATTERN.search(skeleton):
        return  # 已有 GROUP BY，跳过

    # 含嵌套子查询时，SELECT 列表解析可能不准确（子查询里含 FROM 会干扰正则）
    # 保守策略：直接放行，让执行阶段判断（子查询场景通常不需要外层 GROUP BY）
    if re.search(r"\bSELECT\b", skeleton, re.IGNORECASE):
        # 即在 SELECT 列表区域（FROM 之前）还存在另一个 SELECT
        logger.debug("[SEMANTIC] SELECT 列表含嵌套子查询，跳过 GROUP BY 校验: %s", sql[:120])
        return

    # 关键：纯聚合查询（SELECT COUNT(*), SUM(x)）无需 GROUP BY
    if not _has_non_aggregated_columns(sql):
        return

    # 提取非聚合列用于错误提示
    exprs = _extract_select_expressions(sql)
    non_agg = []
    for e in exprs:
        s = e.strip()
        if not _SINGLE_AGG_PATTERN.fullmatch(s) and not _AGGREGATE_PATTERN.search(s):
            non_agg.append(_get_col_alias(s))
    logger.warning(
        "[SEMANTIC] GROUP BY 校验失败（auto_fix 也未能修复）。非聚合列: %s。完整 SQL: %s",
        non_agg, sql[:500],
    )
    raise ValueError(
        "SQL 含聚合函数但缺少 GROUP BY 子句，在 MySQL only_full_group_by 模式下不允许。"
        f"非聚合列: {non_agg}。完整 SQL: {sql[:300]}"
    )


def _extract_select_expressions(sql: str) -> List[str]:
    """
    从 SQL 中提取 SELECT 与 FROM 之间的顶层列表达式。

    通过括号深度追踪正确切分逗号（逗号可能在函数参数 / 子查询内部）。
    """
    m = _SELECT_EXPR_PATTERN.search(sql)
    if not m:
        return []

    raw_exprs = m.group(1).strip()
    # 剥离字符串字面量避免内部逗号干扰
    raw_exprs = re.sub(r"'(?:\\.|''|[^'\\])*'" + r'|"(\\.|""|[^"\\])*"', "", raw_exprs)

    expressions: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in raw_exprs:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            expressions.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        expressions.append("".join(current).strip())
    return expressions


def _get_col_alias(expr: str) -> str:
    """
    从列表达式中提取列引用或别名，用于拼 GROUP BY。

    形如：
      - table.col          → table.col
      - table.col AS alias → alias
      - col                → col
      - col AS alias       → alias
    """
    m = re.search(r"\bAS\s+([a-zA-Z_][a-zA-Z0-9_]*)", expr, re.IGNORECASE)
    if m:
        return m.group(1)
    # 没有别名，取最后一个标识符（含 table.col 形式）
    identifiers = re.findall(r"[a-zA-Z_][a-zA-Z0-9_.]*", expr)
    if identifiers:
        return identifiers[-1]
    return expr.strip()


def auto_fix_group_by(sql: str) -> str:
    """
    自动为缺 GROUP BY 的聚合 SQL 补上 GROUP BY 子句。

    策略：
      1. 提取 SELECT 与 FROM 之间的顶层列表达式；
      2. 过滤掉在聚合函数内部的表达式（如 COUNT(id)、AVG(score)）；
      3. 剩余的非聚合列作为 GROUP BY 目标列；
      4. 在 SQL 末尾（ORDER BY / LIMIT 之前）插入 "GROUP BY col1, col2, ..."。

    如果 SQL 无法解析或无有效非聚合列，返回原始 SQL（不修改）。

    Args:
        sql: 原始 SQL 字符串。

    Returns:
        已补上 GROUP BY 的 SQL（或原 SQL）。
    """
    skeleton = _strip_string_literals(sql)
    if not _AGGREGATE_PATTERN.search(skeleton):
        logger.debug("[AUTO-FIX] 无聚合函数，跳过: %s", sql[:80])
        return sql  # 无聚合函数，不需要修复
    if _GROUP_BY_PATTERN.search(skeleton):
        logger.debug("[AUTO-FIX] 已有 GROUP BY，跳过: %s", sql[:80])
        return sql  # 已有 GROUP BY，跳过

    # 含嵌套子查询时，SELECT 列表解析可能不准确，保守放行
    if re.search(r"\bSELECT\b", skeleton, re.IGNORECASE):
        logger.debug("[AUTO-FIX] 含嵌套子查询，跳过自动修复: %s", sql[:120])
        return sql

    exprs = _extract_select_expressions(sql)
    if not exprs:
        logger.warning("[AUTO-FIX] 无法解析 SELECT 列表: %s", sql[:200])
        return sql  # 无法解析 SELECT 列表，保守返回原 SQL

    # 找出非聚合列（不在聚合函数内的表达式）
    non_agg_cols: List[str] = []
    for expr in exprs:
        # 完全被聚合函数包裹的表达式（如 COUNT(*)、AVG(score)）跳过
        stripped = expr.strip()
        if _SINGLE_AGG_PATTERN.fullmatch(stripped):
            continue
        # 含聚合函数但整体不是聚合（如 COUNT(id) + 1），也跳过其中的聚合部分
        # 但这种组合一般需要整个 SELECT 重写，此处保守处理：如果表达式任
        # 何位置出现聚合函数，整体不纳入 GROUP BY（由 LLM 修正）
        if _AGGREGATE_PATTERN.search(stripped):
            continue
        non_agg_cols.append(_get_col_alias(expr))

    if not non_agg_cols:
        logger.warning("[AUTO-FIX] 全是聚合列，无法自动补 GROUP BY: %s", sql[:200])
        return sql  # 全是聚合列，无法生成 GROUP BY，保守返回原 SQL

    group_by_clause = " GROUP BY " + ", ".join(non_agg_cols)

    # 插入位置：在 ORDER BY / LIMIT / HAVING / UNION 之前，或直接在末尾
    insert_pattern = re.compile(
        r"\b(ORDER\s+BY|LIMIT|HAVING|UNION)\b", re.IGNORECASE
    )
    m = insert_pattern.search(sql)
    if m:
        pos = m.start()
        fixed = sql[:pos].rstrip() + group_by_clause + " " + sql[pos:]
    else:
        fixed = sql.rstrip() + group_by_clause

    logger.info("[AUTO-FIX] 补上 GROUP BY:\n  FROM: %s\n  TO:   %s", sql[:200], fixed[:200])
    return fixed


def check_join_column_belonging(sql: str, tables_schema: Dict[str, Set[str]]) -> None:
    """
    检查 JOIN ... ON 条件中的列是否确实属于对应表。

    例如：JOIN courses c ON c.id = sc.student_id
    若 student_score 表没有 id → OK 的检查方向反了，这里检查的是
    c.id 的 id 是否属于 courses 表，以及 sc.student_id 的 student_id
    是否属于 student_score 表。若任一不属于，则判定为语义错误。

    Raises:
        ValueError: 检测到无效的 JOIN 列归属。
    """
    alias_to_table = _build_alias_map(sql)
    if not alias_to_table:
        return

    skeleton = _strip_string_literals(sql)
    for m in _JOIN_COND_PATTERN.finditer(skeleton):
        l_alias, l_col, r_alias, r_col = (
            m.group(1).lower(),
            m.group(2).lower(),
            m.group(3).lower(),
            m.group(4).lower(),
        )

        # 解析左侧列所属表
        l_table = alias_to_table.get(l_alias)
        if l_table is None:
            continue  # 无法解析别名，保守放行
        l_columns = tables_schema.get(l_table, set())
        if l_columns and l_col not in l_columns:
            logger.warning(
                "[SEMANTIC] JOIN 列 %s.%s 不属于表 %s: %s",
                l_alias, l_col, l_table, sql[:120],
            )
            raise ValueError(
                f"JOIN 条件中 {l_alias}.{l_col} 不是表 {l_table} 的列，"
                f"{l_table} 可用列: {sorted(l_columns)}"
            )

        # 解析右侧列所属表
        r_table = alias_to_table.get(r_alias)
        if r_table is None:
            continue
        r_columns = tables_schema.get(r_table, set())
        if r_columns and r_col not in r_columns:
            logger.warning(
                "[SEMANTIC] JOIN 列 %s.%s 不属于表 %s: %s",
                r_alias, r_col, r_table, sql[:120],
            )
            raise ValueError(
                f"JOIN 条件中 {r_alias}.{r_col} 不是表 {r_table} 的列，"
                f"{r_table} 可用列: {sorted(r_columns)}"
            )


def _extract_referenced_tables(sql: str) -> Set[str]:
    """
    从 SQL 中提取所有被引用的真实表名（去别名）。

    解析 FROM / JOIN 子句后的表名，跳过子查询和无法解析的场景。
    """
    tables: Set[str] = set()
    skeleton = _strip_string_literals(sql)

    # FROM / JOIN 后面紧跟的标识符即为表名（可能带别名，取第一个标识符）
    for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+(?:AS\s+)?[a-zA-Z_][a-zA-Z0-9_]*)?",
        skeleton,
        re.IGNORECASE,
    ):
        tables.add(m.group(1).lower())

    return tables


def check_table_existence(sql: str, db_schema: Dict[str, Set[str]]) -> None:
    """
    检查 SQL 中引用的所有表是否存在于真实数据库。

    Raises:
        ValueError: 引用的表在真实数据库中不存在。
    """
    referenced = _extract_referenced_tables(sql)
    available = set(db_schema.keys())
    missing = referenced - available
    if missing:
        logger.warning(
            "[SEMANTIC] SQL 引用了不存在的表 %s: %s",
            missing, sql[:120],
        )
        raise ValueError(
            f"SQL 引用了数据库中不存在的表: {sorted(missing)}，"
            f"可用表: {sorted(available)}"
        )


def auto_fix_sql_group_by(sql_list: List[str]) -> Tuple[List[str], bool]:
    """
    尝试自动修复 SQL 列表中缺 GROUP BY 的语句。

    对每条 SQL 调用 ``auto_fix_group_by``：若能补上 GROUP BY 则替换原语句；
    若无法修复则保留原语句。

    Returns:
        (修复后的 SQL 列表, 是否有任何一条被修复过)。
    """
    fixed: List[str] = []
    any_changed = False
    for sql in sql_list:
        new_sql = auto_fix_group_by(sql)
        if new_sql != sql:
            any_changed = True
            logger.info(
                "[AUTO-FIX] 已自动补上 GROUP BY:\n  FROM: %s\n  TO:   %s",
                sql[:200], new_sql[:200],
            )
        fixed.append(new_sql)

    # 诊断日志：如果没有任何 SQL 被修复但原始列表包含聚合函数，记录原因
    if not any_changed:
        for sql in sql_list:
            skeleton = _strip_string_literals(sql)
            if _AGGREGATE_PATTERN.search(skeleton) and not _GROUP_BY_PATTERN.search(skeleton):
                logger.warning(
                    "[AUTO-FIX] 含聚合但缺 GROUP BY 且 auto_fix 未修改，将进入 LLM 重试: %s",
                    sql[:200],
                )

    return fixed, any_changed


def validate_sql_semantics(
    sql_list: List[str],
    schema: str,
    db_schema: Dict[str, Set[str]] | None = None,
) -> None:
    """
    对 SQL 列表执行语义校验。

    校验三道关卡（按序执行）：
      1. TABLE EXISTENCE：SQL 中引用的表是否存在于真实数据库
      2. GROUP BY 一致性：含聚合函数但缺少 GROUP BY
      3. JOIN 列归属：JOIN ... ON a.col = b.col 中列是否属于对应表

    Args:
        sql_list:  待校验的 SQL 字符串列表。
        schema:    表结构描述文本（用于解析表-列归属关系，作为 fallback）。
        db_schema: 从 information_schema 查询的真实库结构
                   {table: {col, ...}, ...}。提供时优先使用真实库结构
                   做列归属校验，可发现 schema 文本与真实库之间的漂移。

    Raises:
        ValueError: 任何一条 SQL 未通过语义校验时抛出，消息中附带出错语句片段。
    """
    # 优先使用真实库结构，否则 fallback 到 schema 文本解析
    tables_schema = db_schema if db_schema else _parse_schema_tables(schema)

    for sql in sql_list:
        # 跳过空 SQL
        if not sql or not sql.strip():
            continue

        # 1) 表存在性（有真实库结构时才生效）
        if db_schema:
            check_table_existence(sql, db_schema)

        # 2) GROUP BY 一致性
        check_group_by_consistency(sql)

        # 3) JOIN 列归属（仅在解析出表结构时生效）
        if tables_schema:
            check_join_column_belonging(sql, tables_schema)
