# 粤教留学客服 Agent — API 接口文档

客服 Agent 运行在 `http://127.0.0.1:9000`
Swagger 交互式文档: http://127.0.0.1:9000/docs
ReDoc: http://127.0.0.1:9000/redoc

服务已经自包含：**同时承担课程推荐引擎、活动讲座报名、用户画像库、NL2SQL 查询**，不再依赖独立的 `study_abroad_agent(:5000)` / `Event&Lecture(:8011)` 服务。

---

## 一、通用约定

### 1.1 所有接口统一响应结构

```json
{ "code": 0, "message": "success", "data": { ... } }
```

- `code = 0` 表示成功，非 0 表示失败
- `message` 为可读中文描述
- `data` 为业务负载

### 1.2 UTF-8

所有 JSON 响应都带 `Content-Type: application/json; charset=utf-8`，彻底避免中文乱码。

### 1.3 跨域

服务开启 CORS `Access-Control-Allow-Origin: *`，前端可直接跨域调用。

### 1.4 前缀总览

| 前缀 | 说明 |
|------|------|
| `/chat` | 主对话入口 (自然语言 → 意图分类 → 本地业务) |
| `/api/v1/profiles` | 用户画像 CRUD + 推荐 + 完整性校验 |
| `/api/v1/courses` | 课程库 CRUD |
| `/api/v1/consultations` | 咨询记录 CRUD |
| `/api/v1/nl2sql` | 自然语言转 SQL (覆盖 7 张表) |
| `/api/v1/events` | 活动 / 讲座 CRUD + 报名记录 + NL2SQL 入口 |
| `/admin/*` | 知识库管理 (状态 / 热加载) |
| `/auth/login` | 统一登录 |
| `/portal/*` | 统一前端页面 (静态) |
| `/static/*` | 静态资源 |
| `/health` | 健康检查 |

---

## 二、主对话 `/chat`

> **本服务的核心入口**：用户用自然语言提问，系统先做 **7+1 大意图分类**，再由对应 Handler 调用本地 NL2SQL / 推荐 / RAG / 知识库完成回答。分类逻辑在 `customer_agent/intent.py`，自然语言调用路径即为本接口。

### POST `/chat`

主对话入口。每次返回助手回复 + 识别到的意图 + 会话 ID。

请求体 (同时兼容 JSON / form / urlencoded)：
```json
{
  "message": "德国留学有什么讲座？帮我报名第一个 张三 13800138000",
  "session_id": "可选，不传自动创建",
  "conversation_id": "可选，默认 0，用于关联用户画像"
}
```

响应：
```json
{
  "reply": "🎯 为你匹配到 ... ",
  "intents": [
    { "intent": "event", "confidence": 0.95 }
  ],
  "session_id": "a1b2c3d4e5f6g7h8",
  "actions": [
    { "intent": "event", "result": "ok" }
  ]
}
```

**7+1 大意图说明**：

| intent 名 | 场景 | 处理方式 |
|-----------|------|----------|
| `company_info` | 公司信息咨询 | RAG(公司信息材料) |
| `business_query` | 业务查询 | RAG(公司业务材料) + 本地 NL2SQL 查课程表 |
| `policy` | 海外留学政策查询 | RAG(留学政策材料) |
| `recommend` | 课程与项目推荐 | 多轮参数收集 → 本地 `RecommendService.recommend()` 打分 |
| `event` | 活动与讲座报名 | 多轮参数收集 → 本地 NL2SQL 查库 + 写库 |
| `faq` | 常见问题自助解答 | FAQ 精确匹配 + RAG |
| `chat` | 日常闲聊互动 | 纯 LLM 对话 |

### GET `/context/{session_id}`

调试用：查看某会话完整上下文。

---

## 三、系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |

---

## 四、用户画像 `/api/v1/profiles`

> `conversation_id` 默认值为 `'0'`，**非唯一**，同一 conversation_id 可有多条记录。

### 4.1 查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/profiles?limit=&offset=&country=&education=&status=&keyword=&name=&phone=&email=&wechat=&target_country=&target_major=&major=` | 多字段筛选查询 |
| GET | `/api/v1/profiles/by-id/{profile_id}` | 按 id 查询 |
| GET | `/api/v1/profiles/by-conversation/{conversation_id}` | 按会话 ID 查询 (返回列表) |
| GET | `/api/v1/profiles/by-conversation/{conversation_id}/check` | 画像完整性校验 |

### 4.2 写入 / 删除

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/profiles` | 创建 |
| POST | `/api/v1/profiles/upsert` | 创建或增量更新 |
| PUT | `/api/v1/profiles/by-id/{profile_id}` | 按 id 更新 |
| DELETE | `/api/v1/profiles/by-id/{profile_id}` | 按 id 删除 |
| DELETE | `/api/v1/profiles/by-conversation/{conversation_id}` | 按会话 ID 删除所有匹配记录 |

### 4.3 推荐

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/profiles/recommend` | 基于画像的课程推荐 Top5 |

