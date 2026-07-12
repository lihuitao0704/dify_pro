/**
 * portal.js — 统一门户首页逻辑
 */
document.addEventListener('DOMContentLoaded', () => {
  initLoginTabs();
  initLoginForms();
  initPublicChat();
  initSmartDiagnose();
});

// ============================================================
// Login Modal
// ============================================================
function openLogin() {
  document.getElementById('loginModal').classList.add('active');
}
function closeLogin() {
  document.getElementById('loginModal').classList.remove('active');
}
document.getElementById('loginBtn').addEventListener('click', openLogin);

// Click outside to close
document.getElementById('loginModal').addEventListener('click', (e) => {
  if (e.target === document.getElementById('loginModal')) closeLogin();
});

function initLoginTabs() {
  document.querySelectorAll('.login-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.login-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const role = tab.dataset.role;
      document.getElementById('studentLoginForm').style.display = role === 'student' ? 'block' : 'none';
      document.getElementById('employeeLoginForm').style.display = role === 'employee' ? 'block' : 'none';
      clearLoginErrors();
    });
  });
}

// 登录错误提示（模块级，供 initLoginTabs 和 initLoginForms 共用）
function showLoginError(role, msg) {
  const errEl = document.getElementById(role === 'student' ? 'studentLoginError' : 'employeeLoginError');
  if (errEl) { errEl.textContent = msg; errEl.style.display = ''; }
}
function clearLoginErrors() {
  ['studentLoginError', 'employeeLoginError'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = ''; el.style.display = 'none'; }
  });
}

function initLoginForms() {

  // 复用 auth.js 中的登录方法（Auth.studentLogin / Auth.employeeLogin）
  // 这些方法已内置员工 demo 账号 fallback，前后端逻辑保持一致
  async function doLogin(role) {
    const userEl = document.getElementById(role === 'student' ? 'studentUser' : 'employeeUser');
    const passEl = document.getElementById(role === 'student' ? 'studentPass' : 'employeePass');
    const user = userEl.value.trim();
    const pass = passEl.value;
    clearLoginErrors();
    if (!user || !pass) { showLoginError(role, '请输入用户名和密码'); return; }

    let result;
    try {
      if (role === 'student') {
        result = await Auth.studentLogin(user, pass);
      } else {
        result = await Auth.employeeLogin(user, pass);
      }
    } catch (err) {
      var netMsg = '无法连接服务，请检查网络后重试';
      showLoginError(role, netMsg);
      toast(netMsg, 'error');
      return;
    }

    if (result.success) {
      location.href = role === 'student' ? '/portal/student-dashboard' : '/portal/employee-dashboard';
    } else {
      var errMsg = result.message || '用户名或密码不正确';
      showLoginError(role, errMsg);
      toast(errMsg, 'error');
    }
  }

  // 用表单submit事件
  var sf = document.getElementById('studentLoginForm');
  var ef = document.getElementById('employeeLoginForm');
  if (sf) sf.addEventListener('submit', function(e) { e.preventDefault(); doLogin('student'); });
  if (ef) ef.addEventListener('submit', function(e) { e.preventDefault(); doLogin('employee'); });
  // 兜底：按钮点击
  var sb = document.querySelector('#studentLoginForm button[type="submit"]');
  var eb = document.querySelector('#employeeLoginForm button[type="submit"]');
  if (sb) sb.addEventListener('click', function(e) { e.preventDefault(); doLogin('student'); });
  if (eb) eb.addEventListener('click', function(e) { e.preventDefault(); doLogin('employee'); });
  // 回车键
  document.getElementById('studentPass').addEventListener('keydown', function(e) { if(e.key==='Enter') doLogin('student'); });
  document.getElementById('employeePass').addEventListener('keydown', function(e) { if(e.key==='Enter') doLogin('employee'); });
}

// ============================================================
// 项目契合度分析 (Smart Diagnosis Modal, portal.js 学生视角)
// ============================================================
// 统一渲染入口：fitResult container (id="d_fitResult")
// LLM 语气：学生视角 (student_view=true → 温暖亲近)

