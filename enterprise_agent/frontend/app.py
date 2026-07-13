"""
对话式企业智能助手 - Streamlit 前端
启动：streamlit run frontend/app.py --server.port 8501
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from intent import recognize, format_result, parse_date, parse_leave_type, parse_student_name
from utils import (
    get_todo_all, get_customer_list, get_customer_detail,
    add_customer, update_customer_status, add_customer_follow,
    get_leave_todo, submit_leave_employee, submit_leave_student,
    batch_approve_leave, submit_report, get_report_list,
    get_organization_tree, get_complaint_list, handle_complaint,
    add_score, get_score_list, query_knowledge, query_nl2sql,
    get_student_list, get_student_detail,
    CURRENT_USER_ID, CURRENT_USER_TYPE,
)
import utils as _utils

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(page_title="企业智能助手", page_icon="🤖", layout="wide")

# 自动清除侧边栏折叠缓存，防collapse后无法恢复
st.markdown("""<script>try{sessionStorage.removeItem('stSidebarCollapsed');localStorage.removeItem('stSidebarCollapsed');}catch(e){}</script>""", unsafe_allow_html=True)

# ============================================================
# 自定义 CSS
# ============================================================
st.markdown("""
<style>
    .stApp { background-color: #f0f2f6; }
    .main .block-container { padding: 0; max-width: 100%; }
    .chat-header {
        background: #fff; padding: 12px 24px; border-bottom: 1px solid #e4e7ec;
        display: flex; align-items: center; justify-content: space-between;
        position: sticky; top: 0; z-index: 100;
    }
    .chat-header h1 { font-size: 18px; font-weight: 600; margin: 0; color: #172b4d; }
    .chat-header .user-info { font-size: 13px; color: #5e6c84; display: flex; align-items: center; gap: 8px; }
    .chat-header .user-badge { background: #0052cc; color: white; padding: 2px 10px; border-radius: 100px; font-size: 11px; font-weight: 500; }
    .chat-container { max-width: 800px; margin: 0 auto; padding: 20px 24px 100px; }
    .chat-message { display: flex; margin-bottom: 20px; animation: fadeIn 0.3s ease; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    .chat-message.user { justify-content: flex-end; }
    .chat-message.bot { justify-content: flex-start; }
    .chat-bubble { max-width: 72%; padding: 12px 18px; border-radius: 16px; font-size: 14px; line-height: 1.6; box-shadow: 0 1px 3px rgba(0,0,0,.06); white-space: pre-wrap; word-break: break-word; }
    .chat-bubble.user { background: #0052cc; color: white; border-bottom-right-radius: 4px; }
    .chat-bubble.bot { background: white; color: #172b4d; border: 1px solid #e4e7ec; border-bottom-left-radius: 4px; }
    .section-title { font-size: 11px; font-weight: 600; color: #97a0af; text-transform: uppercase; letter-spacing: 0.5px; padding: 12px 14px 4px; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} .stDeployButton {display:none;}
    div[data-testid="stToolbar"] {display: none;}
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
if "real_name" not in st.session_state:
    st.session_state.real_name = "用户"
if "token" not in st.session_state:
    st.session_state.token = ""
if "pending_input" not in st.session_state:
    st.session_state.pending_input = ""
if "pending_action" not in st.session_state:
    st.session_state.pending_action = None
if "pending_context" not in st.session_state:
    st.session_state.pending_context = {}
if "_stream_idx" not in st.session_state:
    st.session_state._stream_idx = 0  # 已流式输出的消息数

# 首次加载时自动登录默认用户
if not st.session_state.token:
    try:
        r = __import__('requests').post("http://localhost:8001/auth/login",
            json={"username": "13800001001", "password": "123456"}, timeout=5)
        d = r.json()
        if d.get("success"):
            st.session_state.token = d.get("token", "")
            st.session_state.user_id = d.get("user_id", 1)
            st.session_state.real_name = d.get("real_name", "用户")
            st.session_state.user_type = d.get("user_type", "管理者")
            _utils.API_TOKEN = st.session_state.token
    except Exception:
        pass

# 辅助函数：切换用户（走真实登录）
def _switch_user(username, password):
    try:
        r = __import__('requests').post("http://localhost:8001/auth/login",
            json={"username": username, "password": password}, timeout=5)
        d = r.json()
        if d.get("success"):
            st.session_state.token = d.get("token", "")
            st.session_state.user_id = d.get("user_id", 1)
            st.session_state.real_name = d.get("real_name", "用户")
            st.session_state.user_type = d.get("user_type", "管理者")
            _utils.API_TOKEN = st.session_state.token
            st.session_state.messages = []
            st.session_state.pending_action = None
            return True
    except Exception:
        pass
    return False

# ============================================================
# 工具函数（侧边栏使用，放前面）
# ============================================================
def _uid():
    return st.session_state.get("user_id", 1)

def _utype():
    return st.session_state.get("user_type", "管理者")

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.subheader("🤖 企业智能助手")
    st.caption("对话式企业AI · 测试版")

    # 用户信息（可点击弹出职位和登录入口）
    with st.popover(f"👤 {st.session_state.real_name}", use_container_width=True):
        st.markdown(f"**职位：** {st.session_state.user_type}")
        st.markdown(f"**用户ID：** {st.session_state.user_id}")
        if st.button("🔑 切换登录", use_container_width=True, type="primary"):
            # 清除登录状态，后续对接正式登录页后跳转
            for k in ["token", "user_id", "real_name", "user_type", "messages"]:
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()
    st.markdown("**📌 快捷功能**")

    # 快捷功能：一键查询
    for label, prompt in [
        ("📋 待办汇总", "查看我的待办"), ("👤 意向客户", "查看所有客户"),
        ("👤 查学生", "查学生"), ("📅 请假审批", "查看待审批请假"),
        ("📊 日报管理", "查看我的日报"), ("🏢 组织架构", "查看组织架构"),
        ("💬 投诉列表", "查看投诉列表"), ("📝 成绩查询", "查看成绩"),
    ]:
        if st.button(label, key=f"s{label}", use_container_width=True):
            st.session_state.pending_input = prompt
            st.rerun()

    # 快捷功能：需要填写的操作（弹窗表单）
    with st.popover("👤 新增客户", use_container_width=True):
        cname = st.text_input("客户姓名", key="cust_name")
        cphone = st.text_input("电话", key="cust_phone")
        csource = st.selectbox("来源", ["网络","转介绍","展会","电话邀约","线下活动","合作机构"], key="cust_source")
        cdemand = st.text_area("需求描述", key="cust_demand")
        if st.button("录入", type="primary", use_container_width=True, key="cust_btn"):
            if cname:
                data = add_customer({"customer_name": cname, "customer_phone": cphone,
                    "customer_source": csource, "customer_demand": cdemand}, user_id=_uid(), user_type=_utype())
                st.session_state.messages.append({"role": "bot", "content": format_result("add_customer", data), "label": "👤 新增客户"})
                st.rerun()

    with st.popover("📅 我要请假", use_container_width=True):
        lt = st.selectbox("请假类型", ["事假","病假","年假","婚假","其他"], key="leave_type")
        sd = st.date_input("开始日期", key="leave_sd")
        ed = st.date_input("结束日期", key="leave_ed")
        reason = st.text_input("原因（可选）", key="leave_reason")
        if st.button("提交", type="primary", use_container_width=True, key="leave_btn"):
            data = submit_leave_employee(lt, sd.isoformat(), ed.isoformat(), reason, user_id=_uid(), user_type=_utype())
            st.session_state.messages.append({"role": "bot", "content": format_result("submit_leave", data), "label": "📅 请假提交"})
            st.rerun()

    with st.popover("✅ 批量通过", use_container_width=True):
        ids = st.text_input("请假ID，逗号分隔（如 1,2,3）", key="approve_ids")
        if st.button("通过", type="primary", use_container_width=True, key="approve_btn"):
            id_list = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
            if id_list:
                data = batch_approve_leave(id_list, "approve", user_id=_uid(), user_type=_utype())
                st.session_state.messages.append({"role": "bot", "content": format_result("batch_approve_leave", data), "label": "✅ 批量通过"})
                st.rerun()

    with st.popover("❌ 批量驳回", use_container_width=True):
        ids = st.text_input("请假ID，逗号分隔（如 1,2,3）", key="reject_ids")
        if st.button("驳回", type="primary", use_container_width=True, key="reject_btn"):
            id_list = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
            if id_list:
                data = batch_approve_leave(id_list, "reject", user_id=_uid(), user_type=_utype())
                st.session_state.messages.append({"role": "bot", "content": format_result("batch_approve_leave", data), "label": "❌ 批量驳回"})
                st.rerun()

    st.caption("🟢 后端连接正常 · 8001")

# ============================================================
# 处理用户消息
# ============================================================
def process_message(user_text: str):
    if not user_text.strip():
        return
    text = user_text.strip()

    pending = st.session_state.get("pending_action")
    if pending:
        confirm_words = ["确认", "确定", "是", "嗯", "对", "好的", "可以", "yes", "y", "ok", "提交"]
        cancel_words = ["取消", "不了", "不", "否", "不要", "算了", "no", "n"]
        if any(kw in text.lower() for kw in confirm_words):
            st.session_state.pending_action = None
            ctx = st.session_state.pending_context
            st.session_state.pending_context = {}
            st.session_state.messages.append({"role": "user", "content": text})
            result_text = execute_action(pending, ctx.get("intent", {}), ctx.get("raw_text", ""), _uid(), _utype())
            st.session_state.messages.append({"role": "bot", "content": result_text, "label": ctx.get("label", "✅ 操作已执行")})
            return
        elif any(kw in text.lower() for kw in cancel_words):
            st.session_state.pending_action = None
            st.session_state.pending_context = {}
            st.session_state.messages.append({"role": "user", "content": text})
            st.session_state.messages.append({"role": "bot", "content": "❌ 操作已取消", "label": "⏸️ 已取消"})
            return
        else:
            st.session_state.pending_action = None
            st.session_state.pending_context = {}

    intent = recognize(text)
    action = intent["action"]
    label = intent["label"]
    st.session_state.messages.append({"role": "user", "content": text})

    confirm_actions = {"parse_leave_employee", "parse_leave_student", "batch_approve_leave", "add_customer"}
    if action in confirm_actions:
        preview = _preview_action(action, intent, text)
        st.session_state.pending_action = action
        st.session_state.pending_context = {"intent": intent, "raw_text": text, "label": label}
        st.session_state.messages.append({
            "role": "bot",
            "content": preview + "\n\n🤔 **请确认以上操作**\n输入「确认」提交，或「取消」放弃",
            "label": label,
        })
        return

    result_text = execute_action(action, intent, text, _uid(), _utype())
    st.session_state.messages.append({"role": "bot", "content": result_text, "label": label})

# ============================================================
# Action Handlers
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
                kw = parts[1].strip(); break
    data = get_customer_list(keyword=kw, user_id=user_id, user_type=user_type)
    return format_result("get_customer_list", data)

def _parse_customer_info(text):
    """从自然语言中提取客户信息，返回 dict"""
    import re
    info = {"name": "", "phone": "", "source": "", "demand": "", "gender": "", "age": None}

    # 提取姓名：支持"名字XXX"、"名字叫XXX"、"姓名"、"叫XXX"
    for pat in [r"名字叫[着做]?\s*(\w{2,6})", r"名字\s*(\w{2,6})",
                r"姓名[：:为是]?\s*(\w{2,6})", r"叫[着做]?\s*(\w{2,6})",
                r"名称[：:为是]?\s*(\w{2,6})", r"客户[：:为是]?\s*(\w{2,6})"]:
        m = re.search(pat, text)
        if m:
            info["name"] = m.group(1)
            break

    # 提取电话
    m = re.search(r"(?:电话|手机|联系)[0-9\s\-码号]*[：:为是]?\s*(1\d{9,10})", text)
    if m:
        info["phone"] = m.group(1)
    else:
        m = re.search(r"(?<!\d)(1[3-9]\d{8,9})(?!\d)", text)
        if m:
            info["phone"] = m.group(1)

    # 提取来源
    for s in ["网络", "转介绍", "展会", "电话咨询", "电话邀约", "线下活动", "合作机构", "广告"]:
        if s in text:
            info["source"] = s
            break

    # 提取需求（优先"想"/"需求"，避免"咨询"在"电话咨询"中误匹配）
    for pat in [r"(?:需求|想要)[：:为是]?\s*(.{2,40})",
                r"[，,]\s*想[：:为是]?\s*(.{2,40})",
                r"打算[：:为是]?\s*(.{2,40})",
                r"想[要]?\s*(.{2,40})",
                r"(?:了解|看看|问问)[：:为是]?\s*(.{2,40})"]:
        m = re.search(pat, text)
        if m:
            info["demand"] = m.group(1)
            # 截断尾部干扰词
            for stop in ["电话", "来源", "性别", "年龄", "名字", "姓名"]:
                idx = info["demand"].find(stop)
                if idx > 0:
                    info["demand"] = info["demand"][:idx].strip()
            break

    # 提取性别
    if re.search(r"性别\s*男|(?<![男女])\b男\b", text):
        info["gender"] = "男"
    elif re.search(r"性别\s*女|(?<![男女])\b女\b", text):
        info["gender"] = "女"

    # 提取年龄：年龄19 / 19岁
    m = re.search(r"年龄\s*(\d{1,2})|(\d{1,2})\s*岁", text)
    if m:
        info["age"] = int(m.group(1) or m.group(2))

    return info


def _handle_add_customer(raw_text, user_id, user_type):
    info = _parse_customer_info(raw_text)
    if not info["name"]:
        return "📝 请告诉我客户姓名，例如：新增客户 张三，电话13800138000"

    data = add_customer({
        "customer_name": info["name"].strip(),
        "customer_phone": info["phone"].strip() if info["phone"] else None,
        "customer_age": info["age"],
        "customer_gender": info["gender"] if info["gender"] else None,
        "customer_source": info["source"].strip() if info["source"] else None,
        "customer_demand": info["demand"].strip() if info["demand"] else None,
    }, user_id=user_id, user_type=user_type)
    return format_result("add_customer", data)

def _handle_parse_customer(raw_text, user_id, user_type):
    import re
    if "跟进" in raw_text:
        m = re.search(r"客户[#\s]*(\d+)", raw_text)
        if m:
            content = raw_text.split("跟进", 1)[1].strip() or "跟进沟通"
            data = add_customer_follow(int(m.group(1)), content, user_id=user_id, user_type=user_type)
            return format_result("add_customer_follow", data)
        return "请指定客户ID"
    if "状态" in raw_text or "改" in raw_text:
        m = re.search(r"客户[#\s]*(\d+)", raw_text)
        if m:
            status = "已签约" if "签约" in raw_text else "已流失" if "流失" in raw_text else "意向中"
            data = update_customer_status(int(m.group(1)), status, user_id=user_id, user_type=user_type)
            return format_result("update_customer_status", data)
        return "请指定客户ID和状态"
    return "请指定操作：跟进客户或更改客户状态"

def _handle_leave_todo(raw_text, user_id, user_type):
    return format_result("get_leave_todo", get_leave_todo(user_id=user_id, user_type=user_type))

def _handle_leave_employee(raw_text, user_id, user_type):
    lt = parse_leave_type(raw_text); sd = parse_date(raw_text)
    reason = ""
    if "因为" in raw_text: reason = raw_text.split("因为",1)[1].strip()
    if "原因" in raw_text: reason = raw_text.split("原因",1)[1].strip() or reason
    data = submit_leave_employee(lt, sd, sd, reason, user_id=user_id, user_type=user_type)
    return f"{format_result('submit_leave',data)}\n📅 类型：{lt}\n📆 日期：{sd}\n📝 原因：{reason or '无'}"

def _handle_leave_student(raw_text, user_id, user_type):
    sn = parse_student_name(raw_text) or "学生"; lt = parse_leave_type(raw_text); sd = parse_date(raw_text)
    data = submit_leave_student(sn, lt, sd, sd, "", user_id=user_id, user_type=user_type)
    return f"{format_result('submit_leave',data)}\n👤 学生：{sn}\n📅 类型：{lt}\n📆 日期：{sd}"

def _handle_batch_approve(raw_text, user_id, user_type):
    import re
    action = "reject" if any(k in raw_text for k in ["驳回","拒绝","不批"]) else "approve"
    ids = [int(i) for i in re.findall(r'#?(\d+)', raw_text) if int(i) > 0]
    if not ids: return "📋 请指定请假ID，如：`通过 #1,#2`"
    data = batch_approve_leave(ids, action, user_id=user_id, user_type=user_type)
    return f"{format_result('batch_approve_leave',data)}\n📋 {'通过' if action=='approve' else '驳回'} {len(ids)} 条"

def _handle_report_list(raw_text, user_id, user_type):
    return format_result("get_report_list", get_report_list(user_id=user_id, user_type=user_type))

def _handle_report_submit(raw_text, user_id, user_type):
    content = raw_text.replace("提交日报","").replace("写日报","").strip()
    if not content or len(content) < 5:
        return "📊 请告诉我日报内容，如：提交日报 今天完成了客户跟进"
    from datetime import date
    data = submit_report(content, date.today().isoformat(), user_id=user_id, user_type=user_type)
    return f"{format_result('submit_report',data)}\n📝 {content}"

def _handle_org_tree(raw_text, user_id, user_type):
    return format_result("get_organization_tree", get_organization_tree(user_id=user_id, user_type=user_type))

def _handle_complaint_list(raw_text, user_id, user_type):
    return format_result("get_complaint_list", get_complaint_list(user_id=user_id, user_type=user_type))

def _handle_complaint_handle(raw_text, user_id, user_type):
    import re
    m = re.search(r"投诉[#\s]*(\d+)", raw_text)
    if m:
        ns = "已完结" if any(k in raw_text for k in ["完结","完成"]) else "驳回" if "驳回" in raw_text else "处理中"
        return format_result("handle_complaint", handle_complaint(int(m.group(1)), ns, user_id=user_id, user_type=user_type))
    return "请指定投诉ID"

def _handle_score_list(raw_text, user_id, user_type):
    import re
    m = re.search(r"学生[#\s]*(\d+)", raw_text)
    return format_result("get_score_list", get_score_list(student_id=int(m.group(1)) if m else None, user_id=user_id, user_type=user_type))

def _handle_score_add(raw_text, user_id, user_type):
    return "📝 请提供：学生ID、科目和分数"

def _handle_knowledge(raw_text, user_id, user_type):
    return format_result("query_knowledge", query_knowledge(raw_text, user_id=user_id, user_type=user_type))

def _handle_nl2sql(raw_text, user_id, user_type):
    return format_result("query_nl2sql", query_nl2sql(raw_text, user_id=user_id, user_type=user_type))

def _handle_student_list(raw_text, user_id, user_type):
    kw = ""; cleaned = raw_text.strip()
    for p in ["查询","查看","搜索","查找","找一下","帮我查","看看","查一下","查"]:
        if cleaned.startswith(p): cleaned = cleaned[len(p):].strip(); break
    for b in ["学生信息","学生名单","学生列表","全部学生","所有学生","学生","学员"]:
        if cleaned.startswith(b): cleaned = cleaned[len(b):].strip(); break
    for f in ["的","了","给我","一下","看看","数据","信息","情况","资料","名单","列表"]:
        if cleaned == f or cleaned.endswith(f):
            cleaned = cleaned[:-len(f)].strip() if cleaned.endswith(f) else ""; break
    if cleaned: kw = cleaned
    data = get_student_list(keyword=kw, user_id=user_id, user_type=user_type)
    if data.get("code") != 0: return f"❌ {data.get('msg','查询失败')}"
    d = data.get("data",{})
    if not d.get("list"): return "📭 没有找到匹配的学生"
    lines = [f"👤 **学生列表**（共 {d['total']} 人）",""]
    for s in d["list"]:
        lines.append(f"**#{s['id']} {s['name']}**")
        lines.append(f"  📱 {s.get('phone','无')} | {s.get('school','')} | {s.get('status','')}")
        lines.append(f"  项目：{s.get('project_name','未报名')}")
        lines.append("")
    return "\n".join(lines)

def _handle_student_detail(raw_text, user_id, user_type):
    import re
    m = re.search(r'#?(\d+)', raw_text)
    if not m: return "请指定学生ID，如：`查学生 #1001`"
    data = get_student_detail(int(m.group(1)), user_id=user_id, user_type=user_type)
    if data.get("code") != 0: return f"❌ {data.get('msg','查询失败')}"
    s = data.get("data",{})
    if not s: return "学生不存在"
    return f"👤 **{s['name']}** #{s['id']}\n{s.get('phone','')} | {s.get('school','')}\n📋 项目：{s.get('project_name','未报名')} | 状态：{s.get('status','')}"

def _preview_action(action, intent, raw_text):
    if action == "parse_leave_employee":
        lt = parse_leave_type(raw_text); sd = parse_date(raw_text)
        reason = ""
        if "因为" in raw_text: reason = raw_text.split("因为",1)[1].strip()
        if "原因" in raw_text: reason = raw_text.split("原因",1)[1].strip() or reason
        return f"📋 **请假预览**\n\n👤 申请人：自己（员工）\n📌 类型：{lt}\n📅 日期：{sd}\n📝 原因：{reason or '无'}"
    elif action == "parse_leave_student":
        return f"📋 **替学生请假预览**\n\n👤 学生：{parse_student_name(raw_text) or '学生'}\n📌 类型：{parse_leave_type(raw_text)}\n📅 日期：{parse_date(raw_text)}"
    elif action == "batch_approve_leave":
        import re
        al = "通过" if "驳回" not in raw_text else "驳回"
        ids = [int(i) for i in re.findall(r'#?(\d+)', raw_text) if int(i) > 0]
        return f"📋 **批量审批预览**\n\n🔧 操作：{al}\n🔢 请假ID：{ids or '全部'}"
    elif action == "add_customer":
        info = _parse_customer_info(raw_text)
        lines = [f"📋 **新增客户预览**\n"]
        lines.append(f"👤 姓名：{info['name'] or '未识别'}")
        if info['gender']:
            lines.append(f"⚧ 性别：{info['gender']}")
        if info['age']:
            lines.append(f"📅 年龄：{info['age']}岁")
        lines.append(f"📱 电话：{info['phone'] or '未识别'}")
        lines.append(f"🔗 来源：{info['source'] or '未识别'}")
        lines.append(f"📝 需求：{info['demand'] or '未识别'}")
        lines.append("")
        missing = [k for k, v in [('姓名',info['name']),('电话',info['phone']),('来源',info['source']),('需求',info['demand'])] if not v]
        if missing:
            lines.append("💡 **提示：** 以下未识别，可重新输入补全")
            lines.append(f"  缺少：{'、'.join(missing)}")
            lines.append("  格式：`名字叫XXX，电话138...，来源网络，想咨询...`")
        lines.append("")
        lines.append("正确吗？输入「确认」提交")
        return "\n".join(lines)
    return "⚠️ 即将执行操作，请确认"

ACTION_HANDLERS = {
    "get_todo_all": _handle_todo_all, "get_customer_list": _handle_customer_list,
    "add_customer": _handle_add_customer, "parse_customer_action": _handle_parse_customer,
    "get_leave_todo": _handle_leave_todo, "parse_leave_employee": _handle_leave_employee,
    "parse_leave_student": _handle_leave_student, "batch_approve_leave": _handle_batch_approve,
    "get_report_list": _handle_report_list, "parse_report_submit": _handle_report_submit,
    "get_organization_tree": _handle_org_tree, "get_complaint_list": _handle_complaint_list,
    "parse_complaint_handle": _handle_complaint_handle, "get_score_list": _handle_score_list,
    "parse_score_add": _handle_score_add, "query_knowledge": _handle_knowledge,
    "query_nl2sql": _handle_nl2sql, "get_student_list": _handle_student_list,
    "get_student_detail": _handle_student_detail,
}

def execute_action(action, intent, raw_text, user_id, user_type):
    if action == "_not_understood":
        import random
        tips = [
            "嗯…这个我还不太懂呢 🤔\n\n你可以试试：\n• 查客户 — 「查看所有客户」\n• 查待办 — 「我的待办」\n• 请假 — 「我要请病假」\n• 问知识库 — 「德国留学条件」",
            "没太明白你想做什么～\n你可以直接说：「查客户」「我要请假」「看组织架构」「请假审批」",
            "这个暂时还不在我的技能范围内 😅\n但我能帮你查客户、审批请假、看日报、问制度…试试看？",
            "哈哈这个我还没学会～\n试试：「帮我查一下客户」「我要请病假」「德国留学需要什么条件」",
        ]
        return random.choice(tips)
    handler = ACTION_HANDLERS.get(action)
    if handler:
        try: return handler(raw_text, user_id, user_type)
        except Exception as e: return f"❌ 处理出错：{str(e)}"
    return f"🤖 我理解您想「{intent.get('label','')}」，但暂时无法处理"

# ============================================================
# 渲染聊天界面
# ============================================================
st.markdown(f"""
<div class="chat-header">
    <h1>💬 企业智能助手</h1>
    <div class="user-info">
        <span class="user-badge">{st.session_state.real_name}</span>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="chat-container">', unsafe_allow_html=True)

if not st.session_state.messages:
    with st.chat_message("assistant", avatar="🤖"):
        import time as _t
        def _welcome():
            for _ch in "👋 你好！我是**企业智能助手**\n\n试试说：查客户 · 查待办 · 看部门 · 查学生\n\n💡 侧边栏有快捷功能按钮":
                yield _ch
                _t.sleep(0.015)
        st.write_stream(_welcome)

for i, msg in enumerate(st.session_state.messages):
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(msg["content"])
    else:
        label = msg.get("label", "🤖 企业智能助手")
        with st.chat_message("assistant", avatar="🤖"):
            st.caption(label)
            # 新消息流式输出，旧消息直接显示
            if i >= st.session_state._stream_idx:
                import time as _t
                def _stream(text=msg["content"]):
                    for _chunk in text.split(" "):
                        yield _chunk + " "
                        _t.sleep(0.02)
                st.write_stream(_stream)
                st.session_state._stream_idx = i + 1
            else:
                st.markdown(msg["content"])

st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# 输入区
# ============================================================
if st.session_state.pending_input:
    text = st.session_state.pending_input
    st.session_state.pending_input = ""
    process_message(text)
    st.rerun()

user_input = st.chat_input(
    placeholder='直接告诉我你要做什么',
    key="chat_input_widget",
)
if user_input:
    process_message(user_input)
    st.rerun()
