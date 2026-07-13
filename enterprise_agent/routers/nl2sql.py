"""
NL2SQL 自然语言转SQL查询路由
POST /api/agent/query/nl2sql - 自然语言转SQL并执行
"""
from fastapi import APIRouter, Depends, HTTPException
import logging
import re

from enterprise_agent.database import get_db, execute_raw_sql, validate_select_sql
from enterprise_agent.schemas import ApiResponse, NL2SQLRequest
from enterprise_agent.utils import require_operator
from sqlalchemy.orm import Session

logger = logging.getLogger("enterprise_agent.nl2sql")
router = APIRouter()


# ==================== 简易 NL2SQL 规则引擎 ====================
# 定义表结构信息（用于生成SQL）
TABLE_META = {
    "intention_customer": {
        "comment": "意向客户表",
        "fields": ["customer_id", "customer_name", "customer_age", "customer_gender",
                    "customer_phone", "customer_source", "customer_demand",
                    "current_status", "sales_user_id", "create_time"],
    },
    "employee_daily_report": {
        "comment": "员工日报表",
        "fields": ["id", "user_id", "dept_id", "report_content", "report_date", "submit_time"],
    },
    "leave_application": {
        "comment": "请假申请表",
        "fields": ["id", "student_name", "leave_type", "start_date", "end_date",
                    "reason", "status", "applicant_type", "applicant_id", "create_time"],
    },
    "student_score": {
        "comment": "学生成绩表",
        "fields": ["id", "student_id", "subject", "score", "exam_type", "exam_date"],
    },
    "student_complaint": {
        "comment": "投诉反馈表",
        "fields": ["id", "student_id", "complaint_detail", "complaint_type",
                    "handle_status", "handler_user_id", "create_time"],
    },
    "student_info": {
        "comment": "学生信息表（已签约学员）",
        "fields": ["id", "name", "phone", "email", "education", "school", "major",
                    "project_name", "status", "language_exam", "language_score",
                    "consultant_id", "enroll_date", "student_no"],
    },
    "employee": {
        "comment": "员工表",
        "fields": ["emp_id", "emp_name", "dept_id", "position", "phone", "email"],
    },
    "department": {
        "comment": "部门表",
        "fields": ["dept_id", "dept_name", "dept_desc", "manager_id", "parent_dept_id"],
    },
    "account": {
        "comment": "账户表",
        "fields": ["user_id", "username", "real_name", "user_type", "dept_id", "phone", "email", "status"],
    },
    "application_record": {
        "comment": "留学申请记录表",
        "fields": ["id", "student_id", "university", "program_name", "application_status",
                    "submitted_date", "decision_date", "intake", "current_step"],
    },
    "appointment": {
        "comment": "咨询预约记录表",
        "fields": ["id", "student_id", "consultant_id", "appointment_type",
                    "appointment_date", "status", "notes"],
    },
    "document_checklist": {
        "comment": "申请材料清单表",
        "fields": ["id", "application_id", "doc_name", "doc_type", "status", "deadline"],
    },
    "student_mental_alert": {
        "comment": "学生心理预警表",
        "fields": ["id", "student_id", "student_name", "risk_level", "trigger_reason",
                    "follow_up_status", "created_at"],
    },
}


