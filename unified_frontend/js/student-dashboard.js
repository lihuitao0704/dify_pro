/**
 * student-dashboard.js — 学生工作台逻辑
 * 依赖: auth.js, chat.js
 */

const STUDENT_API = 'http://localhost:8000';
let chat;

document.addEventListener('DOMContentLoaded', () => {
  // ── 权限检查 ──
  if (!Auth.requireRole('student')) return;

  // ── 显示用户信息 ──
  const name = Auth.userName();
  const id = Auth.userId();
  document.getElementById('sidebarName').textContent = name || '同学';
  document.getElementById('sidebarAvatar').textContent = (name || '同')[0];

  // ── 初始化聊天 ──
  chat = new ChatWidget({
    apiUrl: `${STUDENT_API}/chat`,
    container: '#chatMessages',
    input: '#chatInput',
    sendBtn: '#sendBtn',
    onPreSend: (msg) => ({
      student_id: parseInt(id),
      message: msg,
      session_id: chat.sessionId || '',
    }),
    onReply: (data) => {
      // 每次回复后刷新右侧面板
      refreshProfile();
      refreshReminders();
    },
    welcome: '嗨同学你好呀 👋 我是小留同学，你的留学全程AI助手！\n\n你可以问我：\n📅 查学业日程  📝 请假  📊 申请进度\n🏠 海外生活指南  💙 心理关怀  🎯 升学咨询',
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
      if (action === 'leave') openModal('leaveModal');
      if (action === 'feedback') openModal('feedbackModal');
    });
  });

  // ── 初始加载 ──
  refreshProfile();
  refreshReminders();
});

// ── 面板切换 ──
function switchPanel(panel) {
  const titles = {
    chat: '💬 AI 助手', profile: '😊 我的状态',
    schedule: '📅 学业日程', tickets: '📋 反馈工单', progress: '📊 申请进度',
  };
  document.getElementById('topTitle').textContent = titles[panel] || '💬 AI 助手';
  // 显示/隐藏右侧面板区块
  ['profileSection','scheduleSection','ticketSection','progressSection'].forEach(s => {
    document.getElementById(s).style.display = 'none';
  });
  const sectionMap = {
    profile: 'profileSection', schedule: 'scheduleSection',
    tickets: 'ticketSection', progress: 'progressSection',
  };
  if (sectionMap[panel]) {
    document.getElementById(sectionMap[panel]).style.display = '';
  }
  if (panel === 'schedule') refreshSchedule();
  if (panel === 'tickets') refreshTickets();
  if (panel === 'progress') refreshProgress();
}

// ── 刷新我的状态 ──
async function refreshProfile() {
  const id = Auth.userId();
  try {
    const r = await fetch(`${STUDENT_API}/my/profile/${id}`);
    const data = await r.json();
    const emotion = data.mental?.emotion || '正常';
    const risk = data.mental?.risk_level || 'low';
    const score = data.mental?.risk_score || 0;
    document.getElementById('emotionStatus').textContent = emotion;
    const riskColor = { low: '#10b981', medium: '#f59e0b', high: '#ef4444', critical: '#dc2626' };
    document.getElementById('emotionStatus').style.color = riskColor[risk] || '#10b981';
    document.getElementById('emotionRisk').textContent = `风险等级: ${risk} | 评分: ${score}`;
    if (data.upgrades && data.upgrades.length > 0) {
      const u = data.upgrades[0];
      document.getElementById('upgradeStatus').textContent =
        `${u.interest_country || ''} ${u.interest_degree || ''} (${u.conversion_status || ''})`;
    }
  } catch (e) { /* ignore */ }
}

// ── 刷新日程 ──
async function refreshSchedule() {
  const id = Auth.userId();
  try {
    const r = await fetch(`${STUDENT_API}/my/schedule/${id}`);
    const data = await r.json();
    const deadlines = data.deadlines || [];
    const list = document.getElementById('scheduleList');
    if (deadlines.length === 0) {
      list.innerHTML = '<div class="list-item"><span class="label">暂无日程</span></div>';
      return;
    }
    list.innerHTML = deadlines.slice(0, 8).map(d => `
      <div class="list-item">
        <span>${d.title || d.event_type}</span>
        <span class="value" style="font-size:12px;color:${d.days_left < 3 ? '#ef4444' : '#64748b'}">
          ${d.days_left != null ? d.days_left + '天' : ''}
        </span>
      </div>
    `).join('');
    const badge = document.getElementById('scheduleBadge');
    badge.textContent = deadlines.length;
    badge.style.display = deadlines.length > 0 ? '' : 'none';
  } catch (e) { /* ignore */ }
}

