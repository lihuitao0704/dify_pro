"""
智能留学顾问系统 - 后端 API 服务 (Flask-RESTX)
提供课程查询、用户信息保存、咨询记录等功能
访问 Swagger 文档: http://localhost:8005/docs

新增 /api/agent 自然语言入口（NL2SQL 模式 + 规则模式），
支持 Dify 通过自然语言进行增删改查操作。
"""
import json
import re
from datetime import datetime
from decimal import Decimal

import pymysql
from flask import Flask, request
from flask_restx import Api, Namespace, Resource, fields

from config import (
    DB_CONFIG, API_HOST, API_PORT,
    LANGUAGE_THRESHOLD, GPA_LOW_THRESHOLD,
    SUPPORTED_COUNTRIES, GERMAN_LANGUAGE_TESTS, COUNTRY_BUDGET_GUIDE,
)

app = Flask(__name__)

# ============================================
# Flask-RESTX API 配置
# ============================================
api = Api(
    app,
    version="1.0",
    title="智能留学顾问 API",
    description="智能留学顾问系统 - 后端 API 服务<br>"
                "提供课程查询、用户信息保存、咨询记录等功能<br>"
                "新增 /api/agent 自然语言入口，支持 Dify 自然语言增删改查",
    doc="/docs",
    prefix="",
)

# 定义命名空间
ns_courses = Namespace("courses", description="课程相关操作")
ns_users = Namespace("users", description="用户相关操作")
ns_consultations = Namespace("consultations", description="咨询记录操作")
ns_agent = Namespace("agent", description="自然语言智能代理 (NL2SQL)")

api.add_namespace(ns_courses, path="/api/courses")
api.add_namespace(ns_users, path="/api/users")
api.add_namespace(ns_consultations, path="/api/consultations")
api.add_namespace(ns_agent, path="/api/agent")


# ============================================
# API 模型定义（用于 Swagger 文档）
# ============================================
recommend_model = ns_courses.model("RecommendRequest", {
    "education": fields.String(description="学历背景", example="本科"),
    "major": fields.String(description="专业", example="机械工程"),
    "gpa": fields.Float(description="GPA", example=3.2),
    "target_country": fields.String(description="意向国家（德国/新加坡）", example="德国"),
    "target_major": fields.String(description="意向专业", example="车辆工程"),
    "budget": fields.Integer(description="预算(元)", example=200000),
    "language_level": fields.String(description="语言水平描述", example="良好"),
    "language_score": fields.String(description="具体语言成绩", example="TestDaF 4"),
})

user_model = ns_users.model("UserRequest", {
    "name": fields.String(description="姓名", example="张三"),
    "age": fields.Integer(description="年龄", example=22),
    "education": fields.String(description="学历背景", example="本科"),
    "major": fields.String(description="专业", example="机械工程"),
    "gpa": fields.Float(description="GPA", example=3.2),
    "target_country": fields.String(description="意向国家", example="德国"),
    "target_major": fields.String(description="意向专业", example="车辆工程"),
    "budget": fields.Integer(description="预算(元)", example=200000),
    "language_level": fields.String(description="语言水平", example="良好"),
    "language_score": fields.String(description="语言成绩", example="TestDaF 4"),
    "phone": fields.String(description="手机号", example="13800138000"),
    "wechat": fields.String(description="微信号", example="zhangsan"),
    "contact_method": fields.String(description="首选联系方式", example="phone"),
})

contact_model = ns_users.model("ContactRequest", {
    "phone": fields.String(description="手机号", example="13800138000"),
    "wechat": fields.String(description="微信号", example="zhangsan"),
    "contact_method": fields.String(description="首选联系方式", example="phone"),
})

consultation_model = ns_consultations.model("ConsultationRequest", {
    "user_id": fields.Integer(description="用户ID", example=1),
    "course_id": fields.Integer(description="课程ID", example=1),
    "conversation_summary": fields.String(description="对话摘要", example="用户咨询德国留学"),
    "recommended_courses": fields.List(fields.Integer, description="推荐课程ID列表", example=[1, 2, 3]),
    "user_feedback": fields.String(description="用户反馈", example="很满意"),
    "status": fields.String(description="状态", example="new"),
})

agent_nl_model = ns_agent.model("AgentNLRequest", {
    "query": fields.String(description="用户自然语言输入", example="查看所有课程"),
})

agent_sql_model = ns_agent.model("AgentSQLRequest", {
    "sql": fields.String(description="Dify LLM 生成的 SQL 语句", example="SELECT * FROM courses WHERE is_active = 1"),
    "params": fields.Raw(description="SQL 参数列表（可选）"),
})

# ============================================
# 数据库连接工具
# ============================================
def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


def query_db(sql, params=None, fetch_one=False, fetch_all=False):
    """执行查询SQL"""
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(sql, params)
            if fetch_one:
                return cursor.fetchone()
            if fetch_all:
                return cursor.fetchall()
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def query_db_raw(sql, params=None):
    """执行 SQL 并返回结果 + 影响行数，用于 NL2SQL 模式"""
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(sql, params)
            if sql.strip().upper().startswith("SELECT"):
                rows = cursor.fetchall()
                return {"type": "select", "data": rows, "count": len(rows)}
            else:
                conn.commit()
                return {
                    "type": "modify",
                    "affected_rows": cursor.rowcount,
                    "lastrowid": cursor.lastrowid,
                }
    except Exception as e:
        raise e
    finally:
        conn.close()


# ============================================
# JSON 序列化辅助
# ============================================
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        return super().default(obj)


def json_response(data, status=200):
    return app.response_class(
        response=json.dumps(data, ensure_ascii=False, cls=JSONEncoder),
        status=status,
        mimetype="application/json",
    )


# ============================================
# 数据库表结构定义（供 NL2SQL prompt 使用）
# ============================================
DB_SCHEMA = """
-- 表1: courses（课程表）
-- 列: id(INT,自增主键), course_name(VARCHAR,课程名称), category(VARCHAR,类别:留学方案/语言课程/背景提升),
--     sub_category(VARCHAR,子类别), country(VARCHAR,目标国家), target_education(VARCHAR,适用学历),
--     min_gpa(DECIMAL,最低GPA), max_budget(DECIMAL,最高预算), min_budget(DECIMAL,最低预算),
--     language_requirement(VARCHAR,语言要求), duration(VARCHAR,时长), price(DECIMAL,价格),
--     description(TEXT,描述), highlights(TEXT,亮点), is_active(TINYINT,是否上架1=是),
--     created_at(DATETIME,创建时间)

-- 表2: user_profiles（用户信息表）
-- 列: id(INT,自增主键), name(VARCHAR,姓名), age(INT,年龄), education(VARCHAR,学历),
--     major(VARCHAR,专业), gpa(DECIMAL,GPA), target_country(VARCHAR,意向国家),
--     target_major(VARCHAR,意向专业), budget(DECIMAL,预算), language_level(VARCHAR,语言水平),
--     language_score(VARCHAR,语言成绩), phone(VARCHAR,手机号), wechat(VARCHAR,微信号),
--     contact_method(VARCHAR,联系方式), consultation_status(VARCHAR,咨询状态:pending/contacted/following_up/closed),
--     created_at(DATETIME,创建时间), updated_at(DATETIME,更新时间)

-- 表3: consultations（咨询记录表）
-- 列: id(INT,自增主键), user_id(INT,用户ID), course_id(INT,课程ID),
--     conversation_summary(TEXT,对话摘要), recommended_courses(TEXT,推荐课程JSON),
--     user_feedback(VARCHAR,用户反馈), status(VARCHAR,状态:new/recommended/interested/not_interested/consulting),
--     created_at(DATETIME,创建时间)
"""


