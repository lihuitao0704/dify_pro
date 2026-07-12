"""
活动 / 讲座 / 报名路由

路由结构：
  /api/v1/events/nl2sql                          自然语言直接查/报 (抛光结果)
  /api/v1/events/lectures[/{id}]                  讲座 CRUD
  /api/v1/events/activities[/{id}]                活动 CRUD
  /api/v1/events/registrations/lectures[/{id}]    讲座报名记录查询/删除
  /api/v1/events/registrations/activities[/{id}]  活动报名记录查询/删除
"""
import json as _json
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from customer_agent.schemas import EventNL2SQLRequest
from customer_agent.services import nl2sql as nl2sql_service
from customer_agent.db import get_db

router = APIRouter(prefix="/events", tags=["活动讲座"])


# ── 自然语言入口 (对齐旧 Event_Lecture /nl2sql 语义) ─────────────────────
@router.post("/nl2sql", summary="自然语言 → SQL → 执行 (活动讲座场景)")
def events_nl2sql(req: EventNL2SQLRequest):
    """
    接收自然语言，由 LongCat 模型识别意图和目标表
    (lectures / activities / lecture_registrations / activity_registrations)，
    生成 SQL 并执行，返回结果 + 自然语言润色回答。

    语义与旧 Event_Lecture_api.py 的 /nl2sql 一致。
    """
    def _json_default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        return str(obj)

    try:
        result = nl2sql_service.run_nl2sql(
            question=req.query,
            include_sql=True,
            polish=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"NL2SQL 调用失败: {e}")

    rows = result.get("rows") or []
    is_empty_query = (result.get("action") == "query" and len(rows) == 0)

    if is_empty_query:
        result_type = "error"
        message = "没有查询到相关记录，请检查查询条件（如日期、关键词）是否正确"
        http_status = 400
    elif result.get("action") == "insert":
        result_type = "dml"
        message = f"操作成功 (inserted_id={result.get('inserted_id')})"
        http_status = 200
    else:
        result_type = "select" if result.get("action") == "query" else result.get("action")
        message = "success"
        http_status = 200

    payload = {
        "query": req.query,
        "sql": result.get("sql"),
        "result_type": result_type,
        "data": rows if result.get("action") == "query" else result.get("inserted_id"),
        "message": message,
        "polished": result.get("polished", ""),
        "status_code": http_status,
    }
    body = _json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
    return Response(
        content=body,
        status_code=http_status,
        media_type="application/json; charset=utf-8",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


# ── 讲座 CRUD ──────────────────────────────────────────────────────────
@router.get("/lectures", summary="查询讲座列表")
def list_lectures(
    keyword: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    sql = "SELECT * FROM lectures WHERE 1=1"
    params: list = []
    if keyword:
        sql += " AND title LIKE %s"
        params.append(f"%{keyword}%")
    sql += " ORDER BY event_time DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    rows = get_db().query(sql, tuple(params))
    return {"code": 0, "data": rows, "message": "success", "total": len(rows)}


@router.get("/lectures/{lecture_id}", summary="按 id 查询讲座")
def get_lecture(lecture_id: int):
    row = get_db().query_one("SELECT * FROM lectures WHERE lecture_id = %s", (lecture_id,))
    if not row:
        raise HTTPException(status_code=404, detail="讲座不存在")
    return {"code": 0, "data": row, "message": "success"}


@router.post("/lectures", summary="创建讲座")
def create_lecture(req: dict):
    keys = ["title", "event_time", "location", "registration_method", "speaker"]
    cols = [k for k in keys if k in req]
    if not cols:
        raise HTTPException(status_code=400, detail="至少提供 title")
    placeholders = ", ".join(["%s"] * len(cols))
    col_names = ", ".join(cols)
    vals = tuple(req[k] for k in cols)
    new_id = get_db().execute(
        f"INSERT INTO lectures ({col_names}) VALUES ({placeholders})", vals
    )
    return {"code": 0, "data": get_db().query_one(
        "SELECT * FROM lectures WHERE lecture_id = %s", (new_id,)
    ), "message": "success"}


@router.put("/lectures/{lecture_id}", summary="按 id 更新讲座")
def update_lecture(lecture_id: int, req: dict):
    existing = get_db().query_one(
        "SELECT * FROM lectures WHERE lecture_id = %s", (lecture_id,)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="讲座不存在")
    fields, vals = [], []
    for k, v in req.items():
        fields.append(f"{k} = %s")
        vals.append(v)
    if fields:
        vals.append(lecture_id)
        get_db().execute(
            f"UPDATE lectures SET {', '.join(fields)} WHERE lecture_id = %s", tuple(vals)
        )
    return {"code": 0, "data": get_db().query_one(
        "SELECT * FROM lectures WHERE lecture_id = %s", (lecture_id,)
    ), "message": "success"}


@router.delete("/lectures/{lecture_id}", summary="按 id 删除讲座")
def delete_lecture(lecture_id: int):
    existing = get_db().query_one(
        "SELECT * FROM lectures WHERE lecture_id = %s", (lecture_id,)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="讲座不存在")
    get_db().execute("DELETE FROM lectures WHERE lecture_id = %s", (lecture_id,))
    return {"code": 0, "data": None, "message": "success"}


# ── 活动 CRUD ──────────────────────────────────────────────────────────
@router.get("/activities", summary="查询活动列表")
def list_activities(
    keyword: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    sql = "SELECT * FROM activities WHERE 1=1"
    params: list = []
    if keyword:
        sql += " AND title LIKE %s"
        params.append(f"%{keyword}%")
    sql += " ORDER BY event_time DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    rows = get_db().query(sql, tuple(params))
    return {"code": 0, "data": rows, "message": "success", "total": len(rows)}


@router.get("/activities/{activity_id}", summary="按 id 查询活动")
def get_activity(activity_id: int):
    row = get_db().query_one("SELECT * FROM activities WHERE activity_id = %s", (activity_id,))
    if not row:
        raise HTTPException(status_code=404, detail="活动不存在")
    return {"code": 0, "data": row, "message": "success"}


@router.post("/activities", summary="创建活动")
def create_activity(req: dict):
    keys = ["title", "event_time", "location", "registration_method"]
    cols = [k for k in keys if k in req]
    if not cols:
        raise HTTPException(status_code=400, detail="至少提供 title")
    placeholders = ", ".join(["%s"] * len(cols))
    col_names = ", ".join(cols)
    vals = tuple(req[k] for k in cols)
    new_id = get_db().execute(
        f"INSERT INTO activities ({col_names}) VALUES ({placeholders})", vals
    )
    return {"code": 0, "data": get_db().query_one(
        "SELECT * FROM activities WHERE activity_id = %s", (new_id,)
    ), "message": "success"}


@router.put("/activities/{activity_id}", summary="按 id 更新活动")
def update_activity(activity_id: int, req: dict):
    existing = get_db().query_one(
        "SELECT * FROM activities WHERE activity_id = %s", (activity_id,)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="活动不存在")
    fields, vals = [], []
    for k, v in req.items():
        fields.append(f"{k} = %s")
        vals.append(v)
    if fields:
        vals.append(activity_id)
        get_db().execute(
            f"UPDATE activities SET {', '.join(fields)} WHERE activity_id = %s", tuple(vals)
        )
    return {"code": 0, "data": get_db().query_one(
        "SELECT * FROM activities WHERE activity_id = %s", (activity_id,)
    ), "message": "success"}


@router.delete("/activities/{activity_id}", summary="按 id 删除活动")
def delete_activity(activity_id: int):
    existing = get_db().query_one(
        "SELECT * FROM activities WHERE activity_id = %s", (activity_id,)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="活动不存在")
    get_db().execute("DELETE FROM activities WHERE activity_id = %s", (activity_id,))
    return {"code": 0, "data": None, "message": "success"}


# ── 报名记录查询 / 删除 ────────────────────────────────────────────────
@router.get("/registrations/lectures", summary="查询讲座报名记录")
def list_lecture_registrations(
    lecture_id: Optional[int] = None,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    sql = "SELECT * FROM lecture_registrations WHERE 1=1"
    params: list = []
    if lecture_id is not None:
        sql += " AND lecture_id = %s"
        params.append(lecture_id)
    if name:
        sql += " AND name LIKE %s"
        params.append(f"%{name}%")
    if phone:
        sql += " AND phone LIKE %s"
        params.append(f"%{phone}%")
    sql += " ORDER BY registration_id DESC LIMIT %s"
    params.append(limit)
    rows = get_db().query(sql, tuple(params))
    return {"code": 0, "data": rows, "message": "success", "total": len(rows)}


@router.get("/registrations/activities", summary="查询活动报名记录")
def list_activity_registrations(
    activity_id: Optional[int] = None,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    sql = "SELECT * FROM activity_registrations WHERE 1=1"
    params: list = []
    if activity_id is not None:
        sql += " AND activity_id = %s"
        params.append(activity_id)
    if name:
        sql += " AND name LIKE %s"
        params.append(f"%{name}%")
    if phone:
        sql += " AND phone LIKE %s"
        params.append(f"%{phone}%")
    sql += " ORDER BY registration_id DESC LIMIT %s"
    params.append(limit)
    rows = get_db().query(sql, tuple(params))
    return {"code": 0, "data": rows, "message": "success", "total": len(rows)}


@router.delete("/registrations/lectures/{registration_id}", summary="删除一条讲座报名记录")
def delete_lecture_registration(registration_id: int):
    get_db().execute(
        "DELETE FROM lecture_registrations WHERE registration_id = %s", (registration_id,)
    )
    return {"code": 0, "data": None, "message": "success"}


@router.delete("/registrations/activities/{registration_id}", summary="删除一条活动报名记录")
def delete_activity_registration(registration_id: int):
    get_db().execute(
        "DELETE FROM activity_registrations WHERE registration_id = %s", (registration_id,)
    )
    return {"code": 0, "data": None, "message": "success"}
