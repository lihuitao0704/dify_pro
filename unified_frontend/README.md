# 粤教留学 · 统一前端

统一前端静态资源目录，由 **customer_agent(:9000)** 通过 `/portal/*` 托管，无需独立 Web 服务器。

访问地址: http://localhost:9000/portal

---

## 一、目录结构

```
unified_frontend/
├── index.html              门户首页 (含嵌入式客服聊天框 + 智能诊断入口)
├── student-dashboard.html  学生工作台 (学业 / 请假 / 心理 / 升学)
├── employee-dashboard.html 员工工作台 (业绩 / 日程 / 考核)
├── css/
│   ├── base.css            全局样式 (变量 / 重置 / 通用组件)
│   ├── portal.css          门户首页样式
│   ├── chat.css            通用聊天气泡 / 输入框样式
│   └── dashboard.css       工作台侧边栏 + 面板样式
└── js/
    ├── utils.js            全局工具 (toast / api / escapeHTML)
    ├── auth.js             统一鉴权 (token / 角色 / 登录态)
    ├── portal.js           门户首页逻辑 (登录 tabs / 公众聊天 / 智能诊断)
    ├── chat.js             ChatWidget 通用聊天组件
    ├── student-dashboard.js 学生工作台逻辑
    └── employee-dashboard.js 员工工作台逻辑
```

---

## 二、页面路由

所有页面由 customer_agent 的 `portal_routes.py` 显式注册，路径如下：

| URL | 文件 | 说明 |
|-----|------|------|
| `/` 或 `/login` | `index.html` | 登录页 (门户首页自动跳转) |
| `/dashboard` | `index.html` | 工作台 (已登录时) |
| `/portal` | `index.html` | 统一门户 (含嵌入式聊天 + 智能诊断) |
| `/portal/student-dashboard` | `student-dashboard.html` | 学生工作台 |
| `/portal/employee-dashboard` | `employee-dashboard.html` | 员工工作台 |
| `/portal/css/{filename}` | `css/*.css` | 门户样式 |
| `/portal/js/{filename}` | `js/*.js` | 门户脚本 |
| `/static/...` | `static/` | 静态资源 (备用) |

业务接口 (chat / CRUD / NL2SQL) 由同一台 customer_agent 承接，通过 REST 调用。

---

## 三、JS 模块

### 3.1 utils.js — 全局工具

| 函数 | 说明 |
|------|------|
| `toast(msg, type, duration)` | 右上角轻提示 (success / error) |
| `api(path, opts)` | 封装 fetch + JSON 解析 |
| `escapeHTML(str)` | XSS 转义 |

### 3.2 auth.js — 统一鉴权

```js
const Auth = {
  get()            // 从 localStorage 读取认证
  set(data)        // 持久化认证
  clear()          // 清除认证
  isLoggedIn()     // 是否登录 (含 token 过期检测)
  role()           // 当前角色 (student/employee)
  userId()         // 当前用户 ID
  userName()       // 当前用户名
  studentLogin(user, pass)   // 学生登录
  employeeLogin(user, pass)  // 员工登录 (含 demo 账号 fallback)
  requireRole(role)          // 角色检查，未通过则跳登录页
}
```

凭证存储在 `localStorage['dify_auth']`。

### 3.3 portal.js — 门户首页

启动入口 `initLoginTabs / initLoginForms / initPublicChat / initSmartDiagnose`。

- 登录 Modal 具 student / employee 两个 Tab
- "智能诊断" 按钮展开学生能力评估表
- 嵌入式公众聊天框直接调 `/chat`

### 3.4 chat.js — ChatWidget 通用聊天组件

可复用组件。构造参数：

```js
const chat = new ChatWidget({
  apiUrl: 'http://localhost:8000/chat',     // 后端 /chat 地址
  container: '#chatMessages',                // 消息容器 selector
  input: '#chatInput',                       // 输入框 selector
  sendBtn: '#sendBtn',                       // 发送按钮 selector
  onPreSend: (msg) => ({ message: msg, session_id: chat.sessionId || '' }),
  onReply: (data) => { /* 回调 */ },
});
```

