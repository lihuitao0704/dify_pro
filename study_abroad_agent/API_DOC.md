# 智能留学顾问系统 —— API 接口文档

服务运行在 `http://127.0.0.1:5000`
Swagger 交互式文档: http://127.0.0.1:5000/docs

所有接口返回统一格式：
```json
{ "code": 0, "message": "success", "data": { ... } }
```

---

## 一、前缀总览

| 前缀 | 说明 |
|------|------|
| `/api/v1/profiles` | 用户画像（CRUD + 推荐） |
| `/api/v1/courses` | 课程库（CRUD） |
| `/api/v1/consultations` | 咨询记录（CRUD） |
| `/api/v1/nl2sql/query` | NL2SQL 自然语言 → SQL → 结果 |
| `/api/dify/*` | 旧版 Dify 兼容接口 |

---

## 二、系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 + DB 连通 |
| GET | `/api/v1/ready` | 就绪探针 |

---

## 三、用户画像 `/api/v1/profiles`

> **注意**：`conversation_id` 默认值为 `'0'`，**非唯一**，同一 conversation_id 可有多条记录。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/profiles?limit=&offset=&country=&education=&status=&keyword=&name=&phone=&email=&wechat=&target_country=&target_major=&major=` | 多字段筛选查询 |
| GET | `/api/v1/profiles/by-id/{profile_id}` | 按 id 查询 |
| GET | `/api/v1/profiles/by-conversation/{conversation_id}` | 按会话 ID 查询（返回列表） |
| GET | `/api/v1/profiles/by-conversation/{conversation_id}/check` | 画像完整性校验 |
| POST | `/api/v1/profiles` | 创建 |
| POST | `/api/v1/profiles/upsert` | 创建或增量更新 |
| PUT | `/api/v1/profiles/by-id/{profile_id}` | 按 id 更新 |
| DELETE | `/api/v1/profiles/by-id/{profile_id}` | 按 id 删除 |
| DELETE | `/api/v1/profiles/by-conversation/{conversation_id}` | 按会话 ID 删除所有匹配记录 |
| POST | `/api/v1/profiles/recommend` | 基于画像的课程推荐 Top5 |

### 请求字段 (ProfileCreate)
| 字段 | 类型 | 必填 |
|------|------|------|
| conversation_id | string | 否（默认 "0"） |
| name / age / major / education / target_major / language_score / target_country / gpa / budget / phone / wechat / email | 各类型 | 否 |

---

## 四、课程 `/api/v1/courses`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/courses?category=&country=&keyword=&is_active=&limit=&offset=` | 列表筛选 |
| GET | `/api/v1/courses/{course_id}` | 查询 |
| POST | `/api/v1/courses` | 创建 |
| PUT | `/api/v1/courses/{course_id}` | 更新 |
| DELETE | `/api/v1/courses/{course_id}` | 删除 |

`category` 仅允许: `留学方案` / `语言课程` / `背景提升`

---

## 五、咨询记录 `/api/v1/consultations`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/consultations?status=&user_id=&limit=&offset=` | 列表 |
| GET | `/api/v1/consultations/{id}` | 按咨询 ID 查 |
| GET | `/api/v1/consultations/by-conversation/{conversation_id}` | 按会话查 |
| POST | `/api/v1/consultations` | 创建 |
| PUT | `/api/v1/consultations/{id}` | 更新 |
| DELETE | `/api/v1/consultations/{id}` | 删除 |

---

## 六、NL2SQL `/api/v1/nl2sql`

> 采用 **LongCat-2.0** 大模型（OpenAI 兼容协议，`api.longcat.chat/openai`），
> 将中文 / 英文自然语言转换为 SQL 并执行。**模型自动判断**查询 (SELECT) 还是新增 (INSERT)，无需手动指定 `intent`。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/nl2sql/query` | 自然语言 → SQL → 执行（自动判断查询/新增） |
| POST | `/api/v1/nl2sql/explain` | 仅生成 SQL，不执行（dry-run） |

### 请求体
```json
{
  "question": "德国留学的语言课程有哪些？",
  "include_sql": true
}
```
- `question`：自然语言问题（查询类如"有哪些""帮我查"，新增类如"新增""添加""录入"）
- `include_sql`：是否返回生成的 SQL 语句

### 查询响应（自动判断为 query）
```json
{
  "code": 0,
  "message": "success",
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

### 新增响应（自动判断为 insert）
```json
{
  "code": 0,
  "message": "success",
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

### 安全特性
- **自动意图判断**：模型根据自然语言语义自动判断查询还是新增，两路有独立校验。
- query：仅允许 SELECT/WITH 开头的只读查询；检测到 DROP/DELETE/UPDATE/INSERT 等写关键字返回 HTTP 400。
- insert：仅允许单条 `INSERT INTO`；表/列名严格按 schema；**不给自增主键 `id` 赋值**；禁止多条语句（含分号）；禁用 SELECT/WITH 防止 `INSERT ... SELECT` 绕过；**表名白名单** `[user_profiles, courses, consultations]`，不在白名单即 400。
- 写入总开关：`config.NL2SQL_ALLOW_WRITE`（默认 `True`），置 `False` 后 insert 返回 400，无需改代码。
- 字符串值使用单引号；默认查询 LIMIT 200。

### 查询示例问题
- "德国留学方案有哪些？"
- "预算低于 1 万的课程"
- "IELTS 6.5 以上能申请的留学方案数量"
- "列出新加坡的语言课程及价格"
- "查询用户姓名、学历和目标国家"

### 新增示例问题
- "新增一门课程：名称=IELTS 7.0 冲刺班，category=语言课程，sub_category=IELTS，country=新加坡，target_education=本科，min_gpa=3.0，price=12800，is_active=1"
- "记录一条用户咨询：conversation_id=conv_999，course_id=1，status=new"
- "新增用户：姓名=张三，学历=本科，目标国家=德国"

---

## 七、旧版 Dify 兼容 `/api/dify/*`

保持与既有 Dify 工作流一致：

| 方法 | 路径 |
|------|------|
| GET | `/api/dify/health` |
| POST | `/api/dify/profile` |
| GET | `/api/dify/profile/{conversation_id}` |
| DELETE | `/api/dify/profile/{conversation_id}` |
| POST | `/api/dify/recommend` |
| POST | `/api/dify/consultation` |

---

## 八、启动与测试

```bash
# 安装依赖
pip install -r requirements.txt

# 启动（开发模式）
python run.py
python app.py

# 接口测试
python test_api.py
```