# ============================================
# 自然语言意图解析（规则模式，零成本快速匹配）
# ============================================
def parse_intent_by_rules(query: str) -> dict:
    """
    用规则+正则解析自然语言意图，不依赖LLM。
    返回 {"action": ..., "entity": ..., "params": {...}} 或 None（匹配失败）。
    """
    q = query.strip()

    # ---- 删除操作 ----
    m = re.search(r"(?:删除|去掉|移除|删掉).*(?:课程|course).*?(?:[Ii][Dd]|编号|号)?\s*[:：]?\s*(\d+)", q)
    if m:
        return {"action": "delete", "entity": "course", "course_id": int(m.group(1))}

    m = re.search(r"(?:删除|去掉|移除|删掉).*(?:用户|user).*?(?:[Ii][Dd]|编号|号)?\s*[:：]?\s*(\d+)", q)
    if m:
        return {"action": "delete", "entity": "user", "user_id": int(m.group(1))}

    m = re.search(r"(?:删除|去掉|移除|删掉).*(?:咨询|记录|consultation).*?(?:[Ii][Dd]|编号|号)?\s*[:：]?\s*(\d+)", q)
    if m:
        return {"action": "delete", "entity": "consultation", "id": int(m.group(1))}

    # ---- 新增操作 ----
    if re.search(r"(?:新增|添加|创建|新建|录入|加入)", q):
        if re.search(r"课程|course", q):
            params = {}
            m = re.search(r"(?:课程)?(?:名[称字]|名称)\s*[:：]?\s*(.+?)(?:[，,。；;]|类别|价格|国家|$)", q)
            if m:
                params["course_name"] = m.group(1).strip()
            m = re.search(r"类别\s*[:：]?\s*(.+?)(?:[，,。；;]|价格|名称|国家|$)", q)
            if m:
                params["category"] = m.group(1).strip()
            m = re.search(r"价格\s*[:：]?\s*(\d+\.?\d*)", q)
            if m:
                params["price"] = float(m.group(1))
            m = re.search(r"国家\s*[:：]?\s*(.+?)(?:[，,。；;]|$)", q)
            if m:
                params["country"] = m.group(1).strip()
            m = re.search(r"描述\s*[:：]?\s*(.+?)(?:[，,。；;]|$)", q)
            if m:
                params["description"] = m.group(1).strip()
            return {"action": "create", "entity": "course", "params": params}

        if re.search(r"用户|user", q):
            params = {}
            m = re.search(r"(?:姓名|名字|名称)\s*[:：]?\s*(.+?)(?:[，,。；;]|学历|专业|$)", q)
            if m:
                params["name"] = m.group(1).strip()
            m = re.search(r"学历\s*[:：]?\s*(.+?)(?:[，,。；;]|$)", q)
            if m:
                params["education"] = m.group(1).strip()
            m = re.search(r"专业\s*[:：]?\s*(.+?)(?:[，,。；;]|$)", q)
            if m:
                params["major"] = m.group(1).strip()
            m = re.search(r"意向.*?(?:国家|留学)\s*[:：]?\s*(.+?)(?:[，,。；;]|$)", q)
            if m:
                params["target_country"] = m.group(1).strip()
            m = re.search(r"(?:手机|电话)\s*[:：]?\s*(\d+)", q)
            if m:
                params["phone"] = m.group(1).strip()
            return {"action": "create", "entity": "user", "params": params}

        if re.search(r"咨询|记录|consultation", q):
            params = {}
            m = re.search(r"(?:用户|user).*?(?:[Ii][Dd]|编号)?\s*[:：]?\s*(\d+)", q)
            if m:
                params["user_id"] = int(m.group(1))
            m = re.search(r"(?:摘要|内容|总结)\s*[:：]?\s*(.+?)(?:[，,。；;]|$)", q)
            if m:
                params["conversation_summary"] = m.group(1).strip()
            return {"action": "create", "entity": "consultation", "params": params}

    # ---- 更新操作 ----
    if re.search(r"(?:修改|更新|改成|改为|改成|调整|设置)", q):
        if re.search(r"课程|course", q):
            params = {}
            m = re.search(r"(?:课程|course).*?(?:[Ii][Dd]|编号|号)?\s*[:：]?\s*(\d+)", q)
            if m:
                params["course_id"] = int(m.group(1))
            m = re.search(r"(?:价格|价钱)\s*(?:改成|改为|更新为|修改为)?\s*[:：]?\s*(\d+\.?\d*)", q)
            if m:
                params["price"] = float(m.group(1))
            m = re.search(r"(?:名称|名字|课程名)\s*(?:改成|改为|更新为|修改为)?\s*[:：]?\s*(.+?)(?:[，,。；;]|价格|$)", q)
            if m:
                params["course_name"] = m.group(1).strip()
            m = re.search(r"(?:上架|下架|激活|停用)", q)
            if m:
                if "下架" in m.group() or "停用" in m.group():
                    params["is_active"] = 0
                elif "上架" in m.group() or "激活" in m.group():
                    params["is_active"] = 1
            if "course_id" in params and len(params) > 1:
                return {"action": "update", "entity": "course", "params": params}

        if re.search(r"用户|user", q):
            params = {}
            m = re.search(r"(?:用户|user).*?(?:[Ii][Dd]|编号|号)?\s*[:：]?\s*(\d+)", q)
            if m:
                params["user_id"] = int(m.group(1))
            m = re.search(r"(?:手机|电话)\s*(?:改成|改为|更新为|修改为)?\s*[:：]?\s*(\d+)", q)
            if m:
                params["phone"] = m.group(1).strip()
            m = re.search(r"微信\s*(?:改成|改为|更新为|修改为)?\s*[:：]?\s*(\S+)", q)
            if m:
                params["wechat"] = m.group(1).strip()
            m = re.search(r"(?:状态|status)\s*(?:改成|改为|更新为|修改为)?\s*[:：]?\s*(\S+)", q)
            if m:
                params["consultation_status"] = m.group(1).strip()
            if "user_id" in params and len(params) > 1:
                return {"action": "update", "entity": "user", "params": params}

        if re.search(r"咨询|记录|consultation", q):
            params = {}
            m = re.search(r"(?:咨询|记录|consultation).*?(?:[Ii][Dd]|编号|号)?\s*[:：]?\s*(\d+)", q)
            if m:
                params["id"] = int(m.group(1))
            m = re.search(r"(?:状态|status)\s*(?:改成|改为|更新为|修改为)?\s*[:：]?\s*(\S+)", q)
            if m:
                params["status"] = m.group(1).strip()
            if "id" in params and len(params) > 1:
                return {"action": "update", "entity": "consultation", "params": params}

    # ---- 查询操作 ----
    # 课程详情
    m = re.search(r"(?:查看|查询|详情|课程|course).*?(?:[Ii][Dd]|编号|号)?\s*[:：]?\s*(\d+)", q)
    if m:
        return {"action": "query", "entity": "course", "course_id": int(m.group(1))}

    # 用户详情
    m = re.search(r"(?:用户|user).*?(?:[Ii][Dd]|编号|号)?\s*[:：]?\s*(\d+)", q)
    if m:
        return {"action": "query", "entity": "user", "user_id": int(m.group(1))}

    # 列表查询
    if re.search(r"(?:所有|全部|有哪些|什么|列出|查看|查询|课程列表|课程|course)", q) and \
       re.search(r"课程|course", q):
        if re.search(r"语言|语言课程", q):
            return {"action": "query", "entity": "course", "filter": "category=语言课程"}
        if re.search(r"背景|背景提升", q):
            return {"action": "query", "entity": "course", "filter": "category=背景提升"}
        if re.search(r"留学|留学方案", q):
            return {"action": "query", "entity": "course", "filter": "category=留学方案"}
        if re.search(r"德国", q):
            return {"action": "query", "entity": "course", "filter": "country=德国"}
        if re.search(r"新加坡", q):
            return {"action": "query", "entity": "course", "filter": "country=新加坡"}
        return {"action": "query", "entity": "course", "filter": "all"}

    if re.search(r"(?:用户|user).*(?:列表|所有|全部|有哪些)", q) or \
       re.search(r"(?:待跟进|pending|所有用户|用户列表|有哪些用户)", q):
        return {"action": "query", "entity": "user", "filter": "all"}

    if re.search(r"(?:咨询|记录|consultation).*(?:列表|所有|全部|有哪些)", q):
        return {"action": "query", "entity": "consultation", "filter": "all"}

    # 模糊查询兜底
    if re.search(r"课程|course", q):
        return {"action": "query", "entity": "course", "filter": "all"}
    if re.search(r"用户|user", q):
        return {"action": "query", "entity": "user", "filter": "all"}
    if re.search(r"咨询|记录|consultation", q):
        return {"action": "query", "entity": "consultation", "filter": "all"}

    return None


