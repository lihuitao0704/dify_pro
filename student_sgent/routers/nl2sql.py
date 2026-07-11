"""
NL2SQL API 路由

POST /api/v1/nl2sql/query    — 自然语言查询数据库
GET  /api/v1/nl2sql/schema   — 查看数据库表结构
GET  /api/v1/nl2sql/templates — 查看预设查询模板
"""

from fastapi import APIRouter, HTTPException

from schemas.student import NL2SQLRequest, NL2SQLResponse
from services.nl2sql_service import (
    execute_nl2sql,
    QUERY_TEMPLATES,
    TABLE_SCHEMAS,
)

router = APIRouter(prefix="/api/v1/nl2sql", tags=["NL2SQL"])


@router.post("/query", response_model=NL2SQLResponse)
async def natural_language_query(body: NL2SQLRequest):
    """
    自然语言查询数据库

    支持中文自然语言输入，如：
        - "查询张三的请假记录"
        - "查看最近对话"
        - "统计最近一周的情绪趋势"
        - "查询所有pending状态的投诉工单"

    流程：
        1. 先尝试预设模板匹配（快速、安全）
        2. 模板未命中时调用 OpenAI 兼容 API 生成 SQL
        3. SQL 安全校验（仅允许 SELECT）
        4. 执行查询并返回结果
    """
    try:
        result = await execute_nl2sql(
            natural_query=body.query,
            student_id=body.student_id,
            use_template=body.use_template,
        )
        return NL2SQLResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询执行失败: {str(e)}")


@router.get("/schema")
def get_table_schema():
    """获取数据库表结构描述"""
    return {
        "database": "hambaki_3",
        "description": "学生智能助手模块数据库",
        "tables": TABLE_SCHEMAS,
    }


@router.get("/templates")
def get_query_templates():
    """获取预设查询模板列表"""
    templates = []
    for name, config in QUERY_TEMPLATES.items():
        templates.append({
            "name": name,
            "pattern": config["pattern"],
            "sql_preview": config["sql"].strip()[:200] + "...",
        })
    return {
        "total": len(templates),
        "templates": templates,
    }
