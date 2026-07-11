"""健康检查路由"""
from fastapi import APIRouter, Depends
from study_abroad_agent.database import get_db, Database

router = APIRouter(tags=["系统"])


@router.get("/health", summary="健康检查")
def health(db: Database = Depends(get_db)):
    """服务存活与数据库连通性检查。"""
    row = db.query_one("SELECT 1 AS ok")
    return {"code": 0, "data": {"db": row}, "message": "success"}


@router.get("/ready", summary="就绪探针")
def ready():
    return {"code": 0, "data": None, "message": "ready"}
