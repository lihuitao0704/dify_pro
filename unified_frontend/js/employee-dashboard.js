/**
 * employee-dashboard.js — 企业工作台逻辑
 * 依赖: auth.js, chat.js
 */

const ENTERPRISE_API = 'http://localhost:8001/api/agent';
let chat;

document.addEventListener('DOMContentLoaded', () => {
  if (!Auth.requireRole('employee')) return;

  const name = Auth.userName();
  const userType = Auth.get()?.user_type || '员工';
  document.getElementById('sidebarName').textContent = name || '员工';
  document.getElementById('sidebarRole').textContent = userType;
  document.getElementById('sidebarAvatar').textContent = (name || '员')[0];
  document.getElementById('userTypeTag').textContent = `身份: ${userType}`;

  // ── 初始化聊天（调 NL2SQL） ──
  chat = new ChatWidget({
    apiUrl: `${ENTERPRISE_API}/query/nl2sql`,
    container: '#chatMessages',
    input: '#chatInput',
    sendBtn: '#sendBtn',
    onPreSend: (msg) => {
      const auth = Auth.get();
      return {
        query: msg,
        current_user_id: auth?.user_id || 1,
        current_user_type: auth?.user_type || '员工',
      };
    },
    onReply: (data) => {
      // NL2SQL 返回格式: { natural_query, generated_sql, summary, results }
      refreshTodo();
    },
    welcome: '你好！我是企业智能助手 💼\n\n直接用自然语言操作：\n📋 "查一下待办事项"\n👥 "查询意向客户列表"\n📝 "查询待审批的请假"\n📮 "查询投诉处理情况"\n📊 "查询学生成绩"\n➕ "新增客户: 姓名XX, 年龄XX..."',
  });

  // ── 侧边栏导航 ──
  document.querySelectorAll('.sidebar-nav a[data-panel]').forEach(a => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.sidebar-nav a').forEach(x => x.classList.remove('active'));
      a.classList.add('active');
      switchPanel(a.dataset.panel);
    });
  });

  // ── 快捷操作 ──
  document.querySelectorAll('.sidebar-nav a[data-action]').forEach(a => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const action = a.dataset.action;
      if (action === 'report') openModal('reportModal');
      if (action === 'addCustomer') openModal('customerModal');
    });
  });

  refreshTodo();
});

function switchPanel(panel) {
  const titles = {
    chat: '💬 企业 AI 助手', todo: '📋 待办事项',
    customers: '👥 客户管理', leaves: '📝 请假审批', scores: '📊 成绩管理',
  };
  document.getElementById('topTitle').textContent = titles[panel] || '💬 企业 AI 助手';
}

async function refreshTodo() {
  const auth = Auth.get();
  try {
    const r = await fetch(`${ENTERPRISE_API}/todo/all?current_user_id=${auth?.user_id || 1}&current_user_type=${encodeURIComponent(auth?.user_type || '员工')}`);
    const data = await r.json();
    const todos = data.data || [];
    document.getElementById('todoList').innerHTML = todos.length === 0
      ? '<div class="list-item"><span class="label">暂无待办</span></div>'
      : todos.map(t => `
        <div class="list-item">
          <span>${t.title || t.reason || '待办事项'}</span>
          <span class="status-dot ${t.status === 'pending' || t.handle_status === '待处理' ? 'danger' : 'warn'}"></span>
        </div>
      `).join('');
    document.getElementById('todoBadge').textContent = todos.length;
    document.getElementById('todoBadge').style.display = todos.length > 0 ? '' : 'none';

    // 统计
    const leaveCount = todos.filter(t => t.type === 'leave').length;
    const complaintCount = todos.filter(t => t.type === 'complaint').length;
    document.getElementById('pendingLeaves').textContent = leaveCount;
    document.getElementById('pendingComplaints').textContent = complaintCount;
  } catch (e) { /* ignore */ }
}

// ── 提交日报 ──
async function submitReport() {
  const auth = Auth.get();
  const btn = document.getElementById('reportSubmitBtn');
  btn.disabled = true; btn.textContent = '提交中...';
  try {
    const r = await fetch(`${ENTERPRISE_API}/report/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_content: document.getElementById('reportContent').value,
        report_date: document.getElementById('reportDate').value,
        current_user_id: auth?.user_id || 1,
        current_user_type: auth?.user_type || '员工',
      }),
    });
    const data = await r.json();
    if (data.code === 0) { toast('日报提交成功 ✅', 'success'); closeModal('reportModal'); }
    else { toast(data.msg || '提交失败', 'error'); }
  } catch (e) { toast('提交失败: ' + e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = '提交'; }
}

// ── 录入客户 ──
async function submitCustomer() {
  const auth = Auth.get();
  const btn = document.getElementById('customerSubmitBtn');
  btn.disabled = true; btn.textContent = '录入中...';
  try {
    const r = await fetch(`${ENTERPRISE_API}/customer/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customer_name: document.getElementById('customerName').value,
        customer_age: parseInt(document.getElementById('customerAge').value) || null,
        customer_gender: document.getElementById('customerGender').value,
        customer_phone: document.getElementById('customerPhone').value,
        customer_source: document.getElementById('customerSource').value,
        customer_demand: document.getElementById('customerDemand').value,
        current_user_id: auth?.user_id || 1,
        current_user_type: auth?.user_type || '员工',
      }),
    });
    const data = await r.json();
    if (data.code === 0) { toast('客户录入成功 ✅', 'success'); closeModal('customerModal'); }
    else { toast(data.msg || '录入失败', 'error'); }
  } catch (e) { toast('录入失败: ' + e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = '录入'; }
}

function quickSend(msg) {
  const input = document.getElementById('chatInput');
  if (input) { input.value = msg; chat.send(); }
}

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) e.target.classList.remove('active');
});
