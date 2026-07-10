"""
Dify 工具 API 路由
供 Dify 工作流中的 HTTP 请求节点调用

设计原则：
- POST 接口使用 JSON Body（符合 REST 规范，支持中文长文本）
- GET 接口使用 Query String
- 接口返回结构化的纯数据，不做自然语言包装（由 Dify LLM 负责生成回复）
- 接口幂等，支持 Dify 重试机制
"""
import logging
import re
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from utils.database import get_db
from services.student_service import student_service
from schemas.student_schemas import (
    LeaveRequestCreate,
    PsychRecordCreate,
    FeedbackTicketCreate,
    DifyInitSession,
    DifyLeaveSubmit,
    DifyEmotionRecord,
    DifyFeedbackSubmit,
    DifyTouchLog,
    DifyMessageLog,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dify/tools", tags=["Dify工具API"])


# ========== 安全取值辅助 ==========

_LEAVE_TYPE_MAP = ["", "病假", "事假", "其他"]
_STATUS_MAP = ["待审", "已通过", "已驳回", "已撤销"]
_EVENT_TYPE_MAP = ["", "论文截止", "考试时间", "选课开始"]
_PUSH_STATUS_MAP = ["待推送", "已推送", "已读"]
_RISK_LEVEL_MAP = ["蓝色标记", "黄色关注", "红色高危"]
_CONFIRM_STATUS_MAP = ["待确认", "已确认", "误报"]
_CATEGORY_MAP = ["", "签证", "文书", "费用", "生活服务", "其他"]
_STUDENT_STATUS_MAP = ["正常", "停用", "流失"]


def _safe_get(arr: list[str], index: int, default: str = "未知") -> str:
    """安全数组取值，防止 IndexError"""
    return arr[index] if 0 <= index < len(arr) else default


def _split_keywords(raw: str | None) -> list[str]:
    """按中英文逗号拆分关键词，安全处理 None"""
    if not raw:
        return []
    return [k.strip() for k in re.split(r"[,，]", raw) if k.strip()]


def _check_student_tool(db: Session, student_id: int) -> dict | None:
    """tools.py 统一学生校验：有效返回 None，无效返回错误 dict。
    调用方模式：err = _check_student_tool(...); if err is not None: return err
    """
    if not student_service.get_student(db, student_id):
        return {"success": False, "error": f"学生 {student_id} 不存在"}
    return None


# ============================================================
# 学生信息 — Dify 查询学生画像
# ============================================================

@router.get("/student-profile")
def dify_get_student(
    student_id: int = Query(..., description="学生ID"),
    db: Session = Depends(get_db),
):
    """
    Dify调用：查询学生基本信息
    返回结构化JSON，Dify的LLM节点用此数据生成自然语言回复
    """
    student = student_service.get_student(db, student_id)
    if not student:
        return {"found": False, "error": f"学生 {student_id} 不存在"}
    return {
        "found": True,
        "student": {
            "id": student.id,
            "name": student.name,
            "grade": f"年级{student.grade}" if student.grade else "未知",
            "target_country": student.target_country or "未设置",
            "status": _safe_get(_STUDENT_STATUS_MAP, student.status),
        },
    }


# ============================================================
# 请假 — Dify 提交请假申请（JSON Body）
# ============================================================

@router.post("/submit-leave")
def dify_submit_leave(
    req: DifyLeaveSubmit,
    db: Session = Depends(get_db),
):
    """
    Dify调用：提交请假申请
    返回{success, leave_id, status}
    """
    # 校验学生存在
    err = _check_student_tool(db, req.student_id)
    if err: return err
    try:
        leave_req = LeaveRequestCreate(
            student_id=req.student_id,
            leave_type=req.leave_type,
            start_date=date.fromisoformat(req.start_date),
            end_date=date.fromisoformat(req.end_date),
            reason=req.reason,
        )
        leave = student_service.create_leave(db, leave_req)
        return {
            "success": True,
            "leave_id": leave.id,
            "status": "已提交，等待审批",
            "status_code": leave.status,
        }
    except ValueError as e:
        logger.warning(f"请假参数错误: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"提交请假失败: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# 请假 — Dify 查询请假记录
# ============================================================

@router.get("/leave-records")
def dify_list_leaves(
    student_id: int = Query(..., description="学生ID"),
    status: int | None = Query(None, description="0-待审 1-通过 2-驳回 3-撤销"),
    db: Session = Depends(get_db),
):
    """
    Dify调用：查询请假记录
    返回结构化列表
    """
    leaves = student_service.list_leaves(db, student_id, status)
    return {
        "count": len(leaves),
        "items": [
            {
                "id": l.id,
                "leave_type": _safe_get(_LEAVE_TYPE_MAP, l.leave_type),
                "start_date": str(l.start_date),
                "end_date": str(l.end_date),
                "reason": l.reason or "",
                "status": _safe_get(_STATUS_MAP, l.status),
                "status_code": l.status,
                "approved_at": str(l.approved_at) if l.approved_at else None,
            }
            for l in leaves
        ],
    }


# ============================================================
# 心理健康 — Dify 记录情绪（JSON Body）
# ============================================================

@router.post("/record-emotion")
def dify_record_emotion(
    req: DifyEmotionRecord,
    db: Session = Depends(get_db),
):
    """
    Dify调用：记录情绪交互

    Dify工作流中，LLM节点输出emotion_score后，由HTTP节点调用此接口。
    接口内部判断阈值，达到红线自动创建预警。
    支持中英文逗号分隔的 trigger_keywords。
    """
    err = _check_student_tool(db, req.student_id)
    if err: return err
    try:
        keywords = _split_keywords(req.trigger_keywords)
        rec_date = (
            date.fromisoformat(req.record_date)
            if req.record_date
            else date.today()
        )

        psych_req = PsychRecordCreate(
            student_id=req.student_id,
            emotion_tag=req.emotion_tag or None,
            emotion_score=Decimal(str(round(req.emotion_score, 2))),
            trigger_keywords=keywords or None,
            interaction_content=req.interaction_content or None,
            record_date=rec_date,
        )
        result = student_service.record_emotion(db, psych_req)
        has_alert = result["alert"] is not None
        return {
            "success": True,
            "alert_triggered": has_alert,
            "risk_level": result["alert"].risk_level if has_alert else None,
            "risk_level_text": (
                _safe_get(_RISK_LEVEL_MAP, result["alert"].risk_level)
                if has_alert
                else "正常"
            ),
            "avg_emotion_today": float(result["snapshot"].avg_emotion_score),
            "chat_count_today": result["snapshot"].daily_chat_count,
        }
    except ValueError as e:
        logger.warning(f"情绪记录参数错误: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"记录情绪失败: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# 心理健康 — Dify 查询预警
# ============================================================

@router.get("/psych-alerts")
def dify_list_psych_alerts(
    student_id: int | None = Query(None, description="按学生筛选"),
    risk_level: int | None = Query(None, description="1-黄 2-红"),
    status: int | None = Query(None, description="0-待确认 1-已确认 2-误报"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """
    Dify调用：查询心理预警列表（分页）
    """
    result = student_service.list_psych_alerts(
        db,
        student_id=student_id,
        risk_level=risk_level,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "items": [
            {
                "id": a.id,
                "student_id": a.student_id,
                "risk_level": _safe_get(_RISK_LEVEL_MAP, a.risk_level),
                "risk_level_code": a.risk_level,
                "trigger_evidence": a.trigger_evidence or "",
                "status": _safe_get(_CONFIRM_STATUS_MAP, a.human_confirmed_status),
                "status_code": a.human_confirmed_status,
                "created_at": str(a.created_at),
            }
            for a in result["items"]
        ],
    }


# ============================================================
# 售后工单 — Dify 提交投诉（JSON Body）
# ============================================================

@router.post("/submit-feedback")
def dify_submit_feedback(
    req: DifyFeedbackSubmit,
    db: Session = Depends(get_db),
):
    """
    Dify调用：提交投诉/反馈工单
    """
    err = _check_student_tool(db, req.student_id)
    if err: return err
    try:
        ticket_req = FeedbackTicketCreate(
            student_id=req.student_id,
            category=req.category,
            title=req.title or None,
            content=req.content,
        )
        ticket = student_service.create_feedback(db, ticket_req)
        return {
            "success": True,
            "ticket_id": ticket.id,
            "status": "已创建",
            "status_code": ticket.status,
            "sla_deadline": str(ticket.sla_deadline),
            "category_text": _safe_get(_CATEGORY_MAP, req.category),
        }
    except Exception as e:
        logger.error(f"提交工单失败: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# DDL查询 — Dify 查询临近DDL
# ============================================================

@router.get("/upcoming-deadlines")
def dify_list_deadlines(
    student_id: int = Query(..., description="学生ID"),
    upcoming_days: int = Query(7, description="未来天数"),
    db: Session = Depends(get_db),
):
    """
    Dify调用：查询临近DDL
    """
    deadlines = student_service.list_deadlines(db, student_id, upcoming_days)
    return {
        "count": len(deadlines),
        "items": [
            {
                "id": d.id,
                "event_type": _safe_get(_EVENT_TYPE_MAP, d.event_type),
                "event_name": d.event_name,
                "deadline_time": str(d.deadline_time),
                "push_status": _safe_get(_PUSH_STATUS_MAP, d.push_status),
                "days_left": (
                    (d.deadline_time.date() - date.today()).days
                    if d.deadline_time
                    else None
                ),
            }
            for d in deadlines
        ],
    }


# ============================================================
# 会话 — Dify 对话日志（JSON Body）
# ============================================================

@router.post("/log-message")
def dify_log_message(
    req: DifyMessageLog,
    db: Session = Depends(get_db),
):
    """
    Dify调用：记录对话消息（审计+成本核算）
    Dify工作流每个节点完成后调用此接口记录
    """
    try:
        msg = student_service.log_message(
            db,
            session_id=req.session_id,
            role=req.role,
            content=req.content,
            emotion_score=(
                Decimal(str(round(req.emotion_score, 2)))
                if req.emotion_score is not None
                else None
            ),
            cost_token=req.cost_token,
            llm_model=req.llm_model,
        )
        return {"success": True, "message_id": msg.id}
    except LookupError as e:
        logger.warning(f"会话不存在: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"记录消息失败: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# 会话初始化 — Dify 工作流开始节点调用
# ============================================================

@router.post("/init-session")
def dify_init_session(
    req: DifyInitSession,
    db: Session = Depends(get_db),
):
    """
    Dify调用：开始节点对接，创建会话并返回 session_id（JSON Body）

    Dify HTTP节点配置：
      POST {{FASTAPI_BASE_URL}}/api/v1/dify/tools/init-session
      Body: {"student_id": {{start.student_id}}, "agent_type": "student"}
      返回 {"success":true, "session_id":1, "session_token":"xxx"}
    """
    err = _check_student_tool(db, req.student_id)
    if err: return err
    sess = student_service.create_session(db, req.student_id, req.agent_type)
    return {
        "success": True,
        "session_id": sess.id,
        "session_token": sess.session_token,
    }


# ============================================================
# 申请进度查询 — Dify 调用（外部教务系统桥接说明）
# ============================================================

@router.get("/progress-lookup")
def dify_progress_lookup(
    student_id: int = Query(..., description="学生ID"),
    db: Session = Depends(get_db),
):
    """
    Dify调用：查询学生申请进度

    注：原始进度数据在外部教务系统，此接口返回学生基本信息和对接状态。
    Dify LLM 据此生成"当前查询方式说明"。
    实际对接教务系统后替换此实现。
    """
    student = student_service.get_student(db, student_id)
    if not student:
        return {"found": False, "error": f"学生 {student_id} 不存在"}
    return {
        "found": True,
        "student": {"id": student.id, "name": student.name, "grade": student.grade},
        "application_stages": [
            "document_prep", "submitted", "under_review",
            "offer_received", "visa_processing", "enrolled",
        ],
        "note": "详细进度请通过 edu_system_id 查询教务系统",
        "edu_system_id": student.edu_system_id,
    }


# ============================================================
# 增值触达 — Dify 调用（记录营销推荐）
# ============================================================

@router.post("/log-touch")
def dify_log_touch(
    req: DifyTouchLog,
    db: Session = Depends(get_db),
):
    """
    Dify调用：记录增值营销触达（JSON Body，支持长文本）

    Dify HTTP节点配置：
      POST {{FASTAPI_BASE_URL}}/api/v1/dify/tools/log-touch
      Body: {"student_id": {{sid}}, "program_id": "bgts", "text": "..."}
    """
    err = _check_student_tool(db, req.student_id)
    if err: return err
    result = student_service.log_marketing_touch(db, req.student_id, req.program_id, req.text)
    if result is None:
        return {"success": False, "error": "冷却期内，已拦截"}
    return {"success": True, "touch_id": result.id}


# ============================================================
# 海外生活 — Dify 知识库提示（纯LLM场景，FastAPI提供学生上下文）
# ============================================================

@router.get("/overseas-context")
def dify_overseas_context(
    student_id: int = Query(..., description="学生ID"),
    db: Session = Depends(get_db),
):
    """
    Dify调用：获取学生留学信息，供海外生活LLM节点使用

    Dify拿到学生的基础信息后，结合知识库RAG回答海外生活问题。
    """
    student = student_service.get_student(db, student_id)
    if not student:
        return {"found": False, "error": f"学生 {student_id} 不存在"}
    return {
        "found": True,
        "country": student.target_country or "未设置",
        "name": student.name,
        "grade": student.grade,
        "tip": "请基于学生留学国家，从知识库检索当地生活指南",
    }