def execute_parsed_intent(intent: dict) -> dict:
    """根据解析后的意图执行实际数据库操作"""
    action = intent["action"]
    entity = intent["entity"]

    try:
        # ---- 删除 ----
        if action == "delete":
            if entity == "course":
                query_db("DELETE FROM courses WHERE id = %s", (intent["course_id"],))
                return {"code": 0, "message": f"课程 ID={intent['course_id']} 已删除"}
            elif entity == "user":
                query_db("DELETE FROM user_profiles WHERE id = %s", (intent["user_id"],))
                return {"code": 0, "message": f"用户 ID={intent['user_id']} 已删除"}
            elif entity == "consultation":
                query_db("DELETE FROM consultations WHERE id = %s", (intent["id"],))
                return {"code": 0, "message": f"咨询记录 ID={intent['id']} 已删除"}

        # ---- 新增 ----
        elif action == "create":
            if entity == "course":
                p = intent.get("params", {})
                sql = """
                    INSERT INTO courses (course_name, category, sub_category, country,
                    target_education, price, description, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                """
                cid = query_db(sql, (
                    p.get("course_name", ""),
                    p.get("category", ""),
                    p.get("sub_category", ""),
                    p.get("country", ""),
                    p.get("target_education", "不限"),
                    p.get("price", 0),
                    p.get("description", ""),
                ))
                course = query_db("SELECT * FROM courses WHERE id = %s", (cid,), fetch_one=True)
                return {"code": 0, "message": f"课程「{p.get('course_name', '')}」已创建", "data": course}

            elif entity == "user":
                p = intent.get("params", {})
                sql = """
                    INSERT INTO user_profiles
                    (`name`, `education`, `major`, `target_country`, `phone`, `consultation_status`)
                    VALUES (%s, %s, %s, %s, %s, 'pending')
                """
                uid = query_db(sql, (
                    p.get("name", ""),
                    p.get("education", ""),
                    p.get("major", ""),
                    p.get("target_country", ""),
                    p.get("phone", ""),
                ))
                user = query_db("SELECT * FROM user_profiles WHERE id = %s", (uid,), fetch_one=True)
                return {"code": 0, "message": f"用户「{p.get('name', '')}」已创建", "data": user}

            elif entity == "consultation":
                p = intent.get("params", {})
                sql = """
                    INSERT INTO consultations (user_id, conversation_summary, status)
                    VALUES (%s, %s, 'new')
                """
                cid = query_db(sql, (
                    p.get("user_id"),
                    p.get("conversation_summary", ""),
                ))
                return {"code": 0, "message": "咨询记录已创建", "data": {"id": cid}}

        # ---- 更新 ----
        elif action == "update":
            if entity == "course":
                p = intent.get("params", {})
                cid = p.pop("course_id")
                fields = []
                vals = []
                for k, v in p.items():
                    fields.append(f"`{k}` = %s")
                    vals.append(v)
                vals.append(cid)
                query_db(f"UPDATE courses SET {', '.join(fields)} WHERE id = %s", vals)
                course = query_db("SELECT * FROM courses WHERE id = %s", (cid,), fetch_one=True)
                return {"code": 0, "message": f"课程 ID={cid} 已更新", "data": course}

            elif entity == "user":
                p = intent.get("params", {})
                uid = p.pop("user_id")
                fields = []
                vals = []
                for k, v in p.items():
                    fields.append(f"`{k}` = %s")
                    vals.append(v)
                vals.append(uid)
                query_db(f"UPDATE user_profiles SET {', '.join(fields)} WHERE id = %s", vals)
                user = query_db("SELECT * FROM user_profiles WHERE id = %s", (uid,), fetch_one=True)
                return {"code": 0, "message": f"用户 ID={uid} 已更新", "data": user}

            elif entity == "consultation":
                p = intent.get("params", {})
                rid = p.pop("id")
                fields = []
                vals = []
                for k, v in p.items():
                    fields.append(f"`{k}` = %s")
                    vals.append(v)
                vals.append(rid)
                query_db(f"UPDATE consultations SET {', '.join(fields)} WHERE id = %s", vals)
                return {"code": 0, "message": f"咨询记录 ID={rid} 已更新"}

        # ---- 查询 ----
        elif action == "query":
            # 课程详情
            if entity == "course" and "course_id" in intent:
                course = query_db("SELECT * FROM courses WHERE id = %s", (intent["course_id"],), fetch_one=True)
                if not course:
                    return {"code": 404, "message": "课程不存在"}
                return {"code": 0, "data": course}

            # 课程列表
            if entity == "course":
                filt = intent.get("filter", "all")
                if filt == "all":
                    sql = "SELECT * FROM courses WHERE is_active = 1 ORDER BY category, id"
                    courses = query_db(sql, fetch_all=True)
                elif filt.startswith("category="):
                    cat = filt.split("=", 1)[1]
                    sql = "SELECT * FROM courses WHERE is_active = 1 AND category = %s ORDER BY id"
                    courses = query_db(sql, (cat,), fetch_all=True)
                elif filt.startswith("country="):
                    cty = filt.split("=", 1)[1]
                    sql = "SELECT * FROM courses WHERE is_active = 1 AND (country LIKE %s OR country LIKE %s) ORDER BY category, id"
                    courses = query_db(sql, (f"%{cty}%", f"%{cty}%"), fetch_all=True)
                else:
                    courses = query_db("SELECT * FROM courses WHERE is_active = 1 ORDER BY category, id", fetch_all=True)
                return {"code": 0, "data": courses, "total": len(courses)}

            # 用户详情
            if entity == "user" and "user_id" in intent:
                user = query_db("SELECT * FROM user_profiles WHERE id = %s", (intent["user_id"],), fetch_one=True)
                if not user:
                    return {"code": 404, "message": "用户不存在"}
                return {"code": 0, "data": user}

            # 用户列表
            if entity == "user":
                users = query_db("SELECT * FROM user_profiles ORDER BY updated_at DESC LIMIT 50", fetch_all=True)
                return {"code": 0, "data": users, "total": len(users)}

            # 咨询记录列表
            if entity == "consultation":
                sql = "SELECT c.*, u.name as user_name FROM consultations c LEFT JOIN user_profiles u ON c.user_id = u.id ORDER BY c.created_at DESC LIMIT 50"
                records = query_db(sql, fetch_all=True)
                return {"code": 0, "data": records, "total": len(records)}

    except Exception as e:
        return {"code": 500, "message": f"操作失败: {str(e)}"}

    return {"code": 400, "message": "无法识别该操作"}


