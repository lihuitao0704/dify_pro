"""
会话状态管理（重构版）
管理每个 session 的对话历史、意图锁定、多轮业务流程状态。

核心抽象 BusinessState:
  - current_intent          : 当前锁定的意图（None = 空闲，可重新分类）
  - course_recommendation_state : 课程推荐多轮参数收集状态
  - activity_register_state     : 活动报名多轮信息收集状态
  - last_activity_results       : 最近一次活动查询结果缓存（供报名选序号）

支持 has_active_flow() 统一判断是否存在未完成业务，
  供 agent.py 主流程前置检查，实现 flow-first 架构。
"""

import copy
import hashlib
import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field


# ============================================================
# 课程推荐流程参数（原 RecommendationState，改名对齐 PRD）
# ============================================================
@dataclass
class CourseRecommendationState:
    """课程推荐的多轮参数收集状态"""
    # ── 必填三件套（推荐 API 最低要求）──
    education: str = ""            # 学历（必须）
    target_major: str = ""         # 意向专业（必须）
    language_score: str = ""       # 语言成绩（必须）
    # ── 画像补充字段（enrichment 阶段逐步追问，补齐 user_profiles）──
    country: str = ""              # 意向国家
    gpa: str = ""                  # GPA
    budget: str = ""               # 预算
    intake: str = ""               # 入学时间
    work_experience: str = ""      # 工作经验
    age: str = ""                  # 年龄
    wechat: str = ""               # 微信
    # ── 追问追踪 ──
    asked_fields: list = field(default_factory=list)  # 已追问过的字段（含必填+补充）
    phase: str = "required"        # required → enrichment → recommend
    # ── 推荐后转化收集 ──
    name: str = ""                 # 收集姓名（推荐后转化用）
    phone: str = ""                # 收集手机号

    # 所有需要逐步追问的字段（必填优先，随后是补充）
    _ALL_FIELDS = [
        "education", "target_major", "language_score",
        "country", "gpa", "budget", "intake", "work_experience",
        "age", "wechat",
    ]
    # 其中前 3 个是必填（API 硬性要求），其余是补充
    _REQUIRED_FIELDS = ["education", "target_major", "language_score"]

    def is_ready(self) -> bool:
        """三个核心参数是否齐全（才允许调推荐 API）"""
        return bool(self.education and self.target_major and self.language_score)

    def has_all_fields(self) -> bool:
        """所有字段是否都已收集（必填 + 补充）"""
        return all(getattr(self, f) for f in self._ALL_FIELDS)

    def next_missing_field(self) -> Optional[str]:
        """返回下一个需要追问的字段。
        顺序：必填三件套 → 画像补充字段（国家/GPA/预算/入学/工作/年龄/微信）→ None。
        全部补齐后返回 None，主流程才会调推荐 API。
        """
        for f in self._ALL_FIELDS:
            if not getattr(self, f):
                if f not in self.asked_fields:
                    self.asked_fields.append(f)
                return f
        return None

    def fill_from_message(self, msg: str):
        """从用户消息提取推荐参数到自身（正则 + 关键词）"""
        # 学历
        if not self.education:
            for pat, val in [
                (r"(高中|职高|中专)", "高中"),
                (r"(本科|大学|在读本科|本科学历)", "本科"),
                (r"(硕士|研究生|在读硕士|硕士学历)", "硕士"),
                (r"(博士|在读博士)", "博士"),
                (r"(大专|专科)", "大专"),
            ]:
                if re.search(pat, msg):
                    self.education = val
                    break

        # 国家
        if not self.country:
            if "德国" in msg or "german" in msg.lower():
                self.country = "德国"
            elif "新加坡" in msg or "singapore" in msg.lower():
                self.country = "新加坡"

        # GPA
        if not self.gpa:
            m = re.search(r"(?:gpa|绩点|均分|成绩)[^\d]*(\d+(?:\.\d+)?)", msg, re.I)
            if m:
                self.gpa = m.group(1)

        # 语言成绩
        if not self.language_score:
            m = re.search(r"(?:ielts|雅思)[^\d]*(\d+(?:\.\d+)?)", msg, re.I)
            if m:
                self.language_score = f"IELTS {m.group(1)}"
            if not self.language_score:
                m = re.search(r"(?:toefl|托福)[^\d]*(\d+)", msg, re.I)
                if m:
                    self.language_score = f"TOEFL {m.group(1)}"
            if not self.language_score and "德语" in msg:
                m2 = re.search(r"德语\s*([a-zA-Z0-9]+)", msg)
                self.language_score = f"德语{m2.group(1)}" if m2 else "有德语基础"
            if not self.language_score and re.search(r"(没有.*成绩|暂无.*成绩|还没考|没考过)", msg):
                self.language_score = "暂无"

        # 专业/方向
        if not self.target_major:
            m = re.search(r"(?:想读|申请|专业|方向)[是为]?[：:\s]*([一-龥A-Za-z&]{2,20})", msg)
            if m:
                self.target_major = m.group(1)
        if not self.target_major:
            for kw in ["计算机", "商科", "机械", "电子", "医学", "法学", "艺术",
                       "金融", "会计", "管理", "工程", "生物", "化学", "物理",
                       "数学", "传媒", "教育", "心理"]:
                if kw in msg:
                    self.target_major = kw
                    break

        # 预算
        if not self.budget:
            m = re.search(r"(?:预算|费用|学费).*?(\d+)万", msg)
            if m:
                self.budget = f"{m.group(1)}万"

        # 入学时间
        if not self.intake:
            m = re.search(r"(20\d{2})年?(?:秋季|春季|夏季|冬季|入学)?", msg)
            if m:
                self.intake = m.group(0)

        # 工作经验（支持 "工作2年"、"2年工作经验"、"1年实习" 等表述）
        if not self.work_experience:
            m = re.search(r"(\d+)\s*年.*?(工作|实习)|(工作|实习).*?(\d+)\s*年", msg)
            if m:
                # 取匹配到的数字组（两种顺序必有一组非 None）
                num = m.group(1) or m.group(4)
                kind = m.group(2) or m.group(3)
                self.work_experience = f"{num}年{kind}"

        # 年龄
        if not self.age:
            m = re.search(r"(?:年龄|年纪|岁数)[^\d]*(\d{1,3})", msg, re.I)
            if m:
                self.age = m.group(1)
            elif re.search(r"(\d{1,3})\s*岁", msg):
                self.age = re.search(r"(\d{1,3})\s*岁", msg).group(1)

        # 微信（支持 "微信xxx"、"wechat:xxx"、"wx-xxx" 等格式）
        if not self.wechat:
            m = re.search(r"(?:微信|wechat|wx)[：:\s_-]*([a-zA-Z0-9_-]{2,20})", msg, re.I)
            if m:
                self.wechat = m.group(1)

    def diff_new_fields(self, msg: str) -> dict:
        """
        执行 fill_from_message 前后对比，返回这一步新提取的字段。
        只返回"之前为空、现在非空"的字段。 router.py 据此判断是否有新信息写库。
        例：用户说"我的专业是计算机" → {"target_major": "计算机"}
        """
        _FIELDS = self._ALL_FIELDS  # 全量字段统一 diff
        before = {f: getattr(self, f) for f in _FIELDS}
        self.fill_from_message(msg)
        new_fields = {}
        for f in _FIELDS:
            after_val = getattr(self, f)
            if after_val and not before[f]:
                new_fields[f] = after_val
        return new_fields

    def get_question(self, field: str) -> str:
        """获取对应字段的追问话术（覆盖全部字段）"""
        questions = {
            "education":       "请问您目前是什么学历呢？（高中/本科/硕士/博士）",
            "target_major":    "请问您希望申请什么专业方向呢？（如计算机、商科、机械等）",
            "language_score":  "目前有雅思、托福或德语成绩吗？大概多少分呢？",
            "country":         "您有倾向的留学国家吗？我们主要做德国和新加坡～",
            "gpa":             "方便说一下您的GPA或均分吗？（例如 3.2/4.0 或 82/100）",
            "budget":          "您的留学预算大概在什么范围？（例如 15 万/年、总预算 30 万）",
            "intake":          "计划什么时间入学呢？（如 2027 秋季）",
            "work_experience": "有没有相关的工作或实习经验？",
            "age":             "方便告诉我您的年龄吗？（用于匹配学制和签证方案）",
            "wechat":          "可以留一个微信吗？后续顾问可以直接加您同步方案～",
        }
        q = questions.get(field, f"请补充一下：{field}")
        return q + "\n（边聊边记住你的信息哦～）"


