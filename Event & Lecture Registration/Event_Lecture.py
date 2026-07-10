"""
NL2SQL 引擎 —— 活动与讲座报名系统
功能：调用千问模型将自然语言转为 SQL，对 MySQL 数据库进行增删改查。
"""
import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# ── MySQL 连接配置 ──────────────────────────────────────────
DB_CONFIG = {
    "host": "192.168.48.121",
    "port": 3306,
    "user": "offer",
    "password": "123456",
    "database": "dify_pro",
    "charset": "utf8mb4",
}

# ── 表结构定义（用于给模型描述 schema） ─────────────────────
SCHEMA = {
    "lectures": {
        "description": "讲座表，存储留学相关讲座（德国、新加坡等国家）",
        "columns": {
            "lecture_id": "INT 自增主键，讲座唯一ID",
            "title": "VARCHAR 讲座主题",
            "event_time": "DATETIME 讲座时间",
            "location": "VARCHAR 地点（线上填链接，线下填地址）",
            "registration_method": "VARCHAR 报名方式（扫码、链接、对话报名）",
            "speaker": "VARCHAR 主讲人",
        },
    },
    "activities": {
        "description": "活动表，存储团建等公司活动",
        "columns": {
            "activity_id": "INT 自增主键，活动唯一ID",
            "title": "VARCHAR 活动主题",
            "event_time": "DATETIME 活动时间",
            "location": "VARCHAR 活动地点",
            "registration_method": "VARCHAR 报名方式",
        },
    },
    "lecture_registrations": {
        "description": "讲座报名表，存储客户对留学讲座的报名记录",
        "columns": {
            "registration_id": "INT 自增主键，报名唯一ID",
            "lecture_id": "INT 关联讲座ID，对应 lectures.lecture_id",
            "name": "VARCHAR 报名人姓名",
            "phone": "VARCHAR 报名人手机号码",
        },
    },
    "activity_registrations": {
        "description": "活动报名表，存储员工对团建活动的报名记录",
        "columns": {
            "registration_id": "INT 自增主键，报名唯一ID",
            "activity_id": "INT 关联活动ID，对应 activities.activity_id",
            "name": "VARCHAR 报名人姓名",
            "phone": "VARCHAR 报名人手机号码",
        },
    },
}


# ════════════════════════════════════════════════════════════
# 数据库连接
# ════════════════════════════════════════════════════════════
def get_conn():
    import pymysql

    conn = pymysql.connect(**DB_CONFIG)
    return conn


# ════════════════════════════════════════════════════════════
# Schema → 给模型的描述文本
# ════════════════════════════════════════════════════════════
def schema_prompt() -> str:
    """生成给千问模型看的 schema 描述。"""
    lines = ["以下是 dify_pro 数据库中的三张表及其字段：\n"]
    for table, meta in SCHEMA.items():
        lines.append(f"【表 {table}】{meta['description']}")
        for col, desc in meta["columns"].items():
            lines.append(f"  - {col}: {desc}")
        lines.append("")
    lines.append("关联关系：lecture_registrations.lecture_id = lectures.lecture_id；activity_registrations.activity_id = activities.activity_id")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# 调用千问模型生成 SQL
# ════════════════════════════════════════════════════════════
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://ws-80gz91pjbhgouudd.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
)
MODEL = "qwen-plus"


