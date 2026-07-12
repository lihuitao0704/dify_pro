"""
FastAPI 应用入口。

职责：
  - 创建 FastAPI 实例，挂载 CORS 与所有路由
  - 提供 ``/`` 与 ``/health`` 探活端点
  - 使用 ``python -m summary_report.main`` 或
    ``uvicorn summary_report.main:app`` 启动

运行方式（项目根目录）：
    uvicorn summary_report.main:app --host 0.0.0.0 --port 8000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from summary_report.api.routes import all_routers
from summary_report.api.schemas import HealthResponse, RootResponse
from summary_report.core.config import APP_HOST, APP_PORT
from summary_report.core.logger import get_logger, setup_logging

logger = get_logger(__name__)

# ── FastAPI 实例 ────────────────────────────────────────────
app = FastAPI(
    title="智能报告API",
    description="基于 NL2SQL 的五份核心汇总报告接口（客户经营/员工日报/心理健康/投诉周报）+ 通用查询",
    version="2.0.0",
)

# ── 中间件 ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 诊断中间件（临时）：打印每个请求的来源与路径 ────────────
@app.middleware("http")
async def debug_incoming_request(request, call_next):
    """临时诊断用：记录来源 IP、method、完整 path，便于排查 Dify 404。"""
    client_host = request.client.host if request.client else "?"
    logger.info(
        "[DIAG] <- %s %s %s (from %s)",
        request.method, request.url.path, dict(request.query_params), client_host,
    )
    response = await call_next(request)
    logger.info("[DIAG] -> %s %s => HTTP %d", request.method, request.url.path, response.status_code)
    return response

# ── 统一注册所有路由 ────────────────────────────────────────
for r in all_routers:
    app.include_router(r, prefix="/report")


# ── 根路径 & 健康检查 ─────────────────────────────────────
@app.get("/", response_model=RootResponse)
def root() -> dict:
    return {
        "service": "全域经营分析汇总报告 API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/test", response_class=HTMLResponse, include_in_schema=False)
def test_panel():
    """智能报告独立测试页面（无需登录）。"""
    test_html = Path(__file__).parent / "test_report.html"
    if not test_html.is_file():
        return HTMLResponse("<h1>测试页面文件未找到</h1>", status_code=404)
    return HTMLResponse(test_html.read_text(encoding="utf-8"))


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    return {
        "status": "ok",
        "reports": [
            "POST /report/customer_operation  - 全域客户经营分析报告",
            "POST /report/employee_daily      - 员工日报智能汇总报告",
            "POST /report/student_mental      - 学生心理健康周报",
            "POST /report/complaint_weekly    - 投诉处理周报",
            "POST /report/nl2sql              - 通用自然语言查询（支持 query_type 表单筛选："
            "general / student / enterprise）",
        ],
    }


# ── 启动入口 ────────────────────────────────────────────────
def main() -> None:
    """开发调试用启动函数（生产建议使用 uvicorn gunicorn 等方式）。"""
    import uvicorn

    setup_logging()
    logger.info("启动 %s v2.0.0 @ %s:%s", app.title, APP_HOST, APP_PORT)
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)


if __name__ == "__main__":
    main()
