"""
对话式企业智能助手 - 意图识别 + 结果格式化
将用户自然语言映射到后端接口，并将返回数据格式化为友好文本
"""
import re
from datetime import date
from typing import Optional

# ============================================================
# 意图识别
# ============================================================

def recognize(text: str) -> dict:
    """
    识别用户意图，返回调用参数
    支持同义词、口语化表达
    """
    t = text.strip().lower()

    # ===== 待办 =====
    todo_kw = ["待办", "待处理", "待审批", "待审核", "我的任务", "我有哪些事",
                "需要我做", "未完成", "未处理", "代办", "todo", "待办事项",
                "有什么事情", "需要处理", "待办任务"]
    if any(kw in t for kw in todo_kw):
        return {"action": "get_todo_all", "method": "GET", "params": {}, "body": None,
                "label": "📋 待办汇总"}

    # ===== 客户 =====
    cust_kw = ["客户", "意向", "潜在客户", "客人", "准客户", "线索"]
    if any(kw in t for kw in cust_kw):
        add_kw = ["新增", "添加", "录入", "创建", "新建", "增加", "新客户", "加一个"]
        if any(kw in t for kw in add_kw):
            return {"action": "add_customer", "method": "POST", "params": {}, "body": {"parse": "customer"},
                    "label": "👤 新增客户"}
        follow_kw = ["跟进", "联系", "沟通", "回访", "打电话", "记录"]
        status_kw = ["改状态", "更新状态", "改", "状态变成", "变成"]
        if any(kw in t for kw in follow_kw + status_kw):
            return {"action": "parse_customer_action", "method": "PARSE", "params": {}, "body": {"text": t},
                    "label": "👤 客户操作"}
        search_kw = ["搜索", "查找", "找", "查询", "搜", "看", "看看", "查看"]
        if any(kw in t for kw in search_kw) or "什么" in t:
            return {"action": "get_customer_list", "method": "GET", "params": {"page": 1, "page_size": 10},
                    "label": "👤 搜索客户"}
        return {"action": "get_customer_list", "method": "GET", "params": {"page": 1, "page_size": 10},
                "label": "👤 意向客户"}

    # ===== 请假 =====
    leave_kw = ["请假", "请病假", "请年假", "请事假", "请婚假",
                "休假", "休息", "休", "调休", "年休"]
    if any(kw in t for kw in leave_kw):
        # 审批关键词优先匹配
        approve_kw = ["审批", "通过", "驳回", "批准", "同意", "拒绝", "不批", "审核"]
        if any(kw in t for kw in approve_kw):
            # 如果包含数字ID → 直接执行审批，否则显示待审批列表
            if re.search(r'#?\d+', t):
                return {"action": "batch_approve_leave", "method": "PARSE", "params": {}, "body": {"text": t},
                        "label": "✅ 执行审批"}
            return {"action": "get_leave_todo", "method": "GET", "params": {}, "body": None,
                    "label": "📅 请假审批"}
        # 个人请假（含"我"、"申请"等）
        me_kw = ["我", "自己", "想请", "我要", "帮我请"]
        if any(kw in t for kw in me_kw):
            return {"action": "parse_leave_employee", "method": "PARSE", "params": {}, "body": {"text": t},
                    "label": "📅 员工请假"}
        # 替学生请假
        student_kw = ["学生", "替", "帮", "代", "小明", "同学"]
        if any(kw in t for kw in student_kw):
            return {"action": "parse_leave_student", "method": "PARSE", "params": {}, "body": {"text": t},
                    "label": "📅 替学生请假"}
        return {"action": "get_leave_todo", "method": "GET", "params": {}, "body": None,
                "label": "📅 请假管理"}

    # ===== 日报 =====
    report_kw = ["日报", "汇报", "工作总结", "今日工作", "工作内容", "日志",
                  "工作汇报", "日报提交", "写日报"]
    if any(kw in t for kw in report_kw):
        submit_kw = ["提交", "写", "创建", "发", "发日报", "写日报"]
        if any(kw in t for kw in submit_kw):
            return {"action": "parse_report_submit", "method": "PARSE", "params": {}, "body": {"text": t},
                    "label": "📊 提交日报"}
        view_kw = ["查看", "看", "查", "浏览", "我的日报", "最近"]
        if any(kw in t for kw in view_kw):
            return {"action": "get_report_list", "method": "GET", "params": {"page": 1, "page_size": 10},
                    "label": "📊 日报查看"}
        return {"action": "get_report_list", "method": "GET", "params": {"page": 1, "page_size": 10},
                "label": "📊 日报管理"}

    # ===== 组织架构 =====
    org_kw = ["组织", "部门", "架构", "员工列表", "谁在", "组织结构", "公司架构",
               "有哪些部门", "部门有哪些", "全体员工", "通讯录"]
    if any(kw in t for kw in org_kw):
        return {"action": "get_organization_tree", "method": "GET", "params": {}, "body": None,
                "label": "🏢 组织架构"}

    # ===== 投诉 =====
    complaint_kw = ["投诉", "抱怨", "不满", "意见", "投诉反馈", "工单"]
    if any(kw in t for kw in complaint_kw):
        handle_kw = ["处理", "完结", "完成", "解决"]
        if any(kw in t for kw in handle_kw):
            return {"action": "parse_complaint_handle", "method": "PARSE", "params": {}, "body": {"text": t},
                    "label": "💬 处理投诉"}
        return {"action": "get_complaint_list", "method": "GET", "params": {"page": 1, "page_size": 20},
                "label": "💬 投诉反馈"}

    # ===== 学生信息 =====
    stu_kw = ["学生信息", "查学生", "学生名单", "学员", "查学员", "学生列表",
              "所有学生", "全部学生", "查看学生", "查找学生", "搜索学生"]
    if any(kw in t for kw in stu_kw):
        # 如果包含数字ID就走详情，否则走列表
        if re.search(r'#?\d+', t):
            return {"action": "get_student_detail", "method": "GET", "params": {}, "body": {"text": t},
                    "label": "👤 学生详情"}
        return {"action": "get_student_list", "method": "GET", "params": {}, "body": {"text": t},
                "label": "👤 学生列表"}

    # ===== 成绩 =====
    score_kw = ["成绩", "分数", "得分", "考试", "考分", "绩", "exam", "score"]
    if any(kw in t for kw in score_kw):
        add_kw = ["录入", "添加", "新增", "登记", "写入"]
        if any(kw in t for kw in add_kw):
            return {"action": "parse_score_add", "method": "PARSE", "params": {}, "body": {"text": t},
                    "label": "📝 录入成绩"}
        return {"action": "get_score_list", "method": "GET", "params": {"page": 1, "page_size": 50},
                "label": "📝 成绩查询"}

    # ===== 知识库 =====
    kb_kw = ["知识库", "制度", "规章", "规定", "年假", "病假", "事假", "婚假",
              "工资", "薪资", "福利", "考勤", "加班", "报销", "入职", "培训",
              "保密", "办公规范", "怎么算", "怎么办", "如何", "什么情况",
              "手册", "员工手册", "政策", "流程", "公司规定", "制度查询",
              "怎么请", "多少天", "多少钱", "什么条件", "怎么报销", "标准",
              "上班", "下班", "打卡", "迟到", "早退", "休假"]
    if any(kw in t for kw in kb_kw):
        return {"action": "query_knowledge", "method": "POST", "params": {}, "body": {"question": t},
                "label": "📚 知识库"}

    # ===== 审批操作 =====
    approve_ops = ["通过", "驳回", "批准", "拒绝", "审批"]
    if any(kw in t for kw in approve_ops):
        if re.search(r'#?\d+', t):
            # 有数字ID → 执行审批
            return {"action": "batch_approve_leave", "method": "PARSE", "params": {}, "body": {"text": t},
                    "label": "✅ 执行审批"}
        # 无ID → 显示待审批列表
        return {"action": "get_leave_todo", "method": "GET", "params": {}, "body": None,
                "label": "📅 请假审批"}

    # ===== 泛学生查询 =====
    if "学生" in t and not any(kw in t for kw in ["请假", "成绩", "考试"]):
        if re.search(r'#?\d+', t):
            return {"action": "get_student_detail", "method": "GET", "params": {}, "body": {"text": t},
                    "label": "👤 学生详情"}
        return {"action": "get_student_list", "method": "GET", "params": {}, "body": {"text": t},
                "label": "👤 学生列表"}

    # ===== NL2SQL（通用兜底） =====
    return {"action": "query_nl2sql", "method": "POST", "params": {}, "body": {"query": t},
            "label": "🤖 NL2SQL"}