# ============================================
# 自然语言 → 格式化自然语言回复
# ============================================
def format_nl_result(result: dict, original_query: str) -> str:
    """将结构化结果格式化为自然语言回复，便于 Dify 展示"""
    if result["code"] == 404:
        return result.get("message", "未找到相关记录")
    if result["code"] == 500:
        return result.get("message", "操作出错，请重试")
    if result["code"] != 0:
        return result.get("message", "操作失败")

    data = result.get("data")
    msg = result.get("message", "")
    total = result.get("total", 0)

    # 查询操作 - 列表
    if isinstance(data, list):
        if total == 0:
            return "未找到相关记录。"
        lines = [f"共找到 {total} 条记录："]
        for i, item in enumerate(data[:10], 1):
            if "course_name" in item:
                lines.append(f"{i}. [{item.get('category', '')}] {item['course_name']} - "
                           f"价格: {item.get('price', 0)}元 - "
                           f"ID: {item.get('id', '')}")
            elif "user_name" in item or "conversation_summary" in item:
                lines.append(f"{i}. [咨询] 用户: {item.get('user_name', '')} - "
                           f"状态: {item.get('status', '')} - "
                           f"摘要: {str(item.get('conversation_summary', ''))[:50]}")
            elif "name" in item:
                lines.append(f"{i}. {item.get('name', '')} - "
                           f"{item.get('education', '')} {item.get('major', '')} - "
                           f"意向: {item.get('target_country', '')} - "
                           f"ID: {item.get('id', '')}")
        if total > 10:
            lines.append(f"... 还有 {total - 10} 条记录未显示")
        return "\n".join(lines)

    # 查询操作 - 单条
    if isinstance(data, dict):
        if "course_name" in data:
            return (f"课程详情：\n"
                    f"  ID: {data['id']}\n"
                    f"  名称: {data['course_name']}\n"
                    f"  类别: {data.get('category', '')}\n"
                    f"  国家: {data.get('country', '')}\n"
                    f"  价格: {data.get('price', 0)}元\n"
                    f"  描述: {data.get('description', '')}")
        if "name" in data:
            return (f"用户详情：\n"
                    f"  ID: {data['id']}\n"
                    f"  姓名: {data.get('name', '')}\n"
                    f"  学历: {data.get('education', '')}\n"
                    f"  专业: {data.get('major', '')}\n"
                    f"  GPA: {data.get('gpa', '')}\n"
                    f"  意向国家: {data.get('target_country', '')}\n"
                    f"  意向专业: {data.get('target_major', '')}\n"
                    f"  预算: {data.get('budget', 0)}元\n"
                    f"  手机: {data.get('phone', '')}\n"
                    f"  微信: {data.get('wechat', '')}\n"
                    f"  状态: {data.get('consultation_status', '')}")

    # 修改/删除操作
    if msg:
        return msg

    return "操作完成"


# ============================================
# 健康检查
# ============================================
@app.route("/api/health", methods=["GET"])
def health_check():
    return json_response({"status": "ok", "service": "留学顾问API", "port": API_PORT})


# ============================================
# 课程相关接口（CRUD 完整）
# ============================================
@ns_courses.route("")
class CourseList(Resource):
    @ns_courses.doc("get_all_courses")
    def get(self):
        """获取所有课程"""
        sql = "SELECT * FROM courses WHERE is_active = 1 ORDER BY category, id"
        courses = query_db(sql, fetch_all=True)
        return json_response({"code": 0, "data": courses, "total": len(courses)})

    @ns_courses.doc("create_course")
    def post(self):
        """新增课程"""
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)
        sql = """
            INSERT INTO courses (course_name, category, sub_category, country,
            target_education, min_gpa, min_budget, max_budget, language_requirement,
            duration, price, description, highlights, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
        """
        cid = query_db(sql, (
            data.get("course_name", ""),
            data.get("category", ""),
            data.get("sub_category", ""),
            data.get("country", ""),
            data.get("target_education", ""),
            data.get("min_gpa", 0),
            data.get("min_budget"),
            data.get("max_budget"),
            data.get("language_requirement", ""),
            data.get("duration", ""),
            data.get("price", 0),
            data.get("description", ""),
            data.get("highlights", ""),
        ))
        course = query_db("SELECT * FROM courses WHERE id = %s", (cid,), fetch_one=True)
        return json_response({"code": 0, "data": course, "message": "课程已创建"}, 201)


