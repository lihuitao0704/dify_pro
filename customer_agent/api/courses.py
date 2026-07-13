"""课程 CRUD 路由"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from customer_agent.schemas import CourseCreate, CourseUpdate
from customer_agent.services.courses import CoursesService

router = APIRouter(prefix="/courses", tags=["课程"])


@router.get("", summary="列表查询课程")
def list_courses(
    category: Optional[str] = Query(None, pattern="^(留学方案|语言课程|背景提升)$"),
    country: Optional[str] = None,
    keyword: Optional[str] = None,
    is_active: Optional[int] = Query(None, ge=0, le=1),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = CoursesService.list_courses(category, country, keyword, is_active, limit, offset)
    total = CoursesService.count(category, country, keyword, is_active)
    return {"code": 0, "data": rows, "message": "success", "total": total}


@router.get("/{course_id}", summary="按 id 查询单个课程")
def get_course(course_id: int):
    course = CoursesService.get_by_id(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    return {"code": 0, "data": course, "message": "success"}


@router.post("", summary="创建课程")
def create_course(req: CourseCreate):
    new_id = CoursesService.create(req.model_dump(exclude_unset=True))
    course = CoursesService.get_by_id(new_id)
    return {"code": 0, "data": course, "message": "success"}


@router.put("/{course_id}", summary="按 id 更新课程")
def update_course(course_id: int, req: CourseUpdate):
    existing = CoursesService.get_by_id(course_id)
    if not existing:
        raise HTTPException(status_code=404, detail="课程不存在")
    CoursesService.update(course_id, req.model_dump(exclude_unset=True))
    return {"code": 0, "data": CoursesService.get_by_id(course_id), "message": "success"}


@router.delete("/{course_id}", summary="按 id 删除课程")
def delete_course(course_id: int):
    existing = CoursesService.get_by_id(course_id)
    if not existing:
        raise HTTPException(status_code=404, detail="课程不存在")
    CoursesService.delete(course_id)
    return {"code": 0, "data": None, "message": "success"}
