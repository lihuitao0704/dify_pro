"""
用户画像评估模块（多项目 + 指定用户 + 自然语言返回）
=========================================================
- 评估时指定用户（1个/多个/全部）
- 自动找出 portrait_rule 表中所有 project_id
- 每个 project_id 独立评分（该 project_id 下所有规则分数之和 >= 60 即通过）
- 结果写入 intention_diagnosis 表（诊断id, user_id, project_id, score, rule_details）
- 大模型润色结果为自然语言返回
"""

import os
import json
import hashlib
import logging
import re
from typing import Optional

import pymysql
from pymysql.cursors import DictCursor
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.48.121"),
    # "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "offer"),
    "password": os.getenv("DB_PASSWORD", "123456"),
    "database": os.getenv("DB_NAME", "dify_pro"),
    "charset": "utf8mb4",
}

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "https://ws-80gz91pjbhgouudd.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
)
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")

PASS_SCORE = 60


def get_conn():
    return pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)


_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("DASHSCOPE_API_KEY", DASHSCOPE_API_KEY)
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY 未设置")
        _client = OpenAI(api_key=api_key, base_url=LLM_BASE_URL)
    return _client


# ────────────────────────────────────────────────────────────
# 数据读取
# ────────────────────────────────────────────────────────────
def get_all_project_ids() -> list[int]:
    """获取 portrait_rule 表中所有不重复的 project_id"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT project_id FROM portrait_rule WHERE is_active = 1 ORDER BY project_id")
            return [row["project_id"] for row in cur.fetchall()]
    finally:
        conn.close()


def get_rules_by_project(project_id: int) -> list[dict]:
    """获取指定 project_id 的所有活跃规则"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rule_id, rule_key, rule_value, score_max, score_desc
                FROM portrait_rule
                WHERE project_id = %s AND is_active = 1
                ORDER BY sort_order ASC, rule_id ASC
            """, (project_id,))
            return cur.fetchall()
    finally:
        conn.close()


def get_user_filter_sql(user_ids: Optional[list[int]] = None,
                        user_names: Optional[list[str]] = None) -> str:
    """
    根据用户 id 或姓名构建 WHERE 条件片段。
    返回空串表示评估全部。
    """
    if user_ids:
        ids_str = ", ".join(str(uid) for uid in user_ids)
        return f"id IN ({ids_str})"
    if user_names:
        names_str = ", ".join(f"'{n}'" for n in user_names)
        return f"name IN ({names_str})"
    return ""


def get_target_users(user_ids=None, user_names=None) -> list[dict]:
    """查询待评估的用户列表（返回全字段，供意向客户表插入使用）"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT id, name, age, phone, development, abilities,
                       target_country, budget, gpa, language_score, major,
                       education, target_major, `is_Closed_loop`
                FROM user_profiles
                WHERE name IS NOT NULL AND name != ''
            """
            params = []
            if user_ids:
                sql += " AND id IN (%s)" % ", ".join(["%s"] * len(user_ids))
                params.extend(user_ids)
            elif user_names:
                placeholders = ", ".join(["%s"] * len(user_names))
                sql += f" AND name IN ({placeholders})"
                params.extend(user_names)
            sql += " ORDER BY id"
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────
# NL2SQL：为每个 project_id 生成评分表达式
# ────────────────────────────────────────────────────────────

def _build_project_scoring_prompt(rules, project_id):
    rules_text_parts = []
    for i, r in enumerate(rules, 1):
        line = '  规则{}【{}】最高分={}：{}(评分标准：{})'.format(
            i, r['rule_key'], r['score_max'], r['rule_value'], r.get('score_desc') or '无'
        )
        rules_text_parts.append(line)
    rules_text = chr(10).join(rules_text_parts)
    total_max = sum(r['score_max'] for r in rules)

    lines = []
    lines.append('你是 SQL 专家。根据以下 project_id={} 的评分规则，生成一个 MySQL 评分表达式。'.format(project_id))
    lines.append('')
    lines.append('【user_profiles 可用字段】')
    lines.append('id, name, age, education, major, gpa, target_country, target_major, budget, language_score, phone, wechat, email, consultation_status, assess')
    lines.append('')
    lines.append('【评分规则】（满分 {} 分）'.format(total_max))
    lines.append(rules_text)
    lines.append('')
    lines.append('【重要评分原则】')
    lines.append('- rule_value 中的描述是自然语言举例，不要将其中数学符号当作 SQL 运算符')
    lines.append('- 例如 14-16岁2+2 表示该年龄段符合条件，评分时直接给满分')
    lines.append('- 请从宽评分：符合条件给满分，接近给一半，完全不满足才给 0')
    lines.append('')
    lines.append('【要求】')
    lines.append('1. 将每条规则翻译为 CASE WHEN 表达式')
    lines.append('2. 用 + 连接所有规则的 CASE WHEN，构成总分表达式')
    lines.append('3. 字段名用反引号包裹')
    lines.append('4. THEN 后面只写数字如 15, 8, 0')
    lines.append('5. 满分 = {} 分，>= {} 分视为通过'.format(total_max, PASS_SCORE))
    lines.append('6. THEN 后面绝对不要写 2+2 这类算式')
    lines.append('')
    lines.append('【返回格式】严格输出 JSON：')
    lines.append('{"expression": "(CASE WHEN ... THEN 15 ELSE 0 END + CASE WHEN ... END)", "max_score": ' + str(total_max) + ', "rule_expressions": {"规则key": "CASE WHEN ... THEN 15 ELSE 0 END"}}')
    lines.append('')
    lines.append('【约束】')
    lines.append('- expression 只使用上方列出的字段名')
    lines.append("- 字符串匹配用 LIKE '%关键词%'")
    lines.append("- education 匹配：`education` = '本科' OR `education` = '硕士'")
    lines.append("- language_score 匹配：`language_score` LIKE '%B1%'")
    return chr(10).join(lines)



def _compute_rule_hash(rules: list[dict]) -> str:
    """计算规则的 MD5 哈希，用于检测规则是否变更（变更则缓存失效）"""
    key = json.dumps([(r['rule_key'], r['score_max'], r['rule_value']) for r in rules], sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()


def _get_cached_expression(project_id: int, rules: list[dict]) -> dict | None:
    """从缓存获取表达式。如果规则已变更（hash 不同）返回 None（缓存失效）"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT expression_json, rule_hash FROM project_expression_cache WHERE project_id = %s",
                (project_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            # 校验规则是否变更
            current_hash = _compute_rule_hash(rules)
            if row["rule_hash"] != current_hash:
                logger.info(f"project {project_id} 规则已变更，缓存失效")
                return None
            return json.loads(row["expression_json"])
    finally:
        conn.close()


def _set_cached_expression(project_id: int, rules: list[dict], expr_data: dict):
    """写入/更新缓存"""
    rule_hash = _compute_rule_hash(rules)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project_expression_cache (project_id, expression_json, rule_hash)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE expression_json = VALUES(expression_json), rule_hash = VALUES(rule_hash)
            """, (project_id, json.dumps(expr_data, ensure_ascii=False), rule_hash))
            conn.commit()
    finally:
        conn.close()


def generate_project_expression(rules: list[dict], project_id: int) -> dict:
    """为单个 project_id 生成评分表达式（带缓存）"""
    # 先查缓存
    cached = _get_cached_expression(project_id, rules)
    if cached is not None:
        logger.info(f"project {project_id} 使用缓存表达式（跳过 LLM）")
        return cached

    # 缓存未命中 → 调 LLM 生成
    logger.info(f"project {project_id} 缓存未命中，调 LLM 生成表达式")
    prompt = _build_project_scoring_prompt(rules, project_id)

    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是 SQL 专家。严格按 JSON 格式输出评分表达式。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception as e:
        raise RuntimeError(f"千问 API 失败: {e}") from e

    cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            raise ValueError(f"JSON 解析失败: {raw}")

    # 校验字段合法性
    valid_fields = {"id", "name", "age", "education", "major", "gpa", "target_country",
                    "target_major", "budget", "language_score", "phone", "wechat", "email",
                    "consultation_status", "assess", "conversation_id", "created_at", "updated_at"}
    expr = data.get("expression", "")
    used = set(re.findall(r'`(\w+)`', expr))
    bad = [c for c in used if c not in valid_fields]
    if bad:
        raise ValueError(f"project {project_id} 表达式引用了不存在的字段: {bad}")

    # 写入缓存
    _set_cached_expression(project_id, rules, data)
    return data


# ────────────────────────────────────────────────────────────
# 评估执行：按 project_id 循环，每个 project 独立评分
# ────────────────────────────────────────────────────────────
def run_assessment(
    user_ids: Optional[list[int]] = None,
    user_names: Optional[list[str]] = None,
) -> list[dict]:
    """
    评估流程：
    1. 确定目标用户
    2. 获取所有 project_id
    3. 对每个 project_id：
       - 取出该 project_id 的规则
       - LLM 生成评分表达式
       - 计算每个用户在该项目下的得分
       - >= PASS_SCORE 的记录写入 intention_diagnosis 表
    4. 返回所有通过诊断的记录
    """
    # Step 1: 确定目标用户
    users = get_target_users(user_ids=user_ids, user_names=user_names)
    if not users:
        return []

    user_id_list = [u["id"] for u in users]
    user_name_map = {u["id"]: u["name"] for u in users}
    logger.info(f"目标用户 {len(users)} 人: {list(user_name_map.values())}")

    # 构建用户筛选条件
    user_filter = ""
    if user_ids:
        user_filter = f"AND up.id IN ({', '.join(str(uid) for uid in user_ids)})"
    elif user_names:
        names_quoted = ", ".join(f"'{n}'" for n in user_names)
        user_filter = f"AND up.name IN ({names_quoted})"

    # Step 2: 获取所有 project_id
    project_ids = get_all_project_ids()
    if not project_ids:
        logger.warning("portrait_rule 表中没有活跃规则")
        return []

    logger.info(f"待评估项目: {project_ids}")

    # Step 3: 按 project_id 循环评估
    passed_diagnoses = []  # 通过的诊断记录

    conn = get_conn()
    try:
        # 先检查哪些用户已有诊断记录（有则报错，不允许重复诊断）
        with conn.cursor() as cur:
            for user in users:
                cur.execute(
                    "SELECT project_id, score FROM intention_diagnosis WHERE user_id = %s",
                    (user["id"],)
                )
                existing = cur.fetchall()
                if existing:
                    proj_list = ", ".join(f"项目{r['project_id']}({r['score']}分)" for r in existing)
                    raise ValueError(
                        f"用户 {user['name']}（ID {user['id']}）已是意向客户，已诊断项目：{proj_list}，不可重复诊断"
                    )

        for project_id in project_ids:
            rules = get_rules_by_project(project_id)
            if not rules:
                continue

            logger.info(f"Project {project_id}: {len(rules)} 条规则")

            # LLM 生成评分表达式
            try:
                expr_data = generate_project_expression(rules, project_id)
            except Exception as e:
                logger.warning(f"Project {project_id} 表达式生成失败，跳过: {e}")
                continue

            expression = expr_data["expression"]
            max_score = expr_data["max_score"]
            rule_expressions = expr_data.get("rule_expressions", {})

            # 评估每个用户
            with conn.cursor() as cur:
                for user in users:
                    uid = user["id"]
                    uname = user["name"]

                    # 计算总分
                    score_sql = f"SELECT CAST(GREATEST(0, LEAST(({expression}), 999)) AS SIGNED) AS total FROM user_profiles WHERE id = {uid}"
                    cur.execute(score_sql)
                    score = cur.fetchone()["total"]

                    if score >= PASS_SCORE:
                        # 检查该用户在该项目下是否已有诊断记录（防重复）
                        cur.execute(
                            "SELECT diag_id FROM intention_diagnosis WHERE user_id = %s AND project_id = %s",
                            (uid, project_id)
                        )
                        if cur.fetchone():
                            raise ValueError(f"用户 {uname}（ID {uid}）已是项目 {project_id} 的意向客户，不可重复诊断")

                        # 计算每个规则的得分
                        rule_scores = {}
                        for rule_key, rule_expr in rule_expressions.items():
                            try:
                                r_sql = f"SELECT CAST(GREATEST(0, LEAST(({rule_expr}), 999)) AS SIGNED) AS s FROM user_profiles WHERE id = {uid}"
                                cur.execute(r_sql)
                                rule_scores[rule_key] = cur.fetchone()["s"]
                            except Exception:
                                rule_scores[rule_key] = 0

                        # 写入 intention_diagnosis 表
                        cur.execute("""
                            INSERT INTO intention_diagnosis (user_id, project_id, score, rule_details)
                            VALUES (%s, %s, %s, %s)
                        """, (uid, project_id, score, json.dumps(rule_scores, ensure_ascii=False)))

                        passed_diagnoses.append({
                            "user_id": uid,
                            "user_name": uname,
                            "project_id": project_id,
                            "score": score,
                            "max_score": max_score,
                            "rule_scores": rule_scores,
                        })

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info(f"评估完成：{len(passed_diagnoses)} 条通过记录")
    return passed_diagnoses


# ────────────────────────────────────────────────────────────
# 大模型润色为自然语言（含不达标原因分析）
# ────────────────────────────────────────────────────────────
def generate_natural_response(passed: list[dict], total_users: int,
                               failed: list[dict] | None = None,
                               rules_map: dict[int, list[dict]] | None = None,
                               student_view: bool = False) -> str:
    """
    将诊断结果润色为自然语言。
    - passed: 达标用户列表
    - total_users: 总评估用户数
    - failed: 不达标用户列表（含各规则得分）
    - rules_map: project_id → 规则列表（含 score_max，用于分析失分原因）
    - student_view: True = 学生端（温暖亲切），False = 企业端（专业简练）
    """
    failed = failed or []
    rules_map = rules_map or {}

    # ── 不达标用户：详细分析失分原因 ──
    if not passed and failed:
        return _build_failed_report(failed, rules_map, student_view=student_view)

    # ── 有通过也有不达标 ──
    if passed and failed:
        passed_part = _build_passed_summary(passed, total_users, student_view=student_view)
        failed_part = _build_failed_report(failed, rules_map, brief=True, student_view=student_view)
        return passed_part + "\n" + failed_part

    # ── 全部通过 ──
    if passed:
        return _build_passed_summary(passed, total_users, student_view=student_view)

    # ── 兜底（不会走到） ──
    return f"本次共评估 {total_users} 位用户，全部已完成研判。"


def _build_passed_summary(passed: list[dict], total_users: int,
                           student_view: bool = False) -> str:
    """
    生成达标用户的总结（内部函数）。
    注意：已达标的条件是"至少有一个项目 ≥ 60 分"，不是所有项目都通过。
    student_view: True = 学生端（温暖亲切），False = 企业端（专业简练）
    """
    # 查询项目名称
    all_proj_ids = list(set(d["project_id"] for d in passed))
    project_names = _get_project_names(all_proj_ids)

    # 按用户分组
    user_results = {}
    for d in passed:
        uname = d["user_name"]
        if uname not in user_results:
            user_results[uname] = {"user_id": d["user_id"], "projects": []}
        user_results[uname]["projects"].append({
            "project_id": d["project_id"],
            "project_name": project_names.get(d["project_id"], f"项目 {d['project_id']}"),
            "score": d["score"],
        })

    # 构造推荐列表（每个通过的 project 都列出）
    recommend_lines = []
    for uname, info in user_results.items():
        sorted_projects = sorted(info["projects"], key=lambda p: p["score"], reverse=True)
        proj_texts = [f"{p['project_name']}（{p['score']} 分）" for p in sorted_projects]
        recommend_lines.append(f"{uname}：{'、'.join(proj_texts)}")

    passed_count = len(user_results)

    if not student_view:
        # 企业端：专业简练
        if total_users <= 1:
            header = "已完成研判。"
        else:
            header = f"本次共评估 {total_users} 位用户，已通过 {passed_count} 人。"

        prompt = f"""你是一名留学咨询数据分析师。请根据以下评估结果，生成一段简练的中文总结。

【评估总览】
- {header}

【通过的用户及推荐项目】
{chr(10).join(recommend_lines)}

【写作要求】
1. 开头复述总览内容
2. 每个用户列出推荐的项目名称和得分，格式如"张三: 新加坡国际本硕升学计划（85分）"
3. 如果一个用户有多个项目通过，都列出
4. 用简洁的中文段落，不要 JSON、列表或markdown格式
5. 语气专业客观，不超过 100 字
"""
    else:
        # 学生端：温暖亲切
        if total_users <= 1:
            single_uname = list(user_results.keys())[0]
            header = f"{single_uname} 同学，你好！很高兴认识你，感谢你的信任。以下是你本次评估的结果："
        else:
            header = f"以下是你和同学们的评估结果："

        prompt = f"""你是一名温暖、专业的留学咨询顾问。请根据以下评估结果，生成一段鼓励性的中文反馈。

【评估总览】
- {header}

【通过的用户及推荐项目】
{chr(10).join(recommend_lines)}

【写作要求】
1. 开头以用户的名字打招呼，表达感谢和欢迎
2. 用积极正向的语气告诉用户通过了哪些项目，格式如"恭喜你通过了新加坡国际本硕升学计划（85分）"
3. 如果一个用户多个项目通过，都列出来表示赞赏
4. 结尾给予温暖鼓励，如"期待与你一起开启美好的留学旅程"
5. 用连贯的中文段落，不要 JSON、列表或markdown格式
6. 语气像朋友聊天一样自然温暖
7. 不超过 200 字
"""

    system_prompt = ("你是一名温暖、专业的留学咨询顾问。用朋友聊天的语气反馈评估结果，让用户感受到温暖和鼓励。"
                     if student_view else
                     "你是留学咨询数据分析师。请用简洁自然的中文总结评估结果。")

    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return header + " " + "；".join(recommend_lines) + "。"


def _get_project_names(project_ids: list[int]) -> dict[int, str]:
    """查询 study_project 表，返回 project_id → project_name 映射"""
    if not project_ids:
        return {}
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(project_ids))
            cur.execute(
                f"SELECT project_id, project_name FROM study_project WHERE project_id IN ({placeholders})",
                project_ids
            )
            return {row["project_id"]: row["project_name"] for row in cur.fetchall()}
    finally:
        conn.close()


def _build_failed_report(failed: list[dict], rules_map: dict[int, list[dict]],
                          brief: bool = False, student_view: bool = False) -> str:
    """
    生成不达标用户的详细原因分析（内部函数）。
    对每个用户，找出失分最多的规则维度（实际得分 / 满分 最低者）。
    student_view: True = 学生端（温暖亲切），False = 企业端（专业简练）
    """
    # 查询项目名称（用于显示实际项目名称而非ID）
    all_proj_ids = list(set(d["project_id"] for d in failed))
    project_names = _get_project_names(all_proj_ids)

    # 构建规则满分映射（用于分析失分比例）
    rule_max_map_global = {}
    for proj_id, rules in rules_map.items():
        for r in rules:
            rule_max_map_global[(proj_id, r["rule_key"])] = r["score_max"]

    user_reports = []
    for d in failed:
        uid = d["user_id"]
        uname = d["user_name"]
        proj_id = d["project_id"]
        proj_name = project_names.get(proj_id, f"项目 {proj_id}")
        score = d["score"]
        max_score = d.get("max_score", 100)
        rule_scores = d.get("rule_scores", {})

        # 分析每条规则的得分率，找出最低的几个
        rule_analysis = []
        for rk, actual in rule_scores.items():
            rmax = rule_max_map_global.get((proj_id, rk), 0)
            if rmax > 0:
                ratio = actual / rmax
                rule_analysis.append((rk, actual, rmax, ratio))

        # 按得分率升序排列（最低的在前）
        rule_analysis.sort(key=lambda x: x[3])

        # 取前 3 个最弱项
        weak_points = rule_analysis[:3]

        if student_view:
            # 学生端：建议更口语化、鼓励性
            weak_items = []
            for rk, actual, rmax, _ in weak_points:
                if "GPA" in rk or "学业" in rk or "成绩" in rk:
                    suggestion = "学术表现可以再提升一些，比如加强核心课程的学习"
                elif "预算" in rk or "资金" in rk or "费用" in rk:
                    suggestion = "留学预算方面可以再做更细致的资金规划"
                elif "语言" in rk or "雅思" in rk or "托福" in rk:
                    suggestion = "语言成绩还有提升空间，建议持续加强语言能力的准备"
                elif "专业" in rk or "背景" in rk:
                    suggestion = "如果能补充相关领域的专业背景经历会更加匹配"
                elif "年龄" in rk:
                    suggestion = "可以考虑更合适年龄段的留学项目"
                else:
                    suggestion = f"{rk}方面还可以进一步优化"
                weak_items.append(f"{rk}（{actual}/{rmax}分）- {suggestion}")

            weak_desc = "；".join(weak_items)
            user_reports.append(
                f"{uname} 同学（ID: {uid}）在 {proj_name} 中获得了 {score} 分（满分 {max_score}），"
                f"距离建议标准（60 分）还有一定的距离。"
                f"具体来说：{weak_desc}"
            )
        else:
            # 企业端：结构化、专业
            weak_items = []
            for rk, actual, rmax, _ in weak_points:
                weak_items.append(f"{rk}（{actual}/{rmax} 分）")

            weak_desc = "；".join(weak_items)
            user_reports.append(
                f"{uname}（ID: {uid}）- {proj_name}：总分 {score}/{max_score}，"
                f"失分维度：{weak_desc}"
            )

    if brief:
        return ("暂未达标：" if student_view else "未达标：") + "｜".join(user_reports)

    # ── 构建 prompt ──
    if student_view:
        # 学生端
        if len(failed) <= 1 and len(set(d["user_id"] for d in failed)) <= 1:
            single_uid = list(set(d["user_id"] for d in failed))[0]
            single_uname = [d for d in failed if d["user_id"] == single_uid][0]["user_name"]
            header = f"{single_uname} 同学（ID: {single_uid}）的评估结果如下："
        else:
            unique_users = list({(d["user_id"], d["user_name"]) for d in failed})
            header = "、".join(f"{uname}（ID: {uid}）" for uid, uname in unique_users) + " 的评估结果如下："

        prompt = f"""你是一名温暖、专业的留学咨询顾问。请根据以下评估结果，生成一段鼓励性的中文反馈。

【评估结果】
- {header}

【各用户薄弱环节与提升建议】
{chr(10).join(user_reports)}

【写作要求】
1. 直接以"某某同学，你好"或用户的名字开头，不要使用"全部用户均已完成研判"这类生硬的表述
2. 先肯定用户的积极性（如"感谢你的信任""很高兴认识你"），然后委婉地说明本次评估的建议标准是 60 分，暂时没有达到
3. 列出具体的薄弱环节（用原始维度名称 + 得分 + 提升建议），格式如"GPA（5/15分）- 学术表现可以再提升一些"
4. 结尾必须温暖鼓励，如"别灰心，调整好后随时欢迎再来找我聊"，加上"如果之后有更适合你的项目，我会第一时间联系你"
5. 用连贯的中文段落，不要 JSON、列表或 markdown 格式
6. 语气像朋友聊天一样自然，把"没通过"包装为"暂时不太匹配"，强调具体提升方向，让用户觉得还有希望
7. 不超过 300 字
"""
        system_prompt = "你是一名温暖、专业的留学咨询顾问。用朋友聊天的语气反馈评估结果，像学长/学姐一样关心用户，给出真诚的建议，让用户感受到温暖和希望。"
    else:
        # 企业端
        if len(failed) <= 1 and len(set(d["user_id"] for d in failed)) <= 1:
            single_uid = list(set(d["user_id"] for d in failed))[0]
            single_uname = [d for d in failed if d["user_id"] == single_uid][0]["user_name"]
            header = f"{single_uname}（ID: {single_uid}）研判结果："
        else:
            unique_users = list({(d["user_id"], d["user_name"]) for d in failed})
            header = "；".join(f"{uname}（ID: {uid}）" for uid, uname in unique_users) + " 研判结果："

        prompt = f"""你是一名留学咨询数据分析师。请根据以下评估结果，生成一段专业简练的中文总结。

【评估结果】
- {header}

【各用户失分详情】
{chr(10).join(user_reports)}

【写作要求】
1. 开头说明"某某 暂未达到 60 分达标线"
2. 列出每个用户的总得分和失分维度（格式：维度名（实得/满分 分）），简洁明了
3. 不用鼓励语、不用寒暄，客观陈述即可
4. 用简洁的中文段落，不要 JSON、列表或markdown格式
5. 语气专业，不超过 150 字
"""
        system_prompt = "你是留学咨询数据分析师。请用专业、简练的中文总结评估结果，客观陈述即可，不需要寒暄或鼓励。"

    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        # fallback
        if student_view:
            return header + " " + " ".join(user_reports) + " 别灰心，调整好后随时欢迎再来找我聊！如果之后有更适合你的项目，我会第一时间联系你。"
        else:
            return header + " " + " ".join(user_reports)


# ────────────────────────────────────────────────────────────
# 自然语言意图解析
# ────────────────────────────────────────────────────────────
def parse_intent(user_query: str) -> dict:
    """
    用 LLM 解析用户的自然语言研判意图。
    返回: {"intent_type": "evaluate_all|evaluate_one|evaluate_by_condition",
            "names": [...], "sql_filter": "..."}
    """
    prompt = f"""你是用户意图识别助手。用户会对你说一句话，要求对某些用户进行"画像研判评估"。

请分析用户输入，判断要评估哪些目标用户。

【输入】"{user_query}"

【意图类型】
- "evaluate_all": 评估所有用户（全部、所有、整个等）
- "evaluate_one": 评估某些具体用户（给了名字）
- "evaluate_by_condition": 评估符合条件的用户

【user_profiles 表中的姓名字段是 name】

【返回格式】严格输出 JSON：
{{"intent_type": "evaluate_all" 或 "evaluate_one" 或 "evaluate_by_condition",
 "names": ["张三", "李四"],
 "reason": "判断理由"}}

约束：
- 全部/所有/整个/所有用户 → evaluate_all，names=[]
- 明确提到具体名字 → evaluate_one，names=[那些名字]
- 无法识别出任何名字、也不是"全部"指令 → evaluate_one，names=[]（禁止模糊降级为全量扫描）
"""
    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是意图识别专家。严格按 JSON 格式输出。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception as e:
        raise RuntimeError(f"意图解析失败: {e}") from e

    # 解析 JSON
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            return {"intent_type": "evaluate_all", "names": [], "sql_filter": "", "reason": "JSON 解析失败"}

    intent_type = data.get("intent_type", "evaluate_all")
    names = data.get("names", [])

    # 构建 SQL 筛选条件
    sql_filter = ""
    if intent_type == "evaluate_one" and names:
        name_list = ", ".join(f"'{n}'" for n in names)
        sql_filter = f"`name` IN ({name_list})"

    return {
        "intent_type": intent_type,
        "names": names,
        "sql_filter": sql_filter,
        "reason": data.get("reason", ""),
    }


# ────────────────────────────────────────────────────────────
# 销售顾问自动分配（咨询部轮询，跟进数最少者优先）
# ────────────────────────────────────────────────────────────
def assign_sales_user_id(conn) -> int:
    """
    自动分配销售顾问：
    1. 查 department 表中 dept_name='咨询部' 的 dept_id
    2. 查 account 表中该 dept_id 的所有有效员工 user_id
    3. 统计每个员工当前跟进中非'已签约'的客户数
    4. 返回跟进数最少的员工 user_id（负载均衡）
    """
    with conn.cursor() as cur:
        # Step 1: 咨询部 dept_id
        cur.execute("SELECT dept_id FROM department WHERE dept_name = '咨询部' LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("未找到'咨询部'，无法分配销售顾问")
        dept_id = row["dept_id"]

        # Step 2: 该部门的员工账号（仅有效状态的员工/管理者）
        cur.execute("""
            SELECT user_id FROM account
            WHERE dept_id = %s AND user_type IN ('员工', '管理者') AND status = 1
        """, (dept_id,))
        accounts = cur.fetchall()
        if not accounts:
            raise RuntimeError(f"咨询部（dept_id={dept_id}）下无有效员工账号")
        uid_list = [a["user_id"] for a in accounts]

        # Step 3: 每个员工的跟进客户数（排除已签约）
        placeholders = ", ".join(["%s"] * len(uid_list))
        cur.execute(f"""
            SELECT sales_user_id, COUNT(*) AS cnt
            FROM intention_customer
            WHERE sales_user_id IN ({placeholders})
              AND current_status != '已签约'
            GROUP BY sales_user_id
        """, uid_list)
        count_map = {row["sales_user_id"]: row["cnt"] for row in cur.fetchall()}

        # Step 4: 找最少跟进数的人（不在 count_map 中的人 = 0 个跟进，优先分配）
        best_id = None
        best_cnt = float("inf")
        for uid in uid_list:
            cnt = count_map.get(uid, 0)
            if cnt < best_cnt:
                best_cnt = cnt
                best_id = uid
        return best_id


# ────────────────────────────────────────────────────────────
# 意向客户表插入
# ────────────────────────────────────────────────────────────
def insert_intention_customer(user: dict, project_id: int, score: int, conn) -> int:
    """
    将达标用户写入 intention_customer，返回 customer_id。
    sales_user_id 由 assign_sales_user_id() 自动分配（咨询部轮询）。
    字段映射：
      user_profiles.age   → customer_age（SmallInteger，自动截断到 0-150）
      user_profiles.phone → customer_phone（VARCHAR(20)，自动截断）
    """
    sales_uid = assign_sales_user_id(conn)

    # 数据清洗：确保类型与 intention_customer 表兼容
    age_val = user.get("age")
    try:
        age_val = int(age_val)
        if age_val < 0 or age_val > 150:
            age_val = None
    except (ValueError, TypeError):
        age_val = None

    phone_val = user.get("phone")
    if phone_val:
        phone_val = str(phone_val)[:20]  # VARCHAR(20) 防止超长

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO intention_customer
            (customer_name, customer_age, customer_phone, customer_source,
             customer_demand, current_status, sales_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            user.get("name"),
            age_val,
            phone_val,
            "表单录入",
            user.get("development"),
            "意向中",
            sales_uid,
        ))
        return cur.lastrowid


# ────────────────────────────────────────────────────────────
# 针对特定用户子集的评估（含重复检查）
# ────────────────────────────────────────────────────────────
def _rule_lookup_key(r: dict) -> str:
    """从 portrait_rule 记录中挑选最友好的雷达维度展示名：rule_subcategory > rule_category > rule_key"""
    return r.get("rule_subcategory") or r.get("rule_category") or r.get("rule_key") or ""


def _build_detail_view(all_results: list[dict], rules_map: dict[int, list[dict]]) -> list[dict]:
    """
    从 all_results 构建前端「四合一」所需的结构化分数数据。
    返回按 (user_id, project_id) 聚合的结果列表：
      [{ project_id, project_name, user_id, total_score, max_score, pass_threshold,
         is_pass, dimensions: [{ key, name, score, max }] }]
    """
    project_names = _get_project_names(list(rules_map.keys()))

    # 构建 (project_id, rule_key) → 规则元数据 查找表
    rule_lookup: dict[tuple[int, str], dict] = {}
    for pid, rules in rules_map.items():
        for r in rules:
            rule_lookup[(pid, r["rule_key"])] = r

    # 按 (user_id, project_id) 分组（取最高分的记录）
    grouped: dict[tuple[int, int], dict] = {}
    for r in all_results:
        key = (r["user_id"], r["project_id"])
        if key not in grouped or r["score"] > grouped[key]["score"]:
            grouped[key] = r

    results = []
    for (uid, pid), r in grouped.items():
        dims = []
        for rk, actual in (r.get("rule_scores") or {}).items():
            rl = rule_lookup.get((pid, rk), {})
            rmax = int(rl.get("score_max") or 0)
            name = _rule_lookup_key(rl) or rk
            dims.append({
                "key": rk,
                "name": name,
                "score": int(actual or 0),
                "max": rmax,
            })
        results.append({
            "project_id": pid,
            "project_name": project_names.get(pid, "项目 %d" % pid),
            "user_id": uid,
            "total_score": int(r["score"] or 0),
            "max_score": int(r.get("max_score") or 100),
            "pass_threshold": PASS_SCORE,
            "is_pass": bool(r["is_pass"]),
            "dimensions": dims,
        })
    return results


def run_targeted_assessment(sql_filter: str, student_view: bool = False, detail_view: bool = False):
    """
    对指定的用户子集执行评估。
    :param sql_filter: WHERE 条件片段（空串表示全部）
    :param student_view: True = 学生端（温暖亲切），False = 企业端（专业简练）
    :param detail_view: True = 返回结构化 dict（含 scores + summary），False = NL 字符串
    :return: NL 字符串，或 detail_view=True 时的结构化 dict
    """
    # 1. 获取目标用户（严格精确匹配，禁止模糊 LIKE 兜底）
    #    安全说明：原代码在精确匹配落空时会退回 LIKE '%name%' 模糊匹配，
    #    导致任意 2 个中文字符都可能命中大量无关用户（如"无敌"→"王无敌""张无敌"），
    #    现已删除此兜底，sql_filter 必须精准命中，否则直接报错。
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            base_sql = "SELECT id, name FROM user_profiles WHERE name IS NOT NULL AND name != ''"
            if sql_filter:
                base_sql += " AND (" + sql_filter + ")"
            base_sql += " ORDER BY id"
            cur.execute(base_sql)
            users = cur.fetchall()
    finally:
        conn.close()

    if not users:
        return "没有找到符合条件的用户，请检查输入是否正确。"

    # 2. 检查重复诊断（仅按 user_id，防同名不同人误伤）
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for user in users:
                uid = user["id"]
                uname = user["name"]
                cur.execute(
                    "SELECT project_id, score FROM intention_diagnosis WHERE user_id = %s",
                    (uid,)
                )
                existing = cur.fetchone()
                if existing:
                    raise ValueError(
                        "用户 {}（ID {}）已是意向客户，已诊断项目：项目{}({}分)".format(uname, uid, existing["project_id"], existing["score"])
                    )
    finally:
        conn.close()

    # 3. 获取所有 project_id 并逐个评估
    project_ids = get_all_project_ids()
    if not project_ids:
        return "portrait_rule 表中没有活跃规则，无法评估。"

    # ── 统一记录每个用户在每个项目上的得分 ──
    all_results = []  # {uid, uname, project_id, score, max_score, rule_scores, is_pass}

    conn = get_conn()
    try:
        # ── 评估阶段：遍历所有项目 × 所有用户 ──
        for project_id in project_ids:
            rules = get_rules_by_project(project_id)
            if not rules:
                continue

            try:
                expr_data = generate_project_expression(rules, project_id)
            except Exception as e:
                logger.warning("Project %d expression failed: %s", project_id, e)
                continue

            expression = expr_data["expression"]
            rule_expressions = expr_data.get("rule_expressions", {})
            max_score = expr_data.get("max_score", 100)

            with conn.cursor() as cur:
                for user in users:
                    uid = user["id"]
                    uname = user["name"]

                    cur.execute(
                        "SELECT CAST(GREATEST(0, LEAST((" + expression + "), 999)) AS SIGNED) AS total "
                        "FROM user_profiles WHERE id = " + str(uid)
                    )
                    score = cur.fetchone()["total"]

                    # 计算每个规则维度的得分
                    rule_scores = {}
                    for rk, rexpr in rule_expressions.items():
                        try:
                            cur.execute(
                                "SELECT CAST(GREATEST(0, LEAST((" + rexpr + "), 999)) AS SIGNED) AS s "
                                "FROM user_profiles WHERE id = " + str(uid)
                            )
                            rule_scores[rk] = cur.fetchone()["s"]
                        except Exception:
                            rule_scores[rk] = 0

                    is_pass = score >= PASS_SCORE
                    all_results.append({
                        "user_id": uid,
                        "user_name": uname,
                        "project_id": project_id,
                        "score": score,
                        "max_score": max_score,
                        "rule_scores": rule_scores,
                        "is_pass": is_pass,
                    })

        # ── 汇总阶段：按用户聚合，判断是否至少有一个项目达标 ──
        user_best_pass = {}   # uid → 最佳通过的 project
        user_all_fail = []    # 全部未通过的用户（取最高分的 project 用于分析）
        for r in all_results:
            uid = r["user_id"]
            if r["is_pass"]:
                # 保留该用户得分最高的通过 project
                if uid not in user_best_pass or r["score"] > user_best_pass[uid]["score"]:
                    user_best_pass[uid] = r
            else:
                user_all_fail.append(r)

        # 通过的用户（至少一个项目达标）
        passed_uids = set(user_best_pass.keys())

        # 未通过的用户 = 全部 project 都未达标
        # 如果一个用户有任何 project 通过，即使在其他 project 未通过，也视为通过
        failed_user_ids = set()
        failed_diagnoses = []
        for r in user_all_fail:
            uid = r["user_id"]
            if uid not in passed_uids:
                failed_user_ids.add(uid)
                failed_diagnoses.append(r)

        # 取每个未通过用户得分最高的 project 来分析薄弱项
        failed_best = {}
        for r in failed_diagnoses:
            uid = r["user_id"]
            if uid not in failed_best or r["score"] > failed_best[uid]["score"]:
                failed_best[uid] = r
        failed_diagnoses_unique = list(failed_best.values())

        # ── 数据库写入阶段 ──
        # 1. 通过的用户：insert intention_diagnosis（每个通过的 project 都记）
        passed_diagnoses = []
        for r in all_results:
            if r["is_pass"]:
                uid = r["user_id"]
                uname = r["user_name"]
                proj_id = r["project_id"]
                cur.execute(
                    # 注意：intention_diagnosis 表没有 user_name 列，只写 user_id
                    "INSERT INTO intention_diagnosis (user_id, project_id, score, rule_details) "
                    "VALUES (%s, %s, %s, %s)",
                    (uid, proj_id, r["score"], json.dumps(r["rule_scores"], ensure_ascii=False))
                )
                passed_diagnoses.append(r)

        # 2. 未通过全部 project 的用户：assess 改为 '已研判'
        for uid in failed_user_ids:
            conn.cursor().execute(
                "UPDATE user_profiles SET assess = '已研判' WHERE id = %s "
                "AND (assess IS NULL OR assess != '已研判')",
                (uid,)
            )

        conn.commit()

        # 3. 通过的用户：insert intention_customer（只取最佳 project）→ 验证 → 删除 user_profiles
        if passed_uids:
            high_users = {u["id"]: u for u in users if u["id"] in passed_uids}
            try:
                for uid in passed_uids:
                    user = high_users[uid]
                    best = user_best_pass[uid]  # 已通过验证存在
                    new_cid = insert_intention_customer(user, best["project_id"], best["score"], conn)
                    # 验证插入成功
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT customer_id FROM intention_customer WHERE customer_id = %s",
                            (new_cid,)
                        )
                        if not cur.fetchone():
                            raise RuntimeError(
                                f"意向客户表插入验证失败：用户 {user['name']}（ID {uid}）"
                            )

                # 全部验证通过后才删除 user_profiles
                del_ids = ", ".join(str(uid) for uid in passed_uids)
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM user_profiles WHERE id IN (" + del_ids + ")")

                conn.commit()
            except Exception as e:
                conn.rollback()
                raise RuntimeError(f"意向客户转移失败，已回滚：{e}") from e

    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

    # 构建 project_id → 规则列表映射 + project_id → 项目名称
    rules_map = {}
    for project_id in project_ids:
        rules_map[project_id] = get_rules_by_project(project_id)

    # 通过的所有 project 详情（不仅仅是最佳），供_summary展示所有通过的项目
    all_passed = [r for r in all_results if r["is_pass"]]

    summary = generate_natural_response(
        all_passed, len(users),
        failed=failed_diagnoses_unique, rules_map=rules_map,
        student_view=student_view
    )

    if detail_view:
        # 返回结构化 dict，供前端雷达图 + 百分制使用
        # user_ids 仅保留"真正被研判的用户"，不把已判别的列入
        return {
            "summary": summary,
            "pass_threshold": PASS_SCORE,
            "results": _build_detail_view(all_results, rules_map),
            "user_ids": [u["id"] for u in users],
        }
    return summary



def polish_error_message(error_msg: str) -> str:
    """调用大模型将异常信息润色为友好的自然语言"""
    prompt = f"""你是留学咨询系统助手。系统出现了一条异常信息，请转换为友好自然的中文告知用户。

异常信息：{error_msg}

要求：
1. 用简洁自然的中文解释
2. 如果是"重复诊断"或"已是意向客户"，温和告知用户无需重复操作
3. 控制在 50 字以内
"""
    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是留学咨询系统助手。请将系统异常转换为友好的用户提示。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return error_msg