@ns_courses.route("/<int:course_id>")
@ns_courses.param("course_id", "课程ID")
class CourseDetail(Resource):
    @ns_courses.doc("get_course_detail")
    def get(self, course_id):
        """获取课程详情"""
        course = query_db("SELECT * FROM courses WHERE id = %s", (course_id,), fetch_one=True)
        if not course:
            return json_response({"code": 404, "message": "课程不存在"}, 404)
        return json_response({"code": 0, "data": course})

    @ns_courses.doc("update_course")
    def put(self, course_id):
        """更新课程信息"""
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)
        allowed = ["course_name", "category", "sub_category", "country", "target_education",
                    "min_gpa", "min_budget", "max_budget", "language_requirement",
                    "duration", "price", "description", "highlights", "is_active"]
        fields = []
        params = []
        for k in allowed:
            if k in data:
                fields.append(f"`{k}` = %s")
                params.append(data[k])
        if not fields:
            return json_response({"code": 400, "message": "没有要更新的字段"}, 400)
        params.append(course_id)
        query_db(f"UPDATE courses SET {', '.join(fields)} WHERE id = %s", params)
        course = query_db("SELECT * FROM courses WHERE id = %s", (course_id,), fetch_one=True)
        return json_response({"code": 0, "data": course, "message": "课程已更新"})

    @ns_courses.doc("delete_course")
    def delete(self, course_id):
        """删除课程（软删除：设为不活跃）"""
        query_db("UPDATE courses SET is_active = 0 WHERE id = %s", (course_id,))
        return json_response({"code": 0, "message": f"课程 ID={course_id} 已下架"})


@ns_courses.route("/recommend")
class CourseRecommend(Resource):
    @ns_courses.doc("recommend_courses")
    @ns_courses.expect(recommend_model, validate=False)
    def post(self):
        """根据用户画像智能推荐课程（仅德国和新加坡）"""
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)
        if not data:
            return json_response({"code": 400, "message": "请求参数不能为空"}, 400)

        education = data.get("education", "")
        target_country = data.get("target_country", "")
        gpa = float(data.get("gpa", 0))
        budget = float(data.get("budget", 0))
        language_score = data.get("language_score", "")
        language_level = data.get("language_level", "")

        if target_country and target_country not in SUPPORTED_COUNTRIES:
            return json_response({
                "code": 400,
                "message": f"目前仅支持德国和新加坡的留学方案，您输入的'{target_country}'暂不支持。",
            }, 400)

        recommendations = []
        analysis = []

        # 1. 语言能力评估
        need_language_course = False
        lang_reason = ""

        if target_country in LANGUAGE_THRESHOLD:
            threshold = LANGUAGE_THRESHOLD[target_country]
            if target_country == "德国":
                has_german = any(t in language_score for t in GERMAN_LANGUAGE_TESTS)
                if has_german:
                    match = re.search(r"TestDaF\s*(\d+)", language_score, re.IGNORECASE)
                    if match:
                        score = int(match.group(1))
                        if score < threshold.get("TestDaF", 4):
                            need_language_course = True
                            lang_reason = f"您的TestDaF成绩为{score}分，德国大学一般要求TestDaF 4级以上"
                    match = re.search(r"[Bb](\d)", language_score)
                    if match:
                        level = int(match.group(1))
                        if level < 2:
                            need_language_course = True
                            lang_reason = f"您的德语水平为B{level}，德国大学一般要求B2以上"
                else:
                    if "IELTS" in language_score.upper() or "TOEFL" in language_score.upper():
                        match_ielts = re.search(r"IELTS\s*(\d+\.?\d*)", language_score, re.IGNORECASE)
                        match_toefl = re.search(r"TOEFL\s*(\d+)", language_score, re.IGNORECASE)
                        if match_ielts and float(match_ielts.group(1)) < threshold.get("IELTS", 6.0):
                            need_language_course = True
                            lang_reason = f"您的IELTS成绩{match_ielts.group(1)}分，德国英语授课项目建议{threshold.get('IELTS', 6.0)}分以上"
                        elif match_toefl and int(match_toefl.group(1)) < threshold.get("TOEFL", 80):
                            need_language_course = True
                            lang_reason = f"您的TOEFL成绩{int(match_toefl.group(1))}分，德国英语授课项目建议{threshold.get('TOEFL', 80)}分以上"
                    else:
                        need_language_course = True
                        lang_reason = "德国留学需要德语B2/TestDaF 4或英语IELTS 6.0+/TOEFL 80+，建议先提升语言能力"
            elif target_country == "新加坡":
                if "IELTS" in language_score.upper():
                    match = re.search(r"IELTS\s*(\d+\.?\d*)", language_score, re.IGNORECASE)
                    if match and float(match.group(1)) < threshold.get("IELTS", 6.0):
                        need_language_course = True
                        lang_reason = f"您的IELTS成绩{match.group(1)}分，新加坡名校一般要求{threshold.get('IELTS', 6.0)}分以上"
                elif "TOEFL" in language_score.upper():
                    match = re.search(r"TOEFL\s*(\d+)", language_score, re.IGNORECASE)
                    if match and int(match.group(1)) < threshold.get("TOEFL", 85):
                        need_language_course = True
                        lang_reason = f"您的TOEFL成绩{int(match.group(1))}分，新加坡名校一般要求{threshold.get('TOEFL', 85)}分以上"
                elif not language_score or language_score.strip() == "":
                    need_language_course = True
                    lang_reason = "新加坡留学需要IELTS 6.0+/TOEFL 85+，建议先参加语言培训"

        if not language_score or language_score.strip() == "":
            need_language_course = True
            if not lang_reason:
                lang_reason = "您尚未提供语言成绩，建议先参加语言培训"

        if language_level in ["一般", "较差", "初级", "入门"]:
            need_language_course = True
            if not lang_reason:
                lang_reason = f"您的语言水平为{language_level}，建议先提升语言能力"

        if need_language_course:
            analysis.append({"type": "language", "need": True, "reason": lang_reason})
            lang_courses = query_db(
                """SELECT * FROM courses WHERE category = '语言课程' AND is_active = 1
                   AND (country LIKE %s OR country LIKE %s OR country = '不限')
                   AND (target_education LIKE %s OR target_education LIKE %s)
                   AND (min_budget IS NULL OR min_budget <= %s) ORDER BY price ASC""",
                (f"%{target_country}%", "%德国/新加坡%", f"%{education}%", "%不限%", budget),
                fetch_all=True,
            )
            for c in lang_courses:
                c["match_reason"] = "语言成绩需要提升"
            recommendations.extend(lang_courses)
        else:
            analysis.append({"type": "language", "need": False, "reason": "语言成绩达标"})

        # 2. GPA 评估
        if gpa > 0 and gpa < GPA_LOW_THRESHOLD:
            analysis.append({
                "type": "background", "need": True,
                "reason": f"您的GPA为{gpa}，偏低，建议通过背景提升项目增强竞争力",
            })
            bg_courses = query_db(
                """SELECT * FROM courses WHERE category = '背景提升' AND is_active = 1
                   AND (country LIKE %s OR country LIKE %s OR country = '不限')
                   AND (target_education LIKE %s OR target_education LIKE %s)
                   AND (min_budget IS NULL OR min_budget <= %s) ORDER BY price ASC LIMIT 5""",
                (f"%{target_country}%", "%德国/新加坡%", f"%{education}%", "%不限%", budget),
                fetch_all=True,
            )
            for c in bg_courses:
                c["match_reason"] = "GPA偏低，建议通过此项目提升背景"
            recommendations.extend(bg_courses)
        else:
            analysis.append({
                "type": "background", "need": False,
                "reason": "GPA满足基本要求" if gpa > 0 else "未提供GPA信息",
            })

        # 3. 留学方案推荐
        plan_courses = query_db(
            """SELECT * FROM courses WHERE category = '留学方案' AND is_active = 1
               AND (country LIKE %s OR country LIKE %s OR sub_category = %s OR country = '不限')
               AND (target_education LIKE %s OR target_education LIKE %s)
               AND (min_gpa IS NULL OR min_gpa <= %s)
               AND (min_budget IS NULL OR min_budget <= %s)
               ORDER BY CASE WHEN country = %s THEN 1 WHEN country LIKE %s THEN 2 ELSE 3 END, price ASC""",
            (f"%{target_country}%", "%德国/新加坡%", target_country, f"%{education}%",
             "%不限%", gpa if gpa > 0 else 0, budget, target_country, f"%{target_country}%"),
            fetch_all=True,
        )
        for c in plan_courses:
            c["match_reason"] = "匹配您的留学意向"
        recommendations.extend(plan_courses)

        # 预算评估
        if target_country in COUNTRY_BUDGET_GUIDE:
            guide = COUNTRY_BUDGET_GUIDE[target_country]
            if budget > 0:
                if budget < guide["low"]:
                    analysis.append({
                        "type": "budget", "level": "low",
                        "reason": f"您的预算{budget:.0f}元/年偏低，{target_country}留学建议至少{guide['low']}元/年。{guide['note']}",
                    })
                elif budget < guide["mid"]:
                    analysis.append({
                        "type": "budget", "level": "moderate",
                        "reason": f"您的预算{budget:.0f}元/年适中，可以覆盖{target_country}基本留学费用。{guide['note']}",
                    })
                else:
                    analysis.append({
                        "type": "budget", "level": "sufficient",
                        "reason": f"您的预算{budget:.0f}元/年充足，可以享受{target_country}优质留学体验。{guide['note']}",
                    })
            else:
                analysis.append({
                    "type": "budget", "level": "unknown",
                    "reason": f"{target_country}留学参考：{guide['note']}",
                })

        analysis.append({
            "type": "plan", "need": True,
            "reason": f"为您推荐{target_country}留学方案" if target_country else "为您推荐德国和新加坡留学方案",
        })

        # 4. 去重整理
        seen_ids = set()
        unique_recommendations = []
        for c in recommendations:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                unique_recommendations.append(c)

        grouped = {"语言课程": [], "背景提升": [], "留学方案": []}
        for c in unique_recommendations:
            cat = c["category"]
            if cat in grouped:
                grouped[cat].append(c)

        return json_response({
            "code": 0,
            "data": {
                "user_profile": data,
                "analysis": analysis,
                "recommendations": grouped,
                "total_count": len(unique_recommendations),
                "summary": generate_summary(analysis, grouped),
            },
        })