# ============================================================
# 🆕 活动报名流程参数
# ============================================================
@dataclass
class ActivityRegisterState:
    """活动报名的多轮信息收集状态"""
    activity_id: str = ""          # 活动ID（来自查询结果映射）
    activity_name: str = ""        # 活动名称（用户直接说或从结果映射）
    activity_index: int = -1       # 用户选"第N个"对应的序号
    name: str = ""                 # 报名人姓名（必填）
    phone: str = ""                # 报名人手机号（必填）
    asked_fields: list = field(default_factory=list)  # 已追问过的字段
    last_query_results: list = field(default_factory=list)  # 缓存最近查询结果
    # 🆕 活动详情（resolve_index/resolve_name 时从缓存拷贝，用于报名成功页展示）
    event_time: str = ""           # 活动时间
    location: str = ""             # 活动地点
    speaker: str = ""              # 主讲人
    kind: str = ""                 # 类型: lecture / activity

    def is_ready(self) -> bool:
        """姓名 + 手机号 + 活动(三选一) 齐全才算 ready"""
        has_activity = bool(self.activity_id or self.activity_name or self.activity_index >= 0)
        return bool(self.name and self.phone and has_activity)

    def next_missing_field(self) -> Optional[str]:
        """按优先级返回下一个缺失字段"""
        # 先确定活动（activity_id/name/index 都算确定了活动）
        has_activity = bool(self.activity_id or self.activity_name or self.activity_index >= 0)
        if not has_activity:
            if "activity_select" not in self.asked_fields:
                self.asked_fields.append("activity_select")
            return "activity_select"
        # 再收集姓名
        if not self.name:
            if "name" not in self.asked_fields:
                self.asked_fields.append("name")
            return "name"
        # 再收集手机
        if not self.phone:
            if "phone" not in self.asked_fields:
                self.asked_fields.append("phone")
            return "phone"
        return None

    def diff_new_person(self, msg: str) -> dict:
        """执行 fill_from_message 前后对比，返回这一步新提取的 {name, phone}。"""
        before_name, before_phone = self.name, self.phone
        self.fill_from_message(msg)
        new = {}
        if self.name and not before_name:
            new["name"] = self.name
        if self.phone and not before_phone:
            new["phone"] = self.phone
        return new

    def diff_new_activity(self, msg: str) -> dict | None:
        """
        执行 resolve_index + resolve_name 前后对比，返回新解析的活动信息。
        返回 {"activity_id": str, "activity_name": str} 或 None。
        """
        before = (self.activity_id, self.activity_name, self.activity_index)
        self.resolve_index(msg)
        if not (self.activity_id or self.activity_name):
            self.resolve_name(msg)
        after = (self.activity_id, self.activity_name, self.activity_index)
        if after == before:
            return None
        if not (self.activity_id or self.activity_name):
            return None
        return {"activity_id": self.activity_id, "activity_name": self.activity_name}

    def fill_from_message(self, msg: str):
        """从用户消息提取姓名和手机号"""
        # 姓名
        if not self.name:
            m = re.search(r"(?:我叫|姓名|名字|叫|名为)[：:\s]*([一-龥]{2,4})", msg)
            if m:
                self.name = m.group(1)
        # 直接出现 2-4 字纯中文且前面没识别到，当作姓名
        if not self.name:
            # 排除手机号旁的内容，找独立人名
            m = re.search(r"(?:^|[\s,，。！!]+)([一-龥]{2,4})(?:[\s,，。！!]+|$)", msg)
            if m and not re.match(r"^[\d]+$", m.group(1)):
                # 进一步过滤：不含常见非人名关键词
                non_name = ["报名", "活动", "讲座", "手机", "联系", "预约", "参加", "德国",
                            "新加坡", "留学", "雅思", "托福", "成绩", "本科", "硕士"]
                if m.group(1) not in non_name:
                    self.name = m.group(1)

        # 手机号
        if not self.phone:
            m = re.search(r"1[3-9]\d{9}", msg)
            if m:
                self.phone = m.group(0)

    def resolve_index(self, msg: str) -> bool:
        """解析用户选择 '第一个/第N个/1.' 等，从 last_query_results 映射到具体活动"""
        # 中文数字映射
        cn_num = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

        idx = -1
        # 匹配 "第N个"
        m = re.search(r"第([一二两三四五六七八九十\d]+)个", msg)
        if m:
            num_str = m.group(1)
            idx = cn_num.get(num_str, int(num_str) if num_str.isdigit() else -1)
        else:
            # 匹配独立序号如 "1." "1、" "选1" "1号"
            m = re.search(r"(?:^|[^\d])([1-9])(?:[.、号]?\s|$|[^\d])", msg)
            if m:
                idx = int(m.group(1))
            elif msg.strip() in ("1", "2", "3", "4", "5"):
                idx = int(msg.strip())

        if idx > 0 and self.last_query_results:
            # 1-indexed → 0-indexed
            i = idx - 1
            if 0 <= i < len(self.last_query_results):
                item = self.last_query_results[i]
                self.activity_index = i
                self.activity_id = str(item.get("id", item.get("activity_id", "")))
                self.activity_name = item.get("name", item.get("activity_name",
                                                             item.get("title", "")))
                # 同步活动详情，供报名成功页展示
                self._fill_event_detail(item)
                return True
        return False

    def resolve_name(self, msg: str) -> bool:
        """解析用户说的活动名称（匹配 last_query_results 中文本）"""
        if not self.last_query_results:
            return False
        for i, item in enumerate(self.last_query_results):
            name = item.get("name", item.get("activity_name", item.get("title", "")))
            if name and name in msg:
                self.activity_index = i
                self.activity_id = str(item.get("id", item.get("activity_id", "")))
                self.activity_name = name
                # 同步活动详情，供报名成功页展示
                self._fill_event_detail(item)
                return True
        return False

    def _fill_event_detail(self, item: dict):
        """从缓存结果 item 拷贝活动详情字段。"""
        self.event_time = str(item.get("event_time", ""))
        self.location = item.get("location", "")
        self.speaker = item.get("speaker", "")
        self.kind = item.get("kind", "activity")

    def get_question(self, field: str) -> str:
        """获取对应字段的追问话术"""
        questions = {
            "activity_select": "想报名哪条活动呢？告诉我序号（如'第一个'）或活动名就行～",
            "name":            "好的！请问怎么称呼您呢？",
            "phone":           f"还需要一个联系电话即可完成报名，直接发给我就行～",
        }
        return questions.get(field, f"请补充一下：{field}")


