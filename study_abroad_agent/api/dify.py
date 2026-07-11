"""
兼容旧版 Dify 工作流的路由 (/api/dify/*)
内部转调 services 层，行为与新版 /api/v1 一致。
"""
from fastapi import APIRouter, HTTPException
from study_abroad_agent.schemas import (
    ProfileCreate, RecommendRequest, ConsultationCreate,
)
from study_abroad_agent.services.profile_service import ProfileService
from study_abroad_agent.services.recommend_service import RecommendService
from study_abroad_agent.services.consultation_service import ConsultationService
from study_abroad_agent.database import db

router = APIRouter()


@router.get("/health", summary="健康检查")
def health():
    result = db.query("SELECT 1 AS ok")
    return {"code": 0, "data": result, "message": "success"}


@router.post("/profile", summary="保存/更新用户画像 (兼容)")
def save_profile(req: ProfileCreate):
    profile = ProfileService.save_profile(
        req.conversation_id,
        req.model_dump(exclude={"conversation_id"}, exclude_unset=True),
    )
    check = ProfileService.check_profile(req.conversation_id)
    return {"code": 0, "data": {"profile": profile, **check}, "message": "success"}


@router.get("/profile/{conversation_id}", summary="获取用户画像 (兼容)")
def get_profile(conversation_id: str):
    profiles = ProfileService.get_by_conversation_id(conversation_id)
    if not profiles:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"code": 0, "data": profiles, "message": "success", "total": len(profiles)}


@router.delete("/profile/{conversation_id}", summary="删除用户画像 (兼容)")
def delete_profile(conversation_id: str):
    existing = ProfileService.get_by_conversation_id(conversation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="用户不存在")
    ProfileService.delete_by_conversation_id(conversation_id)
    return {"code": 0, "data": None, "message": "success"}


@router.post("/recommend", summary="课程推荐 (兼容)")
def recommend(req: RecommendRequest):
    result = RecommendService.recommend(req.conversation_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"code": 0, "data": result, "message": "success"}


@router.post("/consultation", summary="保存咨询记录 (兼容)")
def save_consultation(req: ConsultationCreate):
    new_id = ConsultationService.save(
        req.conversation_id,
        req.conversation_summary or "",
        req.recommend_ids,
    )
    return {"code": 0, "data": ConsultationService.get_by_id(new_id), "message": "success"}