def generate_summary(analysis, grouped):
    parts = []
    lang_need = any(a["type"] == "language" and a["need"] for a in analysis)
    bg_need = any(a["type"] == "background" and a["need"] for a in analysis)
    if lang_need:
        parts.append(f"为您推荐了{len(grouped.get('语言课程', []))}门语言提升课程")
    if bg_need:
        parts.append(f"为您推荐了{len(grouped.get('背景提升', []))}个背景提升项目")
    parts.append(f"为您匹配了{len(grouped.get('留学方案', []))}个留学方案")
    return "，".join(parts) + "，请查看详情。"


# ============================================
# 用户相关接口（CRUD 完整）
# ============================================
@ns_users.route("")
class UserCreate(Resource):
    @ns_users.doc("create_user")
    @ns_users.expect(user_model, validate=False)
    def post(self):
        """创建/更新用户信息"""
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)

        name = data.get("name", "")
        phone = data.get("phone", "")
        wechat = data.get("wechat", "")

        existing = None
        if phone:
            existing = query_db("SELECT id FROM user_profiles WHERE phone = %s", (phone,), fetch_one=True)
        if not existing and wechat:
            existing = query_db("SELECT id FROM user_profiles WHERE wechat = %s", (wechat,), fetch_one=True)

        if existing:
            fields = []
            params = []
            for key in ["name", "age", "education", "major", "gpa", "target_country",
                         "target_major", "budget", "language_level", "language_score",
                         "phone", "wechat", "contact_method"]:
                if key in data:
                    fields.append(f"`{key}` = %s")
                    params.append(data[key])
            if fields:
                params.append(existing["id"])
                sql = f"UPDATE user_profiles SET {', '.join(fields)} WHERE id = %s"
                query_db(sql, params)
            user = query_db("SELECT * FROM user_profiles WHERE id = %s", (existing["id"],), fetch_one=True)
            return json_response({"code": 0, "data": user, "message": "用户信息已更新"})

        sql = """
            INSERT INTO user_profiles
            (`name`, `age`, `education`, `major`, `gpa`, `target_country`,
             `target_major`, `budget`, `language_level`, `language_score`,
             `phone`, `wechat`, `contact_method`, `consultation_status`)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """
        params = (
            data.get("name", ""), data.get("age"), data.get("education", ""),
            data.get("major", ""), data.get("gpa"), data.get("target_country", ""),
            data.get("target_major", ""), data.get("budget"), data.get("language_level", ""),
            data.get("language_score", ""), data.get("phone", ""), data.get("wechat", ""),
            data.get("contact_method", ""),
        )
        user_id = query_db(sql, params)
        user = query_db("SELECT * FROM user_profiles WHERE id = %s", (user_id,), fetch_one=True)
        return json_response({"code": 0, "data": user, "message": "用户信息创建成功"}, 201)


@ns_users.route("/<int:user_id>")
@ns_users.param("user_id", "用户ID")
class UserDetail(Resource):
    @ns_users.doc("get_user")
    def get(self, user_id):
        """获取用户信息"""
        user = query_db("SELECT * FROM user_profiles WHERE id = %s", (user_id,), fetch_one=True)
        if not user:
            return json_response({"code": 404, "message": "用户不存在"}, 404)
        return json_response({"code": 0, "data": user})

    @ns_users.doc("update_user")
    def put(self, user_id):
        """更新用户信息"""
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)
        allowed = ["name", "age", "education", "major", "gpa", "target_country",
                    "target_major", "budget", "language_level", "language_score",
                    "phone", "wechat", "contact_method", "consultation_status"]
        fields = []
        params = []
        for k in allowed:
            if k in data:
                fields.append(f"`{k}` = %s")
                params.append(data[k])
        if not fields:
            return json_response({"code": 400, "message": "没有要更新的字段"}, 400)
        params.append(user_id)
        query_db(f"UPDATE user_profiles SET {', '.join(fields)} WHERE id = %s", params)
        user = query_db("SELECT * FROM user_profiles WHERE id = %s", (user_id,), fetch_one=True)
        return json_response({"code": 0, "data": user, "message": "用户信息已更新"})

    @ns_users.doc("delete_user")
    def delete(self, user_id):
        """删除用户"""
        query_db("DELETE FROM user_profiles WHERE id = %s", (user_id,))
        return json_response({"code": 0, "message": f"用户 ID={user_id} 已删除"})