def nl2sql_generate(natural_query: str) -> str:
    """
    自然语言转SQL生成（规则引擎版）
    根据关键词匹配生成对应的 SELECT 查询
    """
    query = natural_query.strip()

    # 如果直接输入了SQL，校验后返回
    if query.upper().strip().startswith("SELECT"):
        return query

    # ===== 客户相关 =====
    if any(kw in query for kw in ["客户", "意向客户", "潜在客户", "客人", "线索", "leads", "准客户"]):
        conditions = []
        if any(kw in query for kw in ["已签约", "签约"]):
            conditions.append("current_status='已签约'")
        if any(kw in query for kw in ["意向中", "跟进中", "跟进"]):
            conditions.append("current_status='意向中'")
        if any(kw in query for kw in ["已流失", "流失"]):
            conditions.append("current_status='已流失'")

        if "所有" in query or "全部" in query or "所有客户" in query or "全部客户" in query:
            sql = "SELECT * FROM intention_customer ORDER BY create_time DESC"
        elif conditions:
            sql = f"SELECT * FROM intention_customer WHERE {' AND '.join(conditions)} ORDER BY create_time DESC"
        else:
            sql = "SELECT * FROM intention_customer ORDER BY create_time DESC LIMIT 20"
        return sql

    # ===== 请假相关 =====
    if any(kw in query for kw in ["请假", "申请"]):
        if "待审批" in query or "待审核" in query or "待批准" in query:
            return "SELECT * FROM leave_application WHERE status=0 ORDER BY create_time DESC"
        elif "已通过" in query or "批准" in query:
            return "SELECT * FROM leave_application WHERE status=1 ORDER BY create_time DESC"
        elif "已驳回" in query or "拒绝" in query:
            return "SELECT * FROM leave_application WHERE status=2 ORDER BY create_time DESC"
        elif "学生" in query:
            return "SELECT * FROM leave_application WHERE applicant_type='学生' ORDER BY create_time DESC"
        elif "员工" in query:
            return "SELECT * FROM leave_application WHERE applicant_type='员工' ORDER BY create_time DESC"
        else:
            return "SELECT * FROM leave_application ORDER BY create_time DESC LIMIT 20"

    # ===== 成绩相关 =====
    if any(kw in query for kw in ["成绩", "分数", "得分"]):
        student_id = None
        m = re.search(r"学生[ID]{0,2}[=:：\s]*(\d+)", query)
        if not m:
            m = re.search(r"(\d+)[号位]", query)
        if not m:
            m = re.search(r"学生.*?(\d+)", query)
        if m:
            student_id = m.group(1)

        if student_id:
            return f"SELECT * FROM student_score WHERE student_id={student_id} ORDER BY exam_date DESC"
        elif "全部" in query or "所有" in query:
            return "SELECT * FROM student_score ORDER BY input_time DESC"
        else:
            return "SELECT * FROM student_score ORDER BY input_time DESC LIMIT 20"

    # ===== 留学申请相关 =====
    if any(kw in query for kw in ["申请", "留学申请", "申请进度", "offer", "录取"]):
        student_id = None
        m = re.search(r"学生[#\s]*(\d+)", query)
        if m:
            student_id = m.group(1)
        if student_id:
            return f"SELECT * FROM application_record WHERE student_id={student_id} ORDER BY updated_at DESC"
        elif "所有" in query or "全部" in query:
            return "SELECT id, student_id, university, program_name, application_status, intake, submitted_date FROM application_record ORDER BY updated_at DESC LIMIT 50"
        else:
            return "SELECT id, student_id, university, program_name, application_status, intake, submitted_date FROM application_record ORDER BY updated_at DESC LIMIT 20"

    # ===== 材料/文档相关 =====
    if any(kw in query for kw in ["材料", "文档", "文件", "资料", "文书"]):
        app_id = None
        m = re.search(r"申请[#\s]*(\d+)", query)
        if m:
            app_id = m.group(1)
        if app_id:
            return f"SELECT * FROM document_checklist WHERE application_id={app_id} ORDER BY deadline ASC"
        elif "待提交" in query or "未交" in query or "pending" in query.lower():
            return "SELECT * FROM document_checklist WHERE status='pending' ORDER BY deadline ASC"
        else:
            return "SELECT * FROM document_checklist ORDER BY deadline ASC LIMIT 20"

    # ===== 预约/面谈相关 =====
    if any(kw in query for kw in ["预约", "面谈", "咨询", "约谈", "见面"]):
        student_id = None
        m = re.search(r"学生[#\s]*(\d+)", query)
        if m:
            student_id = m.group(1)
        if student_id:
            return f"SELECT * FROM appointment WHERE student_id={student_id} ORDER BY appointment_date DESC"
        elif "今天" in query or "今日" in query:
            return "SELECT * FROM appointment WHERE DATE(appointment_date) = CURDATE() ORDER BY appointment_date"
        else:
            return "SELECT * FROM appointment ORDER BY appointment_date DESC LIMIT 20"

    # ===== 心理预警相关 =====
    if any(kw in query for kw in ["心理", "预警", "风险学生", "情绪"]):
        if "高" in query or "high" in query.lower():
            return "SELECT id, student_id, student_name, risk_level, trigger_reason, follow_up_status, created_at FROM student_mental_alert WHERE risk_level='high' ORDER BY created_at DESC"
        elif "待处理" in query:
            return "SELECT id, student_id, student_name, risk_level, trigger_reason, follow_up_status FROM student_mental_alert WHERE follow_up_status='待处理' ORDER BY created_at DESC"
        else:
            return "SELECT id, student_id, student_name, risk_level, trigger_reason, follow_up_status, created_at FROM student_mental_alert ORDER BY created_at DESC LIMIT 20"

    # ===== 投诉相关 =====
    if any(kw in query for kw in ["投诉", "抱怨", "不满"]):
        if "待处理" in query:
            return "SELECT * FROM student_complaint WHERE handle_status='待处理' ORDER BY create_time DESC"
        elif "处理中" in query:
            return "SELECT * FROM student_complaint WHERE handle_status='处理中' ORDER BY create_time DESC"
        elif "已完结" in query:
            return "SELECT * FROM student_complaint WHERE handle_status='已完结' ORDER BY create_time DESC"
        else:
            return "SELECT * FROM student_complaint ORDER BY create_time DESC"

    # ===== 日报相关 =====
    if any(kw in query for kw in ["日报", "汇报", "报告"]):
        return "SELECT * FROM employee_daily_report ORDER BY report_date DESC LIMIT 20"

    # ===== 部门/组织相关 =====
    if any(kw in query for kw in ["部门", "组织", "架构"]):
        return "SELECT d.dept_id, d.dept_name, d.dept_desc, e.emp_name as manager_name FROM department d LEFT JOIN employee e ON d.manager_id=e.emp_id WHERE d.status=1 ORDER BY d.dept_id"

    # ===== 员工相关 =====
    if any(kw in query for kw in ["员工", "人员"]):
        return "SELECT emp_id, emp_name, dept_id, position, phone, email FROM employee WHERE status=1 ORDER BY emp_id"

    # ===== 学生相关（查 student_info 表） =====
    if "学生" in query:
        kw = None
        for w in ["搜索", "查找", "找", "查"]:
            parts = query.split(w, 1)
            if len(parts) > 1 and parts[1].strip():
                kw = parts[1].strip()
                break
        if not kw:
            # 尝试从文本中提取院校名（"清华大学的学生" → 清华大学）
            import re as _re
            m = _re.search(r'(\w+)的\w*生', query)
            if m:
                kw = m.group(1)
        # 如果关键词是"所有"/"全部"等无意义词，忽略过滤
        if kw and kw not in ("所有", "全部", "所有学生", "全部学生", "信息", "列表", "名单", "数据", "资料"):
            safe_kw = kw.replace("'", "\\'")
            return f"SELECT id, name, phone, education, school, major, project_name, status FROM student_info WHERE name LIKE '%{safe_kw}%' OR school LIKE '%{safe_kw}%' OR project_name LIKE '%{safe_kw}%' ORDER BY id LIMIT 20"
        return "SELECT id, name, phone, education, school, major, project_name, status FROM student_info ORDER BY id LIMIT 20"

    # ===== 账户相关 =====
    if any(kw in query for kw in ["账户", "账号", "登录用户"]):
        return "SELECT user_id, username, real_name, user_type, dept_id, phone, email, status FROM account ORDER BY user_id"

    # 无法识别 → 尝试 LLM 生成
    return None


