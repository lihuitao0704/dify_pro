"""
用户画像评估模块（多项目 + 指定用户 + 自然语言返回）
=========================================================
- 评估时指定用户（1个/多个/全部）
- 自动找出 portrait_rule 表中所有 project_id
- 每个 project_id 独立评分（该 project_id 下所有规则分数之和 >= 80 即通过）
- 结果写入 intention_diagnosis 表（诊断id, user_id, project_id, score, rule_details）
- 大模型润色结果为自然语言返回
"""

import os
import json
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

PASS_SCORE = 80


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
    """查询待评估的用户列表"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            sql = "SELECT id, name FROM user_profiles WHERE name IS NOT NULL AND name != ''"
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
    lines.append('id, name, age, education, major, gpa, target_country, target_major, budget, language_score, phone, wechat, email, consultation_status, status')
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



def generate_project_expression(rules: list[dict], project_id: int) -> dict:
    """为单个 project_id 生成评分表达式"""
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
                    "consultation_status", "status", "conversation_id", "created_at", "updated_at"}
    expr = data.get("expression", "")
    used = set(re.findall(r'`(\w+)`', expr))
    bad = [c for c in used if c not in valid_fields]
    if bad:
        raise ValueError(f"project {project_id} 表达式引用了不存在的字段: {bad}")

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
# 大模型润色为自然语言
# ────────────────────────────────────────────────────────────
def generate_natural_response(passed: list[dict], total_users: int) -> str:
    """将诊断结果润色为自然语言"""
    if not passed:
        return f"本次共评估 {total_users} 位用户，全部用户均已完成研判，已通过 0 人。"

    # 按用户分组
    user_results = {}
    for d in passed:
        uname = d["user_name"]
        if uname not in user_results:
            user_results[uname] = {"user_id": d["user_id"], "projects": []}
        user_results[uname]["projects"].append({
            "project_id": d["project_id"],
            "score": d["score"],
            "rule_scores": d.get("rule_scores", {}),
        })

    # 构建推荐信息：每个用户取最高分的项目
    recommend_lines = []
    user_best = {}  # uname -> (project_id, score)
    for uname, info in user_results.items():
        best_project = max(info["projects"], key=lambda p: p["score"])
        user_best[uname] = (best_project["project_id"], best_project["score"])

    for uname, (proj_id, score) in user_best.items():
        recommend_lines.append(f"{uname}：项目 {proj_id}（{score} 分）")

    passed_count = len(user_results)  # 通过的用户数（同名合并后）

    prompt = f"""你是一名留学咨询数据分析师。请根据以下评估结果，生成一段简洁自然的中文总结。

【评估总览】
- 共评估 {total_users} 位用户，全部已完成研判
- 已通过 {passed_count} 人

【通过的用户及推荐项目】
{chr(10).join(recommend_lines)}

【写作要求】
1. 开头先说明"全部用户均已完成研判，已通过 X 人"
2. 如果有通过的用户，另起一行以"Recommendation:"开头，依次列出每个用户和其最佳项目及分数，格式如"Recommendation: Zhang San: Singapore Project (120); Li Si: Germany Project (100)"
3. 如果没有通过的用户，只返回"全部用户均已完成研判，已通过 0 人。"
4. 用简洁的中文段落，不要 JSON、列表或markdown格式
5. 语气专业，不超过 150 字
"""

    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是留学咨询数据分析师。请用简洁自然的中文总结评估结果。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        # 失败时返回默认文本
        summary_parts = []
        for uname, info in user_results.items():
            for p in info["projects"]:
                summary_parts.append(f"{uname} 在项目{p['project_id']}获得{p['score']}分")
        return f"本次评估共 {total_users} 位用户，其中通过研判的有：{'；'.join(summary_parts)}。"


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
- 全部/所有/整个 → evaluate_all，names=[]
- 给了具体名字 → evaluate_one，names=[那些名字]
- 模糊输入 → evaluate_all
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
# 针对特定用户子集的评估（含重复检查）
# ────────────────────────────────────────────────────────────
def run_targeted_assessment(sql_filter: str) -> str:
    """
    对指定的用户子集执行评估。
    :param sql_filter: WHERE 条件片段（空串表示全部）
    :return: 自然语言结果
    """
    # 1. 获取目标用户（先精确匹配，无结果则模糊匹配）
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            base_sql = "SELECT id, name FROM user_profiles WHERE name IS NOT NULL AND name != ''"
            if sql_filter:
                base_sql += " AND (" + sql_filter + ")"
            base_sql += " ORDER BY id"
            cur.execute(base_sql)
            users = cur.fetchall()
            
            # 精确匹配无结果，尝试模糊匹配（用 OR LIKE 拼接所有名字）
            if not users and sql_filter:
                # 从 sql_filter 中提取名字列表
                import re
                name_matches = re.findall(r"'([^']+)'", sql_filter)
                if name_matches:
                    like_conditions = " OR ".join(["name LIKE '%{}%'".format(n.replace("'", "''")) for n in name_matches])
                    cur.execute("SELECT id, name FROM user_profiles WHERE name IS NOT NULL AND name != '' AND (" + like_conditions + ") ORDER BY id")
                    users = cur.fetchall()
    finally:
        conn.close()

    if not users:
        return "没有找到符合条件的用户，请检查输入是否正确。"

    # 2. 检查重复诊断（通过 user_id 或 user_name）
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for user in users:
                uid = user["id"]
                uname = user["name"]
                cur.execute(
                    "SELECT project_id, score FROM intention_diagnosis WHERE user_id = %s OR user_name = %s",
                    (uid, uname)
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

    passed_diagnoses = []

    conn = get_conn()
    try:
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

            with conn.cursor() as cur:
                for user in users:
                    uid = user["id"]
                    uname = user["name"]

                    cur.execute(
                        "SELECT CAST(GREATEST(0, LEAST((" + expression + "), 999)) AS SIGNED) AS total "
                        "FROM user_profiles WHERE id = " + str(uid)
                    )
                    score = cur.fetchone()["total"]

                    if score >= PASS_SCORE:
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

                        cur.execute(
                            "INSERT INTO intention_diagnosis (user_id, user_name, project_id, score, rule_details) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (uid, uname, project_id, score, json.dumps(rule_scores, ensure_ascii=False))
                        )

                        passed_diagnoses.append({
                            "user_id": uid,
                            "user_name": uname,
                            "project_id": project_id,
                            "score": score,
                            "rule_scores": rule_scores,
                        })
                    else:
                        # 未达标：status 改为 '已研判'
                        cur.execute(
                            "UPDATE user_profiles SET status = '已研判' WHERE id = %s "
                            "AND (status IS NULL OR status != '已研判')",
                            (uid,)
                        )

        conn.commit()

        # 删除达标用户
        if passed_diagnoses:
            high_uid_set = {d["user_id"] for d in passed_diagnoses}
            del_ids = ", ".join(str(uid) for uid in high_uid_set)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_profiles WHERE id IN (" + del_ids + ")")
            conn.commit()

    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

    return generate_natural_response(passed_diagnoses, len(users))



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