// 评估服务地址
const P_DIAGNOSE_API = 'http://localhost:8080/api/agent';
// 门户 学生视角 样本 占位 宽容度
const P_FIT_CHARTS = new WeakMap();
let resumeFile = null;

// 标签切换：form / upload
function switchDiagnoseTab(tab) {
  const formPanel = document.getElementById('diagnoseFormPanel');
  const uploadPanel = document.getElementById('diagnoseUploadPanel');
  const tabForm = document.getElementById('tabForm');
  const tabUpload = document.getElementById('tabUpload');
  const errorMsg = document.getElementById('d_errorMsg');
  const fitResult = document.getElementById('d_fitResult');

  // 隐藏之前的结果
  if (fitResult) { fitResult.classList.remove('show'); fitResult.innerHTML = ''; }
  errorMsg.style.display = 'none';

  if (tab === 'form') {
    formPanel.style.display = '';
    uploadPanel.style.display = 'none';
    tabForm.classList.add('active');
    tabUpload.classList.remove('active');
  } else {
    formPanel.style.display = 'none';
    uploadPanel.style.display = '';
    tabUpload.classList.add('active');
    tabForm.classList.remove('active');
  }
}

// 初始化文件上传区域事件
function initResumeUpload() {
  const dropZone = document.getElementById('d_dropZone');
  const fileInput = document.getElementById('d_fileInput');

  // 点击触发文件选择
  dropZone.addEventListener('click', () => fileInput.click());

  // 文件选择
  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) handleResumeFile(file);
  });

  // 拖拽事件
  const dz = dropZone;
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('dragover'); });
  dz.addEventListener('dragleave', () => { dz.classList.remove('dragover'); });
  dz.addEventListener('drop', (e) => {
    e.preventDefault(); dz.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handleResumeFile(file);
  });
}

function handleResumeFile(file) {
  const allowedExt = ['txt', 'pdf', 'docx'];
  const ext = file.name.split('.').pop().toLowerCase();
  if (!allowedExt.includes(ext)) {
    showDiagnoseError('不支持的文件格式，仅支持 txt / pdf / docx');
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showDiagnoseError('文件过大，请上传 10MB 以内的文件');
    return;
  }
  resumeFile = file;
  const info = document.getElementById('d_fileInfo');
  info.innerHTML =
    `<span class="resume-file-name">📄 ${escapeHTML(file.name)} (${(file.size/1024).toFixed(1)} KB)</span>` +
    `<button class="resume-file-remove" onclick="clearResumeFile()" title="移除">×</button>`;
  info.style.display = 'flex';
  document.getElementById('d_uploadBtn').disabled = false;
  document.getElementById('d_errorMsg').style.display = 'none';
}

function clearResumeFile() {
  resumeFile = null;
  document.getElementById('d_fileInput').value = '';
  document.getElementById('d_fileInfo').style.display = 'none';
  document.getElementById('d_uploadBtn').disabled = true;
}

// 门户——文件模式：走 evaluation/detail (multipart, 含 file + student_view)
async function submitResume() {
  if (!resumeFile) return;
  const loading = document.getElementById('d_loading');
  const errorMsg = document.getElementById('d_errorMsg');
  const fitResult = document.getElementById('d_fitResult');
  const uploadBtn = document.getElementById('d_uploadBtn');

  errorMsg.style.display = 'none';
  if (fitResult) { fitResult.classList.remove('show'); fitResult.innerHTML = ''; }
  uploadBtn.disabled = true;
  loading.style.display = 'block';

  const fd = new FormData();
  fd.append('file', resumeFile);
  fd.append('student_view', 'true');

  try {
    const res = await fetch(`${P_DIAGNOSE_API}/evaluation/detail`, { method: 'POST', body: fd });
    const data = await res.json();
    if (data.code !== 0) throw new Error(data.msg || '评估失败');
    renderFitResult(fitResult, data.data, true);
  } catch (err) {
    showDiagnoseError(err.message);
  } finally {
    uploadBtn.disabled = false;
    loading.style.display = 'none';
  }
}

