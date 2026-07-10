# Dify NL2SQL 自然语言增删改查配置指南

## 概述

后端 `backend_api.py` 已新增以下接口供 Dify 调用：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/agent/nl` | POST | 规则模式：零成本匹配常见意图 |
| `/api/agent/sql` | POST | NL2SQL 模式：LLM 生成 SQL，后端安全执行 |
| `/api/agent/schema` | GET | 获取数据库表结构，供 LLM prompt 使用 |
| `/api/courses` | GET/POST | 课程列表 + 新增 |
| `/api/courses/<id>` | GET/PUT/DELETE | 课程详情/更新/删除 |
| `/api/users` | POST | 创建用户 |
| `/api/users/<id>` | GET/PUT/DELETE | 用户详情/更新/删除 |
| `/api/consultations` | GET/POST | 咨询列表 + 新增 |
| `/api/consultations/<id>` | GET/PUT/DELETE | 咨询详情/更新/删除 |

---

## 方案一：规则模式（推荐先用这个，零成本）

### 在 Dify 中添加一个 HTTP 请求节点

**节点配置：**
- 方法：POST
- URL：`{{#API_BASE_URL#}}/agent/nl`
- Body (JSON)：
```json
{
  "query": "{{#sys.query#}}"
}
```

### 自然语言示例

以下自然语言都可以被规则引擎正确识别：

**查询类：**
- "查看所有课程"
- "查看所有语言课程"
- "查看所有背景提升课程"
- "查看德国相关的课程"
- "查看课程ID为3的详情"
- "用户ID为2的信息"
- "查看所有用户"
- "查看待跟进用户"
- "所有咨询记录"

**新增类：**
- "新增课程名称：德语高级班，类别：语言课程，价格：12800"
- "新增用户张三，学历：本科，专业：计算机，意向国家：德国"
- "创建咨询记录，用户ID：1，摘要：用户咨询德国留学"

**修改类：**
- "修改课程5的价格为9800"
- "把用户3的手机号改成13900001111"
- "修改用户2的微信为zhangsan_new"
- "把咨询记录3的状态改为已跟进"

**删除类：**
- "删除课程8"
- "删除用户5"
- "删除咨询记录6"

---

## 方案二：NL2SQL 模式（灵活度更高，需 LLM）

### 在 Dify 中创建 Chatflow/Workflow，添加以下节点链：

```
[用户输入] → [LLM: NL2SQL 生成] → [HTTP: 执行 SQL] → [LLM: 格式化结果] → [输出]
```

### 步骤 1：获取 Schema（可选，一次性获取）

先用一个 HTTP 请求节点调用 `GET {{#API_BASE_URL#}}/agent/schema`，
将返回的表结构作为后续 LLM 节点的知识背景。

### 步骤 2：LLM 节点 - 自然语言转 SQL

**System Prompt（关键！）：**
```
你是一个 NL2SQL 引擎。根据用户的自然语言和数据库表结构，生成对应的 MySQL SQL 语句。

数据库表结构如下：

表1: courses（课程表）
列: id(INT), course_name(VARCHAR), category(VARCHAR, 留学方案/语言课程/背景提升),
    sub_category(VARCHAR), country(VARCHAR), target_education(VARCHAR),
    min_gpa(DECIMAL), max_budget(DECIMAL), min_budget(DECIMAL),
    language_requirement(VARCHAR), duration(VARCHAR), price(DECIMAL),
    description(TEXT), highlights(TEXT), is_active(TINYINT, 1=上架),
    created_at(DATETIME)

表2: user_profiles（用户表）
列: id(INT), name(VARCHAR), age(INT), education(VARCHAR), major(VARCHAR),
    gpa(DECIMAL), target_country(VARCHAR), target_major(VARCHAR), budget(DECIMAL),
    language_level(VARCHAR), language_score(VARCHAR), phone(VARCHAR),
    wechat(VARCHAR), contact_method(VARCHAR),
    consultation_status(VARCHAR, pending/contacted/following_up/closed),
    created_at(DATETIME), updated_at(DATETIME)

表3: consultations（咨询记录表）
列: id(INT), user_id(INT), course_id(INT),
    conversation_summary(TEXT), recommended_courses(TEXT, JSON数组),
    user_feedback(VARCHAR), status(VARCHAR, new/recommended/interested/not_interested/consulting),
    created_at(DATETIME)

规则：
1. 只生成 SELECT/INSERT/UPDATE/DELETE 语句，禁止 DROP/ALTER/TRUNCATE
2. 只用参数化查询风格（占位符用 %s），不要拼接用户输入到 SQL 中
3. 返回严格 JSON 格式：{"sql": "生成的SQL", "params": [参数列表]}
4. 如果用户意图不明确，返回 {"sql": "", "params": [], "error": "无法理解"}

用户输入：{{#sys.query#}}
请生成 SQL：
```

### 步骤 3：HTTP 请求节点 - 执行 SQL

- 方法：POST
- URL：`{{#API_BASE_URL#}}/agent/sql`
- Body (JSON)：
```json
{
  "sql": "{{#步骤2_LLM.sql#}}",
  "params": {{#步骤2_LLM.params#}}
}
```

### 步骤 4：LLM 节点 - 格式化结果

**System Prompt：**
```
你是留学智能顾问。请将以下数据库查询结果格式化为用户友好的回复。
数据库结果：{{#步骤3_HTTP.body#}}
请用自然语言回复用户，简洁清晰。
```

---

## 方案三：混合模式（推荐生产使用）

Dify 中添加一个**条件分支**判断：

```
[用户输入]
    ↓
[LLM: 意图分类]
    ↓
    ├─ 留学推荐类 → 走原有 recommend 流程
    ├─ 简单 CRUD → 走 /api/agent/nl（规则模式）
    ├─ 复杂查询 → 走 /api/agent/sql（NL2SQL 模式）
    └─ 其他 → LLM 直接回复
```

意图分类 LLM Prompt：
```
你是意图分类器。判断用户输入属于哪种类型，返回JSON：
{"intent": "recommend|crud_simple|crud_complex|chat"}
- recommend: 留学规划、选校、推荐课程
- crud_simple: 明确的增删改查操作（如"查看所有课程""删除用户3"）
- crud_complex: 复杂的条件查询（如"查GPA大于3.0且意向德国的所有用户"）
- chat: 闲聊或留学知识问答
```

---

## 完整自然语言示例（所有 CRUD 操作）

### 课程 (courses)

| 操作 | 自然语言 |
|------|---------|
| 查所有 | "查看所有课程"、"有哪些课程"、"列出全部课程" |
| 按类别查 | "有哪些语言课程"、"查看背景提升项目"、"留学方案有哪些" |
| 按国家查 | "德国相关的课程"、"新加坡的留学方案" |
| 查详情 | "查看课程3的详情"、"课程ID为5的信息" |
| 新增 | "新增课程名称：德语高级班，类别：语言课程，价格：12800，描述：高级德语培训" |
| 修改 | "把课程5的价格改成9800"、"修改课程3的名称为德语初级班" |
| 删除 | "删除课程8"、"下架课程2" |

### 用户 (user_profiles)

| 操作 | 自然语言 |
|------|---------|
| 查所有 | "查看所有用户"、"用户列表"、"有哪些用户" |
| 查详情 | "查看用户ID为2的信息"、"用户1的详情" |
| 新增 | "新增用户张三，学历：本科，专业：计算机，意向：德国" |
| 修改 | "把用户3的手机号改成13900001111"、"修改用户2的状态为已跟进" |
| 删除 | "删除用户5" |

### 咨询记录 (consultations)

| 操作 | 自然语言 |
|------|---------|
| 查所有 | "查看所有咨询记录"、"咨询记录列表" |
| 查详情 | "咨询记录ID为3的详情" |
| 新增 | "创建咨询记录，用户ID：1，摘要：咨询德国TU9申请" |
| 修改 | "把咨询记录3的状态改为已跟进" |
| 删除 | "删除咨询记录6" |
