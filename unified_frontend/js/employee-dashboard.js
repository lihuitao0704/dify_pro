/**
 * employee-dashboard.js — 企业工作台逻辑
 * 依赖: auth.js, chat.js
 */

const ENTERPRISE_API = 'http://localhost:8001/api/agent';
const FIT_API = 'http://localhost:8080/api/agent';  // 契合度评估服务入口
let chat;

// 图表实例池（每个结果容器一份）
const FIT_CHARTS = new WeakMap();
// 当前上传文件引用（工作台弹窗）
let fitCurrentFile = null;

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
      if (action === 'projectFit') openFit();
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


// ═══════════════════════════════════════════════════════════
// 项目契合度分析 — 工作台弹窗 (formal 员工视角)
// ═══════════════════════════════════════════════════════════

function openFit() {
  document.getElementById('projectFitModal').classList.add('active');
  // 复位所有动态区
  ['fitFormResult', 'fitUploadResult'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.remove('show'); el.innerHTML = ''; }
  });
  ['fitFormError', 'fitUploadError'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.style.display = 'none'; el.textContent = ''; }
  });
  ['fitFormLoading', 'fitUploadLoading'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  // 复位表单
  const form = document.getElementById('fitForm');
  if (form) form.reset();
  // 复位提交按钮
  const submitBtn = document.getElementById('fitForm').querySelector('.btn-submit');
  if (submitBtn) submitBtn.disabled = false;
  // 复位上传区
  fitCurrentFile = null;
  const upBtn = document.getElementById('fitUploadBtn');
  if (upBtn) upBtn.disabled = true;
  const info = document.getElementById('fitFileInfo');
  if (info) { info.style.display = 'none'; info.innerHTML = ''; }
  // 默认停留在「手动填写」
  switchFitTab('form');
}

function closeFit() {
  document.getElementById('projectFitModal').classList.remove('active');
}

function switchFitTab(tab) {
  const formTab = document.getElementById('tabFitForm');
  const upTab = document.getElementById('tabFitUpload');
  const formPanel = document.getElementById('fitFormPanel');
  const upPanel = document.getElementById('fitUploadPanel');
  // 复位结果/错误
  ['fitFormResult', 'fitUploadResult'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.remove('show'); el.innerHTML = ''; }
  });
  ['fitFormError', 'fitUploadError'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.style.display = 'none'; el.textContent = ''; }
  });

  const isForm = (tab === 'form');
  formTab.classList.toggle('active', isForm);
  upTab.classList.toggle('active', !isForm);
  formPanel.style.display = isForm ? '' : 'none';
  upPanel.style.display = isForm ? 'none' : '';
}

// ── 初始化 ──
document.addEventListener('DOMContentLoaded', () => {
  // 表单 submit
  const form = document.getElementById('fitForm');
  if (form) form.addEventListener('submit', submitFitForm);
  // 上传区
  initFitUpload();
});

// ── 表单提交 ──
async function submitFitForm(e) {
  e.preventDefault();
  const submitBtn = document.querySelector('#fitForm .btn-submit');
  const loading = document.getElementById('fitFormLoading');
  const errEl = document.getElementById('fitFormError');
  const resultEl = document.getElementById('fitFormResult');

  // 校验姓名
  const name = document.getElementById('fit_name')?.value.trim();
  if (!name) { showFitError('fitFormError', '请填写客户姓名'); return; }

  submitBtn.disabled = true;
  loading.style.display = 'flex';
  errEl.style.display = 'none'; errEl.textContent = '';
  resultEl.classList.remove('show'); resultEl.innerHTML = '';

  const fields = {
    name,
    age: val('fit_age'),
    phone: val('fit_phone'),
    education: val('fit_education'),
    major: val('fit_major'),
    target_country: val('fit_target_country'),
    target_major: val('fit_target_major'),
    gpa: val('fit_gpa'),
    language_score: val('fit_language_score'),
    budget: val('fit_budget'),
    is_Closed_loop: val('fit_is_Closed_loop'),
    development: val('fit_development'),
    abilities: val('fit_abilities'),
    wechat: val('fit_wechat'),
    email: val('fit_email'),
    // 员工视角 → 正式语气
    student_view: 'false',
  };

  try {
    const res = await fetch(`${FIT_API}/evaluation/detail`, {
      method: 'POST',
      body: encodeMultipart(fields),
    });
    const data = await res.json();
    if (data.code !== 0) {
      showFitError('fitFormError', data.msg || '研判失败');
      return;
    }
    renderFitResult(resultEl, data.data);
  } catch (err) {
    showFitError('fitFormError', '请求失败：' + err.message);
  } finally {
    submitBtn.disabled = false;
    loading.style.display = 'none';
  }
}