def nl2sql_llm(natural_query: str) -> str:
    """LLM驱动的NL2SQL（规则引擎无法匹配时的降级方案）"""
    import os, json
    try:
        import requests
        api_key = os.getenv("LLM_API_KEY", os.getenv("DASHSCOPE_API_KEY", ""))
        base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        model = os.getenv("LLM_MODEL", "qwen-plus")
        if not api_key:
            return None

        schema_lines = []
        for tname, meta in TABLE_META.items():
            fields_str = ", ".join(meta["fields"])
            schema_lines.append(f"  {tname} ({meta['comment']}): {fields_str}")
        schema_text = "\n".join(schema_lines)

        prompt = f"""你是MySQL专家。根据自然语言生成一条安全的SELECT语句。
数据库表：
{schema_text}

规则：
1. 只生成SELECT语句
2. 不加分号
3. 只输出SQL本身

用户查询：{natural_query}"""

        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": [{"role":"user","content":prompt}], "temperature":0.1, "max_tokens":500},
            timeout=15,
        )
        data = resp.json()
        sql = data["choices"][0]["message"]["content"].strip()
        sql = sql.strip().rstrip(";").strip()
        # 清理markdown代码块（re已在顶部导入）
        sql = re.sub(r'^```(?:sql)?\s*', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\s*```$', '', sql)
        if sql.upper().startswith("SELECT"):
            return sql
        return None
    except Exception as e:
        logger.warning("LLM NL2SQL 调用失败: %s", e)
        return None


# ==================== POST /api/agent/query/nl2sql ====================
@router.post("/query/nl2sql", response_model=ApiResponse, summary="NL2SQL自然语言查询")
def query_nl2sql(req: NL2SQLRequest, db: Session = Depends(get_db)):
    """
    自然语言转SQL查询
    1. 解析自然语言生成 SQL
    2. 校验只允许 SELECT
    3. 执行 SQL 返回结果
    """
    try:
        require_operator(req.current_user_type)

        query_text = req.query.strip()
        if not query_text:
            return ApiResponse(code=400, msg="查询内容不能为空")

        logger.info(f"NL2SQL: query='{query_text}', user_id={req.current_user_id}")

        # 生成 SQL（规则引擎优先，LLM降级）
        sql = nl2sql_generate(query_text)
        if not sql:
            sql = nl2sql_llm(query_text)

        if not sql:
            return ApiResponse(code=400, msg=f"嗯…「{query_text}」这个我暂时还不太明白 🤔\n\n你可以试试这样说：\n• 「查看所有客户」\n• 「查看待审批的请假」\n• 「查询学生成绩」\n• 「查所有学生」")

        # 强制校验只允许 SELECT
        try:
            sql = validate_select_sql(sql)
        except ValueError as e:
            logger.warning("SQL 校验拦截: %s | 原始: %s", e, sql)
            return ApiResponse(code=400, msg=f"查询安全校验未通过：{e}")

        logger.info(f"NL2SQL 生成的SQL: {sql}")

        # 执行查询
        result_data = execute_raw_sql(sql)

        # 生成自然语言总结
        summary = f"查询完成，共找到 {len(result_data)} 条记录"

        return ApiResponse(data={
            "natural_query": query_text,
            "generated_sql": sql,
            "summary": summary,
            "count": len(result_data),
            "results": result_data,
        })

    except HTTPException:
        raise
    except ValueError as e:
        return ApiResponse(code=400, msg=str(e))
    except Exception as e:
        logger.error(f"NL2SQL 执行失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"查询执行失败: {str(e)}")