# ============================================================
# 会话状态（统一 BusinessState）
# ============================================================
@dataclass
class SessionState:
    """单个会话的完整状态（BusinessState）"""
    session_id: str
    history: list = field(default_factory=list)     # [{role, content, ts}]
    current_intent: Optional[str] = None            # 当前锁定的意图
    last_intents: list = field(default_factory=list)  # 最近一次分类结果
    last_topic: str = ""                            # 最近一次业务话题
    followup_rounds: int = 0                        # 当前流程追问轮次

    # 子业务流程状态
    course_recommendation_state: Optional[CourseRecommendationState] = None
    activity_register_state: Optional[ActivityRegisterState] = None

    # 缓存最近查询结果（供报名选序号用）
    last_activity_results: list = field(default_factory=list)

    # 🆕 持久化相关状态
    conversation_id: str = None                     # 派生或外部传入的画像 ID
    _saved_profile_fields: set = field(default_factory=set)  # 已写入库的字段集合

    # 🆕 报名场景路由标记："activity" | "lecture" | None（由 _enter_activity_register_* 注入）
    register_kind: Optional[str] = None

    # 🆕 会话级画像累加器（跨流程存活，unlock不清空）
    # 收集用户整轮对话中透露的所有个人信息，统一增量写库
    profile_slots: dict = field(default_factory=dict)
    _dirty_profile_fields: set = field(default_factory=set)  # 本轮待写入的字段

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        """conversation_id 为空时按 session_id 确定性派生。"""
        if not self.conversation_id:
            self.conversation_id = derive_conversation_id(self.session_id)

    # ── 兼容旧名（router.py 旧代码可能用 sess.recommendation）──
    @property
    def recommendation(self) -> Optional[CourseRecommendationState]:
        return self.course_recommendation_state

    @recommendation.setter
    def recommendation(self, value):
        self.course_recommendation_state = value

    # ── 统一状态操作 ──────────────────────────────────────────
    def has_active_flow(self) -> bool:
        """是否存在未完成的多轮业务流程"""
        if self.current_intent == "course_recommendation":
            return self.course_recommendation_state is not None
        if self.current_intent == "activity_register":
            return self.activity_register_state is not None
        return False

    def lock_intent(self, intent: str):
        """锁定当前意图，阻止重新分类，并初始化对应子状态"""
        self.current_intent = intent
        if intent == "course_recommendation" and self.course_recommendation_state is None:
            self.course_recommendation_state = CourseRecommendationState()
        elif intent == "activity_register" and self.activity_register_state is None:
            self.activity_register_state = ActivityRegisterState()

    def unlock_intent(self):
        """解锁意图，清空所有子状态，恢复正常分类"""
        self.current_intent = None
        self.course_recommendation_state = None
        self.activity_register_state = None
        self.register_kind = None
        self.followup_rounds = 0
        # 注意：不清空 last_activity_results / profile_slots，避免跨流程误用

    def saved_profile_summary(self) -> str:
        """拼出"已记住"反馈文案。无已记住字段返回空串。"""
        if not self._saved_profile_fields:
            return ""
        # 按可读中文名展示
        from customer_agent.persist import PROFILE_FIELD_LABELS
        parts = []
        for f in self._saved_profile_fields:
            # 从 course/activity 子状态拿当前值
            val = self._field_current_value(f)
            if val:
                label = PROFILE_FIELD_LABELS.get(f, f)
                parts.append(f"{label}={val}")
        if not parts:
            return ""
        return "📌 已记住：" + "、".join(parts) + " ✅"

    def _field_current_value(self, field: str) -> str:
        """从当前子状态里读一个字段值（跨 course/activity 聚合）。"""
        # course 侧字段
        if self.course_recommendation_state:
            v = getattr(self.course_recommendation_state, field, None)
            if v:
                return v
        # activity 侧字段（name/phone）
        if self.activity_register_state:
            v = getattr(self.activity_register_state, field, None)
            if v:
                return v
        return ""

    # ── 会话级画像提取 & 写库 ──────────────────────────────────
    # user_profiles 列名 → 正则/提取器
    _PROFILE_EXTRACTORS = {
        "name": [
            (re.compile(r"(?:我叫|姓名|名字|叫|名为)[：:\s]*([一-龥]{2,4})"), 1),
        ],
        "phone": [
            (re.compile(r"(1[3-9]\d{9})"), 1),
        ],
        "target_country": [
            ("德国", "德国"),
            ("新加坡", "新加坡"),
        ],
        "education": [
            ("高中", "高中"), ("职高", "高中"), ("中专", "高中"),
            ("本科", "本科"), ("大学", "本科"), ("大专", "大专"),
            ("硕士", "硕士"), ("研究生", "硕士"),
            ("博士", "博士"),
        ],
        "target_major": [
            ("计算机", "计算机"), ("商科", "商科"), ("金融", "金融"),
            ("会计", "会计"), ("管理", "管理"), ("机械", "机械"),
            ("电子", "电子"), ("土木", "土木"), ("医学", "医学"),
            ("法学", "法学"), ("艺术", "艺术"), ("生物", "生物"),
            ("传媒", "传媒"), ("教育", "教育"), ("心理", "心理"),
            ("人工智能", "人工智能"), ("数据", "数据"),
        ],
        "language_score": [
            (re.compile(r"(?:ielts|雅思)[^\d]*(\d+(?:\.\d+)?)", re.I),
             lambda m: f"IELTS {m.group(1)}"),
            (re.compile(r"(?:toefl|托福)[^\d]*(\d+)", re.I),
             lambda m: f"TOEFL {m.group(1)}"),
        ],
    }

    def extract_profile(self, message: str):
        """
        从单条用户消息提取个人信息 → 合并进 self.profile_slots。
        只填写"之前为空"的字段（不覆盖已有值），并记录 _dirty_profile_fields。

        提取规则说明（profile_upsert 过滤后保留的列）:
          name, phone, education, target_major, language_score, target_country,
          gpa, budget
        未列出的列（age/major/wechat/email/consultation_status 等）暂不在此提取。
        """
        for field, rules in self._PROFILE_EXTRACTORS.items():
            if self.profile_slots.get(field):
                continue  # 已有值不覆盖
            for rule in rules:
                if not (isinstance(rule, tuple) and len(rule) == 2):
                    continue
                pat, val = rule
                if isinstance(pat, re.Pattern):
                    m = pat.search(message)
                    if m:
                        # int → regex group 下标；callable → 处理函数；str → 字面量
                        if isinstance(val, int):
                            self.profile_slots[field] = m.group(val)
                        elif callable(val):
                            self.profile_slots[field] = val(m)
                        else:
                            self.profile_slots[field] = val
                        self._dirty_profile_fields.add(field)
                        break
                else:
                    # 关键词匹配（字面量）
                    if pat in message:
                        self.profile_slots[field] = val
                        self._dirty_profile_fields.add(field)
                        break

        # GPA / budget（定向提取，字段名直接对应）
        if not self.profile_slots.get("gpa"):
            m = re.search(r"(?:gpa|绩点|均分)[^\d]*(\d+(?:\.\d+)?)", message, re.I)
            if m:
                self.profile_slots["gpa"] = float(m.group(1))
                self._dirty_profile_fields.add("gpa")
        if not self.profile_slots.get("budget"):
            m = re.search(r"(\d+)万", message)
            if m:
                self.profile_slots["budget"] = int(m.group(1)) * 10000
                self._dirty_profile_fields.add("budget")

    def sync_profile_to_db(self):
        """
        把本轮 dirty 字段增量写入 user_profiles。
        返回写入的字段集合（空表示无需写入）。
        """
        if not self._dirty_profile_fields:
            return set()
        from customer_agent.persist import profile_upsert
        fields = {k: v for k, v in self.profile_slots.items()
                  if k in self._dirty_profile_fields and v not in (None, "")}
        if not fields:
            self._dirty_profile_fields.clear()
            return set()
        try:
            profile_upsert(self.conversation_id, fields)
        except Exception as e:
            print(f"[Profile] 写库失败（降级内存模式）: {e}")
            self._dirty_profile_fields.clear()
            return set()
        written = set(fields.keys())
        self._saved_profile_fields.update(written)
        self._dirty_profile_fields.clear()
        return written

    def add_turn(self, role: str, content: str):
        """记录一轮对话"""
        self.history.append({
            "role": role,
            "content": content,
            "ts": datetime.now().isoformat(),
        })

    def get_context(self, n: int = 12) -> list:
        """获取最近 n 条对话上下文"""
        return self.history[-n:]

    def round_count(self) -> int:
        """当前会话总轮数"""
        return len(self.history) // 2


# ============================================================
# 全局会话存储
# ============================================================
_sessions: dict[str, SessionState] = {}


def new_session_id() -> str:
    import uuid
    return uuid.uuid4().hex[:16]


def derive_conversation_id(session_id: str) -> str:
    """
    按 session_id 确定性派生唯一 conversation_id。
    - 同 session_id 恒等 → 同一浏览器会话重启后仍能关联到同一份画像
    - 不同 session_id 不碰撞 → 匿名用户不再挤到同一条 '0' 画像
    使用 sha256 前 16 位 hex（64 bit 空间，碰撞概率可忽略）。
    """
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]


def get_session(session_id: str) -> SessionState:
    """获取或创建会话"""
    if session_id not in _sessions:
        _sessions[session_id] = SessionState(session_id=session_id)
    return _sessions[session_id]


def clear_session(session_id: str):
    """清除指定会话（调试/管理用）"""
    _sessions.pop(session_id, None)


def clear_all_sessions():
    """清空所有会话"""
    _sessions.clear()