### 3.5 student-dashboard.js — 学生工作台

| 区域 | 内容 |
|------|------|
| 侧边栏 | 用户信息 + 导航 + 快捷操作 |
| 学业 | 成绩 / 选课 / 毕业进度 |
| 请假 | 在线请假申请 |
| 心理 | 心理测评 + 关怀 |
| 升学 | 留学智能咨询 (接入 /chat) |

后端: `http://localhost:8000/*` (学生智能助手)

### 3.6 employee-dashboard.js — 员工工作台

| 区域 | 内容 |
|------|------|
| 侧边栏 | 员工信息 + 导航 |
| 业绩 | 业绩看板 |
| 团队 | 员工管理 |
| 日程 | 日程 |
| 考核 | 考核评分 |

后端: `http://localhost:8001/*` (企业智能助手)

---

## 四、CSS 体系

| 文件 | 作用 |
|------|------|
| `base.css` | CSS 变量(颜色/圆角/阴影) + reset + 通用按钮/卡片/表单 |
| `portal.css` | 门户首页布局 |
| `chat.css` | 聊天气泡 + 输入框 + typing 动画 |
| `dashboard.css` | 工作台侧边栏 + 面板 + 模块化卡片 |

设计令牌统一在 `base.css` 顶部 `:root` 声明 (主色 / 强调色 / 中性灰)，换肤只需改这些变量。

---

## 五、后端接口对接

| 前端调用 | 后端接口 | 说明 |
|----------|----------|------|
| `/chat` | `POST /chat` | 主对话 (7+1 意图分类) |
| `/auth/login` | `POST /auth/login` | 统一登录 |
| `/api/v1/profiles` | `POST/GET /api/v1/profiles[/*]` | 画像 CRUD + 推荐 |
| `/api/v1/courses` | `* /api/v1/courses[/*]` | 课程 CRUD |
| `/api/v1/consultations` | `* /api/v1/consultations[/*]` | 咨询记录 CRUD |
| `/api/v1/nl2sql/query` | `POST /api/v1/nl2sql/query` | NL2SQL 查 / 写 |
| `/api/v1/events/nl2sql` | `POST /api/v1/events/nl2sql` | 活动讲座自然语言 |
| `/api/v1/events/lectures` | `* /api/v1/events/lectures[/*]` | 讲座 CRUD |
| `/api/v1/events/activities` | `* /api/v1/events/activities[/*]` | 活动 CRUD |
| `/api/v1/events/registrations/*` | `* /api/v1/events/registrations/*` | 报名记录 |
| `/admin/kb-status` `kb-reload` | `GET/POST /admin/*` | 知识库管理 |

> 详细接口字段请参见 `customer_agent/API_DOC.md`。

---

## 六、本地开发与调试

### 6.1 启动后端

```bash
# 启动全部微服务: student/enterprise/assessment/report/customer
python start_all.py

# 仅启动客服 Agent (含统一前端)
python start_all.py customer
# 或: python -m customer_agent.main
```

服务启动后即自动托管本前端目录，浏览器打开 http://localhost:9000/portal 即可。

### 6.2 跨域

customer_agent 已允许 `Access-Control-Allow-Origin: *`，
可直接在其他端口 (如 Vite dev server) 开发时反向代理到 9000。

### 6.3 调试技巧

- 浏览器 DevTools → Network 面板过滤 `localhost:9000` 看所有 API 调用
- `/admin/kb-status` 快速验证知识库加载
- `/context/{session_id}` 查看某会话完整上下文

---

## 七、打包与部署

前端为纯静态 HTML/CSS/JS，无构建步骤。部署时只要：

1. 把 `unified_frontend/` 整个目录放到 `customer_agent/` 同级
2. `customer_agent/portal_routes.py` 中 `_unified_dir` 通过相对路径定位，无需调整
3. 启动 customer_agent 即可对外服务
