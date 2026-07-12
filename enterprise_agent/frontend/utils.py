"""
对话式企业智能助手 - 后端接口调用工具
封装所有 /api/agent/* 接口的 HTTP 调用，支持自动重试
所有接口函数均要求调用方传入 user_id + user_type，禁止硬编码
"""
import requests
import time
from typing import Optional

API_BASE = "http://localhost:8001/api/agent"
MAX_RETRIES = 2
RETRY_DELAY = 0.5

# 默认登录用户（前端测试用，生产环境从登录页获取）
CURRENT_USER_ID = 1
CURRENT_USER_TYPE = "管理者"


def _request(method, path, params=None, body=None, user_id=None, user_type=None):
    """通用请求：带重试、超时、优雅降级"""
    if user_id is None or user_type is None:
        raise ValueError("user_id and user_type are required — do not use defaults")

    url = f"{API_BASE}{path}"
    req_params = {**(params or {}), "current_user_id": user_id, "current_user_type": user_type}
    req_body = {**(body or {}), "current_user_id": user_id, "current_user_type": user_type}

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            if method == "GET":
                r = requests.get(url, params=req_params, timeout=10)
            elif method == "POST":
                r = requests.post(url, json=req_body, timeout=10)
            elif method == "PUT":
                r = requests.put(url, json=req_body, timeout=10)
            else:
                return {"code": -1, "msg": f"Unsupported: {method}", "data": None}
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            last_error = f"Request timed out (attempt {attempt + 1})"
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
        except requests.exceptions.ConnectionError:
            last_error = "Cannot connect to backend"
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
        except requests.exceptions.HTTPError as e:
            return {"code": e.response.status_code, "msg": str(e), "data": None}
        except Exception as e:
            last_error = str(e)
            break
    return {"code": -1, "msg": last_error or "Failed", "data": None}


def _get(path, params=None, user_id=None, user_type=None):
    return _request("GET", path, params=params, user_id=user_id, user_type=user_type)


def _post(path, body=None, user_id=None, user_type=None):
    return _request("POST", path, body=body, user_id=user_id, user_type=user_type)


def _put(path, body=None, user_id=None, user_type=None):
    return _request("PUT", path, body=body, user_id=user_id, user_type=user_type)


# ============================================================
# 业务接口 —— 每个函数都接收 user_id + user_type
# ============================================================

def get_todo_all(user_id=None, user_type=None) -> dict:
    return _get("/todo/all", user_id=user_id, user_type=user_type)


def get_customer_list(keyword="", status="", page=1, user_id=None, user_type=None) -> dict:
    params = {"page": page, "page_size": 10}
    if keyword: params["keyword"] = keyword
    if status: params["status"] = status
    return _get("/customer/list", params, user_id=user_id, user_type=user_type)


def get_customer_detail(customer_id, user_id=None, user_type=None) -> dict:
    return _get(f"/customer/{customer_id}", user_id=user_id, user_type=user_type)


def add_customer(data, user_id=None, user_type=None) -> dict:
    return _post("/customer/add", data, user_id=user_id, user_type=user_type)


def update_customer_status(customer_id, new_status, user_id=None, user_type=None) -> dict:
    return _put("/customer/status", {"customer_id": customer_id, "new_status": new_status},
                user_id=user_id, user_type=user_type)


def add_customer_follow(customer_id, follow_record, user_id=None, user_type=None) -> dict:
    return _put("/customer/follow", {"customer_id": customer_id, "follow_record": follow_record},
                user_id=user_id, user_type=user_type)


def get_leave_todo(user_id=None, user_type=None) -> dict:
    return _get("/leave/todo", user_id=user_id, user_type=user_type)


def submit_leave_employee(leave_type, start_date, end_date, reason="", user_id=None, user_type=None) -> dict:
    return _post("/leave/employee", {
        "leave_type": leave_type, "start_date": start_date, "end_date": end_date, "reason": reason,
    }, user_id=user_id, user_type=user_type)


def submit_leave_student(student_name, leave_type, start_date, end_date, reason="", user_id=None, user_type=None) -> dict:
    return _post("/leave/student", {
        "student_name": student_name, "leave_type": leave_type,
        "start_date": start_date, "end_date": end_date, "reason": reason,
    }, user_id=user_id, user_type=user_type)


def batch_approve_leave(leave_ids, action, user_id=None, user_type=None) -> dict:
    return _post("/leave/batch_approve", {"leave_ids": leave_ids, "action": action},
                 user_id=user_id, user_type=user_type)


def submit_report(report_content, report_date, user_id=None, user_type=None) -> dict:
    return _post("/report/submit", {"report_content": report_content, "report_date": report_date},
                 user_id=user_id, user_type=user_type)


def get_report_list(start_date="", end_date="", page=1, user_id=None, user_type=None) -> dict:
    params = {"page": page, "page_size": 10}
    if start_date: params["start_date"] = start_date
    if end_date: params["end_date"] = end_date
    return _get("/report/list", params, user_id=user_id, user_type=user_type)


def get_organization_tree(user_id=None, user_type=None) -> dict:
    return _get("/organization/tree", user_id=user_id, user_type=user_type)


def get_complaint_list(status="", user_id=None, user_type=None) -> dict:
    params = {"page": 1, "page_size": 20}
    if status: params["status"] = status
    return _get("/complaint/list", params, user_id=user_id, user_type=user_type)


def handle_complaint(complaint_id, new_status, handler_user_id=None, user_id=None, user_type=None) -> dict:
    body = {"complaint_id": complaint_id, "new_status": new_status}
    if handler_user_id: body["handler_user_id"] = handler_user_id
    return _put("/complaint/handle", body, user_id=user_id, user_type=user_type)


def add_score(student_id, subject, score, exam_type="", exam_date="", user_id=None, user_type=None) -> dict:
    body = {"student_id": student_id, "subject": subject, "score": score}
    if exam_type: body["exam_type"] = exam_type
    if exam_date: body["exam_date"] = exam_date
    return _post("/score/add", body, user_id=user_id, user_type=user_type)


def get_score_list(student_id=None, subject="", user_id=None, user_type=None) -> dict:
    params = {"page": 1, "page_size": 50}
    if student_id: params["student_id"] = student_id
    if subject: params["subject"] = subject
    return _get("/score/list", params, user_id=user_id, user_type=user_type)


def query_knowledge(question, user_id=None, user_type=None) -> dict:
    return _post("/knowledge/query", {"question": question}, user_id=user_id, user_type=user_type)


def query_nl2sql(query, user_id=None, user_type=None) -> dict:
    return _post("/query/nl2sql", {"query": query}, user_id=user_id, user_type=user_type)
