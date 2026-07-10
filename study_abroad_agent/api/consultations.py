"""咨询记录 CRUD 路由"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from study_abroad_agent.schemas import ConsultationCreate, ConsultationUpdate
from study_abroad_agent.services.consultation_service import ConsultationService

router = APIRouter(prefix="/consultations", tags=["咨询记录"])


@router.get("", summary="列表查询咨询记录")
def list_consultations(
    status: Optional[str] = Query(
        None, pattern="^(new|recommended|interested|not_interested|consulting)$"
    ),
    user_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = ConsultationService.list_consultations(status, user_id, limit, offset)
    return {"code": 0, "data": rows, "message": "success", "total": len(rows)}


@router.get("/by-conversation/{conversation_id}", summary="按 conversation_id 查询咨询记录")
def get_by_conversation(conversation_id: str):
    rows = ConsultationService.get_by_conversation(conversation_id)
    return {"code": 0, "data": rows, "message": "success"}


@router.get("/{consultation_id}", summary="按 id 查询单个咨询记录")
def get_consultation(consultation_id: int):
    row = ConsultationService.get_by_id(consultation_id)
    if not row:
        raise HTTPException(status_code=404, detail="咨询记录不存在")
    return {"code": 0, "data": row, "message": "success"}


@router.post("", summary="创建咨询记录")
def create_consultation(req: ConsultationCreate):
    new_id = ConsultationService.save(
        req.conversation_id,
        req.conversation_summary or "",
        req.recommend_ids,
        course_id=req.course_id,
        user_feedback=req.user_feedback or "",
        status=req.status or "new",
    )
    return {"code": 0, "data": ConsultationService.get_by_id(new_id), "message": "success"}


@router.put("/{consultation_id}", summary="按 id 更新咨询记录")
def update_consultation(consultation_id: int, req: ConsultationUpdate):
    existing = ConsultationService.get_by_id(consultation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="咨询记录不存在")
    updated = ConsultationService.update(consultation_id, req.model_dump(exclude_unset=True))
    return {"code": 0, "data": updated, "message": "success"}


@router.delete("/{consultation_id}", summary="按 id 删除咨询记录")
def delete_consultation(consultation_id: int):
    existing = ConsultationService.get_by_id(consultation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="咨询记录不存在")
    ConsultationService.delete(consultation_id)
    return {"code": 0, "data": None, "message": "success"}
