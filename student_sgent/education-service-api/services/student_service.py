"""
学生模块业务逻辑层
处理学生助手的核心业务：请假、心理预警、售后工单、DDL提醒、营销触达
"""
import hashlib
import json
import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import desc, text

from models.student_models import (
    Student,
    ConversationSession,
    ConversationMessage,
    LeaveApplication,
    FeedbackTicket,
    EmotionProfileSnapshot,
    RiskIntervention,
    DeadlineReminder,
    MarketingTouchLog,
    SystemConfig,
)
from schemas.student_schemas import (
    LeaveRequestCreate,
    LeaveRequestApprove,
    PsychRecordCreate,
    PsychAlertUpdate,
    FeedbackTicketCreate,
    FeedbackTicketUpdate,
)
from utils.config_manager import config_manager

logger = logging.getLogger(__name__)


class StudentService:
    """学生业务服务"""

    # ========== 学生信息 ==========

    @staticmethod
    def get_student(db: Session, student_id: int) -> Student | None:
        """查询学生基本信息（过滤软删除）"""
        return (
            db.query(Student)
            .filter(Student.id == student_id, Student.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def require_student(db: Session, student_id: int) -> Student:
        """校验学生存在，不存在抛 LookupError。student.py 和 tools.py 公用"""
        s = StudentService.get_student(db, student_id)
        if not s:
            raise LookupError(f"学生 {student_id} 不存在")
        return s

    @staticmethod
    def get_student_by_union_id(db: Session, union_id: str) -> Student | None:
        """按全局唯一ID查询"""
        return (
            db.query(Student)
            .filter(Student.union_id == union_id, Student.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def list_students(
        db: Session,
        keyword: str | None = None,
        status: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询学生列表（分页+搜索）"""
        q = db.query(Student).filter(Student.deleted_at.is_(None))
        if keyword:
            q = q.filter(Student.name.like(f"%{keyword}%"))
        if status is not None:
            q = q.filter(Student.status == status)
        total = q.count()
        items = q.order_by(Student.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def update_student(db: Session, student_id: int, **kwargs) -> Student | None:
        """更新学生信息。仅允许白名单字段，拒绝未知字段并警告"""
        student = StudentService.get_student(db, student_id)
        if not student:
            return None
        allowed = {"name", "grade", "target_country", "status", "crm_customer_id", "edu_system_id"}
        for k, v in kwargs.items():
            if k not in allowed:
                logger.warning(f"update_student 拒绝未知字段: {k}")
                continue
            if v is not None:
                setattr(student, k, v)
        student.updated_at = datetime.now()
        db.commit()
        db.refresh(student)
        return student

    # ========== 请假管理 ==========

    @staticmethod
    def create_leave(db: Session, req: LeaveRequestCreate) -> LeaveApplication:
        """
        提交请假申请（含幂等校验+日期校验）

        幂等键：student_id + start_date + end_date + leave_type
        """
        # 日期校验：end<start 由 Pydantic model_validator 拦截（422），此处仅校验天数上限
        if (req.end_date - req.start_date).days > config_manager.max_leave_days:
            raise ValueError(
                f"请假天数({(req.end_date - req.start_date).days}天)"
                f"超过上限({config_manager.max_leave_days}天)"
            )

        raw = f"{req.student_id}_{req.start_date}_{req.end_date}_{req.leave_type}"
        idempotent_key = hashlib.sha256(raw.encode()).hexdigest()[:64]

        # 幂等检查
        existing = (
            db.query(LeaveApplication)
            .filter(LeaveApplication.idempotent_key == idempotent_key)
            .first()
        )
        if existing:
            logger.info(f"幂等拦截: leave_id={existing.id}, key={idempotent_key}")
            return existing

        leave = LeaveApplication(
            student_id=req.student_id,
            idempotent_key=idempotent_key,
            leave_type=req.leave_type,
            start_date=req.start_date,
            end_date=req.end_date,
            reason=req.reason,
            attachment_url=req.attachment_url,
            status=0,  # 待审
        )
        db.add(leave)
        db.commit()
        db.refresh(leave)
        logger.info(f"请假已创建: id={leave.id}, student={req.student_id}")
        return leave

    @staticmethod
    def approve_leave(
        db: Session, request_id: int, req: LeaveRequestApprove
    ) -> LeaveApplication:
        """
        审批请假
        Raises:
            LookupError: 工单不存在
            ValueError: 工单已被处理过
        """
        leave = (
            db.query(LeaveApplication)
            .with_for_update()  # 悲观锁，防并发重复审批
            .filter(LeaveApplication.id == request_id, LeaveApplication.deleted_at.is_(None))
            .first()
        )
        if not leave:
            raise LookupError(f"请假工单 {request_id} 不存在")
        if leave.status != 0:
            raise ValueError(
                f"请假工单 {request_id} 已被处理(状态={leave.status})，无法重复审批"
            )

        leave.status = req.status
        leave.approver_id = req.approver_id
        leave.approved_at = datetime.now()
        leave.notify_status = 1  # 推送中
        db.commit()
        db.refresh(leave)
        logger.info(f"请假已审批: id={request_id}, status={req.status}")
        return leave

    @staticmethod
    def list_leaves(
        db: Session, student_id: int, status: int | None = None
    ) -> list[LeaveApplication]:
        """查询请假记录列表"""
        q = db.query(LeaveApplication).filter(
            LeaveApplication.student_id == student_id,
            LeaveApplication.deleted_at.is_(None),
        )
        if status is not None:
            q = q.filter(LeaveApplication.status == status)
        return q.order_by(desc(LeaveApplication.created_at)).all()

    # ========== 心理健康 ==========

    @staticmethod
    def record_emotion(db: Session, req: PsychRecordCreate) -> dict:
        """
        记录情绪交互，判断是否触发预警。
        整个过程只 commit 一次，保证快照+预警的原子性。

        返回:
            {"snapshot": EmotionProfileSnapshot, "alert": RiskIntervention | None}
        """
        # 写入/更新当日快照
        existing = (
            db.query(EmotionProfileSnapshot)
            .filter(
                EmotionProfileSnapshot.student_id == req.student_id,
                EmotionProfileSnapshot.snapshot_date == req.record_date,
            )
            .first()
        )

        if existing:
            old_count = existing.daily_chat_count or 0
            old_avg = existing.avg_emotion_score or Decimal("0")
            new_count = old_count + 1
            new_avg = (old_avg * old_count + req.emotion_score) / new_count
            existing.avg_emotion_score = new_avg.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if req.emotion_score < (existing.min_emotion_score or Decimal("0")):
                existing.min_emotion_score = req.emotion_score
            existing.daily_chat_count = new_count
            existing_tags = existing.peak_negative_tags or []
            if req.trigger_keywords:
                existing.peak_negative_tags = list(
                    dict.fromkeys(existing_tags + req.trigger_keywords)
                )
            existing.updated_at = datetime.now()
            # 此时不 commit，等预警写完后统一提交
            snapshot = existing
        else:
            snapshot = EmotionProfileSnapshot(
                student_id=req.student_id,
                snapshot_date=req.record_date,
                avg_emotion_score=req.emotion_score,
                min_emotion_score=req.emotion_score,
                peak_negative_tags=req.trigger_keywords or [],
                daily_chat_count=1,
            )
            db.add(snapshot)
            # 先 flush 获取 ID 但不 commit，保证后续预警写入在同一事务中
            db.flush()

        # 三级风险检测
        alert = None
        emotion_val = float(req.emotion_score)

        if emotion_val <= config_manager.emotion_threshold_red:
            risk_level, rule_id = 2, 1  # 红：高危，推送心理老师
            evidence = (
                f"情绪分{emotion_val}触发红色高危阈值{config_manager.emotion_threshold_red}，"
                f"标签：{req.trigger_keywords}"
            )
        elif emotion_val <= config_manager.emotion_threshold_yellow:
            risk_level, rule_id = 1, 2  # 黄：关注，推送班主任
            evidence = (
                f"情绪分{emotion_val}触发黄色关注阈值{config_manager.emotion_threshold_yellow}"
            )
        elif emotion_val <= config_manager.emotion_threshold_blue:
            risk_level, rule_id = 0, 3  # 蓝：轻度标记，仅记录不入工单
            evidence = (
                f"情绪分{emotion_val}触发蓝色轻度标记{config_manager.emotion_threshold_blue}"
            )
        else:
            risk_level, rule_id, evidence = None, None, None

        if risk_level is not None:
            today_start = datetime.combine(req.record_date, datetime.min.time())
            today_end = today_start + timedelta(days=1)
            existing_alert = (
                db.query(RiskIntervention)
                .with_for_update()  # 悲观锁，防并发重复插入
                .filter(
                    RiskIntervention.student_id == req.student_id,
                    RiskIntervention.risk_level == risk_level,
                    RiskIntervention.human_confirmed_status == 0,
                    RiskIntervention.created_at >= today_start,
                    RiskIntervention.created_at < today_end,
                )
                .first()
            )

            if existing_alert:
                try:
                    old_output = json.loads(existing_alert.ai_raw_output or "{}")
                except (json.JSONDecodeError, TypeError):
                    old_output = {}
                old_tags = old_output.get("tags", []) or []
                old_output["tags"] = list(
                    dict.fromkeys(old_tags + (req.trigger_keywords or []))
                )
                old_output["latest_emotion_score"] = emotion_val
                old_output.setdefault("snippets", []).append(
                    req.interaction_content[:200] if req.interaction_content else ""
                )
                existing_alert.ai_raw_output = json.dumps(old_output, ensure_ascii=False)
                existing_alert.trigger_evidence = (
                    f"{existing_alert.trigger_evidence or ''} | "
                    f"再次触发(分值{emotion_val})"
                )[:490]
                existing_alert.updated_at = datetime.now()
                alert = existing_alert
            else:
                alert = RiskIntervention(
                    student_id=req.student_id,
                    trigger_rule_id=rule_id,
                    risk_level=risk_level,
                    trigger_evidence=evidence,
                    ai_raw_output=json.dumps(
                        {
                            "emotion_score": emotion_val,
                            "tags": req.trigger_keywords,
                            "content_snippet": (
                                req.interaction_content[:200]
                                if req.interaction_content
                                else ""
                            ),
                        },
                        ensure_ascii=False,
                    ),
                    human_confirmed_status=0,
                )
                db.add(alert)

        # 统一提交：快照和预警要么一起成功，要么一起回滚
        db.commit()
        db.refresh(snapshot)
        if alert:
            db.refresh(alert)

        return {"snapshot": snapshot, "alert": alert}

    # ── 私有：预警查询通用分页模板（DRY） ──

    @staticmethod
    def _paginate_alerts(
        db: Session, query, page: int, page_size: int
    ) -> dict:
        total = query.count()
        items = (
            query.order_by(desc(RiskIntervention.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def list_psych_alerts(
        db: Session,
        student_id: int | None = None,
        risk_level: int | None = None,
        status: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询心理预警列表（分页+筛选）"""
        q = db.query(RiskIntervention)
        if student_id is not None:
            q = q.filter(RiskIntervention.student_id == student_id)
        if risk_level is not None:
            q = q.filter(RiskIntervention.risk_level == risk_level)
        if status is not None:
            q = q.filter(RiskIntervention.human_confirmed_status == status)
        return StudentService._paginate_alerts(db, q, page, page_size)

    @staticmethod
    def list_actionable_alerts(
        db: Session,
        student_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """仅查询需要人工处理的预警（黄+红，待确认）"""
        q = db.query(RiskIntervention).filter(
            RiskIntervention.human_confirmed_status == 0,
            RiskIntervention.risk_level >= 1,
        )
        if student_id is not None:
            q = q.filter(RiskIntervention.student_id == student_id)
        return StudentService._paginate_alerts(db, q, page, page_size)

    @staticmethod
    def handle_alert(
        db: Session, alert_id: int, req: PsychAlertUpdate
    ) -> RiskIntervention | None:
        """处理预警（人工确认/误报，悲观锁防并发覆盖）"""
        alert = (
            db.query(RiskIntervention)
            .with_for_update()
            .filter(RiskIntervention.id == alert_id)
            .first()
        )
        if not alert:
            return None
        alert.human_confirmed_status = req.status
        alert.handler_id = req.handler_id
        alert.handled_at = datetime.now()
        if req.follow_record:
            try:
                raw = alert.ai_raw_output or "{}"
                existing = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                existing = {}
            existing["follow_record"] = req.follow_record
            alert.ai_raw_output = json.dumps(existing, ensure_ascii=False)
        db.commit()
        db.refresh(alert)
        return alert

    # ========== 售后工单 ==========

    @staticmethod
    def create_feedback(db: Session, req: FeedbackTicketCreate) -> FeedbackTicket:
        """提交投诉/反馈工单"""
        ticket = FeedbackTicket(
            student_id=req.student_id,
            category=req.category,
            priority=req.priority,
            ai_summary=req.title,
            full_content=req.content,
            status=0,
            sla_deadline=datetime.now() + timedelta(hours=config_manager.sla_hours),
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket

    @staticmethod
    def handle_feedback(
        db: Session, ticket_id: int, req: FeedbackTicketUpdate
    ) -> FeedbackTicket | None:
        """处理工单"""
        ticket = (
            db.query(FeedbackTicket)
            .filter(FeedbackTicket.id == ticket_id, FeedbackTicket.deleted_at.is_(None))
            .first()
        )
        if not ticket:
            return None
        ticket.status = req.status
        ticket.handler_id = req.handler_id
        if req.status == 3:  # 已关闭
            ticket.closed_at = datetime.now()
        if req.solution:
            ticket.ai_summary = (
                f"{ticket.ai_summary or ''} | 解决方案: {req.solution}"
            )
        db.commit()
        db.refresh(ticket)
        return ticket

    @staticmethod
    def list_feedbacks(
        db: Session,
        student_id: int,
        status: int | None = None,
    ) -> list[FeedbackTicket]:
        """查询工单列表"""
        q = db.query(FeedbackTicket).filter(
            FeedbackTicket.student_id == student_id,
            FeedbackTicket.deleted_at.is_(None),
        )
        if status is not None:
            q = q.filter(FeedbackTicket.status == status)
        return q.order_by(desc(FeedbackTicket.created_at)).all()

    @staticmethod
    def list_overdue_tickets(db: Session) -> list[FeedbackTicket]:
        """查询所有超时未关闭的工单"""
        return (
            db.query(FeedbackTicket)
            .filter(
                FeedbackTicket.deleted_at.is_(None),
                FeedbackTicket.status.in_([0, 1, 2]),  # 未关闭
                FeedbackTicket.sla_deadline < datetime.now(),  # 已超时
            )
            .order_by(FeedbackTicket.sla_deadline.asc())
            .all()
        )

    # ========== DDL 提醒 ==========

    @staticmethod
    def list_deadlines(
        db: Session,
        student_id: int,
        upcoming_days: int = 7,
    ) -> list[DeadlineReminder]:
        """查询临近DDL"""
        now = datetime.now()
        deadline = now + timedelta(days=upcoming_days)
        return (
            db.query(DeadlineReminder)
            .filter(
                DeadlineReminder.student_id == student_id,
                DeadlineReminder.deadline_time.between(now, deadline),
                DeadlineReminder.push_status.in_([0, 1]),  # 待推送或已推送
            )
            .order_by(DeadlineReminder.deadline_time.asc())
            .all()
        )

    # ========== 会话管理 ==========

    @staticmethod
    def create_session(
        db: Session, student_id: int, agent_type: str = "student"
    ) -> ConversationSession:
        """创建新会话"""
        session_token = uuid.uuid4().hex
        sess = ConversationSession(
            student_id=student_id,
            session_token=session_token,
            agent_type=agent_type,
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return sess

    @staticmethod
    def log_message(
        db: Session,
        session_id: int,
        role: int,
        content: str,
        emotion_score: Decimal | None = None,
        cost_token: int | None = None,
        llm_model: str | None = None,
    ) -> ConversationMessage:
        """记录对话消息。session 不存在时抛出 LookupError。计数器原子更新防并发丢数"""
        session = (
            db.query(ConversationSession)
            .filter(
                ConversationSession.id == session_id,
                ConversationSession.deleted_at.is_(None),
            )
            .first()
        )
        if not session:
            raise LookupError(f"会话 {session_id} 不存在")

        msg = ConversationMessage(
            session_id=session_id,
            role=role,
            content=content,
            emotion_score=emotion_score,
            cost_token=cost_token,
            llm_model=llm_model,
        )
        db.add(msg)
        # 原子递增，避免 read-modify-write 竞态丢数
        db.execute(
            text("UPDATE conversation_sessions SET message_count = message_count + 1 WHERE id = :sid"),
            {"sid": session_id},
        )
        db.commit()
        db.refresh(msg)
        return msg

    # ========== 营销触达 ==========

    @staticmethod
    def log_marketing_touch(
        db: Session,
        student_id: int,
        program_id: str,
        text: str = "",
    ) -> MarketingTouchLog | None:
        """记录营销触达（含防骚扰冷却校验）"""
        # 检查冷却期内是否已触达过
        cooldown_start = datetime.now() - timedelta(
            days=config_manager.marketing_cooldown_days
        )
        recent = (
            db.query(MarketingTouchLog)
            .filter(
                MarketingTouchLog.student_id == student_id,
                MarketingTouchLog.program_id == program_id,
                MarketingTouchLog.created_at >= cooldown_start,
            )
            .first()
        )
        if recent:
            logger.info(
                f"营销触达冷却拦截: student={student_id}, "
                f"program={program_id}, last_touch={recent.created_at}"
            )
            return None

        log = MarketingTouchLog(
            student_id=student_id,
            program_id=program_id,
            ai_generated_text=text,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def list_marketing_touches(
        db: Session,
        student_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询营销触达记录（分页）"""
        q = db.query(MarketingTouchLog)
        if student_id is not None:
            q = q.filter(MarketingTouchLog.student_id == student_id)
        total = q.count()
        items = (
            q.order_by(desc(MarketingTouchLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # ========== 系统配置 ==========

    @staticmethod
    def load_system_configs(db: Session) -> dict[str, str]:
        """从数据库加载所有系统配置（用于热覆盖 config.py 默认值）"""
        configs = db.query(SystemConfig).all()
        return {c.config_key: c.config_value for c in configs if c.config_value}

    # ========== 会话管理 ==========

    @staticmethod
    def delete_session(db: Session, session_id: int) -> bool:
        """软删除会话"""
        session = (
            db.query(ConversationSession)
            .filter(ConversationSession.id == session_id, ConversationSession.deleted_at.is_(None))
            .first()
        )
        if not session:
            return False
        session.deleted_at = datetime.now()
        session.end_time = datetime.now()
        db.commit()
        return True


# 全局单例
student_service = StudentService()
