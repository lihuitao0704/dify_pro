# 学生智能助手模块 — API 接口文档

> Base URL: `http://localhost:8008` | 认证: `Authorization: Bearer <token>`

---

## 通用说明

### 认证

除 `/health`、`/docs`、`/static`、`/api` 外，所有接口需要在请求头携带：

```
Authorization: Bearer <api-token>
```

- 开发环境默认 token: `dev-token`
- 生产环境通过 `API_TOKEN` 环境变量设定
- 认证 scheme **大小写不敏感**（`bearer` / `Bearer` 均可）

### 响应格式

- 成功: HTTP 200/201 + JSON body
- 客户端错误: HTTP 400/401/403/404 + `{"detail": "..."}`
- 服务端错误: HTTP 500 + `{"detail": "..."}`
- 健康检查异常: HTTP 503 + `{"status":"unhealthy","database":"..."}`

### 分页

列表接口支持 `limit` + `offset` 参数：

```
GET /api/v1/student/schedules?student_id=1&limit=20&offset=0
```

---

## 一、会话与消息 (`/api/v1/chat`)

### 1.1 创建会话

```
POST /api/v1/chat/sessions
```

**Request Body:**
```json
{
  "student_id": 1,
  "session_id": "my-custom-id"   // 可选，不填自动生成
}
```

**Response (200):**
```json
{
  "id": 1,
  "session_id": "sess_abc123",
  "student_id": 1,
  "status": "active",
  "last_message_time": null,
  "message_count": 0,
  "close_time": null,
  "create_time": "2026-07-11T10:00:00"
}
```

---

### 1.2 查询会话列表

```
GET /api/v1/chat/sessions?student_id=1&limit=20&offset=0
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| student_id | int | 是 | 学生ID |
| limit | int | 否 | 返回上限 (1-100, 默认20) |
| offset | int | 否 | 偏移量 (默认0) |

**Response (200):** `SessionResponse[]`

---

### 1.3 查询会话详情

```
GET /api/v1/chat/sessions/{session_id}
```

**Response (200):** `SessionResponse`
**Response (404):** 会话不存在

---

### 1.4 发送消息

```
POST /api/v1/chat/messages
```

**Request Body:**
```json
{
  "session_id": "sess_abc123",
  "role": "user",
  "content": "我今天考试通过了，太开心了！",
  "intent": "general_chat",        // 可选，AI识别意图
  "emotion_tag": "积极",           // 可选，AI提供情绪标签
  "emotion_score": 85,             // 可选，AI提供情绪分值 0-100
  "trigger_keywords": ["开心","通过"], // 可选，AI提取关键词
  "tokens_used": 150,              // 可选
  "response_time_ms": 320          // 可选
}
```

> 💡 **情绪自动分析**: 当 `role=user` 且未提供 `emotion_tag`/`emotion_score` 时，服务端自动进行关键词情绪分析，并同步更新心理画像。LLM/Dify 接入后可直接传入 AI 分析结果。

**Response (200):**
```json
{
  "id": 1,
  "session_id": "sess_abc123",
  "role": "user",
  "content": "我今天考试通过了，太开心了！",
  "intent": "general_chat",
  "emotion_tag": "积极",
  "emotion_score": 85,
  "trigger_keywords": ["开心", "通过"],
  "response_time_ms": null,
  "create_time": "2026-07-11T10:00:01"
}
```

**Response (404):** 会话不存在

---

### 1.5 查询消息历史

```
GET /api/v1/chat/messages?session_id={session_id}&limit=50&offset=0
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | string | 是 | 会话ID |
| limit | int | 否 | 返回上限 (1-200, 默认50) |
| offset | int | 否 | 偏移量 (默认0) |

**Response (200):** `MessageResponse[]`

---

## 二、心理画像与预警 (`/api/v1/student`)

### 2.1 获取心理画像

```
GET /api/v1/student/psych/profile?student_id=1
```

> 不存在时自动创建空画像，返回 200（非 404）。

**Response (200):**
```json
{
  "id": 1,
  "student_id": 1,
  "latest_emotion_tag": "积极",
  "emotion_score": 85,
  "risk_level": "low",
  "emotion_history": [
    {"tag": "焦虑", "score": 30, "risk": "high", "date": "2026-07-10 14:00:00"},
    {"tag": "积极", "score": 85, "risk": "low", "date": "2026-07-11 10:00:00"}
  ],
  "last_interaction_time": "2026-07-11T10:00:01",
  "update_time": "2026-07-11T10:00:01",
  "create_time": "2026-07-10T14:00:00"
}
```

---

### 2.2 创建心理预警

```
POST /api/v1/student/psych/alerts
```

**Request Body:**
```json
{
  "student_id": 1,
  "trigger_reason": "连续3天情绪评分低于30分，学生表现出焦虑和失眠症状",
  "risk_level": "high",
  "source_message_id": 42,
  "risk_tags": ["失眠", "学业压力", "焦虑"]
}
```

