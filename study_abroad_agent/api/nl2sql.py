"""NL2SQL 路由：自然语言转 SQL 查询"""
import json, re
from fastapi import APIRouter, HTTPException
from study_abroad_agent.schemas import NL2SQLRequest
from study_abroad_agent.services import nl2sql as nl2sql_service

router = APIRouter(prefix="/nl2sql", tags=["NL2SQL"])


def _serialize(obj):
    """对日期 / Decimal 等不可 JSON 序列化的字段做转换。"""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def _clean(rows):
    cleaned = []
    for row in rows:
        cleaned.append({k: _serialize(v) for k, v in row.items()})
    return cleaned


@router.post("/query", summary="自然语言转 SQL 查询")
def nl2sql_query(req: NL2SQLRequest):
    """
    将自然语言问题发给 LongCat-2.0 模型转成 SQL，
    执行只读查询并以 JSON 形式返回结果。
    """
    try:
        result = nl2sql_service.run_nl2sql(
            question=req.question,
            include_sql=req.include_sql,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"NL2SQL 调用失败: {e}")

    return {
        "code": 0,
        "message": "success",
        "data": {
            "question": result["question"],
            "row_count": result["row_count"],
            "elapsed_ms": result["elapsed_ms"],
            "sql": result.get("sql"),
            "rows": _clean(result["rows"]),
        },
    }


@router.post("/explain", summary="仅生成 SQL，不执行 (安全检查/调试)")
def nl2sql_explain(req: NL2SQLRequest):
    """让模型生成 SQL 但只返回而不执行，可用于调试。"""
    try:
        result = nl2sql_service.run_nl2sql(question=req.question, include_sql=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "code": 0,
        "message": "success (dry-run, not executed)",
        "data": {"sql": result.get("sql"), "question": req.question},
    }
