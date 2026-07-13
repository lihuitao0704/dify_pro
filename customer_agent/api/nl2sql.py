"""NL2SQL 路由：自然语言转 SQL，自动判断查询 (query) 与新增 (insert)。"""
from fastapi import APIRouter, HTTPException
from customer_agent.schemas import NL2SQLRequest
from customer_agent.services import nl2sql as nl2sql_service

router = APIRouter(prefix="/nl2sql", tags=["NL2SQL"])


def _serialize(obj):
    """对日期 / Decimal 等不可 JSON 序列化的字段做转换。"""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def _clean(rows):
    return [{k: _serialize(v) for k, v in row.items()} for row in rows]


def _build_data(result: dict) -> dict:
    """按 action 构建双形态响应数据。"""
    if result.get("action") == "insert":
        return {
            "question": result["question"],
            "action": "insert",
            "sql": result.get("sql"),
            "inserted_id": result.get("inserted_id"),
            "affected_rows": result.get("affected_rows"),
            "elapsed_ms": result["elapsed_ms"],
        }
    data = {
        "question": result["question"],
        "action": "query",
        "sql": result.get("sql"),
        "rows": _clean(result.get("rows") or []),
        "row_count": result.get("row_count", 0),
        "elapsed_ms": result["elapsed_ms"],
    }
    if result.get("polished"):
        data["polished"] = result["polished"]
    return data


@router.post("/query", summary="自然语言转 SQL（自动判断查询/新增）")
def nl2sql_query(req: NL2SQLRequest):
    """
    将自然语言问题发给 LongCat-2.0，自动判断意图：
    - query  → 只读 SELECT，返回 rows / row_count
    - insert → INSERT (受 config.NL2SQL_ALLOW_WRITE 控制)，返回 inserted_id
    """
    try:
        result = nl2sql_service.run_nl2sql(
            question=req.question,
            include_sql=req.include_sql,
            polish=req.polish,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"NL2SQL 调用失败: {e}")

    return {"code": 0, "message": "success", "data": _build_data(result)}


@router.post("/explain", summary="仅生成 SQL，不执行 (dry-run / 调试)")
def nl2sql_explain(req: NL2SQLRequest):
    """让模型生成 SQL 但只返回不执行，可用于调试。"""
    try:
        result = nl2sql_service.run_nl2sql(
            question=req.question,
            include_sql=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "code": 0,
        "message": "success (dry-run, not executed)",
        "data": {
            "sql": result.get("sql"),
            "question": req.question,
            "action": result.get("action"),
        },
    }
