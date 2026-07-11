"""
对话式企业智能助手 - Streamlit 前端
启动：streamlit run frontend/app.py --server.port 8501
"""
import streamlit as st
import sys
import os

# 确保能导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from intent import recognize, format_result, parse_date, parse_leave_type, parse_student_name
from utils import (
    get_todo_all, get_customer_list, get_customer_detail,
    add_customer, update_customer_status, add_customer_follow,
    get_leave_todo, submit_leave_employee, submit_leave_student,
    batch_approve_leave, submit_report, get_report_list,
    get_organization_tree, get_complaint_list, handle_complaint,
    add_score, get_score_list, query_knowledge, query_nl2sql,
    CURRENT_USER_ID, CURRENT_USER_TYPE,
)

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="企业智能助手",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 自定义 CSS（ChatGPT 风格）
# ============================================================
st.markdown("""
<style>
    /* 全局 */
    .stApp { background-color: #f0f2f6; }
    .main .block-container { padding: 0; max-width: 100%; }

    /* 顶部标题栏 */
    .chat-header {
        background: #fff;
        padding: 12px 24px;
        border-bottom: 1px solid #e4e7ec;
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: sticky;
        top: 0;
        z-index: 100;
    }
    .chat-header h1 {
        font-size: 18px;
        font-weight: 600;
        margin: 0;
        color: #172b4d;
    }
    .chat-header .user-info {
        font-size: 13px;
        color: #5e6c84;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .chat-header .user-badge {
        background: #0052cc;
        color: white;
        padding: 2px 10px;
        border-radius: 100px;
        font-size: 11px;
        font-weight: 500;
    }

    /* 对话容器 */
    .chat-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 20px 24px 100px;
    }
    .chat-message {
        display: flex;
        margin-bottom: 20px;
        animation: fadeIn 0.3s ease;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    .chat-message.user { justify-content: flex-end; }
    .chat-message.bot { justify-content: flex-start; }

    .chat-bubble {
        max-width: 72%;
        padding: 12px 18px;
        border-radius: 16px;
        font-size: 14px;
        line-height: 1.6;
        box-shadow: 0 1px 3px rgba(0,0,0,.06);
        white-space: pre-wrap;
        word-break: break-word;
    }
    .chat-bubble.user {
        background: #0052cc;
        color: white;
        border-bottom-right-radius: 4px;
    }
    .chat-bubble.bot {
        background: white;
        color: #172b4d;
        border: 1px solid #e4e7ec;
        border-bottom-left-radius: 4px;
    }
    .chat-bubble .label {
        font-size: 11px;
        font-weight: 600;
        color: #7a869a;
        margin-bottom: 6px;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    .chat-bubble.user .label { color: rgba(255,255,255,.6); }
    .chat-bubble.bot .label { color: #7a869a; }

    /* 输入区 */
    .input-area {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: #fff;
        border-top: 1px solid #e4e7ec;
        padding: 12px 24px;
        z-index: 100;
        backdrop-filter: blur(10px);
    }
    .input-area .input-inner {
        max-width: 800px;
        margin: 0 auto;
        display: flex;
        gap: 10px;
        align-items: center;
    }
    .input-area input {
        flex: 1;
        padding: 10px 16px;
        border: 1px solid #dfe1e6;
        border-radius: 24px;
        font-size: 14px;
        outline: none;
        background: #f4f5f7;
        transition: all 0.15s;
    }
    .input-area input:focus {
        border-color: #0052cc;
        background: #fff;
        box-shadow: 0 0 0 2px rgba(0,82,204,.1);
    }
    .input-area button {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        border: none;
        background: #0052cc;
        color: white;
        font-size: 18px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        transition: all 0.15s;
    }
    .input-area button:hover { background: #0047b3; }

    /* 快捷菜单 */
    .quick-btn {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 14px;
        margin-bottom: 4px;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.12s;
        font-size: 13px;
        color: #172b4d;
        border: none;
        background: transparent;
        width: 100%;
        text-align: left;
        font-family: inherit;
    }
    .quick-btn:hover { background: #e6f0ff; color: #0052cc; }
    .quick-btn .icon { font-size: 16px; width: 24px; text-align: center; }
    .quick-btn .text { font-weight: 500; }
    .quick-btn .sub { font-size: 11px; color: #7a869a; }

    /* 侧栏标题 */
    .sidebar-title {
        font-size: 16px;
        font-weight: 700;
        padding: 16px 14px 8px;
        color: #172b4d;
    }
    .sidebar-sub {
        font-size: 11px;
        color: #7a869a;
        padding: 0 14px 12px;
        border-bottom: 1px solid #e4e7ec;
        margin-bottom: 8px;
    }

    /* 分隔线 */
    .section-title {
        font-size: 11px;
        font-weight: 600;
        color: #97a0af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 12px 14px 4px;
    }

    /* Markdown inside chat */
    .chat-bubble.bot strong { color: #172b4d; }
    .chat-bubble code {
        background: #f4f5f7;
        padding: 1px 5px;
        border-radius: 3px;
        font-size: 12px;
    }
    .chat-bubble a { color: #0052cc; }

    /* Streamlit 隐藏 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    div[data-testid="stToolbar"] {display: none;}
    div[data-testid="stSidebarNav"] {display: none;}

    /* 滚动 */
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-thumb { background: #dfe1e6; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 会话状态初始化
# ============================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "user_id" not in st.session_state:
    st.session_state.user_id = CURRENT_USER_ID
if "user_type" not in st.session_state:
    st.session_state.user_type = CURRENT_USER_TYPE
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"
if "pending_input" not in st.session_state:
    st.session_state.pending_input = ""

# ============================================================
# 处理用户消息
# ============================================================

def _uid():
    """从 session 获取当前用户ID"""
    return st.session_state.get("user_id", 1)


def _utype():
    """从 session 获取当前用户类型"""
    return st.session_state.get("user_type", "管理者")


def process_message(user_text: str):
    """处理用户消息：识别意图 → 调用接口 → 返回结果"""
    if not user_text.strip():
        return

    intent = recognize(user_text)
    action = intent["action"]
    label = intent["label"]

    st.session_state.messages.append({"role": "user", "content": user_text})

    result_text = execute_action(action, intent, user_text, _uid(), _utype())

    st.session_state.messages.append({"role": "bot", "content": result_text, "label": label})


# ============================================================
# Action Handlers — 每个动作对应一个函数，新增只需在这里加
# ============================================================

def _handle_todo_all(raw_text, user_id, user_type):
    data = get_todo_all(user_id=user_id, user_type=user_type)
    return format_result("get_todo_all", data)


def _handle_customer_list(raw_text, user_id, user_type):
    kw = ""
    for w in ["搜索", "查找", "找", "查询"]:
        if w in raw_text:
            parts = raw_text.split(w, 1)
            if len(parts) > 1 and parts[1].strip():
                kw = parts[1].strip()
                break
    data = get_customer_list(keyword=kw, user_id=user_id, user_type=user_type)
    return format_result("get_customer_list", data)


def _handle_add_customer(raw_text, user_id, user_type):
    data = add_customer({"customer_name": "新客户", "customer_source": "对话录入"}, user_id=user_id, user_type=user_type)
    return format_result("add_customer", data)


def _handle_parse_customer(raw_text, user_id, user_type):
    import re
    if "跟进" in raw_text:
        m = re.search(r"客户[#\s]*(\d+)", raw_text)
        if m:
            cid = int(m.group(1))
            content = raw_text.split("跟进", 1)[1].strip() if "跟进" in raw_text else "跟进沟通"
            data = add_customer_follow(cid, content, user_id=user_id, user_type=user_type)
            return format_result("add_customer_follow", data)
        return "请指定客户ID，例如：跟进客户 #3 今天进行了电话沟通"
    if "状态" in raw_text or "改" in raw_text:
        m = re.search(r"客户[#\s]*(\d+)", raw_text)
        if m:
            cid = int(m.group(1))
            status = "已签约" if "签约" in raw_text else "已流失" if "流失" in raw_text else "意向中"
            data = update_customer_status(cid, status, user_id=user_id, user_type=user_type)
            return format_result("update_customer_status", data)
        return "请指定客户ID和状态，例如：改客户 #3 状态为已签约"
    return "请指定操作：跟进客户或更改客户状态"


def _handle_leave_todo(raw_text, user_id, user_type):
    data = get_leave_todo(user_id=user_id, user_type=user_type)
    return format_result("get_leave_todo", data)


def _handle_leave_employee(raw_text, user_id, user_type):
    leave_type = parse_leave_type(raw_text)
    start = parse_date(raw_text)
    reason = ""
    if "因为" in raw_text:
        reason = raw_text.split("因为", 1)[1].strip()
    if "原因" in raw_text:
        reason = raw_text.split("原因", 1)[1].strip() or reason
    data = submit_leave_employee(leave_type, start, start, reason, user_id=user_id, user_type=user_type)
    return f"{format_result('submit_leave', data)}\n📅 类型：{leave_type}\n📆 日期：{start}\n📝 原因：{reason or '无'}"


def _handle_leave_student(raw_text, user_id, user_type):
    student_name = parse_student_name(raw_text) or "学生"
    leave_type = parse_leave_type(raw_text)
    start = parse_date(raw_text)
    data = submit_leave_student(student_name, leave_type, start, start, "", user_id=user_id, user_type=user_type)
    return f"{format_result('submit_leave', data)}\n👤 学生：{student_name}\n📅 类型：{leave_type}\n📆 日期：{start}"


def _handle_report_list(raw_text, user_id, user_type):
    data = get_report_list(user_id=user_id, user_type=user_type)
    return format_result("get_report_list", data)


def _handle_report_submit(raw_text, user_id, user_type):
    content = raw_text.replace("提交日报", "").replace("写日报", "").strip()
    if not content or len(content) < 5:
        return "📊 请告诉我日报内容，例如：提交日报 今天完成了客户跟进和方案编写"
    today = date.today().isoformat()
    data = submit_report(content, today, user_id=user_id, user_type=user_type)
    return f"{format_result('submit_report', data)}\n📆 日期：{today}\n📝 内容：{content}"


def _handle_org_tree(raw_text, user_id, user_type):
    data = get_organization_tree(user_id=user_id, user_type=user_type)
    return format_result("get_organization_tree", data)


def _handle_complaint_list(raw_text, user_id, user_type):
    data = get_complaint_list(user_id=user_id, user_type=user_type)
    return format_result("get_complaint_list", data)


def _handle_complaint_handle(raw_text, user_id, user_type):
    import re
    m = re.search(r"投诉[#\s]*(\d+)", raw_text)
    if m:
        cid = int(m.group(1))
        new_status = "处理中"
        if "完结" in raw_text or "完成" in raw_text:
            new_status = "已完结"
        elif "驳回" in raw_text:
            new_status = "驳回"
        data = handle_complaint(cid, new_status, user_id=user_id, user_type=user_type)
        return format_result("handle_complaint", data)
    return "请指定投诉ID，例如：处理投诉 #1"


def _handle_score_list(raw_text, user_id, user_type):
    import re
    m = re.search(r"学生[#\s]*(\d+)", raw_text)
    sid = int(m.group(1)) if m else None
    data = get_score_list(student_id=sid, user_id=user_id, user_type=user_type)
    return format_result("get_score_list", data)


def _handle_score_add(raw_text, user_id, user_type):
    return "📝 请提供：学生ID、科目和分数，例如：录入成绩 学生 #1 雅思阅读 7.5"


def _handle_knowledge(raw_text, user_id, user_type):
    data = query_knowledge(raw_text, user_id=user_id, user_type=user_type)
    return format_result("query_knowledge", data)


def _handle_nl2sql(raw_text, user_id, user_type):
    data = query_nl2sql(raw_text, user_id=user_id, user_type=user_type)
    return format_result("query_nl2sql", data)


# Action → Handler 映射表。加新动作只需在这里加一行
ACTION_HANDLERS = {
    "get_todo_all": _handle_todo_all,
    "get_customer_list": _handle_customer_list,
    "add_customer": _handle_add_customer,
    "parse_customer_action": _handle_parse_customer,
    "get_leave_todo": _handle_leave_todo,
    "parse_leave_employee": _handle_leave_employee,
    "parse_leave_student": _handle_leave_student,
    "get_report_list": _handle_report_list,
    "parse_report_submit": _handle_report_submit,
    "get_organization_tree": _handle_org_tree,
    "get_complaint_list": _handle_complaint_list,
    "parse_complaint_handle": _handle_complaint_handle,
    "get_score_list": _handle_score_list,
    "parse_score_add": _handle_score_add,
    "query_knowledge": _handle_knowledge,
    "query_nl2sql": _handle_nl2sql,
}


def execute_action(action, intent, raw_text, user_id, user_type):
    """执行意图对应的接口调用 — 通过 HANDLERS 映射分发"""
    handler = ACTION_HANDLERS.get(action)
    if handler:
        try:
            return handler(raw_text, user_id, user_type)
        except Exception as e:
            return f"❌ 处理出错：{str(e)}"
    return f"🤖 我理解您想「{intent.get('label', '')}」，但暂时无法处理这个请求，请换个说法试试。"


# ============================================================
# 侧边栏 - 快捷功能
# ============================================================

with st.sidebar:
    st.markdown('<div class="sidebar-title">🤖 企业智能助手</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">对话式企业AI · 测试版</div>', unsafe_allow_html=True)

    # 用户信息
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown(f"<div style='background:#0052cc;color:#fff;width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:14px'>王</div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"**王建国**<br><span style='font-size:11px;color:#7a869a'>管理者</span>", unsafe_allow_html=True)

    st.markdown("---")

    # 快捷功能按钮
    st.markdown('<div class="section-title">📌 快捷功能</div>', unsafe_allow_html=True)

    shortcuts = [
        ("📋", "待办汇总", "查看我的待办"),
        ("👤", "意向客户", "查看所有客户"),
        ("👤", "新增客户", "新增客户 张三 25岁 男 13800138000"),
        ("📅", "请假管理", "我要请病假"),
        ("📅", "请假审批", "查看待审批请假"),
        ("📊", "日报管理", "查看我的日报"),
        ("🏢", "组织架构", "查看组织架构"),
        ("💬", "投诉列表", "查看投诉列表"),
        ("📝", "成绩查询", "查看成绩"),
        ("📚", "知识库", "公司年假怎么算"),
        ("🤖", "NL2SQL", "查询所有客户"),
    ]

    for icon, label, prompt in shortcuts:
        if st.button(f"{icon}  {label}", key=f"btn_{label}", use_container_width=True,
                     help=prompt):
            st.session_state.pending_input = prompt
            st.rerun()

    st.markdown("---")
    st.markdown(f"<div style='font-size:11px;color:#97a0af;padding:8px'><span style='display:inline-block;width:6px;height:6px;border-radius:50%;background:#36b37e;margin-right:4px'></span> 后端连接正常 · 8001</div>",
                unsafe_allow_html=True)

# ============================================================
# 主聊天区
# ============================================================

# 顶部标题栏（模拟）
st.markdown(f"""
<div class="chat-header">
    <h1>💬 对话式企业智能助手</h1>
    <div class="user-info">
        <span>👤 {st.session_state.user_type}</span>
        <span class="user-badge">王建国</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ===== 聊天记录（使用 st.chat_message 减少闪烁） =====
st.markdown('<div class="chat-container">', unsafe_allow_html=True)

# 欢迎消息
if not st.session_state.messages:
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown("""👋 你好！我是**企业智能助手**，你可以问我以下问题：

- 📋 **待办汇总** — 查看我的待办任务
- 👤 **意向客户** — 查看客户、新增客户、跟进客户
- 📅 **请假管理** — 请假、查看待审批
- 📊 **日报管理** — 提交日报、查看日报
- 🏢 **组织架构** — 查看公司组织架构
- 💬 **投诉反馈** — 查看投诉、处理投诉
- 📝 **成绩管理** — 查看成绩、录入成绩
- 📚 **知识库** — 查询公司规章制度
- 🤖 **NL2SQL** — 用自然语言查询数据

💡 试试输入"查看我的待办"或点击左侧快捷按钮""")

# 显示聊天历史
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(msg["content"])
    else:
        label = msg.get("label", "🤖 企业智能助手")
        with st.chat_message("assistant", avatar="🤖"):
            st.caption(label)
            st.markdown(msg["content"])

st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# 底部输入区（使用 st.chat_input 自动管理状态）
# ============================================================

st.markdown('<div class="input-area"><div class="input-inner" style="max-width:800px;margin:0 auto">', unsafe_allow_html=True)

# 先处理快捷按钮触发的输入（在 chat_input 之前处理）
if st.session_state.pending_input:
    text = st.session_state.pending_input
    st.session_state.pending_input = ""
    process_message(text)
    st.rerun()

user_input = st.chat_input(
    placeholder="输入你的问题…",
    key="chat_input_widget",
)

if user_input:
    process_message(user_input)
    st.rerun()

st.markdown('</div></div>', unsafe_allow_html=True)
