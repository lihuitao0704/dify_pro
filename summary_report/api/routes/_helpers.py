"""
路由层内部共享的小工具。

四个具体报告路由的处理流程完全一致（调用 service → 序列化 → 返回），
抽成公共函数避免重复。这不是对外接口，仅路由层内部使用。
"""

from typing import Any, Callable, Dict, List, Tuple

from fastapi import HTTPException

from summary_report.core.logger import get_logger
from summary_report.utils.serialize import serialize_rows

logger = get_logger(__name__)


def _serialize_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """序列化 execute_sql 的输出，使其可直接被 FastAPI 返回。"""
    serializable: List[Dict[str, Any]] = []
    for r in results:
        item: Dict[str, Any] = {"sql": r["sql"], "type": r["type"]}
        if r["type"] == "SELECT":
            item["columns"] = r["columns"]
            item["rows"] = serialize_rows(r["rows"])
            item["count"] = r["count"]
        else:
            item["affected_rows"] = r["affected_rows"]
        serializable.append(item)
    return serializable


def handle_report_request(
    question: str,
    report_name: str,
    service_generate: Callable[[str], Tuple[List[str], List[Dict[str, Any]], str]],
) -> Dict[str, Any]:
    """
    通用的报告处理流水线。

    封装了 service 调用、错误转 HTTP、序列化，供四个具体报告路由复用。

    Args:
        question:         用户问题。
        report_name:      报告名（用于日志）。
        service_generate:  具体报告服务的 generate 函数。

    Returns:
        给定的响应字典（符合 ReportResponse 结构）。
    """
    logger.info("📝 [%s] 用户问题: %s", report_name, question)

    try:
        sql_list, results, answer = service_generate(question)
    except HTTPException:
        raise
    except ValueError as exc:
        # LLM 生成的 SQL 校验失败等 → 400
        raise HTTPException(status_code=400, detail=f"SQL 生成失败: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"服务异常: {exc}") from exc

    logger.info("💬 [%s] 回答: %s...", report_name, answer[:100])

    return {
        "question": question,
        "sql_list": sql_list,
        "results": _serialize_results(results),
        "answer": answer,
    }
