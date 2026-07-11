/**
 * portal.js — 统一门户首页逻辑
 */
document.addEventListener('DOMContentLoaded', () => {
  initLoginTabs();
  initLoginForms();
  initPublicChat();
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
  // Student login
  document.getElementById('studentLoginForm').addEventListener('submit', async e => {
    e.preventDefault();
    const id = document.getElementById('studentId').value.trim();
    const name = document.getElementById('studentName').value.trim();
    try {
      const r = await api('/agent/student/auth/login', {
        method: 'POST',
        body: JSON.stringify({ student_id: parseInt(id), name }),
      });
      if (r.success) {
        localStorage.setItem('user_role', 'student');
        localStorage.setItem('user_id', id);
        localStorage.setItem('user_name', name);
        toast('登录成功！正在进入学生助手...', 'success');
        setTimeout(() => {
          window.open('/portal/student-dashboard', '_self');
        }, 600);
      } else {
        toast(r.message || '学号或姓名不正确', 'error');
      }
    } catch (err) {
      // Fallback: 直接调 student_agent 本地接口
      try {
        const resp = await fetch('http://localhost:8000/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ student_id: parseInt(id), name }),
        });
        const r2 = await resp.json();
        if (r2.success) {
          localStorage.setItem('user_role', 'student');
          localStorage.setItem('user_id', id);
          localStorage.setItem('user_name', name);
          toast('登录成功！正在进入学生助手...', 'success');
          setTimeout(() => window.open('/portal/student-dashboard', '_self'), 600);
        } else {
          toast('学号或姓名不正确', 'error');
        }
      } catch (e2) {
        toast('无法连接学生服务：' + e2.message, 'error');
      }
    }
  });

  // Employee login
  document.getElementById('employeeLoginForm').addEventListener('submit', async e => {
    e.preventDefault();
    const user = document.getElementById('employeeUser').value.trim();
    const pass = document.getElementById('employeePass').value;
    try {
      // TODO: 等 enterprise_agent 暴露 /auth/login 后替换
      // 演示用硬编码 admin/admin123
      if (user === 'admin' && pass === 'admin123') {
        localStorage.setItem('user_role', 'employee');
        localStorage.setItem('user_name', user);
        localStorage.setItem('employee_token', 'demo-token');
        toast('登录成功！正在进入企业工作台...', 'success');
        setTimeout(() => window.open('/portal/employee-dashboard', '_self'), 600);
      } else {
        toast('用户名或密码错误', 'error');
      }
    } catch (err) {
      toast('登录失败：' + err.message, 'error');
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