请求体：
```json
{ "conversation_id": "abc123" }
```

响应：
```json
{
  "code": 0,
  "data": {
    "success": true,
    "recommendations": [
      {
        "course_id": 1,
        "course_name": "...",
        "country": "德国",
        "category": "留学方案",
        "sub_category": "...",
        "target_education": "本科",
        "score": 90,
        "reasons": ["学历符合", "专业匹配（工科）", "语言成绩满足", "国家匹配"]
      }
    ]
  }
}
```

### ProfileCreate 字段

| 字段 | 类型 | 必填 |
|------|------|------|
| conversation_id | string | 否（默认 "0"） |
| name / age / major / education / target_major / language_score / target_country / gpa / budget / phone / wechat / email | 各类型 | 否 |
| consultation_status | enum(collecting/recommended/finished) | 否 |
| assess / development / abilities | string | 否 |
| is_Closed-loop | string | 否 |

---

## 五、课程 `/api/v1/courses`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/courses?category=&country=&keyword=&is_active=&limit=&offset=` | 列表筛选 |
| GET | `/api/v1/courses/{course_id}` | 查询 |
| POST | `/api/v1/courses` | 创建 |
| PUT | `/api/v1/courses/{course_id}` | 更新 |
| DELETE | `/api/v1/courses/{course_id}` | 删除 |

`category` 仅允许: `留学方案` / `语言课程` / `背景提升`

---

## 六、咨询记录 `/api/v1/consultations`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/consultations?status=&user_id=&limit=&offset=` | 列表 |
| GET | `/api/v1/consultations/{id}` | 按咨询 ID 查 |
| GET | `/api/v1/consultations/by-conversation/{conversation_id}` | 按会话查 |
| POST | `/api/v1/consultations` | 创建 |
| PUT | `/api/v1/consultations/{id}` | 更新 |
| DELETE | `/api/v1/consultations/{id}` | 删除 |

---

## 七、统一 NL2SQL `/api/v1/nl2sql`

> 采用 **LongCat-2.0** 大模型（OpenAI 兼容协议）。
> **自动判断** 查询 (SELECT) 还是新增 (INSERT)，无需手动指定 `intent`。
> **覆盖 7 张表**：user_profiles / courses / consultations / lectures / activities / lecture_registrations / activity_registrations

### POST `/api/v1/nl2sql/query`

自然语言 → SQL → 执行。

请求体：
```json
{
  "question": "德国留学的语言课程有哪些？",
  "include_sql": true,
  "polish": false
}
```
- `question`：自然语言问题（查 → SELECT，增 → INSERT）
- `include_sql`：是否返回生成的 SQL 语句
- `polish`：是否返回自然语言润色回答 (活动讲座场景推荐开)

查询响应（action = query）：
```json
{
  "code": 0, "message": "success",
  "data": {
    "action": "query",
    "question": "德国留学的语言课程有哪些？",
    "sql": "SELECT ...",
    "rows": [...],
    "row_count": 6,
    "elapsed_ms": 4149.23
  }
}
```

新增响应（action = insert）：
```json
{
  "code": 0, "message": "success",
  "data": {
    "action": "insert",
    "question": "新增一门课程：...",
    "sql": "INSERT INTO courses (...) VALUES (...)",
    "inserted_id": 42,
    "affected_rows": 1,
    "elapsed_ms": 3812.10
  }
}
```

### POST `/api/v1/nl2sql/explain`

仅生成 SQL，不执行（dry-run）。

```json
{
  "question": "GPA 3.0 能申请什么",
  "include_sql": true
}
```

### 安全特性

- **自动意图判断**：模型根据语义自动识别 query / insert
- **query**：仅允许 SELECT/WITH 开头的只读查询；检测到 DROP/DELETE/UPDATE/INSERT 等写关键字返回 HTTP 400
- **insert**：仅允许单条 `INSERT INTO`；表/列名严格按 schema；**不给自增主键 `id` 赋值**；禁止多条语句（含分号）；禁用 SELECT/WITH 防 `INSERT ... SELECT` 绕过
- **表白名单**：`user_profiles, courses, consultations, lectures, activities, lecture_registrations, activity_registrations`，不在白名单即 400
- **写入总开关**：`config.NL2SQL_ALLOW_WRITE`（默认 `True`），置 `False` 后 insert 返回 400
- 字符串值使用单引号；默认查询 LIMIT 200

### 查询示例

- "德国留学方案有哪些？"
- "预算低于 1 万的课程"
- "IELTS 6.5 以上能申请的留学方案数量"
- "近期有哪些留学讲座？"
- "新增一场讲座，主题是新加坡硕士申请，时间是2026-09-20 14:00，地点线上，主讲人赵老师"

### 新增示例

- "新增一门课程：名称=IELTS 7.0 冲刺班，category=语言课程，sub_category=IELTS，country=新加坡，target_education=本科，price=12800"
- "记录一条用户咨询：conversation_id=conv_999，course_id=1，status=new"
- "帮我报名讲座3，姓名张三，手机13800138000"
- "新增用户：姓名=张三，学历=本科，目标国家=德国"