function showDiagnoseError(msg) {
  const errorMsg = document.getElementById('d_errorMsg');
  errorMsg.textContent = '错误：' + msg;
  errorMsg.style.display = 'block';
}

function openDiagnose() {
  document.getElementById('diagnoseModal').classList.add('active');
  const fitResult = document.getElementById('d_fitResult');
  if (fitResult) { fitResult.classList.remove('show'); fitResult.innerHTML = ''; }
  document.getElementById('d_errorMsg').style.display = 'none';
  document.getElementById('d_submitBtn').disabled = false;
}
function closeDiagnose() {
  document.getElementById('diagnoseModal').classList.remove('active');
}
document.getElementById('smartDiagnoseBtn').addEventListener('click', openDiagnose);
// 点击弹窗外部关闭
document.getElementById('diagnoseModal').addEventListener('click', (e) => {
  if (e.target === document.getElementById('diagnoseModal')) closeDiagnose();
});

function initSmartDiagnose() {
  initResumeUpload();
  document.getElementById('diagnoseForm').addEventListener('submit', async function(e) {
    e.preventDefault();

    const submitBtn = document.getElementById('d_submitBtn');
    const loading = document.getElementById('d_loading');
    const errorMsg = document.getElementById('d_errorMsg');
    const fitResult = document.getElementById('d_fitResult');

    errorMsg.style.display = 'none';
    if (fitResult) { fitResult.classList.remove('show'); fitResult.innerHTML = ''; }
    submitBtn.disabled = true;
    loading.style.display = 'block';

    // 收集表单数据（学生端专用字段，与新接口 multipart 对齐）
    const fd = new URLSearchParams();
    const fdMap = {
      name: 'd_name', age: 'd_age', major: 'd_major', education: 'd_education',
      target_major: 'd_target_major', language_score: 'd_language_score',
      target_country: 'd_target_country', gpa: 'd_gpa', budget: 'd_budget',
      phone: 'd_phone', development: 'd_development', abilities: 'd_abilities',
      is_Closed_loop: 'd_is_Closed_loop', wechat: 'd_wechat', email: 'd_email',
    };
    for (const [k, id] of Object.entries(fdMap)) {
      const el = document.getElementById(id);
      if (el && el.value.trim() !== '') fd.append(k, el.value.trim());
    }
    // 学生视角
    fd.append('student_view', 'true');

    try {
      const res = await fetch(`${P_DIAGNOSE_API}/evaluation/detail`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: fd.toString(),
      });
      const data = await res.json();
      if (data.code !== 0) throw new Error(data.msg || '评估失败');
      renderFitResult(fitResult, data.data, true);
    } catch (err) {
      showDiagnoseError(err.message);
    } finally {
      submitBtn.disabled = false;
      loading.style.display = 'none';
    }
  });
}

// ============================================================
// 四合一渲染器：契合徽章 + 百分制环形 + 维度雷达图 + LLM 文本
// ============================================================
/**
 * @param {HTMLElement} container  result wrapper
 * @param {Object} data           { user_id, summary, pass_threshold, results: [...] }
 * @param {boolean} studentView   学生视角: true → .fit_summary.student (绿色), false → 企业版深蓝
 */
