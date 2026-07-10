"""用户画像 CRUD 路由"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from study_abroad_agent.schemas import (
    ProfileCreate, ProfileUpdate, ProfileCheck, RecommendRequest,
)
from study_abroad_agent.services.profile_service import ProfileService
from study_abroad_agent.services.recommend_service import RecommendService

router = APIRouter(prefix="/profiles", tags=["用户画像"])


@router.get("", summary="列表查询用户 profiles")
def list_profiles(
    country: Optional[str] = None,
    education: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(collecting|recommended|finished)$"),
    keyword: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows = ProfileService.list_profiles(country, education, status, keyword, limit, offset)
    return {"code": 0, "data": rows, "message": "success", "total": len(rows)}


@router.get("/{conversation_id}", summary="按 conversation_id 查询单条 profile")
def get_profile(conversation_id: str):
    profile = ProfileService.get_by_conversation_id(conversation_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"code": 0, "data": profile, "message": "success"}


@router.get("/{conversation_id}/check", summary="画像完整性校验")
def check_profile(conversation_id: str):
    data = ProfileService.check_profile(conversation_id)
    return {"code": 0, "data": data, "message": "success"}


@router.post("", summary="创建 profile")
def create_profile(req: ProfileCreate):
    """根据 conversation_id 创建用户画像。已存在则返回 409。"""
    existing = ProfileService.get_by_conversation_id(req.conversation_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"conversation_id={req.conversation_id} 已存在")
    profile = ProfileService.create(req.model_dump(exclude_unset=True))
    return {"code": 0, "data": profile, "message": "success"}


@router.post("/upsert", summary="创建或增量更新 profile (兼容旧接口)")
def upsert_profile(req: ProfileCreate):
    """存在则增量更新，不存在则创建。"""
    profile = ProfileService.save_profile(
        req.conversation_id,
        req.model_dump(exclude={"conversation_id"}, exclude_unset=True),
    )
    check = ProfileService.check_profile(req.conversation_id)
    return {"code": 0, "data": {"profile": profile, **check}, "message": "success"}


@router.put("/{conversation_id}", summary="按 conversation_id 更新 profile")
def update_profile(conversation_id: str, req: ProfileUpdate):
    existing = ProfileService.get_by_conversation_id(conversation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="用户不存在")
    profile = ProfileService.update_by_id(
        existing["id"], req.model_dump(exclude_unset=True)
    )
    return {"code": 0, "data": profile, "message": "success"}


@router.delete("/{conversation_id}", summary="按 conversation_id 删除 profile")
def delete_profile(conversation_id: str):
    existing = ProfileService.get_by_conversation_id(conversation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="用户不存在")
    ProfileService.delete_by_conversation_id(conversation_id)
    return {"code": 0, "data": None, "message": "success"}


@router.post("/recommend", summary="课程推荐 (按 profile 画像)")
def recommend(req: RecommendRequest):
    result = RecommendService.recommend(req.conversation_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"code": 0, "data": result, "message": "success"}
