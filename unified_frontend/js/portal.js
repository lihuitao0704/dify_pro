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
    });
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
    if (!user || !pass) { toast('请输入用户名和密码', 'error'); return; }

    let result;
    try {
      if (role === 'student') {
        result = await Auth.studentLogin(user, pass);
      } else {
        result = await Auth.employeeLogin(user, pass);
      }
    } catch (err) {
      toast('无法连接服务，请检查网络后重试', 'error');
      return;
    }

    if (result.success) {
      location.href = role === 'student' ? '/portal/student-dashboard' : '/portal/employee-dashboard';
    } else {
      toast(result.message || '用户名或密码不正确', 'error');
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
// 智能诊断 (Smart Diagnosis Modal)
// ============================================================

// 标签切换：form / upload
function switchDiagnoseTab(tab) {
  const formPanel = document.getElementById('diagnoseFormPanel');
  const uploadPanel = document.getElementById('diagnoseUploadPanel');
  const tabForm = document.getElementById('tabForm');
  const tabUpload = document.getElementById('tabUpload');
  const resultBox = document.getElementById('d_resultBox');
  const errorMsg = document.getElementById('d_errorMsg');

  // 隐藏之前的结果
  resultBox.classList.remove('show', 'success', 'fail');
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

// 简历上传相关变量
let resumeFile = null;

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
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });
  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
  });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handleResumeFile(file);
  });
}

function handleResumeFile(file) {
  const allowedExt = ['txt', 'pdf', 'docx'];
  const ext = file.name.rsplit('.', 1)[-1].toLowerCase();
  if (!allowedExt.includes(ext)) {
    showDiagnoseError('不支持的文件格式，仅支持 TXT / PDF / DOCX');
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showDiagnoseError('文件过大，请上传 10MB 以内的文件');
    return;
  }
  resumeFile = file;
  document.getElementById('d_fileName').textContent = file.name;
  document.getElementById('d_fileInfo').style.display = 'flex';
  document.getElementById('d_uploadBtn').disabled = false;
  // 隐藏错误
  document.getElementById('d_errorMsg').style.display = 'none';
}

function clearResumeFile() {
  resumeFile = null;
  document.getElementById('d_fileInput').value = '';
  document.getElementById('d_fileInfo').style.display = 'none';
  document.getElementById('d_uploadBtn').disabled = true;
}

function submitResume() {
  if (!resumeFile) return;

  const loading = document.getElementById('d_loading');
  const errorMsg = document.getElementById('d_errorMsg');
  const resultBox = document.getElementById('d_resultBox');
  const resultTitle = document.getElementById('d_resultTitle');
  const resultContent = document.getElementById('d_resultContent');
  const uploadBtn = document.getElementById('d_uploadBtn');

  errorMsg.style.display = 'none';
  resultBox.classList.remove('show', 'success', 'fail');
  uploadBtn.disabled = true;
  loading.style.display = 'block';

  // 构建 FormData 上传文件
  const fd = new FormData();
  fd.append('file', resumeFile);

  fetch('http://localhost:8080/api/agent/resume/upload', {
    method: 'POST',
    body: fd,
  })
    .then(async (res) => {
      const data = await res.json();
      if (data.code !== 0) throw new Error(data.msg || '诊断失败');

      const result = data.data.assessment_result || '诊断完成，无详细结论。';
      resultContent.textContent = result;
      if (result.includes('已通过') && !result.includes('已通过 0 人')) {
        resultBox.classList.add('success');
        resultTitle.textContent = '研判结论 - 已通过';
      } else {
        resultBox.classList.add('fail');
        resultTitle.textContent = '研判结论 - 暂未达标';
      }
      resultBox.classList.add('show');
    })
    .catch((err) => {
      showDiagnoseError(err.message);
    })
    .finally(() => {
      uploadBtn.disabled = false;
      loading.style.display = 'none';
    });
}

