"""用户画像 CRUD 路由 + 推荐"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from customer_agent.schemas import (
    ProfileCreate, ProfileUpdate, RecommendRequest,
)
from customer_agent.services.profiles import ProfileService
from customer_agent.services.recommend import RecommendService

router = APIRouter(prefix="/profiles", tags=["用户画像"])


@router.get("", summary="多字段筛选查询用户 profiles")
def list_profiles(
    country: Optional[str] = None,
    education: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(collecting|recommended|finished)$"),
    keyword: Optional[str] = None,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    wechat: Optional[str] = None,
    target_country: Optional[str] = None,
    target_major: Optional[str] = None,
    major: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows = ProfileService.list_profiles(
        country=country, education=education, status=status, keyword=keyword,
        name=name, phone=phone, email=email, wechat=wechat,
        target_country=target_country, target_major=target_major, major=major,
        limit=limit, offset=offset,
    )
    return {"code": 0, "data": rows, "message": "success", "total": len(rows)}


@router.get("/by-id/{profile_id}", summary="按 id 查询单条 profile")
def get_profile_by_id(profile_id: int):
    profile = ProfileService.get_by_id(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"code": 0, "data": profile, "message": "success"}


@router.get("/by-conversation/{conversation_id}", summary="按 conversation_id 查询 profile 列表")
def get_profile_by_conversation(conversation_id: str):
    profiles = ProfileService.get_by_conversation_id(conversation_id)
    if not profiles:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"code": 0, "data": profiles, "message": "success", "total": len(profiles)}


@router.get("/by-conversation/{conversation_id}/check", summary="画像完整性校验")
def check_profile(conversation_id: str):
    data = ProfileService.check_profile(conversation_id)
    return {"code": 0, "data": data, "message": "success"}


@router.post("", summary="创建 profile")
def create_profile(req: ProfileCreate):
    profile = ProfileService.create(req.model_dump(exclude_unset=True))
    return {"code": 0, "data": profile, "message": "success"}


@router.post("/upsert", summary="创建或增量更新 profile (兼容旧接口)")
def upsert_profile(req: ProfileCreate):
    profile = ProfileService.save_profile(
        req.conversation_id,
        req.model_dump(exclude={"conversation_id"}, exclude_unset=True),
    )
    check = ProfileService.check_profile(req.conversation_id)
    return {"code": 0, "data": {"profile": profile, **check}, "message": "success"}


@router.put("/by-id/{profile_id}", summary="按 id 更新 profile")
def update_profile_by_id(profile_id: int, req: ProfileUpdate):
    existing = ProfileService.get_by_id(profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="用户不存在")
    profile = ProfileService.update_by_id(profile_id, req.model_dump(exclude_unset=True))
    return {"code": 0, "data": profile, "message": "success"}


@router.delete("/by-id/{profile_id}", summary="按 id 删除 profile")
def delete_profile_by_id(profile_id: int):
    existing = ProfileService.get_by_id(profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="用户不存在")
    ProfileService.delete_by_id(profile_id)
    return {"code": 0, "data": None, "message": "success"}


@router.delete("/by-conversation/{conversation_id}", summary="按 conversation_id 删除所有匹配 profile")
def delete_profile_by_conversation(conversation_id: str):
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