# ============================================================
# 参数解析（从自然语言中提取结构化参数）
# ============================================================

def parse_date(text: str) -> Optional[str]:
    """从文本中提取日期 YYYY-MM-DD，没有则返回今天"""
    m = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})[日号]?", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 明天、后天等
    if "今天" in text or "今日" in text:
        return date.today().isoformat()
    if "明天" in text:
        from datetime import timedelta
        return (date.today() + timedelta(days=1)).isoformat()
    if "后天" in text:
        from datetime import timedelta
        return (date.today() + timedelta(days=2)).isoformat()
    return date.today().isoformat()


def parse_leave_type(text: str) -> str:
    """从文本中提取请假类型"""
    if "病假" in text: return "病假"
    if "年假" in text: return "年假"
    if "婚假" in text: return "婚假"
    if "事假" in text: return "事假"
    return "事假"


def parse_student_name(text: str) -> Optional[str]:
    """从文本中提取学生姓名"""
    # 匹配"替【名字】请假" 或 "【名字】请假"
    # 使用标准 CJK 统一表意文字区间 一-鿿
    m = re.search(r"替[的]?([一-鿿]{2,4})", text)
    if m:
        return m.group(1)
    m = re.search(r"学生[一-鿿]{2,4}", text)
    if m:
        return m.group(0)[2:]
    return None