function showDiagnoseError(msg) {
  const errorMsg = document.getElementById('d_errorMsg');
  errorMsg.textContent = '错误：' + msg;
  errorMsg.style.display = 'block';
}
function openDiagnose() {
  document.getElementById('diagnoseModal').classList.add('active');
  // 隐藏之前的结果
  document.getElementById('d_resultBox').classList.remove('show', 'success', 'fail');
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
    const resultBox = document.getElementById('d_resultBox');
    const resultTitle = document.getElementById('d_resultTitle');
    const resultContent = document.getElementById('d_resultContent');

    // 隐藏之前的结果
    errorMsg.style.display = 'none';
    resultBox.classList.remove('show', 'success', 'fail');
    submitBtn.disabled = true;
    loading.style.display = 'block';

    // 收集表单数据
    const formData = {
      name: document.getElementById('d_name').value,
      age: parseInt(document.getElementById('d_age').value),
      major: document.getElementById('d_major').value,
      education: document.getElementById('d_education').value,
      target_major: document.getElementById('d_target_major').value,
      language_score: document.getElementById('d_language_score').value,
      target_country: document.getElementById('d_target_country').value,
      gpa: parseFloat(document.getElementById('d_gpa').value),
      budget: parseFloat(document.getElementById('d_budget').value),
      phone: document.getElementById('d_phone').value,
      development: document.getElementById('d_development').value,
      abilities: document.getElementById('d_abilities').value,
      is_Closed_loop: document.getElementById('d_is_Closed_loop').value,
      wechat: document.getElementById('d_wechat').value || null,
      email: document.getElementById('d_email').value || null,
      conversation_id: null
    };

    try {
      // 调用 Assessment 研判接口
      const res = await fetch('http://localhost:8080/api/agent/resume/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      const data = await res.json();

      if (data.code !== 0) {
        throw new Error(data.msg || '诊断失败');
      }

      const result = data.data.assessment_result || '诊断完成，无详细结论。';
      resultContent.textContent = result;

      // 根据结论判断是"通过"还是"未通过"
      if (result.includes('已通过') && !result.includes('已通过 0 人')) {
        resultBox.classList.add('success');
        resultTitle.textContent = '研判结论 - 已通过';
      } else {
        resultBox.classList.add('fail');
        resultTitle.textContent = '研判结论 - 暂未达标';
      }

      resultBox.classList.add('show');

    } catch (err) {
      errorMsg.textContent = '错误：' + err.message;
      errorMsg.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      loading.style.display = 'none';
    }
  });
}

// ============================================================
// Public Customer Agent Chat
// ============================================================
let publicSessionId = null;
function initPublicChat() {
  const input = document.getElementById('publicInput');
  const btn = document.getElementById('publicSendBtn');
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') publicSend(); });
  btn.addEventListener('click', publicSend);

  // 彩蛋：输入框聚焦时显示提示
  input.addEventListener('focus', () => {
    input.placeholder = '试试：德国留学有什么要求？';
  });
  input.addEventListener('blur', () => {
    input.placeholder = '输入你的留学问题...';
  });
}

async function publicSend() {
  const input = document.getElementById('publicInput');
  const btn = document.getElementById('publicSendBtn');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  btn.disabled = true;
  addPublicMsg(text, 'user');

  // 打字动画
  const typingEl = document.createElement('div');
  typingEl.className = 'msg-item bot typing';
  typingEl.innerHTML = '<span class="avatar">AI</span><div class="bubble">思考中<span class="dots">...</span></div>';
  const box = document.querySelector('.hero-chat-card .chat-mockup');
  if (box) box.appendChild(typingEl);

  try {
    // 直接调用客服Agent（同域下 /chat 是对 customer_agent 的直接调用）
    // 在统一门户部署模式下，前端通过代理转发；直连模式直接访问
    let r;
    try {
      r = await fetch('http://localhost:9000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: publicSessionId }),
      });
      r = await r.json();
    } catch (err) {
      // fallback: 尝试相对路径
      r = await api('/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text, session_id: publicSessionId }),
      });
    }
    publicSessionId = r.session_id;
    removeTyping();
    addPublicMsg(r.reply || '(无回复)', 'bot');
  } catch (err) {
    removeTyping();
    addPublicMsg('暂时连接不上 AI 服务，请稍后再试～\n(' + err.message.slice(0, 80) + ')', 'bot');
  } finally {
    btn.disabled = false;
  }
}

function addPublicMsg(text, who) {
  const box = document.querySelector('.hero-chat-card .chat-mockup');
  if (!box) return;
  // 移除 mock 提示类的内容（前3条是静态 mock），只追加到末尾
  const div = document.createElement('div');
  div.className = 'msg-item ' + who;
  if (who === 'user') {
    div.innerHTML = `<div class="bubble">${escapeHTML(text)}</div><span class="avatar">你</span>`;
  } else {
    div.innerHTML = `<span class="avatar">AI</span><div class="bubble">${escapeHTML(text).replace(/\n/g, '<br/>')}</div>`;
  }
  box.appendChild(div);
  // 滚动到底部（如果模拟框有滚动）
  box.scrollTop = box.scrollHeight;
}

function removeTyping() {
  document.querySelectorAll('.hero-chat-card .typing').forEach(el => el.remove());
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