// ── 文件上传 ──
function initFitUpload() {
  const zone = document.getElementById('fitDropZone');
  const fileInput = document.getElementById('fitFileInput');
  if (!zone || !fileInput) return;

  zone.addEventListener('click', () => fileInput.click());

  ['dragenter', 'dragover'].forEach(ev =>
    zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('dragover'); })
  );
  ['dragleave', 'drop'].forEach(ev =>
    zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.remove('dragover'); })
  );
  zone.addEventListener('drop', e => {
    const f = e.dataTransfer?.files?.[0];
    if (f) handleFitFile(f);
  });
  fileInput.addEventListener('change', e => {
    const f = e.target.files?.[0];
    if (f) handleFitFile(f);
  });

  document.getElementById('fitUploadBtn').addEventListener('click', uploadFitFile);
}

function handleFitFile(file) {
  const suffix = (file.name.split('.').pop() || '').toLowerCase();
  if (!['txt', 'pdf', 'docx'].includes(suffix)) {
    showFitError('fitUploadError', '不支持的文件类型，请上传 txt / pdf / docx');
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showFitError('fitUploadError', '文件过大，请上传 10MB 以内的文件');
    return;
  }
  fitCurrentFile = file;
  const errEl = document.getElementById('fitUploadError');
  errEl.style.display = 'none'; errEl.textContent = '';

  const info = document.getElementById('fitFileInfo');
  info.innerHTML =
    `<span class="fit-upload-file-name">📄 ${escapeHtml(file.name)}（${(file.size/1024).toFixed(1)} KB）</span>` +
    `<button class="fit-upload-remove" onclick="clearFitFile()" title="移除">×</button>`;
  info.style.display = 'flex';
  document.getElementById('fitUploadBtn').disabled = false;
}

function clearFitFile() {
  fitCurrentFile = null;
  const fileInput = document.getElementById('fitFileInput');
  if (fileInput) fileInput.value = '';
  const info = document.getElementById('fitFileInfo');
  info.style.display = 'none'; info.innerHTML = '';
  document.getElementById('fitUploadBtn').disabled = true;
}

async function uploadFitFile() {
  if (!fitCurrentFile) return;
  const loading = document.getElementById('fitUploadLoading');
  const errEl = document.getElementById('fitUploadError');
  const resultEl = document.getElementById('fitUploadResult');
  const btn = document.getElementById('fitUploadBtn');

  btn.disabled = true;
  loading.style.display = 'flex';
  errEl.style.display = 'none'; errEl.textContent = '';
  resultEl.classList.remove('show'); resultEl.innerHTML = '';

  const fd = new FormData();
  fd.append('file', fitCurrentFile);
  fd.append('student_view', 'false');

  try {
    const res = await fetch(`${FIT_API}/evaluation/detail`, {
      method: 'POST',
      body: fd,
    });
    const data = await res.json();
    if (data.code !== 0) {
      showFitError('fitUploadError', data.msg || '研判失败');
      return;
    }
    renderFitResult(resultEl, data.data);
  } catch (err) {
    showFitError('fitUploadError', '请求失败：' + err.message);
  } finally {
    btn.disabled = false;
    loading.style.display = 'none';
  }
}

// ── 工具函数 ──
function val(id) {
  const el = document.getElementById(id);
  if (!el) return undefined;
  const v = el.value.trim();
  return v === '' ? undefined : v;
}

function encodeMultipart(obj) {
  return new URLSearchParams(
    Object.entries(obj).filter(([, v]) => v !== undefined)
  );
}

function showFitError(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
}