@ns_users.route("/<int:user_id>/contact")
@ns_users.param("user_id", "用户ID")
class UserContact(Resource):
    @ns_users.doc("save_contact")
    @ns_users.expect(contact_model, validate=False)
    def post(self, user_id):
        """保存用户联系方式（电话/微信）"""
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)

        phone = data.get("phone", "")
        wechat = data.get("wechat", "")
        contact_method = data.get("contact_method", "")
        if not phone and not wechat:
            return json_response({"code": 400, "message": "请至少提供手机号或微信号"}, 400)

        update_fields = []
        params = []
        if phone:
            update_fields.append("`phone` = %s"); params.append(phone)
        if wechat:
            update_fields.append("`wechat` = %s"); params.append(wechat)
        if contact_method:
            update_fields.append("`contact_method` = %s"); params.append(contact_method)
        update_fields.append("`consultation_status` = 'contacted'")
        params.append(user_id)
        query_db(f"UPDATE user_profiles SET {', '.join(update_fields)} WHERE id = %s", params)
        return json_response({
            "code": 0,
            "message": "联系方式已保存，我们的顾问将在1个工作日内与您联系！",
        })


@ns_users.route("/pending")
class UserPending(Resource):
    @ns_users.doc("get_pending_users")
    def get(self):
        """获取待跟进用户列表"""
        sql = "SELECT * FROM user_profiles WHERE phone != '' OR wechat != '' ORDER BY updated_at DESC"
        users = query_db(sql, fetch_all=True)
        return json_response({"code": 0, "data": users, "total": len(users)})


