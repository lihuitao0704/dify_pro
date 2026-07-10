"""
活动与讲座报名系统 —— FastAPI 接口
提供唯一的 /nl2sql 端点，接收自然语言，返回 SQL 及执行结果。
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from Event_Lecture import nl2sql


class UTF8JSONResponse(JSONResponse):
    """强制 Content-Type 带 charset=utf-8 的 JSON 响应（解决 dify 调用时报 ASCII 编码错误）。"""
    media_type = "application/json; charset=utf-8"


class UTF8Middleware(BaseHTTPMiddleware):
    """兜底：给所有响应补上 charset=utf-8。"""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if "charset" not in ct:
            if ct.startswith("application/json") or ct.startswith("text/"):
                response.headers["content-type"] = ct + "; charset=utf-8"
        return response


app = FastAPI(
    title="活动与讲座报名 NL2SQL 系统",
    description="通过千问模型将自然语言转为 SQL，对讲座表、活动表、讲座报名表、活动报名表进行增删改查。",
    version="1.0.0",
    default_response_class=UTF8JSONResponse,
)

# ── 中间件（注意顺序：后添加的先执行）──
app.add_middleware(UTF8Middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 请求 / 响应模型 ─────────────────────────────────────────
class NL2SQLRequest(BaseModel):
    """请求体：只需提供一个自然语言问题。
    示例：
        - "查询所有德国留学讲座"
        - "近期有哪些团建活动"
        - "帮我报名讲座3，姓名张三，手机13800138000"
        - "新增一场讲座，主题是新加坡硕士申请，时间是2026-09-20 14:00，地点线上，主讲人赵老师"
        - "删除报名手机号13800138000的记录"
    """
    query: str


class NL2SQLResponse(BaseModel):
    query: str
    sql: str
    result_type: str   # select / dml / error
    data: object
    message: str
    polished: str      # 千问润色后的自然语言回答


# ── 唯一接口 ────────────────────────────────────────────────
@app.post("/nl2sql", summary="自然语言 → SQL → 执行")
def nl2sql_endpoint(req: NL2SQLRequest):
    """
    接收自然语言，由千问模型识别意图（增/删/改/查）和目标表（lectures / activities / lecture_registrations / activity_registrations），
    生成 SQL 并执行，返回结果。
    """
    import json as _json
    out = nl2sql(req.query)
    result = out["result"]
    # 查询结果为 0 条时，统一视为 error 类型返回给前端
    if result["type"] == "select" and (not result.get("data") or len(result.get("data", [])) == 0):
        result["type"] = "error"
        result["message"] = "没有查询到相关记录，请检查查询条件（如日期、关键词）是否正确"
    payload = {
        "query": out["query"],
        "sql": out["sql"],
        "result_type": result["type"],
        "data": result["data"],
        "message": result["message"],
        "polished": out.get("polished", ""),
    }
    # 手动序列化为 UTF-8 字节，彻底避开框架默认编码
    body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


# ── 健康检查 ────────────────────────────────────────────────
@app.get("/health", summary="健康检查")
def health():
    return {"status": "ok"}


# ── 本地运行入口 ────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("el_api:app", host="0.0.0.0", port=8010, reload=True)
