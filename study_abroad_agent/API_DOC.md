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

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/profiles?limit=&offset=&country=&education=&status=&keyword=` | 列表筛选 |
| GET | `/api/v1/profiles/{conversation_id}` | 按会话 ID 查询 |
| GET | `/api/v1/profiles/{conversation_id}/check` | 画像完整性 |
| POST | `/api/v1/profiles` | 创建（已存在返回 409） |
| POST | `/api/v1/profiles/upsert` | 创建或增量更新 |
| PUT | `/api/v1/profiles/{conversation_id}` | 全量字段更新 |
| DELETE | `/api/v1/profiles/{conversation_id}` | 删除 |
| POST | `/api/v1/profiles/recommend` | 基于画像的课程推荐 Top5 |

### 请求字段 (ProfileCreate)
| 字段 | 类型 | 必填 |
|------|------|------|
| conversation_id | string | 是 |
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
> 将中文 / 英文自然语言转换为 **只读** SQL 并执行。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/nl2sql/query` | 自然语言 → SQL → 执行 → 返回结果 |
| POST | `/api/v1/nl2sql/explain` | 仅生成 SQL，不执行（dry-run） |

### 请求体
```json
{
  "question": "德国留学的语言课程有哪些？",
  "include_sql": true
}
```

### 响应
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "question": "德国留学的语言课程有哪些？",
    "sql": "SELECT * FROM courses WHERE country = '德国' AND category = '语言课程'",
    "rows": [...],
    "row_count": 6,
    "elapsed_ms": 4149.23
  }
}
```

### 安全特性
- 仅允许 SELECT 开头的只读查询
- 检测到 DROP/DELETE/UPDATE/INSERT 等写关键字返回 HTTP 400
- 字符串值使用单引号，防止注入
- 默认 LIMIT 200

### 示例问题
- "德国留学方案有哪些？"
- "预算低于 1 万的课程"
- "IELTS 6.5 以上能申请的留学方案数量"
- "列出新加坡的语言课程及价格"

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
