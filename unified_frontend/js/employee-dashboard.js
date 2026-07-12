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
    smartReport: '📈 智能报告',
  };
  document.getElementById('topTitle').textContent = titles[panel] || '💬 企业 AI 助手';

  // 切换报告面板的显示/隐藏
  const reportPanel = document.getElementById('smartReportPanel');
  const chatPanel = document.getElementById('chatPanel');
  const infoPanel = document.getElementById('infoPanel');
  if (panel === 'smartReport') {
    reportPanel.style.display = 'flex';
    chatPanel.style.display = 'none';
    if (infoPanel) infoPanel.style.display = 'none';
  } else {
    reportPanel.style.display = 'none';
    chatPanel.style.display = '';
    if (infoPanel) infoPanel.style.display = '';
  }
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

// ═══════════════════════════════════════════════════════════
// 智能报告 (summary_report API @ localhost:8003)
// ═══════════════════════════════════════════════════════════

const REPORT_API = 'http://localhost:8003/report';

// 推荐问题
const REPORT_SUGGESTIONS = {
  customer_operation: [
    '最近一周各渠道的客户数量和签约转化率',
    '本月已签约客户的目标国家和预算分布',
    '哪些渠道的客户流失率最高',
    '各销售顾问的客户数量和签约业绩',
    '意向客户的状态分布和占比',
  ],
  employee_daily: [
    '本周各部门的日报提交情况',
    '最近一周员工日报中提到的风险或阻塞项',
    '各部门的工作产出统计对比',
    '哪些员工连续多天未提交日报',
  ],
  student_mental: [
    '本月学生整体情绪态势和趋势',
    '当前有哪些高风险等级的学生',
    '最近一周心理预警的处理情况',
    '近4周学生情绪评分的变化趋势',
  ],
  complaint_weekly: [
    '本周投诉工单的总量和分类分布',
    '各类型投诉的处理进度和积压情况',
    '哪些投诉超过3天未处理需要预警',
    '投诉满意度评分按类别统计',
  ],
  nl2sql: [
    '各国家方向的课程数量和价格区间',
    '留学申请各阶段的学生数量分布',
    '最近一周新增的意向客户来源分析',
    '讲座活动的报名人数统计',
  ],
};

let currentReportType = 'customer_operation';

// ── 渲染推荐问题 ──
function renderReportSuggestions(type) {
  const list = REPORT_SUGGESTIONS[type] || [];
  const container = document.getElementById('suggestTags');
  if (!container) return;
  container.innerHTML = list.map(q =>
    `<span class="suggest-tag" onclick="pickReportSuggestion(this)">${escapeHTML(q)}</span>`
  ).join('');
}

// ── 点击推荐问题 → 填入并生成 ──
function pickReportSuggestion(el) {
  document.getElementById('reportQuestion').value = el.textContent;
  document.querySelectorAll('#suggestTags .suggest-tag').forEach(t => {
    t.style.background = ''; t.style.color = '';
  });
  el.style.background = 'var(--primary)';
  el.style.color = '#fff';
  generateSmartReport();
}

// ── 报告类型切换 ──
document.querySelectorAll('.report-type-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.report-type-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentReportType = btn.dataset.report;
    document.getElementById('reportQuestion').value = '';
    document.getElementById('reportResult').style.display = 'none';
    document.getElementById('reportEmpty').style.display = '';
    renderReportSuggestions(currentReportType);
  });
});

// 初始加载推荐问题
renderReportSuggestions(currentReportType);

// ── 生成报告 ──
async function generateSmartReport() {
  const question = document.getElementById('reportQuestion').value.trim();
  if (!question) {
    toast('请输入你的问题', 'error');
    return;
  }

  const btn = document.getElementById('generateReportBtn');
  const loading = document.getElementById('reportLoading');
  const resultDiv = document.getElementById('reportResult');
  const emptyDiv = document.getElementById('reportEmpty');

  btn.disabled = true;
  btn.textContent = '⏳ 分析中...';
  loading.style.display = 'flex';
  resultDiv.style.display = 'none';
  emptyDiv.style.display = 'none';

  try {
    const r = await fetch(`${REPORT_API}/${currentReportType}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'question=' + encodeURIComponent(question),
    });

    if (!r.ok) {
      const errText = await r.text();
      let errMsg = `请求失败 (HTTP ${r.status})`;
      try {
        const errJson = JSON.parse(errText);
        errMsg = errJson.detail || errMsg;
      } catch (_) {}
      toast(errMsg, 'error');
      emptyDiv.style.display = '';
      return;
    }

    const data = await r.json();
    renderSmartReport(data);
    resultDiv.style.display = '';
  } catch (e) {
    toast('请求失败: ' + e.message, 'error');
    emptyDiv.style.display = '';
  } finally {
    btn.disabled = false;
    btn.textContent = '📈 生成报告';
    loading.style.display = 'none';
  }
}

// ── 渲染报告 ──
function renderSmartReport(data) {
  // 1. 渲染润色后的报告文本（Markdown → HTML）
  const answerDiv = document.getElementById('reportAnswer');
  answerDiv.innerHTML = markdownToHtml(data.answer || '暂无报告内容');

  // 2. 渲染数据表格
  const tablesDiv = document.getElementById('reportTables');
  if (data.results && data.results.length > 0) {
    tablesDiv.innerHTML = '<h3 class="report-tables-title">📋 数据明细</h3>'
      + data.results.map((r, i) => renderResultTable(r, i + 1)).join('');
  } else {
    tablesDiv.innerHTML = '';
  }
}

// ── 单条结果渲染为表格 ──
function renderResultTable(result, index) {
  if (result.type !== 'SELECT' || !result.rows || result.rows.length === 0) {
    return `<div class="result-block">
      <div class="result-sql">SQL ${index}: ${escapeHtml(result.sql || '')}</div>
      <p style="color:#64748b;font-size:13px;margin:8px 0">(无数据)</p>
    </div>`;
  }

  const cols = result.columns || Object.keys(result.rows[0]);
  return `<div class="result-block">
    <div class="result-meta">查询 ${index} — 共 ${result.count} 条记录</div>
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>
        <tbody>
          ${result.rows.map(row => `<tr>${cols.map(c => {
            const v = row[c];
            if (v === null || v === undefined) return '<td class="null">—</td>';
            const s = String(v);
            // 截断过长文本
            return `<td title="${escapeHtml(s)}">${escapeHtml(s.length > 100 ? s.slice(0, 100) + '...' : s)}</td>`;
          }).join('')}</tr>`).join('')}
        </tbody>
      </table>
    </div>
    <details class="result-sql-detail">
      <summary>查看 SQL</summary>
      <code>${escapeHtml(result.sql || '')}</code>
    </details>
  </div>`;
}

// ── 简易 Markdown → HTML ──
function markdownToHtml(md) {
  if (!md) return '';
  let html = escapeHtml(md);

  // 标题
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');

  // 粗体 + 斜体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // 无序列表
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

  // 数字列表
  html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');

  // 分隔线
  html = html.replace(/^---+$/gm, '<hr>');

  // 换行
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');

  return '<p>' + html + '</p>';
}

// ── HTML 转义 ──
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