---

## 八、活动 / 讲座 `/api/v1/events`

### 8.1 NL2SQL 入口 (对齐旧 Event&Lecture `%nl2sql`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/events/nl2sql` | 自然语言查/报活动讲座 (抛光结果) |

请求体：
```json
{ "query": "近期有哪些留学讲座？" }
```

或报名：
```json
{ "query": "帮我报名讲座3，姓名张三，手机13800138000" }
```

响应：
```json
{
  "query": "近期有哪些留学讲座？",
  "sql": "SELECT ...",
  "result_type": "select",
  "data": [{ "lecture_id": 1, "title": "...", "event_time": "..." }],
  "message": "success",
  "polished": "近期有 3 场讲座 ...",
  "status_code": 200
}
```

`result_type` 取值：`select` / `dml` / `error`。HTTP 状态码按语义返回 200 / 400 / 409。

### 8.2 讲座 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/events/lectures?keyword=&limit=&offset=` | 列表 |
| GET | `/api/v1/events/lectures/{lecture_id}` | 单条 |
| POST | `/api/v1/events/lectures` | 创建 |
| PUT | `/api/v1/events/lectures/{lecture_id}` | 更新 |
| DELETE | `/api/v1/events/lectures/{lecture_id}` | 删除 |

创建 / 更新请求体示例：
```json
{
  "title": "新加坡硕士申请讲座",
  "event_time": "2026-09-20 14:00:00",
  "location": "线上",
  "registration_method": "对话报名",
  "speaker": "赵老师"
}
```

### 8.3 活动 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/events/activities?keyword=&limit=&offset=` | 列表 |
| GET | `/api/v1/events/activities/{activity_id}` | 单条 |
| POST | `/api/v1/events/activities` | 创建 |
| PUT | `/api/v1/events/activities/{activity_id}` | 更新 |
| DELETE | `/api/v1/events/activities/{activity_id}` | 删除 |

创建 / 更新请求体示例：
```json
{
  "title": "团建活动",
  "event_time": "2026-08-01 10:00:00",
  "location": "公司大厅",
  "registration_method": "扫码"
}
```

### 8.4 报名记录

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/events/registrations/lectures?lecture_id=&name=&phone=&limit=` | 查询讲座报名 |
| GET | `/api/v1/events/registrations/activities?activity_id=&name=&phone=&limit=` | 查询活动报名 |
| DELETE | `/api/v1/events/registrations/lectures/{registration_id}` | 删除一条讲座报名 |
| DELETE | `/api/v1/events/registrations/activities/{registration_id}` | 删除一条活动报名 |

---

## 九、管理接口 `/admin`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/kb-status` | 知识库状态 (chunks / FAQ 数 / 文档数) |
| POST | `/admin/kb-reload` | 热加载知识库 |

---

## 十、前端相关

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 统一登录 (account 表，bcrypt / 明文兼容) |
| GET | `/` / `/login` | 登录页 |
| GET | `/dashboard` | 工作台 |
| GET | `/portal` | 统一门户首页 |
| GET | `/portal/student-dashboard` | 学生看板 |
| GET | `/portal/employee-dashboard` | 员工看板 |
| GET | `/portal/css/{filename}` | 门户样式 |
| GET | `/portal/js/{filename}` | 门户脚本 |

登录请求：
```json
{ "username": "zs", "password": "123456" }
```

登录成功响应：
```json
{
  "success": true,
  "student": {
    "id": 1, "name": "张三", "user_id": 1,
    "user_type": "student", "student_id": 1,
    "phone": "", "email": ""
  }
}
```

---

## 十一、启动与测试

```bash
# 启动所有服务
python start_all.py

# 单独启动客服 Agent (本次合并的目标)
python start_all.py customer

# 或直接
python -m customer_agent.main
# → http://localhost:9000
# → 文档 http://localhost:9000/docs
```

### 切换独立模式 (调试)

若仍需把课程推荐 / 活动讲座作为独立进程运行 (例如做对比测试)，可单独保留 `study_abroad_agent/app.py` 和 `Event & Lecture Registration/Event_Lecture_api.py`，
并把 `customer_agent/services/__init__.py` 的本地适配器切回 HTTP 桥接 (旧 `bridge.py`) — 这也是合并后保留旧目录的初衷。

---

## 十二、NL2SQL 表白名单速查

| 表名 | 用途 | 主要字段 |
|------|------|----------|
| user_profiles | 用户画像 | conversation_id, name, education, target_major, language_score, target_country, gpa, budget, phone |
| courses | 课程库 | course_name, category, sub_category, country, target_education, price, is_active |
| consultations | 咨询记录 | user_id, course_id, status |
| lectures | 讲座 | lecture_id, title, event_time, location, speaker |
| activities | 活动 | activity_id, title, event_time, location |
| lecture_registrations | 讲座报名 | lecture_id, name, phone |
| activity_registrations | 活动报名 | activity_id, name, phone |