**Response (200):**
```json
{
  "id": 1,
  "student_id": 1,
  "source_message_id": 42,
  "trigger_reason": "连续3天情绪评分低于30分...",
  "risk_tags": ["失眠", "学业压力", "焦虑"],
  "risk_level": "high",
  "status": "pending",
  "teacher_id": null,
  "follow_record": null,
  "resolved_time": null,
  "update_time": "2026-07-11T10:00:02",
  "create_time": "2026-07-11T10:00:02"
}
```

---

### 2.3 查询预警列表

```
GET /api/v1/student/psych/alerts?student_id=1&risk_level=high&status=pending&limit=50&offset=0
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| student_id | int | 否 | 学生ID |
| risk_level | string | 否 | low / medium / high |
| status | string | 否 | pending / following / resolved / dismissed |
| limit | int | 否 | (1-200, 默认50) |
| offset | int | 否 | (默认0) |

---

### 2.4 处理预警

```
PUT /api/v1/student/psych/alerts/{alert_id}
```

**Request Body:**
```json
{
  "status": "following",
  "teacher_id": 5,
  "follow_record": "已电话沟通，学生表示最近考试压力大",
  "risk_tags": ["学业压力", "失眠"]
}
```

> `status` 为 `resolved` 或 `dismissed` 时，`resolved_time` 自动写入当前时间。

**Response (200):** `RiskInterventionResponse`
**Response (404):** 预警不存在

---

## 三、投诉工单 (`/api/v1/student`)

### 3.1 提交工单

```
POST /api/v1/student/feedback-tickets
```

**Request Body:**
```json
{
  "student_id": 1,
  "ticket_type": "complaint",
  "category": "签证办理",
  "title": "签证材料迟迟未发",
  "content": "我已经等了两周了，签证材料一直没有收到",
  "detail": "详细描述...",
  "priority": "high"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| ticket_type | string | complaint / suggestion / consult |
| category | string | 签证办理 / 院校申请 / 生活服务 / 其他 |
| priority | string | low / medium / high / urgent |

---

### 3.2 查询工单列表

```
GET /api/v1/student/feedback-tickets?student_id=1&status=pending&category=签证办理&limit=50&offset=0
```

---

### 3.3 处理工单

```
PUT /api/v1/student/feedback-tickets/{ticket_id}
```

**Request Body:**
```json
{
  "status": "resolved",
  "assignee_id": 3,
  "solution": "材料已补发，预计3个工作日到达",
  "satisfaction": 5,
  "is_notified": true,
  "priority": "high"
}
```

> `status` 为 `resolved` 或 `closed` 时，`resolved_time` 自动写入。

**Response (200):** `FeedbackTicketResponse`
**Response (404):** 工单不存在

---

## 四、学业日程 (`/api/v1/student`)

### 4.1 创建日程

```
POST /api/v1/student/schedules
```

**Request Body:**
```json
{
  "student_id": 1,
  "schedule_type": "course",
  "title": "雅思冲刺班",
  "description": "第3周课程",
  "start_time": "2026-07-15T09:00:00",
  "end_time": "2026-07-15T11:00:00",
  "location": "线上-Zoom",
  "is_recurring": false,
  "reminder_enabled": true,
  "reminder_minutes": 30
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| schedule_type | string | course / exam / task / personal |
| reminder_minutes | int | 提前N分钟提醒 |

---

### 4.2 查询日程

```
GET /api/v1/student/schedules?student_id=1&schedule_type=course&status=pending&limit=50&offset=0
```

---

## 五、DDL 提醒 (`/api/v1/student`)

### 5.1 创建DDL

```
POST /api/v1/student/deadlines
```

**Request Body:**
```json
{
  "title": "曼彻斯特大学申请截止",
  "deadline": "2026-08-01T23:59:00",
  "deadline_type": "application",
  "student_id": 1,
  "description": "提交所有申请材料",
  "reminder_days": [7, 3, 1],
  "related_schedule_id": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| deadline_type | string | paper / exam / application / visa / other |
| student_id | int | NULL=通用提醒(全量学生) |
| reminder_days | array | 如 [7,3,1] 表示提前7/3/1天提醒；`[]`=不提醒；不传=默认[7,3,1] |

---

### 5.2 查询即将到期的DDL

```
GET /api/v1/student/deadlines?student_id=1&upcoming_days=7&limit=30&offset=0
```

| 参数 | 类型 | 说明 |
|------|------|------|
| upcoming_days | int | 未来N天内到期 (1-365, 默认7) |

---

## 六、升学意向 (`/api/v1/student`)

### 6.1 创建升学意向

```
POST /api/v1/student/intentions
```

**Request Body:**
```json
{
  "student_id": 1,
  "target_country": "英国",
  "target_school": "曼彻斯特大学",
  "target_major": "计算机科学",
  "education_level": "硕士",
  "expected_enroll_time": "2027-09",
  "budget_range": "30-50万",
  "language_score": "雅思6.5",
  "priority": 0
}
```

> `priority`: 越小越优先，0=最高优先级

---

### 6.2 查询升学意向

```
GET /api/v1/student/intentions?student_id=1&limit=50&offset=0
```

---

## 七、申请进度 (`/api/v1/student`)

### 7.1 创建申请进度

```
POST /api/v1/student/applications
```

**Request Body:**
```json
{
  "student_id": 1,
  "intention_id": 1,
  "target_country": "英国",
  "target_school": "曼彻斯特大学",
  "target_major": "计算机科学",
  "stage": "under_review",
  "progress_detail": "材料已提交，等待审核",
  "deadline": "2026-08-01T00:00:00",
  "next_action": "准备补充材料",
  "handler_id": 3
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| stage | string | document_prep / submitted / under_review / offer_received / visa_processing / enrolled |
| status | string | (自动) ongoing / paused / completed / cancelled |

**阶段流转:**
```
document_prep → submitted → under_review → offer_received → visa_processing → enrolled
```

---

### 7.2 查询申请进度

```
GET /api/v1/student/applications?student_id=1&stage=under_review&status=ongoing&limit=30&offset=0
```

---

## 八、NL2SQL 自然语言查询 (`/api/v1/nl2sql`)

### 8.1 自然语言查询

```
POST /api/v1/nl2sql/query
```

**Request Body:**
```json
{
  "query": "查看学生档案",
  "student_id": 1,
  "use_template": true
}
```

**Response (200):**
```json
{
  "natural_query": "查看学生档案",
  "generated_sql": "SELECT e.student_id, e.latest_emotion_tag...",
  "matched_template": "查看学生档案",
  "data": [{"student_id":1,"latest_emotion_tag":"积极","emotion_score":85,"risk_level":"LOW"}],
  "row_count": 1,
  "elapsed_ms": 4.1
}
```

**预设查询模板 (12个):**

| 模板名 | 触发示例 |
|--------|----------|
| 查看学生档案 | "学生信息" "学生档案" |
| 查询对话记录 | "最近对话" "聊天记录" |
| 查询心理状态 | "心理状态怎样" "情绪报告" |
| 查询心理预警 | "心理预警" "风险警报" |
| 查询投诉记录 | "投诉记录" "工单进度" |
| 查询学业日程 | "课程安排" "今天什么课" |
| 查询DDL | "DDL" "截止日期" |
| 查询升学意向 | "升学意向" "留学目标" |
| 查询申请进度 | "申请进度" "offer" "录取情况" |
| 统计情绪趋势 | "情绪趋势" "心理统计" |
| 统计申请数量 | "申请数量" "统计offer" |
| 通用查询 | 兜底，返回最近10条消息 |

**安全措施:** 仅允许单条 SELECT，禁止多语句，禁止 INSERT/UPDATE/DELETE/DROP 等，结果上限 1000 行。

---

### 8.2 查看数据库 Schema

```
GET /api/v1/nl2sql/schema
```

**Response (200):**
```json
{
  "database": "hambaki_3",
  "description": "学生智能助手模块数据库",
  "tables": { ... }
}
```

---

### 8.3 查看查询模板

```
GET /api/v1/nl2sql/templates
```

---

## 九、系统接口

### 9.1 健康检查

```
GET /health
```

**Response (200):**
```json
{"status": "ok", "database": "connected"}
```

**Response (503):** 数据库不可用

---

### 9.2 API 信息

```
GET /api
```

无需认证。

---

### 9.3 Swagger 文档

```
GET /docs
```

无需认证，可直接在浏览器中交互测试所有 API。

---

## 附录：枚举值速查

| 枚举 | 可选值 |
|------|--------|
| 会话状态 | `active` `closed` `timeout` |
| 消息角色 | `user` `assistant` `system` |
| 风险等级 | `low` `medium` `high` |
| 预警状态 | `pending` `following` `resolved` `dismissed` |
| 工单类型 | `complaint` `suggestion` `consult` |
| 工单状态 | `pending` `processing` `resolved` `closed` |
| 优先级 | `low` `medium` `high` `urgent` |
| 日程类型 | `course` `exam` `task` `personal` |
| 日程状态 | `pending` `done` `cancelled` |
| DDL类型 | `paper` `exam` `application` `visa` `other` |
| DDL状态 | `pending` `reminded` `done` `missed` |
| 意向状态 | `active` `frozen` `completed` `cancelled` |
| 申请阶段 | `document_prep` `submitted` `under_review` `offer_received` `visa_processing` `enrolled` |
| 申请状态 | `ongoing` `paused` `completed` `cancelled` |