# ============================================
# 咨询记录相关接口（CRUD 完整）
# ============================================
@ns_consultations.route("")
class ConsultationList(Resource):
    @ns_consultations.doc("create_consultation")
    @ns_consultations.expect(consultation_model, validate=False)
    def post(self):
        """创建咨询记录"""
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)
        sql = """
            INSERT INTO consultations
            (user_id, course_id, conversation_summary, recommended_courses, user_feedback, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cid = query_db(sql, (
            data.get("user_id"), data.get("course_id"),
            data.get("conversation_summary", ""),
            json.dumps(data.get("recommended_courses", []), ensure_ascii=False),
            data.get("user_feedback", ""), data.get("status", "new"),
        ))
        return json_response({"code": 0, "data": {"id": cid}, "message": "咨询记录已创建"}, 201)

    @ns_consultations.doc("list_consultations", params={
        "status": "按状态筛选", "user_id": "按用户ID筛选"
    })
    def get(self):
        """获取咨询记录列表"""
        status = request.args.get("status", "")
        user_id = request.args.get("user_id", "")
        sql = "SELECT c.*, u.name as user_name FROM consultations c LEFT JOIN user_profiles u ON c.user_id = u.id WHERE 1=1"
        params = []
        if status:
            sql += " AND c.status = %s"; params.append(status)
        if user_id:
            sql += " AND c.user_id = %s"; params.append(int(user_id))
        sql += " ORDER BY c.created_at DESC LIMIT 50"
        records = query_db(sql, params, fetch_all=True)
        return json_response({"code": 0, "data": records, "total": len(records)})


@ns_consultations.route("/<int:record_id>")
@ns_consultations.param("record_id", "咨询记录ID")
class ConsultationDetail(Resource):
    @ns_consultations.doc("get_consultation")
    def get(self, record_id):
        """获取咨询记录详情"""
        sql = "SELECT c.*, u.name as user_name FROM consultations c LEFT JOIN user_profiles u ON c.user_id = u.id WHERE c.id = %s"
        record = query_db(sql, (record_id,), fetch_one=True)
        if not record:
            return json_response({"code": 404, "message": "咨询记录不存在"}, 404)
        return json_response({"code": 0, "data": record})

    @ns_consultations.doc("update_consultation")
    def put(self, record_id):
        """更新咨询记录"""
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)
        allowed = ["user_id", "course_id", "conversation_summary", "user_feedback", "status"]
        fields = []
        params = []
        for k in allowed:
            if k in data:
                fields.append(f"`{k}` = %s")
                params.append(data[k])
        if not fields:
            return json_response({"code": 400, "message": "没有要更新的字段"}, 400)
        params.append(record_id)
        query_db(f"UPDATE consultations SET {', '.join(fields)} WHERE id = %s", params)
        return json_response({"code": 0, "message": f"咨询记录 ID={record_id} 已更新"})

    @ns_consultations.doc("delete_consultation")
    def delete(self, record_id):
        """删除咨询记录"""
        query_db("DELETE FROM consultations WHERE id = %s", (record_id,))
        return json_response({"code": 0, "message": f"咨询记录 ID={record_id} 已删除"})


# ============================================
# ========== 自然语言智能代理接口 =============
# ============================================

@ns_agent.route("/nl")
class AgentNL(Resource):
    """模式1：规则匹配（零成本，适合简单意图）"""
    @ns_agent.doc("agent_nl_rule")
    @ns_agent.expect(agent_nl_model, validate=False)
    def post(self):
        """接收自然语言，用规则解析意图并执行 CRUD 操作"""
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)

        query = data.get("query", "").strip()
        if not query:
            return json_response({"code": 400, "message": "query 不能为空"}, 400)

        intent = parse_intent_by_rules(query)
        if not intent:
            return json_response({
                "code": 400,
                "message": "无法理解您的意图，请尝试更明确的表达。例如：查看所有课程、新增用户张三、删除课程3、修改课程5价格为10000",
                "parsed": None,
            }, 400)

        result = execute_parsed_intent(intent)
        result["parsed_intent"] = intent
        result["nl_reply"] = format_nl_result(result, query)
        return json_response(result)


@ns_agent.route("/sql")
class AgentSQL(Resource):
    """模式2：NL2SQL 模式（Dify LLM 生成 SQL，后端安全执行）"""
    @ns_agent.doc("agent_nl2sql")
    @ns_agent.expect(agent_sql_model, validate=False)
    def post(self):
        """
        接收 Dify LLM 生成的 SQL 语句，安全执行并返回结果。

        Dify 侧的 LLM prompt 应包含 DB_SCHEMA 定义，让 LLM 根据用户自然语言生成 SQL。
        本接口会做基本安全检查（禁止 DROP/ALTER/TRUNCATE 等危险操作）。
        """
        try:
            data = request.get_json(force=True)
        except Exception:
            return json_response({"code": 400, "message": "请求参数格式错误"}, 400)

        sql = (data.get("sql", "") or "").strip()
        params = data.get("params") or None

        if not sql:
            return json_response({"code": 400, "message": "sql 不能为空"}, 400)

        # ---- 安全检查：禁止危险操作 ----
        sql_upper = sql.upper()
        dangerous = ["DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"]
        for keyword in dangerous:
            if re.search(rf"\b{keyword}\b", sql_upper):
                return json_response({
                    "code": 403,
                    "message": f"禁止执行 {keyword} 操作，仅支持 SELECT/INSERT/UPDATE/DELETE",
                }, 403)

        try:
            result = query_db_raw(sql, params)
        except Exception as e:
            return json_response({"code": 500, "message": f"SQL 执行失败: {str(e)}"}, 500)

        # 格式化返回
        if result["type"] == "select":
            return json_response({
                "code": 0,
                "data": result["data"],
                "total": result["count"],
                "nl_reply": format_sql_result(result),
            })
        else:
            return json_response({
                "code": 0,
                "data": result,
                "message": f"操作完成，影响 {result['affected_rows']} 行",
                "nl_reply": f"操作完成，影响 {result['affected_rows']} 行。",
            })


@ns_agent.route("/schema")
class AgentSchema(Resource):
    """返回数据库表结构，供 Dify 构造 NL2SQL prompt"""
    @ns_agent.doc("get_schema")
    def get(self):
        """获取数据库表结构定义（供 Dify LLM 生成 SQL 使用）"""
        return json_response({
            "code": 0,
            "data": {
                "schema": DB_SCHEMA.strip(),
                "tables": [
                    {
                        "name": "courses",
                        "columns": [
                            {"name": "id", "type": "INT", "desc": "自增主键"},
                            {"name": "course_name", "type": "VARCHAR", "desc": "课程名称"},
                            {"name": "category", "type": "VARCHAR", "desc": "类别：留学方案/语言课程/背景提升"},
                            {"name": "sub_category", "type": "VARCHAR", "desc": "子类别"},
                            {"name": "country", "type": "VARCHAR", "desc": "目标国家"},
                            {"name": "target_education", "type": "VARCHAR", "desc": "适用学历"},
                            {"name": "min_gpa", "type": "DECIMAL", "desc": "最低GPA要求"},
                            {"name": "max_budget", "type": "DECIMAL", "desc": "最高预算"},
                            {"name": "min_budget", "type": "DECIMAL", "desc": "最低预算"},
                            {"name": "language_requirement", "type": "VARCHAR", "desc": "语言要求"},
                            {"name": "duration", "type": "VARCHAR", "desc": "课程时长"},
                            {"name": "price", "type": "DECIMAL", "desc": "课程价格(元)"},
                            {"name": "description", "type": "TEXT", "desc": "课程描述"},
                            {"name": "highlights", "type": "TEXT", "desc": "课程亮点"},
                            {"name": "is_active", "type": "TINYINT", "desc": "是否上架 1=是 0=否"},
                            {"name": "created_at", "type": "DATETIME", "desc": "创建时间"},
                        ],
                    },
                    {
                        "name": "user_profiles",
                        "columns": [
                            {"name": "id", "type": "INT", "desc": "自增主键"},
                            {"name": "name", "type": "VARCHAR", "desc": "用户姓名"},
                            {"name": "age", "type": "INT", "desc": "年龄"},
                            {"name": "education", "type": "VARCHAR", "desc": "学历：高中/本科/硕士/博士"},
                            {"name": "major", "type": "VARCHAR", "desc": "专业"},
                            {"name": "gpa", "type": "DECIMAL", "desc": "GPA成绩"},
                            {"name": "target_country", "type": "VARCHAR", "desc": "意向留学国家"},
                            {"name": "target_major", "type": "VARCHAR", "desc": "意向专业"},
                            {"name": "budget", "type": "DECIMAL", "desc": "预算(元)"},
                            {"name": "language_level", "type": "VARCHAR", "desc": "语言水平"},
                            {"name": "language_score", "type": "VARCHAR", "desc": "语言成绩"},
                            {"name": "phone", "type": "VARCHAR", "desc": "手机号"},
                            {"name": "wechat", "type": "VARCHAR", "desc": "微信号"},
                            {"name": "contact_method", "type": "VARCHAR", "desc": "联系方式 phone/wechat"},
                            {"name": "consultation_status", "type": "VARCHAR", "desc": "状态: pending/contacted/following_up/closed"},
                            {"name": "created_at", "type": "DATETIME", "desc": "创建时间"},
                            {"name": "updated_at", "type": "DATETIME", "desc": "更新时间"},
                        ],
                    },
                    {
                        "name": "consultations",
                        "columns": [
                            {"name": "id", "type": "INT", "desc": "自增主键"},
                            {"name": "user_id", "type": "INT", "desc": "用户ID"},
                            {"name": "course_id", "type": "INT", "desc": "课程ID"},
                            {"name": "conversation_summary", "type": "TEXT", "desc": "对话摘要"},
                            {"name": "recommended_courses", "type": "TEXT", "desc": "推荐课程ID列表(JSON)"},
                            {"name": "user_feedback", "type": "VARCHAR", "desc": "用户反馈"},
                            {"name": "status", "type": "VARCHAR", "desc": "状态: new/recommended/interested/not_interested/consulting"},
                            {"name": "created_at", "type": "DATETIME", "desc": "创建时间"},
                        ],
                    },
                ],
            },
        })


def format_sql_result(result: dict) -> str:
    """将 SQL 查询结果格式化为自然语言"""
    if result["type"] == "select":
        count = result["count"]
        if count == 0:
            return "未找到相关记录。"
        rows = result["data"]
        lines = [f"共找到 {count} 条记录："]
        for i, row in enumerate(rows[:10], 1):
            lines.append(f"{i}. {json.dumps(row, ensure_ascii=False, cls=JSONEncoder)}")
        if count > 10:
            lines.append(f"... 还有 {count - 10} 条记录未显示")
        return "\n".join(lines)
    return f"操作完成，影响 {result['affected_rows']} 行。"


# ============================================
# 启动服务
# ============================================
if __name__ == "__main__":
    import sys
    import io
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("=" * 50)
    print("  智能留学顾问 API 服务")
    print("=" * 50)
    print(f"  API 地址:      http://{API_HOST}:{API_PORT}")
    print(f"  Swagger文档:    http://localhost:{API_PORT}/docs")
    print(f"  健康检查:      http://localhost:{API_PORT}/api/health")
    print(f"  NL Agent(规则): POST /api/agent/nl")
    print(f"  NL2SQL Agent:   POST /api/agent/sql")
    print(f"  Schema 定义:    GET  /api/agent/schema")
    print("=" * 50)
    app.run(host=API_HOST, port=API_PORT, debug=True)