function renderFitResult(container, data, studentView) {
  if (!container) return;
  if (!data) return;
  container.innerHTML = '';
  container.classList.add('show');

  const results = Array.isArray(data.results) ? data.results : [];
  const summary = data.summary || '';

  if (results.length === 0 && summary) {
    const pre = document.createElement('pre');
    pre.className = 'fit-summary' + (studentView ? ' student' : '');
    pre.textContent = summary;
    container.appendChild(pre);
    return;
  }

  results.forEach((r, idx) => {
    const percent = r.max_score > 0 ? Math.round(r.total_score / r.max_score * 100) : 0;
    const passed = !!r.is_pass;
    const projLabel = results.length > 1 ? `${idx + 1}. ${r.project_name}` : r.project_name;

    // 1) 契合徽章
    const badge = document.createElement('div');
    badge.className = 'fit-badge ' + (passed ? 'pass' : 'fail');
    badge.textContent = passed ? '✓ 契合' : '✗ 未契合';
    const badgeWrap = document.createElement('div');
    badgeWrap.style.textAlign = 'center';
    badgeWrap.appendChild(badge);
    container.appendChild(badgeWrap);

    // 2) 项目卡（百分制环形 + 维度条 + 雷达图）
    const card = document.createElement('div');
    card.className = 'fit-project';
    card.innerHTML = `
      <div class="fit-project-header">
        <span class="fit-project-name">${escapeHTML(projLabel)}</span>
        <span style="font-size:12px;color:var(--text-secondary)">总分 ${r.total_score} / ${r.max_score}</span>
      </div>
    `;

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
          <span class="fit-dim-name">${escapeHTML(d.name || d.key)}</span>
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
      requestAnimationFrame(() => renderFitRadar(canvas, dims));
    }

    container.appendChild(card);
  });

  // 4) LLM 文本（统一摘要）
  if (summary) {
    const pre = document.createElement('pre');
    pre.className = 'fit-summary' + (studentView ? ' student' : '');
    pre.textContent = summary;
    container.appendChild(pre);
  }
}

// ── Chart.js 雷达图（无依赖回退：维度条已表达信息，雷达隐藏） ──
function renderFitRadar(canvas, dims) {
  if (typeof Chart === 'undefined') {
    const wrap = canvas.parentElement;
    if (wrap) wrap.style.display = 'none';
    return;
  }
  if (P_FIT_CHARTS.has(canvas)) {
    P_FIT_CHARTS.get(canvas).destroy();
    P_FIT_CHARTS.delete(canvas);
  }
  const labels = dims.map(d => d.name || d.key);
  const data = dims.map(d => d.max > 0 ? +(d.score / d.max * 100).toFixed(1) : 0);
  const closedLabels = labels.length >= 3 ? [...labels, labels[0]] : labels;
  const closedData = dims.length >= 3 ? [...data, data[0]] : data;

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
          pointLabels: { font: { size: 11 }, color: '#475569' },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw}%` } },
      },
    },
  });
  P_FIT_CHARTS.set(canvas, chart);
}

// ============================================================
// 智能客服弹框（浮动按钮 + 弹出式滚动聊天）
// ============================================================
let popupChat = null;

function initPublicChat() {
  // Hero CTA 按钮 → 打开弹框
  document.getElementById('heroOpenChatBtn')?.addEventListener('click', () => {
    toggleChatPopup(true);
  });

  // 初始化 ChatWidget（绑定到弹框的消息容器 + 输入框）
  popupChat = new ChatWidget({
    apiUrl: resolveApiUrl() + '/chat',
    container: '#chatPopupMessages',
    input: '#chatPopupInput',
    sendBtn: '#chatPopupSendBtn',
    welcome: '嗨同学你好呀 👋 我是粤教留学小助手，有什么留学相关问题尽管问我！',
  });
}

function resolveApiUrl() {
  // 统一门户模式下 /api 代理到 customer_agent(:9000)；直连用 localhost:8000
  if (location.port === '9000') return '';
  if (location.port === '8000') return '';
  return 'http://localhost:9000';
}

function toggleChatPopup(forceOpen) {
  const pop = document.getElementById('chatPopup');
  const fab = document.getElementById('chatFab');
  const shouldBeOpen = forceOpen === true ? true : !pop.classList.contains('active');
  if (shouldBeOpen) {
    pop.classList.add('active');
    fab?.classList.add('hidden');
    document.getElementById('chatFabBadge').style.display = 'none';
    // 聚焦输入框（延迟等动画结束）
    setTimeout(() => document.getElementById('chatPopupInput')?.focus(), 250);
  } else {
    pop.classList.remove('active');
    fab?.classList.remove('hidden');
  }
}

function popupSend() {
  // 直接转发给 ChatWidget
  if (popupChat) popupChat.send();
}

function quickAsk(text) {
  toggleChatPopup(true);
  setTimeout(() => {
    const input = document.getElementById('chatPopupInput');
    if (input) input.value = text;
    if (popupChat) popupChat.send();
  }, 300);
}

// 平滑滚动
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', (e) => {
    const target = document.querySelector(a.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});
