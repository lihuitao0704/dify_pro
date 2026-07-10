# 智能留学顾问系统 —— study_abroad_agent

> 基于 **FastAPI + MySQL** 的留学课程推荐后端服务，集成 **NL2SQL**（LongCat-2.0）自然语言查询能力。
> 支持用户画像 / 课程库 / 咨询记录的增删改查，以及规则打分推荐引擎。

---

## 目录

- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [数据库设计](#数据库设计)
- [API 接口文档](#api-接口文档)
- [NL2SQL 说明](#nl2sql-说明)
- [配置说明](#配置说明)

---

## 项目结构

```
study_abroad_agent/
├── app.py                          # FastAPI 应用入口
├── config.py                       # 配置（数据库 + LongCat 大模型）
├── database.py                     # PyMySQL 数据库连接与表结构描述
├── schemas.py                      # Pydantic 请求/响应模型
├── run.py                          # 启动入口
├── requirements.txt                # Python 依赖
├── init_db.sql                     # 数据库初始化脚本（含示例数据）
├── API_DOC.md                      # 详细 API 接口文档
├── test_api.py                     # 接口自动化测试脚本
├── demo_nl2sql.py                  # NL2SQL 演示脚本
├── api/                            # FastAPI 路由
│   ├── health.py                   # 健康检查
│   ├── profiles.py                 # 用户画像 CRUD + 推荐
│   ├── courses.py                  # 课程 CRUD
│   ├── consultations.py           # 咨询记录 CRUD
│   ├── nl2sql.py                   # NL2SQL 自然语言查询
│   └── dify.py                     # 旧版 Dify 兼容路由
├── services/                       # 业务逻辑
│   ├── profile_service.py
│   ├── courses_service.py
│   ├── consultation_service.py
│   ├── recommend_service.py        # 规则打分推荐
│   └── nl2sql.py                   # NL2SQL 服务（调用 LongCat-2.0）
└── utils/
    └── logger.py                   # 日志配置
```

---

## 环境要求

| 组件 | 版本 |
|------|------|
| Python | 3.9+ |
| MySQL | 5.7+ / 8.0+ |
| FastAPI | >=0.115 |
| Uvicorn | >=0.34 |
| Pydantic | >=2.7 |
| PyMySQL | >=1.1 |
| openai | >=1.4（OpenAI 兼容协议调用 LongCat） |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化数据库

确保 MySQL 已启动，然后执行：

```bash
mysql -u root -p --default-character-set=utf8mb4 < init_db.sql
```

脚本会自动创建 `dify_pro` 数据库、`user_profiles` / `courses` / `consultations` 三张表，并插入 27 条示例课程数据。

### 3. 配置

在 `.env` 文件中配置数据库连接与 LongCat API Key：

```env
LONGCAT_API_KEY=ak_xxx
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=dify_pro
```

### 4. 启动服务

```bash
python run.py
```

或：

```bash
python app.py
```

服务运行在 **http://0.0.0.0:5000**

Swagger 交互式文档: **http://0.0.0.0:5000/docs**

### 5. 接口测试

```bash
python test_api.py
```

### 6. NL2SQL 演示

```bash
python demo_nl2sql.py
```

---

## 数据库设计

### 核心表

| 表名 | 说明 |
|------|------|
| `user_profiles` | 用户画像（学历、专业、语言成绩、GPA、预算等） |
| `courses` | 课程库（留学方案 / 语言课程 / 背景提升） |
| `consultations` | 咨询记录（对话摘要 + 推荐课程 JSON） |

### 关联关系

```
user_profiles.id  ←──  consultations.user_id
courses.id        ←──  consultations.course_id
user_profiles.conversation_id  ←──  Dify 会话 ID
```

---

## API 接口文档

| 前缀 | 说明 |
|------|------|
| `/api/v1/profiles` | 用户画像 CRUD + 推荐 |
| `/api/v1/courses` | 课程 CRUD |
| `/api/v1/consultations` | 咨询记录 CRUD |
| `/api/v1/nl2sql/query` | NL2SQL 自然语言 → SQL → 结果 |
| `/api/dify/*` | 旧版 Dify 兼容接口 |

所有接口返回统一格式：

```json
{ "code": 0, "message": "success", "data": { ... } }
```

详细接口文档见 [API_DOC.md](./API_DOC.md)。

### 用户画像 `/api/v1/profiles`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/profiles` | 列表筛选（country / education / status / keyword） |
| GET | `/api/v1/profiles/{conversation_id}` | 按会话 ID 查询 |
| GET | `/api/v1/profiles/{conversation_id}/check` | 画像完整性校验 |
| POST | `/api/v1/profiles` | 创建（409 如果已存在） |
| POST | `/api/v1/profiles/upsert` | 创建或增量更新 |
| PUT | `/api/v1/profiles/{conversation_id}` | 字段更新 |
| DELETE | `/api/v1/profiles/{conversation_id}` | 删除 |
| POST | `/api/v1/profiles/recommend` | 基于画像的课程推荐 Top 5 |

### 课程 `/api/v1/courses`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/courses` | 列表筛选（category / country / keyword） |
| GET | `/api/v1/courses/{course_id}` | 查询单条 |
| POST | `/api/v1/courses` | 创建 |
| PUT | `/api/v1/courses/{course_id}` | 更新 |
| DELETE | `/api/v1/courses/{course_id}` | 删除 |

### 咨询记录 `/api/v1/consultations`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/consultations` | 列表 |
| GET | `/api/v1/consultations/{id}` | 按咨询 ID 查 |
| GET | `/api/v1/consultations/by-conversation/{conversation_id}` | 按会话查 |
| POST | `/api/v1/consultations` | 创建 |
| PUT | `/api/v1/consultations/{id}` | 更新 |
| DELETE | `/api/v1/consultations/{id}` | 删除 |

---

## NL2SQL 说明

> 采用 **LongCat-2.0** 大模型（OpenAI 兼容协议，`api.longcat.chat/openai`），
> 将自然语言转换为 **只读 SQL** 并执行。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/nl2sql/query` | 自然语言 → SQL → 执行 → 结果 |
| POST | `/api/v1/nl2sql/explain` | 仅生成 SQL，不执行（调试用） |

### 请求示例

```json
{
  "question": "德国留学的语言课程有哪些？",
  "include_sql": true
}
```

### 响应示例

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

- 仅允许 `SELECT` / `WITH` 开头的只读查询
- DROP / DELETE / UPDATE / INSERT 等写关键字返回 HTTP 400
- 默认 LIMIT 200

### 大模型配置

```python
client = OpenAI(
    api_key=os.getenv("LONGCAT_API_KEY"),
    base_url="https://api.longcat.chat/openai",
)
MODEL = "LongCat-2.0"
```

---

## 推荐引擎说明

`RecommendService` 基于**规则打分**模式，从 5 个维度评分：

| 维度 | 分值 | 匹配逻辑 |
|------|------|----------|
| 学历 | 30 分 | 用户学历是否包含在课程的 `target_education` 中 |
| 专业 | 35 分 | 用户专业关键词是否命中课程名 / 描述 / 亮点 |
| 语言 | 20 分 | 解析用户与课程的语言成绩数值，比较是否达标 |
| 国家 | 10 分 | 用户目标国家是否包含在课程的 `country` 中 |
| GPA | 5 分 | 用户 GPA 是否 >= 课程的 `min_gpa` |

**最终排序：** 总分降序 → 取 Top 5。

---

## 配置说明

`config.py` 通过 `.env` 环境变量加载：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LONGCAT_API_KEY` | LongCat API 密钥 | — |
| `MYSQL_HOST` | 数据库主机 | localhost |
| `MYSQL_PORT` | 数据库端口 | 3306 |
| `MYSQL_USER` | 数据库用户 | root |
| `MYSQL_PASSWORD` | 数据库密码 | 123456 |
| `MYSQL_DATABASE` | 数据库名 | dify_pro |

---

## 许可

内部项目，仅供学习与内部使用。