// ── 刷新工单 ──
async function refreshTickets() {
  const id = Auth.userId();
  try {
    const r = await fetch(`${STUDENT_API}/my/tickets/${id}`);
    const data = await r.json();
    const tickets = data.tickets || [];
    document.getElementById('ticketList').innerHTML = tickets.length === 0
      ? '<div class="list-item"><span class="label">暂无工单</span></div>'
      : tickets.map(t => `
        <div class="list-item">
          <span>[${t.category}] ${t.title}</span>
          <span class="status-dot ${t.status === 'resolved' ? 'ok' : t.status === 'processing' ? 'warn' : 'pending'}"></span>
        </div>
      `).join('');
  } catch (e) { /* ignore */ }
}

// ── 刷新申请进度 ──
async function refreshProgress() {
  const id = Auth.userId();
  try {
    const r = await fetch(`${STUDENT_API}/my/schedule/${id}`);
    const data = await r.json();
    const apps = data.applications || [];
    document.getElementById('progressList').innerHTML = apps.length === 0
      ? '<div class="list-item"><span class="label">暂无申请记录</span></div>'
      : apps.map(a => `
        <div class="list-item">
          <span>${a.program_name} @ ${a.university}</span>
          <span class="value" style="font-size:12px">${a.current_step}</span>
        </div>
      `).join('');
  } catch (e) { /* ignore */ }
}

// ── 刷新未读提醒 ──
async function refreshReminders() {
  const id = Auth.userId();
  try {
    const r = await fetch(`${STUDENT_API}/reminders/${id}`);
    const data = await r.json();
    const reminders = data.reminders || [];
    document.getElementById('reminderCount').textContent = reminders.length;
    document.getElementById('reminderCount').style.display = reminders.length > 0 ? '' : 'none';
    document.getElementById('reminderList').innerHTML = reminders.length === 0
      ? '<div class="list-item"><span class="label">暂无提醒</span></div>'
      : reminders.slice(0, 5).map(r => `
        <div class="list-item">
          <span>${r.message || r.remind_type}</span>
          <button class="quick-action" onclick="markRead(${r.id})">已读</button>
        </div>
      `).join('');
  } catch (e) { /* ignore */ }
}

async function markRead(reminderId) {
  try {
    await fetch(`${STUDENT_API}/reminders/${reminderId}/read`, { method: 'POST' });
    refreshReminders();
  } catch (e) { /* ignore */ }
}

// ── 请假提交 ──
async function submitLeave() {
  const id = Auth.userId();
  const btn = document.getElementById('leaveSubmitBtn');
  btn.disabled = true;
  btn.textContent = '提交中...';
  try {
    const r = await fetch(`${STUDENT_API}/leave/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_id: parseInt(id),
        leave_type: document.getElementById('leaveType').value,
        start_time: document.getElementById('leaveStart').value,
        end_time: document.getElementById('leaveEnd').value,
        reason: document.getElementById('leaveReason').value,
      }),
    });
    const data = await r.json();
    if (data.success) {
      toast('请假申请已提交 ✅', 'success');
      closeModal('leaveModal');
    } else {
      toast(data.message || '提交失败', 'error');
    }
  } catch (e) {
    toast('提交失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '提交申请';
  }
}

// ── 反馈提交 ──
async function submitFeedback() {
  const id = Auth.userId();
  const btn = document.getElementById('feedbackSubmitBtn');
  btn.disabled = true;
  btn.textContent = '提交中...';
  try {
    const r = await fetch(`${STUDENT_API}/feedback/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_id: parseInt(id),
        category: document.getElementById('feedbackCategory').value,
        title: document.getElementById('feedbackTitle').value,
        content: document.getElementById('feedbackContent').value,
        urgency: document.getElementById('feedbackUrgency').value.startsWith('urgent') ? 'urgent' : 'normal',
      }),
    });
    const data = await r.json();
    if (data.success) {
      toast('反馈已提交 ✅', 'success');
      closeModal('feedbackModal');
    } else {
      toast(data.message || '提交失败', 'error');
    }
  } catch (e) {
    toast('提交失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '提交';
  }
}

// ── 快捷发送 ──
function quickSend(msg) {
  const input = document.getElementById('chatInput');
  if (input) {
    input.value = msg;
    chat.send();
  }
}

// ── Modal 辅助 ──
function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }
// Click outside to close
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) e.target.classList.remove('active');
});