// ── 四合一渲染：契合徽章 + 百分制 + 维度雷达图 + LLM 文本 ──
function renderFitResult(container, data) {
  if (!container) return;
  container.innerHTML = '';
  container.classList.add('show');

  const results = Array.isArray(data.results) ? data.results : [];
  const summary = data.summary || '';
  const passThreshold = data.pass_threshold || 60;

  if (results.length === 0 && summary) {
    // 兜底：仅有 NL 文本
    const pre = document.createElement('pre');
    pre.className = 'fit-summary';
    pre.textContent = summary;
    container.appendChild(pre);
    return;
  }

  // 逐个 project 渲染
  results.forEach((r, idx) => {
    const percent = r.max_score > 0 ? Math.round(r.total_score / r.max_score * 100) : 0;
    const passed = r.is_pass;
    // 如有多个项目，加上编号标题
    const projLabel = results.length > 1
      ? `${idx + 1}. ${r.project_name}`
      : r.project_name;

    // 1) 契合徽章
    const badge = document.createElement('div');
    badge.className = 'fit-badge ' + (passed ? 'pass' : 'fail');
    badge.textContent = passed ? '✓ 契合' : '✗ 未契合';
    // 居中对齐容器
    const badgeWrap = document.createElement('div');
    badgeWrap.style.textAlign = 'center';
    badgeWrap.appendChild(badge);
    container.appendChild(badgeWrap);

    // 2) 项目卡片（百分制 + 维度条 + 雷达图）
    const card = document.createElement('div');
    card.className = 'fit-project';
    card.innerHTML = `
      <div class="fit-project-header">
        <span class="fit-project-name">${escapeHtml(projLabel)}</span>
        <span style="font-size:12px;color:var(--text-secondary)">总分 ${r.total_score} / ${r.max_score}</span>
      </div>
    `;

    // 百分制环形环
    const scoreWrap = document.createElement('div');
    scoreWrap.className = 'fit-score';
    const r26 = 26;
    const circ = 2 * Math.PI * r26;
    const offset = circ * (1 - percent / 100);
    scoreWrap.innerHTML = `
      <div class="fit-score-ring">
        <svg width="56" height="56" viewBox="0 0 56 56">
          <circle class="ring-bg" cx="28" cy="28" r="${r26}"/>
          <circle class="ring-fg ${passed ? 'pass' : 'fail'}" cx="28" cy="28" r="${r26}"
            stroke-dasharray="${circ}" stroke-dashoffset="${offset}"/>
        </svg>
        <div class="fit-score-num">
          <span class="pct">${percent}%</span>
          <span class="lbl">${passed ? '契合' : '未契合'}</span>
        </div>
      </div>
    `;
    card.appendChild(scoreWrap);

    // 维度明细条
    const dims = Array.isArray(r.dimensions) ? r.dimensions : [];
    if (dims.length > 0) {
      const dimsWrap = document.createElement('div');
      dimsWrap.className = 'fit-dims';
      dims.forEach(d => {
        const pct = d.max > 0 ? Math.round(d.score / d.max * 100) : 0;
        const fillClass = pct >= 60 ? 'hi' : (pct >= 30 ? 'mid' : 'low');
        const row = document.createElement('div');
        row.className = 'fit-dim';
        row.innerHTML = `
          <span class="fit-dim-name">${escapeHtml(d.name || d.key)}</span>
          <div class="fit-dim-bar"><div class="fit-dim-bar-fill ${fillClass}" style="width:${pct}%"></div></div>
          <span class="fit-dim-val">${d.score}/${d.max}</span>
        `;
        dimsWrap.appendChild(row);
      });
      card.appendChild(dimsWrap);

      // 雷达图
      const radar = document.createElement('div');
      radar.className = 'fit-radar';
      const canvas = document.createElement('canvas');
      radar.appendChild(canvas);
      card.appendChild(radar);
      // 使用 requestAnimationFrame 保证容器已布局
      requestAnimationFrame(() => renderFitRadar(canvas, dims));
    }

    container.appendChild(card);
  });

  // 4) LLM 文本（统一摘要）
  if (summary) {
    const pre = document.createElement('pre');
    pre.className = 'fit-summary';  // 员工视角 → 不添加 .student（深蓝色边框，正式）
    pre.textContent = summary;
    container.appendChild(pre);
  }
}

// ── Chart.js 雷达图（无依赖回退：当 Chart.js 未加载时，采用纯文本维度清单） ──
function renderFitRadar(canvas, dims) {
  if (typeof Chart === 'undefined') {
    // 回退：移除雷达容器，维度条已经表达了信息
    const wrap = canvas.parentElement;
    if (wrap) wrap.style.display = 'none';
    return;
  }
  // 销毁旧实例（如果有）
  const prev = FIT_CHARTS.get(canvas);
  if (prev) prev.destroy();

  const labels = dims.map(d => d.name || d.key);
  const dataScores = dims.map(d => d.max > 0 ? +(d.score / d.max * 100).toFixed(1) : 0);
  // 闭合雷达：末尾补首项
  const closedLabels = labels.length >= 3 ? [...labels, labels[0]] : labels;
  const closedData = dims.length >= 3 ? [...dataScores, dataScores[0]] : dataScores;

  const chart = new Chart(canvas, {
    type: 'radar',
    data: {
      labels: closedLabels,
      datasets: [{
        label: '维度得分率 (%)',
        data: closedData,
        fill: true,
        backgroundColor: 'rgba(74, 144, 217, 0.18)',
        borderColor: 'rgba(74, 144, 217, 0.9)',
        pointBackgroundColor: '#4a90d9',
        pointBorderColor: '#fff',
        pointBorderWidth: 1.5,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 1,
      scales: {
        r: {
          min: 0, max: 100,
          ticks: { stepSize: 25, display: false },
          grid: { color: 'rgba(0,0,0,0.08)' },
          angleLines: { color: 'rgba(0,0,0,0.08)' },
          pointLabels: {
            font: { size: 11 },
            color: '#475569',
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.label}: ${ctx.raw}%`,
          },
        },
      },
    },
  });
  FIT_CHARTS.set(canvas, chart);
}