def call_qwen_sql(user_query: str) -> str:
    """调用千问模型（通过 OpenAI 兼容接口），将自然语言转为 SQL。"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未设置，请在 .env 文件或环境变量中配置")

    # 预计算相对时间的具体日期，直接注入到 prompt 里让模型"看到答案"
    from datetime import datetime, timedelta
    _today = datetime.now().date()
    _weekdays_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    _today_str = _today.strftime("%Y-%m-%d")
    _today_wd = _today.weekday()  # Monday=0

    def _d(offset):
        return (_today + timedelta(days=offset)).strftime("%Y-%m-%d")

    # 下周X 天数差（下周一 = 即将到来的下一个周一）
    # 例：周四 → 下周一 = (0-3) % 7 = 4 天 → 7/13 ✓
    #     周一 → 下周一 = (0-0) % 7 → 当天 → +7 = 14 → 7/20（下周一=7天后）
    days_next = {}
    for i in range(7):
        diff = (i - _today_wd) % 7
        if diff == 0:
            days_next[i] = 7  # 今天就是 X，下周 = 7 天后
        else:
            days_next[i] = diff  # 未来最近的 X

    # 预计算用户查询中所有提到的相对时间 → 真实日期
    def _resolve_time_in_query(q: str):
        """识别查询中的相对时间表达，返回 {表达: 日期} 字典。"""
        resolved = {}
        # 简单相对天
        if "大后天" in q:
            resolved["大后天"] = _d(3)
        if "后天" in q:
            resolved["后天"] = _d(2)
        if "明天" in q:
            resolved["明天"] = _d(1)
        if "今天" in q or "今日" in q:
            resolved["今天"] = _today_str
        if "昨天" in q:
            resolved["昨天"] = _d(-1)
        if "前天" in q:
            resolved["前天"] = _d(-2)
        # 本周X / 下周X
        import re
        for m in re.finditer(r"(本|下)?周([一二三四五六日天])", q):
            which = m.group(1)
            wd_char = m.group(2)
            wd_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
            target_wd = wd_map[wd_char]
            if which == "下":
                resolved[m.group(0)] = _d(days_next[target_wd])
            elif which == "本":
                resolved[m.group(0)] = _d(days_this[target_wd])
            else:
                # 省略本/下 → 默认下周
                resolved[m.group(0)] = _d(days_next[target_wd])
        return resolved

    _resolved = _resolve_time_in_query(user_query)

    # 构造时间说明文本
    _date_help_lines = [f"当前日期：{_today_str}（{_weekdays_cn[_today_wd]}）。"]
    if _resolved:
        _date_help_lines.append("用户查询中相对时间对应的具体日期（必须在 SQL 中直接使用这些日期）：")
        for expr, date_str in _resolved.items():
            _date_help_lines.append(f"  - 「{expr}」= {date_str}")
    _date_help = "\n".join(_date_help_lines)

    system_prompt = (
        f"【重要】用户查询中的相对时间已经换算完成，换算结果如下：\n{_date_help}\n"
        "**必须直接使用以上换算出的日期，禁止自行推算！**\n\n"
        "你是一个 NL2SQL 助手。根据用户自然语言，结合下方表结构，"
        "生成一条可在 MySQL 上直接执行的 SQL 语句。\n"
        "要求：\n"
        "1. 只输出 SQL，不要任何解释、不要 markdown 代码块。\n"
        "2. 操作类型可能是 SELECT / INSERT / UPDATE / DELETE，根据用户意图判断。\n"
        "3. 根据用户意图选择正确的表（lectures / activities / lecture_registrations / activity_registrations）。\n"
        "4. INSERT 时不需要自增主键，数据库会自动生成。\n"
        "5. 时间条件使用 NOW() 比较。\n"
        "6. 用户提到相对时间时，必须在上方给出的对应关系中找到具体日期，"
        "   **直接在 SQL 中写出该日期字符串**（如 '2026-07-20'），禁止自行推算。\n"
        "7. 用户提及讲座/活动的主题关键词（如「研讨会」「留学讲座」「德国留学」）时，"
        "   必须在 WHERE 中加 title LIKE '%关键词%' 进行模糊匹配。\n"
        "8. 表之间没有外键约束，DELETE 直接操作目标表即可，不需要级联删除。\n"
        "\n" + schema_prompt()
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
    )

    sql = response.choices[0].message.content.strip()
    sql = re.sub(r"^```(?:sql)?\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql).strip()
    return sql


# ════════════════════════════════════════════════════════════
# 规则匹配降级方案（无 API Key 时使用）
# ════════════════════════════════════════════════════════════

# 中文相对时间 → 天数偏移（相对于今天）
_WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def _parse_relative_date(query: str):
    """解析中文相对时间表达，返回 (start_date, end_date) 或 None。

    支持：今天、明天、后天、大后天、昨天、前天、本周X、下周X。
    返回的日期格式为 'YYYY-MM-DD'，end_date 为当天 23:59:59 对应的日期（同一天）。
    """
    from datetime import datetime, timedelta

    today = datetime.now().date()

    # ── 简单相对天数 ──
    if "大后天" in query:
        d = today + timedelta(days=3)
        return d.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")
    if "后天" in query:
        d = today + timedelta(days=2)
        return d.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")
    if "明天" in query:
        d = today + timedelta(days=1)
        return d.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")
    if "今天" in query or "今日" in query:
        return today.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if "昨天" in query:
        d = today - timedelta(days=1)
        return d.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")
    if "前天" in query:
        d = today - timedelta(days=2)
        return d.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")

    # ── 本周X / 下周X ──
    import re
    m = re.search(r"(本|下)?周([一二三四五六日天])", query)
    if m:
        which_week = m.group(1)  # 本 / 下 / None
        target_wd = _WEEKDAY_MAP[m.group(2)]
        today_wd = today.weekday()  # Monday=0

        # 下周X：即将到来的下一个 X（下周一 = 7/13 而不是 7/20）
        diff = (target_wd - today_wd) % 7
        if diff == 0:
            days_until_next = 7  # 今天就是 X，下周 = 7 天后
        else:
            days_until_next = diff  # 未来最近的 X

        if which_week == "下":
            days_until = days_until_next
        elif which_week == "本":
            # 本周X：本周内（含今天）的 X
            days_until = (target_wd - today_wd) % 7
        else:
            # 口语中省略"本/下"时（如"周一那场"），默认指下周
            days_until = days_until_next

        d = today + timedelta(days=days_until)
        return d.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d")

    return None


def rule_match_sql(user_query: str) -> str:
    """关键词规则匹配，作为无 API Key 时的降级方案。"""
    q = user_query.lower()

    is_insert = any(k in q for k in ["新增", "添加", "插入", "报名", "增加", "创建"])
    is_delete = any(k in q for k in ["删除", "删掉", "移除", "取消"])
    is_update = any(k in q for k in ["修改", "更新", "更改", "改一下"])

    # 判断目标表
    if any(k in q for k in ["报名", "报名人", "报名信息", "手机号", "电话", "注册"]):
        # 区分是讲座报名还是活动报名
        if any(k in q for k in ["活动", "团建", "运动会", "烧烤", "露营", "拓展"]):
            target = "activity_registrations"
        else:
            target = "lecture_registrations"
    elif any(k in q for k in ["活动", "团建", "运动会", "烧烤", "露营", "拓展"]):
        target = "activities"
    else:
        target = "lectures"

    lid = _extract_int(user_query, ["讲座", "活动", "lecture_id", "activity_id", "id"])
    phone = _extract_phone(user_query)
    name = _extract_name(user_query)
    date_range = _parse_relative_date(user_query)

    # 优先级：delete > insert > update > select（避免"报名"干扰"删除报名"的判断）
    if is_delete:
        return _rule_delete(target, lid, phone, name, date_range, user_query)
    if is_insert:
        return _rule_insert(user_query, target)
    if is_update:
        return _rule_update(user_query, target, lid, phone, name)
    return _rule_select(user_query, target, lid, phone, name, date_range)


def _extract_int(text, prefixes):
    for pre in prefixes:
        m = re.search(rf"{pre}[^\d]*(\d+)", text)
        if m:
            return int(m.group(1))
    return None


def _extract_phone(text):
    m = re.search(r"1[3-9]\d{9}", text)
    return m.group(0) if m else None


def _extract_name(text):
    m = re.search(r"(?:姓名|名字|叫|名为)\s*([一-龥]{2,4})", text)
    return m.group(1) if m else None


def _rule_insert(user_query, table):
    if table == "lecture_registrations":
        lid = _extract_int(user_query, ["讲座"])
        name = _extract_name(user_query)
        phone = _extract_phone(user_query)
        if lid and name and phone:
            return f"INSERT INTO lecture_registrations (lecture_id, name, phone) VALUES ({lid}, '{name}', '{phone}')"
        return "INSERT INTO lecture_registrations (lecture_id, name, phone) VALUES (/*讲座ID*/, '/*姓名*/', '/*手机号*/')"
    if table == "activity_registrations":
        aid = _extract_int(user_query, ["活动"])
        name = _extract_name(user_query)
        phone = _extract_phone(user_query)
        if aid and name and phone:
            return f"INSERT INTO activity_registrations (activity_id, name, phone) VALUES ({aid}, '{name}', '{phone}')"
        return "INSERT INTO activity_registrations (activity_id, name, phone) VALUES (/*活动ID*/, '/*姓名*/', '/*手机号*/')"
    if table == "activities":
        return "INSERT INTO activities (title, event_time, location, registration_method) VALUES ('/*主题*/', '/*时间*/', '/*地点*/', '/*报名方式*/')"
    return "INSERT INTO lectures (title, event_time, location, registration_method, speaker) VALUES ('/*主题*/', '/*时间*/', '/*地点*/', '/*报名方式*/', '/*主讲人*/')"


def _rule_select(user_query, table, lid, phone, name, date_range=None):
    where = []
    if lid:
        if table == "lectures":
            where.append(f"lecture_id = {lid}")
        elif table == "activities":
            where.append(f"activity_id = {lid}")
        elif table == "lecture_registrations":
            where.append(f"lecture_id = {lid}")
        elif table == "activity_registrations":
            where.append(f"activity_id = {lid}")
    if phone:
        where.append(f"phone = '{phone}'")
    if name:
        where.append(f"name = '{name}'")

    # 相对时间范围
    if date_range and table in ("lectures", "activities"):
        start_d, end_d = date_range
        where.append(f"DATE(event_time) >= '{start_d}' AND DATE(event_time) <= '{end_d}'")

    if any(k in user_query for k in ["近期", "最近", "即将"]):
        where.append("event_time >= NOW()")
    where_clause = f" WHERE {' AND '.join(where)}" if where else ""
    if any(k in user_query for k in ["近期", "最近", "即将"]) or date_range:
        where_clause += " ORDER BY event_time ASC"
    return f"SELECT * FROM {table}{where_clause}"


def _build_time_conditions(table, date_range, user_query: str = ""):
    """根据日期范围和关键词，生成 WHERE 条件片段（用于 lectures/activities 表）。"""
    conditions = []

    # 时间条件：映射到表的时间字段
    if date_range:
        start_d, end_d = date_range
        time_col = "event_time"
        # 子查询里都用 event_time
        conditions.append(
            f"DATE({time_col}) >= '{start_d}' AND DATE({time_col}) <= '{end_d}'"
        )

    # 关键词条件：从用户提问里提取可能的标题关键词
    if user_query:
        for kw in ["研讨会", "讲座", "留学", "团建", "运动会", "烧烤", "露营", "拓展", "说明会", "分享会"]:
            if kw in user_query:
                conditions.append(f"title LIKE '%{kw}%'")
                break  # 只取第一个匹配的关键词，避免过度限制

    return conditions


def _rule_delete(table, lid, phone, name, date_range=None, user_query=""):
    # 直接操作目标表，无需级联删除
    if lid:
        if table == "lectures":
            return f"DELETE FROM lectures WHERE lecture_id = {lid}"
        if table == "activities":
            return f"DELETE FROM activities WHERE activity_id = {lid}"
        if table == "lecture_registrations":
            return f"DELETE FROM lecture_registrations WHERE lecture_id = {lid}"
        if table == "activity_registrations":
            return f"DELETE FROM activity_registrations WHERE activity_id = {lid}"
    if phone:
        return f"DELETE FROM {table} WHERE phone = '{phone}'"
    if name:
        return f"DELETE FROM {table} WHERE name = '{name}'"
    # 无 ID/手机/姓名，但有时间/关键词 → 按条件删
    conds = _build_time_conditions(table, date_range, user_query)
    if conds:
        where = " AND ".join(conds)
        return f"DELETE FROM {table} WHERE {where}"
    return f"DELETE FROM {table} WHERE /* 补充条件 */"


def _rule_update(user_query, table, lid, phone, name):
    if table == "lectures" and lid:
        return f"UPDATE lectures SET /*字段=*/ WHERE lecture_id = {lid}"
    if table == "activities" and lid:
        return f"UPDATE activities SET /*字段=*/ WHERE activity_id = {lid}"
    if table == "lecture_registrations":
        if phone:
            return f"UPDATE lecture_registrations SET /*字段=*/ WHERE phone = '{phone}'"
        if lid:
            return f"UPDATE lecture_registrations SET /*字段=*/ WHERE lecture_id = {lid}"
    if table == "activity_registrations":
        if phone:
            return f"UPDATE activity_registrations SET /*字段=*/ WHERE phone = '{phone}'"
        if lid:
            return f"UPDATE activity_registrations SET /*字段=*/ WHERE activity_id = {lid}"
    return f"UPDATE {table} SET /*字段=*/ WHERE /*条件=*/"


# ════════════════════════════════════════════════════════════
# SQL 执行器
# ════════════════════════════════════════════════════════════
def _check_duplicate(cursor, table: str, values_str: str) -> bool:
    """检查 INSERT 的目标行是否已存在。

    values_str 形如 \"1, '张三', '13800138000'\"，按 columns 顺序匹配。
    根据表名选择用于判重的列：
      - lecture_registrations: lecture_id + name + phone
      - activity_registrations: activity_id + name + phone
      - lectures / activities: title + event_time
    """
    # 解析值列表（简单 split，适用于本系统的简单 INSERT）
    raw_vals = [v.strip().strip("'\"") for v in values_str.split(",")]

    if table == "lecture_registrations":
        # 列顺序: lecture_id, name, phone
        if len(raw_vals) >= 3:
            where = f"lecture_id = {raw_vals[0]} AND name = '{raw_vals[1]}' AND phone = '{raw_vals[2]}'"
        else:
            return False
    elif table == "activity_registrations":
        if len(raw_vals) >= 3:
            where = f"activity_id = {raw_vals[0]} AND name = '{raw_vals[1]}' AND phone = '{raw_vals[2]}'"
        else:
            return False
    elif table == "lectures":
        # 列顺序: title, event_time, location, registration_method, speaker
        # event_time 用 DATE 比较，兼容 '2026-09-20 14:00:00' 与 '2026-09-20 14:00'
        if len(raw_vals) >= 2:
            where = f"title = '{raw_vals[0]}' AND DATE(event_time) = DATE('{raw_vals[1]}')"
        else:
            return False
    elif table == "activities":
        if len(raw_vals) >= 2:
            where = f"title = '{raw_vals[0]}' AND DATE(event_time) = DATE('{raw_vals[1]}')"
        else:
            return False
    else:
        return False

    cursor.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE {where}")
    row = cursor.fetchone()
    return row[0] > 0 if row else False


def execute_sql(sql: str) -> dict:
    """执行 SQL，支持多条以分号隔开的语句，返回结构化结果。

    特殊处理：
    - SELECT 无结果 → 返回 error 类型，提示没有数据
    - INSERT 重复数据 → 返回 error 类型，提示数据已存在
    - DELETE/UPDATE 影响 0 行 → 返回 error 类型，提示未找到匹配数据
    """
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            # 拆分多条 SQL
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            total_affected = 0

            for stmt in statements:
                # INSERT 前先检查重复（兼容带列名或不带列名的写法）
                m = re.match(
                    r"INSERT\s+INTO\s+(\w+)\s*(?:\([^)]*\))?\s+VALUES\s*\((.+)\)\s*$",
                    stmt, re.IGNORECASE
                )
                if m:
                    table_name = m.group(1)
                    values_str = m.group(2)
                    if _check_duplicate(cursor, table_name, values_str):
                        return {
                            "type": "error",
                            "data": None,
                            "message": f"数据已存在：{table_name} 中已有相同的记录，请勿重复添加",
                        }

                cursor.execute(stmt)
                total_affected += cursor.rowcount

            # 最后一条决定返回类型
            last_stmt = statements[-1].upper()
            if last_stmt.startswith("SELECT"):
                cols = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
                if not rows:
                    return {
                        "type": "error",
                        "data": [],
                        "message": "没有查询到相关记录，请检查查询条件（如日期、关键词）是否正确",
                    }
                return {"type": "select", "data": rows, "message": f"查询到 {len(rows)} 条记录"}
            else:
                conn.commit()
                if total_affected == 0:
                    return {
                        "type": "error",
                        "data": 0,
                        "message": "未找到匹配的数据，没有内容被删除/修改，请检查查询条件（如日期、关键词）是否正确",
                    }
                return {
                    "type": "dml",
                    "data": total_affected,
                    "message": f"执行成功，共影响 {total_affected} 行",
                }
    except Exception as e:
        return {"type": "error", "data": None, "message": str(e)}
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════
# 千问润色结果
# ════════════════════════════════════════════════════════════
def polish_result(user_query: str, sql: str, result: dict) -> str:
    """用千问模型将 SQL 查询结果润色为自然语言。"""
    if result["type"] == "error":
        return f"抱歉，查询出错：{result['message']}"

    if result["type"] == "dml":
        # 增删改直接返回操作结果，不需要润色
        return result["message"]

    # 只有 SELECT 才需要润色
    rows = result["data"]
    if not rows:
        return "没有查询到相关记录。"
    result_text = json.dumps(rows, ensure_ascii=False, default=str)

    prompt = (
        f"用户提问：「{user_query}」\n"
        f"数据库返回的原始数据（JSON）：\n{result_text}\n\n"
        "请根据用户提问，把 JSON 中的数据拆解成自然语言回答。\n"
        "要求：\n"
        "1. 每条记录用「字段名: 值」的格式列出，字段名用中文（如 主题、时间、地点、报名方式、主讲人、姓名、手机号），不同字段用逗号分隔。\n"
        "2. 多条记录时每条占一行，开头用「活动：」「讲座：」「报名：」等对应表类型的词。\n"
        "3. 时间格式统一为 YYYY-MM-DD HH:MM，不要带 T 和秒。\n"
        "4. 不要提 SQL、数据库、JSON，不要加任何前缀说明，只输出润色后的回答。\n"
        "示例：活动：年中总结暨团队烧烤派对，时间: 2026-08-02 17:00，地点: 广州番禺生态园，报名方式: 扫码报名"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        # 润色失败时降级返回原始信息
        return result["message"]


# ════════════════════════════════════════════════════════════
# 对外主入口
# ════════════════════════════════════════════════════════════
def nl2sql(user_query: str) -> dict:
    """自然语言 → SQL → 执行 → 润色 → 返回结果。"""
    try:
        sql = call_qwen_sql(user_query)
    except Exception as e:
        sql = rule_match_sql(user_query)

    # 安全校验：如果用户没要增删改，但生成了非 SELECT，拦截
    user_wants_modification = any(k in user_query for k in ["新增", "添加", "插入", "报名", "增加", "创建",
                                                           "删除", "删掉", "移除", "取消",
                                                           "修改", "更新", "更改", "改一下"])
    first_stmt = sql.split(";")[0].strip().upper()
    if not user_wants_modification and not first_stmt.startswith("SELECT"):
        return {
            "query": user_query,
            "sql": sql,
            "result": {"type": "error", "data": None, "message": "安全拦截：查询操作不允许执行增删改语句"},
            "polished": "抱歉，您的查询请求生成了非查询语句，已被安全策略拦截。",
        }

    result = execute_sql(sql)
    # 用千问润色结果
    polished = polish_result(user_query, sql, result)
    return {"query": user_query, "sql": sql, "result": result, "polished": polished}
