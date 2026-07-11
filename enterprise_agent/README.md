# 🤖 企业智能助手 · 集成文档

> 企业级后端模块，提供意向客户管理、请假审批、日报管理、组织架构、投诉反馈、成绩管理、知识库问答、NL2SQL 自然语言查询等功能。
>
> **版本:** 2.0.0 | **技术栈:** Python 3.9+ / FastAPI / SQLAlchemy / pymysql / Streamlit

---

## 目录

1. [项目概述](#1-项目概述)
2. [项目结构](#2-项目结构)
3. [安装步骤](#3-安装步骤)
4. [配置说明](#4-配置说明)
5. [启动方式](#5-启动方式)
6. [API 接口清单](#6-api-接口清单)
7. [接口调用示例](#7-接口调用示例)
8. [整合步骤](#8-整合步骤)
9. [常见问题](#9-常见问题)

---

## 1. 项目概述

### 功能范围

| 模块 | 接口数 | 说明 |
|------|--------|------|
| 意向客户管理 | 5 | 客户录入/查询/详情/状态更新/跟进记录 |
| 请假管理 | 4 | 替学生请假/员工请假/批量审批/待审批列表 |
| 日报管理 | 2 | 提交日报/查询日报列表 |
| 组织架构 | 1 | 树形组织架构（部门+负责人+员工） |
| 待办汇总 | 1 | 合并待审批请假 + 待处理投诉 |
| 投诉反馈 | 2 | 投诉列表/处理投诉 |
| 成绩管理 | 2 | 录入成绩/查询成绩 |
| 知识库问答 | 1 | 规章制度检索（当前为 Mock 实现） |
| NL2SQL 查询 | 1 | 自然语言转 SQL，仅允许 SELECT |

### 权限体系

| 角色 | 权限 |
|------|------|
| 管理者 | 可查看和操作**全部**数据 |
| 员工 | 只能查看和操作**自己负责**的数据（sales_user_id=自己） |
| 学员 | 仅可查看组织架构、知识库，其余接口返回 403 |
| 游客 | 同上 |

> ⚠️ **安全说明：** 当前版本的身份信息（`current_user_id` + `current_user_type`）由前端/调用方传入，服务端校验用户类型合法性。生产环境请替换为 JWT / Session 鉴权。

---

## 2. 项目结构

```
enterprise_agent/                      # 独立模块目录
├── README.md                          # ← 本文档
├── .env                               # 数据库配置（敏感，已加入 .gitignore）
├── .gitignore
├── __init__.py
│
├── config.py                          # 应用 + 数据库 + 日志配置
├── database.py                        # SQLAlchemy 引擎 + 会话管理
├── models.py                          # ORM 模型（10张表）
├── schemas.py                         # Pydantic 请求/响应模型
├── utils.py                           # 公共工具（权限校验、常量）
├── main.py                            # FastAPI 入口（注册路由）
│
├── routers/                           # API 路由模块（共9个）
│   ├── __init__.py
│   ├── customer.py                    # 意向客户管理（5个接口）
│   ├── leave.py                       # 请假管理（4个接口）
│   ├── report.py                      # 日报管理（2个接口）
│   ├── organization.py                # 组织架构（1个接口）
│   ├── todo.py                        # 待办汇总（1个接口）
│   ├── complaint.py                   # 投诉反馈（2个接口）
│   ├── score.py                       # 成绩管理（2个接口）
│   ├── knowledge.py                   # 知识库问答（1个接口）
│   └── nl2sql.py                      # NL2SQL 查询（1个接口）
│
├── frontend/                          # 测试前端（Streamlit，可选）
│   ├── __init__.py
│   ├── app.py                         # Streamlit 对话界面
│   ├── utils.py                       # API 调用封装
│   └── intent.py                      # 意图识别 + 结果格式化
│
├── seed_data.py                       # 测试数据（幂等，可重复跑）
├── sync_accounts.py                   # 账户同步（employee+student → account）
├── test_api.py                        # 自动化测试（14项）
│
├── start.bat                          # Windows 快捷启动菜单
└── __pycache__/                       # Python 字节码（可忽略）
```

**关键文件说明：**

| 文件 | 同事需要做什么 |
|------|--------------|
| `config.py` | 确认 `.env` 配置正确，一般不用改 |
| `database.py` | 会话管理，一般不用改 |
| `models.py` | 如需新增表，在此添加 ORM 模型 |
| `utils.py` | 权限校验函数，整合时确认与主项目的鉴权方式是否兼容 |
| `routers/*.py` | 每个文件独立，可按需引入，不需要的模块直接不注册即可 |
| `main.py` | 注册路由的地方，整合时移到主项目的 FastAPI app 中 |

---

## 3. 安装步骤

### 环境要求

- Python 3.9+
- MySQL 8.0+（数据库已预先部署）

### 依赖安装

```bash
pip install fastapi uvicorn sqlalchemy pymysql python-dotenv
```

完整依赖清单：

```
fastapi>=0.100.0
uvicorn[standard]>=0.20.0
sqlalchemy>=2.0.0
pymysql>=1.0.0
python-dotenv>=1.0.0
```

### 测试前端（可选）

```bash
pip install streamlit requests
```

---

## 4. 配置说明

### .env 文件

在 `enterprise_agent/` 目录下创建 `.env` 文件（已提供）：

```ini
# 数据库连接
DB_HOST=192.168.48.121
DB_PORT=3306
DB_USER=offer
DB_PASSWORD=123456
DB_NAME=dify_pro

# 应用配置
APP_HOST=0.0.0.0
APP_PORT=8001
APP_DEBUG=true

# 日志级别
LOG_LEVEL=INFO
```

### 配置加载优先级

1. 系统环境变量（最高）
2. `.env` 文件
3. `config.py` 中的默认值（最低）

### 安全提醒

> ⚠️ 生产环境请修改数据库密码，`.env` 文件已加入 `.gitignore`，不会提交到版本控制。如果使用默认密码 `123456`，启动时控制台会打印安全警告。

---

## 5. 启动方式

### 方式1：命令行启动（推荐）

```bash
cd D:/dify_0511/dify_pro
python -m uvicorn enterprise_agent.main:app --host 0.0.0.0 --port 8001 --reload
```

### 方式2：双击 start.bat

在 Windows 资源管理器中双击 `enterprise_agent/start.bat`，选择 `[1]` 启动后端。

### 验证启动

启动后访问：
- **API 文档:** http://localhost:8001/docs
- **健康检查:** http://localhost:8001/health

预期响应：
```json
{"status":"ok","service":"enterprise_agent","version":"2.0.0"}
```

### 测试前端启动（可选）

```bash
streamlit run enterprise_agent/frontend/app.py --server.port 8501
```

---

## 6. API 接口清单

统一响应格式：

```json
{
    "code": 0,          // 0=成功，非0=失败
    "msg": "success",   // 提示信息
    "data": { ... }     // 响应数据
}
```

所有接口均需传入鉴权参数：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `current_user_id` | int | 是 | 当前操作用户ID |
| `current_user_type` | string | 是 | 用户类型：`员工`/`管理者`/`学员`/`游客` |

---

### 一、意向客户管理（5个接口）

#### 1.1 录入客户

```
POST /api/agent/customer/add
```

**请求体：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `customer_name` | string | 是 | 客户姓名（1-64字符） |
| `customer_age` | int | 否 | 年龄（0-150） |
| `customer_gender` | string | 否 | 性别 |
| `customer_phone` | string | 否 | 联系电话（最多20字符） |
| `customer_source` | string | 否 | 客户来源 |
| `customer_demand` | string | 否 | 客户需求 |
| `current_user_id` | int | 是 | 当前用户ID（自动设为销售人员） |
| `current_user_type` | string | 是 | 当前用户类型 |

**响应示例：**
```json
{"code": 0, "msg": "success", "data": {"customer_id": 1}}
```

---

#### 1.2 查询客户列表

```
GET /api/agent/customer/list
```

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 模糊搜索姓名/电话 |
| `status` | string | 否 | 筛选状态：`意向中`/`已签约`/`已流失` |
| `page` | int | 否 | 页码（默认1） |
| `page_size` | int | 否 | 每页数量（默认20，最大100） |
| `current_user_id` | int | 是 | 用户ID |
| `current_user_type` | string | 是 | 用户类型 |

**权限：** 管理者查看全部，员工只看自己负责的。

**响应示例：**
```json
{
    "code": 0,
    "msg": "success",
    "data": {
        "total": 20,
        "page": 1,
        "page_size": 10,
        "list": [
            {
                "customer_id": 1,
                "customer_name": "张明",
                "customer_phone": "13910001001",
                "customer_source": "网络",
                "current_status": "意向中",
                "sales_user_id": 112,
                "follow_record": "\n【2026-07-10 10:00:00】初步沟通了留学意向",
                "create_time": "2026-07-11 10:00:00",
                "update_time": "2026-07-11 10:00:00"
            }
        ]
    }
}
```

---

#### 1.3 客户详情

```
GET /api/agent/customer/{customer_id}
```

**权限：** 管理者可查看任意，员工只能查看自己负责的。

---

#### 1.4 更新客户状态

```
PUT /api/agent/customer/status
```

**请求体：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `customer_id` | int | 是 | 客户ID |
| `new_status` | string | 是 | 新状态：`意向中`/`已签约`/`已流失` |

---

#### 1.5 追加跟进记录

```
PUT /api/agent/customer/follow
```

**请求体：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `customer_id` | int | 是 | 客户ID |
| `follow_record` | string | 是 | 跟进内容（自动追加【时间】前缀） |

---

### 二、请假管理（4个接口）

#### 2.1 替学生请假

```
POST /api/agent/leave/student
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `student_name` | string | 是 | 学生姓名 |
| `leave_type` | string | 是 | 请假类型：`事假`/`病假`/`年假`/`其他` |
| `start_date` | string | 是 | 开始日期（YYYY-MM-DD） |
| `end_date` | string | 是 | 结束日期 |
| `reason` | string | 否 | 请假原因 |

#### 2.2 员工自己请假

```
POST /api/agent/leave/employee
```

参数同上（无 `student_name`）。

#### 2.3 批量审批

```
POST /api/agent/leave/batch_approve
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `leave_ids` | int[] | 是 | 请假ID数组（最多50个） |
| `action` | string | 是 | `approve`（通过）或 `reject`（驳回） |

**权限：** 仅管理者。

#### 2.4 待审批列表

```
GET /api/agent/leave/todo
```

**权限：** 管理者查看全部待审批，员工只看自己提交的。

---

### 三、日报管理（2个接口）

#### 3.1 提交日报

```
POST /api/agent/report/submit
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `report_content` | string | 是 | 日报内容 |
| `report_date` | string | 是 | 日期（YYYY-MM-DD） |

> `user_id` 和 `dept_id` 从 `account` 表自动查询。

#### 3.2 查询日报列表

```
GET /api/agent/report/list
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `start_date` | string | 否 | 筛选开始日期 |
| `end_date` | string | 否 | 筛选结束日期 |
| `page` | int | 否 | 页码 |
| `page_size` | int | 否 | 每页数量 |

**权限：** 管理者查看全部，员工只看自己的。

---

### 四、组织架构（1个接口）

```
GET /api/agent/organization/tree
```

**权限：** 所有人可查看。

**响应结构：**
```json
{
    "code": 0,
    "data": {
        "tree": [{
            "dept_id": 1,
            "dept_name": "咨询部",
            "manager_name": "王建国",
            "employees": [
                {"emp_id": 112, "emp_name": "张伟", "position": "资深咨询师"}
            ],
            "children": [
                {"dept_id": 6, "dept_name": "美国咨询组", "employees": [...]}
            ]
        }]
    }
}
```

---

### 五、待办汇总（1个接口）

```
GET /api/agent/todo/all
```

**响应示例：**
```json
{
    "code": 0,
    "data": {
        "total": 8,
        "leave_pending": 4,
        "complaint_pending": 4,
        "list": [
            {"todo_type": "请假审批", "todo_id": 1, "detail": "类型：病假，2026-07-14 至 2026-07-15", "status": "待审批"},
            {"todo_type": "投诉处理", "todo_id": 1, "detail": "对课程安排不满意...", "status": "待处理"}
        ]
    }
}
```

---

### 六、投诉反馈（2个接口）

#### 6.1 投诉列表

```
GET /api/agent/complaint/list
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 否 | 筛选：`待处理`/`处理中`/`已完结`/`驳回` |

**权限：** 管理者全部，员工只看自己负责的。

#### 6.2 处理投诉

```
PUT /api/agent/complaint/handle
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `complaint_id` | int | 是 | 投诉ID |
| `new_status` | string | 是 | `处理中` 或 `已完结` |
| `handler_user_id` | int | 否 | 处理人ID |

---

### 七、成绩管理（2个接口）

#### 7.1 录入成绩

```
POST /api/agent/score/add
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `student_id` | int | 是 | 学生ID |
| `subject` | string | 是 | 科目 |
| `score` | float | 是 | 分数（0-100） |
| `exam_type` | string | 否 | 考试类型 |
| `exam_date` | string | 否 | 考试日期 |

#### 7.2 查询成绩

```
GET /api/agent/score/list
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `student_id` | int | 否 | 学生ID |
| `subject` | string | 否 | 科目筛选 |

---

### 八、知识库问答（1个接口）

```
POST /api/agent/knowledge/query
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | 是 | 用户问题 |

**响应：**
```json
{
    "code": 0,
    "data": {
        "question": "请假怎么请",
        "answer": "员工请假需提前提交申请...",
        "source": "《员工考勤管理制度》第3章"
    }
}
```

> 当前为 Mock 实现，知识库内容在 `routers/knowledge.py` 的 `KNOWLEDGE_BASE` 字典中。生产环境请替换为数据库或向量检索。

---

### 九、NL2SQL 查询（1个接口）

```
POST /api/agent/query/nl2sql
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 自然语言查询 |

**安全限制：**
- ❌ 仅允许 `SELECT` 语句
- ❌ 禁止 `DROP`/`DELETE`/`INSERT`/`UPDATE`/`ALTER`/`TRUNCATE`/`CREATE` 等关键字
- ❌ 禁止多条语句（分号分隔）
- ✅ 自动追加 `LIMIT 200`

**响应：**
```json
{
    "code": 0,
    "data": {
        "natural_query": "查看所有客户",
        "generated_sql": "SELECT * FROM intention_customer ORDER BY create_time DESC LIMIT 200",
        "summary": "查询完成，共找到 20 条记录",
        "count": 20,
        "results": [{"customer_id": 1, "customer_name": "张明", ...}]
    }
}
```

---

## 7. 接口调用示例

### curl 示例

```bash
# 1. 待办汇总
curl "http://localhost:8001/api/agent/todo/all?current_user_id=1&current_user_type=%E7%AE%A1%E7%90%86%E8%80%85"

# 2. 客户列表
curl "http://localhost:8001/api/agent/customer/list?page=1&page_size=10&current_user_id=1&current_user_type=%E7%AE%A1%E7%90%86%E8%80%85"

# 3. 录入客户
curl -X POST "http://localhost:8001/api/agent/customer/add" \
  -H "Content-Type: application/json" \
  -d '{"customer_name":"张三","customer_age":25,"customer_gender":"男","customer_phone":"13800138000","customer_source":"网络","customer_demand":"咨询留学","current_user_id":1,"current_user_type":"管理者"}'

# 4. 知识库问答
curl -X POST "http://localhost:8001/api/agent/knowledge/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"公司年假怎么算","current_user_id":1,"current_user_type":"员工"}'

# 5. 组织架构
curl "http://localhost:8001/api/agent/organization/tree?current_user_id=1&current_user_type=%E7%AE%A1%E7%90%86%E8%80%85"
```

### JavaScript (fetch) 示例

```javascript
// 配置
const API_BASE = 'http://localhost:8001/api/agent';
const AUTH = { current_user_id: 1, current_user_type: '管理者' };

// 通用请求函数
async function api(path, options = {}) {
  const { method = 'GET', body, params = {} } = options;
  const auth = { current_user_id: 1, current_user_type: '管理者' };
  let url = API_BASE + path;
  const query = new URLSearchParams({ ...auth, ...params });
  if (method === 'GET') url += '?' + query.toString();

  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify({ ...body, ...auth });

  const res = await fetch(url, opts);
  return res.json();
}

// 调用示例
async function demo() {
  // 1. 获取待办
  const todo = await api('/todo/all');
  console.log('待办:', todo.data);

  // 2. 查询客户
  const customers = await api('/customer/list', { params: { page: 1, page_size: 10 } });
  console.log('客户:', customers.data);

  // 3. 提交日报
  const report = await api('/report/submit', {
    method: 'POST',
    body: { report_content: '今日工作内容...', report_date: '2026-07-11' }
  });
  console.log('日报:', report);
}
```

### Python (requests) 示例

```python
import requests

API_BASE = "http://localhost:8001/api/agent"
AUTH = {"current_user_id": 1, "current_user_type": "管理者"}

# GET 请求
def get(path, params=None):
    p = {**AUTH, **(params or {})}
    r = requests.get(f"{API_BASE}{path}", params=p)
    return r.json()

# POST 请求
def post(path, body=None):
    b = {**AUTH, **(body or {})}
    r = requests.post(f"{API_BASE}{path}", json=b)
    return r.json()

# 使用
print(get("/todo/all"))
print(post("/customer/add", {"customer_name": "测试客户"}))
print(post("/knowledge/query", {"question": "上班时间"}))
```

---

## 8. 整合步骤

> 同事将本模块集成到主项目中的标准流程。

### 步骤1：复制代码

将 `enterprise_agent/` 目录整体复制到主项目的 `app/modules/` 下（或任意目录）：

```
your-main-project/
├── app/
│   ├── main.py              # 你的 FastAPI 主入口
│   ├── routers/
│   └── modules/
│       └── enterprise_agent/  # ← 复制到这里
```

### 步骤2：安装依赖

```bash
pip install fastapi uvicorn sqlalchemy pymysql python-dotenv
```

### 步骤3：注册路由

在你的 `main.py` 中：

```python
from fastapi import FastAPI
from app.modules.enterprise_agent.routers import (
    customer, leave, report, organization,
    todo, complaint, score, knowledge, nl2sql,
)

app = FastAPI()

# 注册企业智能助手路由（全部以 /api/agent 为前缀）
app.include_router(customer.router, prefix="/api/agent")
app.include_router(leave.router, prefix="/api/agent")
app.include_router(report.router, prefix="/api/agent")
app.include_router(organization.router, prefix="/api/agent")
app.include_router(todo.router, prefix="/api/agent")
app.include_router(complaint.router, prefix="/api/agent")
app.include_router(score.router, prefix="/api/agent")
app.include_router(knowledge.router, prefix="/api/agent")
app.include_router(nl2sql.router, prefix="/api/agent")
```

> 如果不需要某个模块，直接删掉对应的 `include_router` 行即可。

### 步骤4：配置数据库

在你的项目根目录创建 `.env` 文件：

```ini
DB_HOST=192.168.48.121
DB_PORT=3306
DB_USER=offer
DB_PASSWORD=123456
DB_NAME=dify_pro
```

或设置环境变量。

### 步骤5：替换鉴权（重要）

当前模块的身份校验通过 `enterprise_agent/utils.py` 中的函数实现：

```python
from enterprise_agent.utils import require_operator, is_manager

# require_operator(user_type) → 检查是否员工/管理者，否则抛出 HTTPException(403)
# is_manager(user_type) → bool
```

**生产环境整合时建议：**

1. 替换 `require_operator` 为你主项目的 JWT Token 校验
2. 删除每个 router 中的 `current_user_id`/`current_user_type` 请求参数
3. 改为从 `request.headers` 或 `request.state.user` 中提取

如果暂时不想换，保持现状也可以工作——前端每次请求传入这两个参数即可。

### 步骤6：可选 — 初始化测试数据

```bash
python -m app.modules.enterprise_agent.seed_data
```

幂等设计，可重复运行。

---

## 9. 常见问题

### Q1: 启动报错 `ModuleNotFoundError: No module named 'enterprise_agent'`

**原因：** Python 找不到 `enterprise_agent` 包。  
**解决：** 确保启动命令在 `dify_pro/` 目录下执行，或手动添加路径：

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

### Q2: 数据库连接失败

**原因：** `.env` 文件配置错误或数据库未启动。  
**解决：** 检查 `.env` 中的 `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME`。

### Q3: 接口返回 `403` 权限不足

**原因：** `current_user_type` 不是 `员工` 或 `管理者`。  
**解决：** 检查传入的用户类型，学员和游客只能访问组织架构和知识库。

### Q4: `PendingRollbackError` 后续请求全挂

**原因：** 前一个请求异常导致会话回滚未正确处理。  
**解决：** 已修复——`get_db()` 使用 `try→yield→else→commit→finally→close` 模式。

### Q5: 录入成绩报 `Duplicate entry`

**原因：** 数据库 `student_score.subject` 字段有唯一索引。  
**解决：** 同一学生已存在该科目的成绩时，使用更新而非新增。

### Q6: NL2SQL 返回 400 "禁止的关键字"

**原因：** 查询中包含了 `DROP`/`DELETE`/`INSERT` 等关键字。  
**解决：** 安全拦截，正常使用。如需执行非 SELECT 语句，直接调用对应业务接口。

### Q7: 种子数据跑完没有变化

**原因：** 幂等设计——数据已存在则会跳过。  
**解决：** 如需重置，先清表再跑：

```sql
TRUNCATE intention_customer;
TRUNCATE leave_application;
-- ... 其他表
```

### Q8: 端口 8001 被占用

**解决：** 修改 `.env` 中的 `APP_PORT` 或启动时指定：

```bash
python -m uvicorn enterprise_agent.main:app --host 0.0.0.0 --port 8002
```

### Q9: 前端页面（index.html）在哪？

**答：** 已被移除。当前测试前端使用 Streamlit：

```bash
streamlit run enterprise_agent/frontend/app.py --server.port 8501
```

同事整合时请使用 Swagger 文档（`http://localhost:8001/docs`）或直接调用 API。

---

> **文档版本：** 2.0.0 | **最后更新：** 2026-07-11 | **维护人：** 企业智能助手开发组