def parse_name(text: str) -> Optional[str]:
    """从文本中提取姓名"""
    m = re.search(r"([一-龥]{2,4})", text)
    return m.group(1) if m else None


# ============================================================
# 结果格式化
# ============================================================

def format_result(action: str, data: dict) -> str:
    """将接口返回数据格式化为用户友好的文本"""
    if data.get("code") != 0 and data.get("code") is not None:
        return f"❌ 出错了：{data.get('msg', '未知错误')}"

    d = data.get("data")
    if d is None:
        return "✅ 操作成功！"

    # ---- 待办汇总 ----
    if action == "get_todo_all":
        total = d.get("total", 0)
        lines = [f"📋 **待办汇总**（共 {total} 项）", ""]
        for item in d.get("list", []):
            name = item.get("applicant_name", "")
            lines.append(f"🔸 **#{item.get('todo_id')}** {item.get('title', '')}")
            lines.append(f"  👤 {name or '未知'}")
            lines.append(f"  📝 {item.get('detail', '')}")
            lines.append(f"  ⏱ {item.get('create_time', '')[:10]}")
            lines.append("")
        return "\n".join(lines) if len(lines) > 3 else "🎉 没有待办，清闲得很！"

    # ---- 客户列表 ----
    if action == "get_customer_list":
        total = d.get("total", 0)
        lines = [f"👤 **意向客户**（共 {total} 条）", ""]
        for c in d.get("list", []):
            lines.append(f"**{c.get('customer_name')}** 📞 {c.get('customer_phone', '无电话')}")
            lines.append(f"  来源：{c.get('customer_source', '未知')} | 状态：{c.get('current_status', '未知')}")
            lines.append(f"  需求：{c.get('customer_demand', '无')}")
            lines.append("")
        if not d.get("list"):
            return "👤 暂无客户数据"
        return "\n".join(lines)

    # ---- 客户详情 ----
    if action == "get_customer_detail":
        return (
            f"👤 **{d.get('customer_name')}**\n"
            f"📞 {d.get('customer_phone', '无')}\n"
            f"来源：{d.get('customer_source', '未知')} | 状态：{d.get('current_status', '未知')}\n"
            f"需求：{d.get('customer_demand', '无')}\n"
            f"跟进：{d.get('follow_record', '暂无跟进记录')[:200]}"
        )

    # ---- 新增客户 ----
    if action == "add_customer":
        return f"✅ 客户已录入成功！客户 ID：{d.get('customer_id')}"

    # ---- 跟进 ----
    if action == "add_customer_follow":
        return "✅ 跟进记录已添加！"

    # ---- 状态更新 ----
    if action == "update_customer_status":
        return f"✅ 状态已更新为：{d.get('new_status')}"

    # ---- 待审批请假 ----
    if action == "get_leave_todo":
        total = len(d.get("list", []))
        lines = [f"📅 **待审批请假**（共 {total} 条）", ""]
        for lv in d.get("list", []):
            applicant = lv.get("applicant_name") or lv.get("student_name") or f"用户#{lv.get('applicant_id')}"
            reason = lv.get("reason") or "空"
            lines.append(f"🔸 **#{lv.get('id')}** {lv.get('leave_type')}")
            lines.append(f"  👤 {applicant}")
            lines.append(f"  📅 {lv.get('start_date')} → {lv.get('end_date')}")
            lines.append(f"  📝 {reason}")
            lines.append("")
        if not d.get("list"):
            return "🎉 没有待审批的请假"
        lines.append("💡 **审批操作：**")
        lines.append("  • `通过 #1,#2,#3` — 批量通过")
        lines.append("  • `驳回 #4` — 驳回指定申请")
        return "\n".join(lines)

    # ---- 请假提交 ----
    if action == "submit_leave":
        return f"✅ 请假已提交！请假编号：{d.get('leave_id')}"

    # ---- 批量审批 ----
    if action == "batch_approve_leave":
        action_label = d.get("action", "处理")
        count = d.get("count", 0)
        ids = d.get("leave_ids", [])
        skipped = d.get("skipped_ids", [])
        lines = [f"✅ 已{action_label} {count} 条记录"]
        if ids:
            lines.append(f"  请假ID：{ids}")
        if skipped:
            lines.append(f"  ⚠️ 以下ID已跳过（非待审批状态）：{skipped}")
        return "\n".join(lines)

    # ---- 日报列表 ----
    if action == "get_report_list":
        lines = ["📊 **日报列表**", ""]
        for r in d.get("list", []):
            lines.append(f"📅 {r.get('report_date')} | 用户 {r.get('user_id')}")
            lines.append(f"  {r.get('report_content', '')[:100]}")
            lines.append("")
        if not d.get("list"):
            return "📊 暂无日报"
        return "\n".join(lines)

    # ---- 提交日报 ----
    if action == "submit_report":
        return f"✅ 日报已提交！"

    # ---- 组织架构 ----
    if action == "get_organization_tree":
        lines = ["🏢 **组织架构**", ""]

        def print_tree(nodes, level=0):
            for n in nodes:
                prefix = "  " * level
                mgr = f"（负责人：{n.get('manager_name', '无')}）" if n.get('manager_name') else ""
                lines.append(f"{prefix}📁 **{n.get('dept_name')}** {mgr}")
                for e in n.get("employees", []):
                    lines.append(f"{prefix}  👤 {e.get('emp_name')} {e.get('position', '')}")
                if n.get("children"):
                    print_tree(n.get("children"), level + 1)

        print_tree(d.get("tree", []))
        return "\n".join(lines)

    # ---- 投诉列表 ----
    if action == "get_complaint_list":
        lines = ["💬 **投诉列表**", ""]
        for c in d.get("list", []):
            lines.append(f"🔸 #{c.get('id')} | 学生 {c.get('student_id')} | **{c.get('handle_status')}**")
            lines.append(f"  {c.get('complaint_detail', '')[:100]}")
            lines.append("")
        if not d.get("list"):
            return "💬 暂无投诉"
        return "\n".join(lines)

    # ---- 处理投诉 ----
    if action == "handle_complaint":
        return f"✅ 投诉已处理，状态：{d.get('new_status')}"

    # ---- 成绩 ----
    if action == "get_score_list":
        lines = ["📝 **成绩列表**", ""]
        for s in d.get("list", []):
            lines.append(f"学生 {s.get('student_id')} | **{s.get('subject')}**：{s.get('score')} 分")
            lines.append(f"  类型：{s.get('exam_type', '无')} | 日期：{s.get('exam_date', '无')}")
            lines.append("")
        if not d.get("list"):
            return "📝 暂无成绩数据"
        return "\n".join(lines)

    # ---- 录入成绩 ----
    if action == "add_score":
        return f"✅ 成绩已录入！"

    # ---- 知识库 ----
    if action == "query_knowledge":
        return f"💡 **{d.get('question', '')}**\n\n{d.get('answer', '暂无答案')}\n\n📖 来源：{d.get('source', '无')}"

    # ---- NL2SQL ----
    if action == "query_nl2sql":
        lines = [f"🔍 **查询结果**", "", f"📝 生成的 SQL：`{d.get('generated_sql', '')}`", f"📊 {d.get('summary', '')}", ""]
        for row in d.get("results", []):
            lines.append(" | ".join([f"{k}: {v}" for k, v in row.items()]))
        if not d.get("results"):
            lines.append("（无结果）")
        return "\n".join(lines)

    return "✅ 操作完成！"
