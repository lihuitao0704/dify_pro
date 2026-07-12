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

  // ── 快速提问 ──
  document.querySelectorAll('.sidebar-nav a[data-quick]').forEach(a => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const msg = a.dataset.quick;
      if (msg) quickSend(msg);
    });
  });

  // ── 初始加载 ──
  refreshProfile();
  refreshReminders();
});

// ── 工具函数 ──
function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return mins + '分钟前';
  const hours = Math.floor(mins / 60);
  if (hours < 24) return hours + '小时前';
  const days = Math.floor(hours / 24);
  if (days < 30) return days + '天前';
  const months = Math.floor(days / 30);
  return months + '个月前';
}

const EMOJI_MAP = { '正常':'😊','焦虑':'😰','低落':'😢','孤独':'💔','适应困难':'🌧️','积极':'😄' };
const FLAG_MAP = { '新加坡':'🇸🇬','法国':'🇫🇷','英国':'🇬🇧','美国':'🇺🇸','德国':'🇩🇪','日本':'🇯🇵','澳洲':'🇦🇺','加拿大':'🇨🇦','香港':'🇭🇰','荷兰':'🇳🇱' };
const EVENT_ICON = { '论文DDL':'📝','考试':'📚','答辩':'🎤','选课截止':'✏️' };
const APP_STEPS = ['选校定校','材料准备','文书撰写','文书审核','递交申请','等待Offer','签证办理'];

function el(id) { return document.getElementById(id); }

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
    const riskLevel = data.mental?.risk_level || 'low';
    const score = data.mental?.risk_score || 0;

    const riskPct = Math.min(100, Math.max(0, score));
    const card = el('emotionCard');
    card.className = 'card risk-' + riskLevel;

    el('emotionEmoji').textContent = EMOJI_MAP[emotion] || '😊';
    el('emotionStatus').textContent = emotion;
    el('emotionStatus').style.color = { low:'#10b981', medium:'#f59e0b', high:'#f97316', critical:'#dc2626' }[riskLevel] || '#10b981';
    el('emotionRisk').textContent = `风险评分 ${score}/100  ·  ${riskLevel === 'low' ? '状态良好' : riskLevel === 'medium' ? '需关注' : riskLevel === 'high' ? '⚠️ 高风险' : '🚨 危急'}`;
    el('riskFill').style.width = riskPct + '%';

    const upEl = el('upgradeStatus');
    if (data.upgrades && data.upgrades.length > 0) {
      const u = data.upgrades[0];
      const flag = FLAG_MAP[u.interest_country] || '🌍';
      const st = u.conversion_status || '';
      const stBadge = { 'converted':'✅ 已转化','contacted':'📞 已联系','interested':'⭐ 感兴趣','identified':'🔍 已识别','lost':'❌ 已流失' }[st] || st;
      upEl.innerHTML = `<div style="font-size:18px;font-weight:700;margin-bottom:2px">${flag} ${u.interest_country || ''} ${u.interest_degree || ''}</div>
        <div style="font-size:12px;color:#64748b">${stBadge}</div>`;
    } else {
      upEl.innerHTML = '<span style="color:#94a3b8">暂无升学意向记录</span>';
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
    const list = el('scheduleList');
    if (deadlines.length === 0) {
      list.innerHTML = '<div class="empty-state"><div style="font-size:36px;margin-bottom:8px;opacity:.4">📅</div>暂无日程安排</div>';
      el('scheduleBadge').style.display = 'none';
      return;
    }
    list.innerHTML = deadlines.slice(0, 8).map(d => {
      const days = d.days_left;
      const cls = days == null ? 'safe' : days < 0 ? 'overdue' : days < 3 ? 'urgent' : days < 7 ? 'warning' : 'safe';
      const txt = days == null ? '--' : days < 0 ? '已过期' : days === 0 ? '今天' : days + '天';
      const icon = EVENT_ICON[d.event_type] || '📌';
      const date = d.deadline ? d.deadline.slice(0, 16).replace('T', ' ') : '';
      return `<div class="ddl-card">
        <div class="ddl-icon">${icon}</div>
        <div class="ddl-info">
          <div class="ddl-title">${d.title || d.event_type}</div>
          ${d.course_name ? `<div class="ddl-course">${d.course_name}</div>` : ''}
          ${date ? `<div class="ddl-date">${date}</div>` : ''}
        </div>
        <span class="badge-ddl ${cls}">${txt}</span>
      </div>`;
    }).join('');
    const badge = el('scheduleBadge');
    badge.textContent = deadlines.length;
    badge.style.display = '';
  } catch (e) { /* ignore */ }
}

// ── 刷新工单 ──
async function refreshTickets() {
  const id = Auth.userId();
  try {
    const r = await fetch(`${STUDENT_API}/my/tickets/${id}`);
    const data = await r.json();
    const tickets = data.tickets || [];
    const list = el('ticketList');
    if (tickets.length === 0) {
      list.innerHTML = '<div class="empty-state"><div style="font-size:36px;margin-bottom:8px;opacity:.4">📋</div>暂无工单</div>';
      return;
    }
    const typeCls = { '生活服务':'life','服务质量':'teach','签证办理':'visa','院校申请':'apply','教务':'teach','财务':'visa','后勤':'life' };
    list.innerHTML = tickets.map(t => {
      const cls = typeCls[t.complaint_type] || 'other';
      const statusCls = t.handle_status === '已完结' ? 'ok' : t.handle_status === '处理中' ? 'warn' : 'pending';
      const statusText = t.handle_status || '待处理';
      const detail = (t.complaint_detail || '').length > 50 ? (t.complaint_detail || '').slice(0, 50) + '...' : (t.complaint_detail || '');
      return `<div class="ticket-card">
        <div class="ticket-meta">
          <span class="badge-tag ${cls}">${t.complaint_type || '其他'}</span>
          <span class="status-dot ${statusCls}"></span>
          <span>${statusText}</span>
          <span style="margin-left:auto">${timeAgo(t.create_time)}</span>
        </div>
        <div class="ticket-body">${detail || '--'}</div>
      </div>`;
    }).join('');
  } catch (e) { /* ignore */ }
}

// ── 刷新申请进度 ──
async function refreshProgress() {
  const id = Auth.userId();
  try {
    const r = await fetch(`${STUDENT_API}/my/schedule/${id}`);
    const data = await r.json();
    const apps = data.applications || [];
    const list = el('progressList');
    if (apps.length === 0) {
      list.innerHTML = `<div class="empty-state"><div style="font-size:36px;margin-bottom:8px;opacity:.4">📊</div>暂无申请记录</div>
        <div style="text-align:center;font-size:12px;color:#94a3b8;margin-top:4px">跟小留说"查申请进度"开始追踪</div>`;
      return;
    }
    list.innerHTML = apps.map(a => {
      const curStep = a.current_step || '';
      const curIdx = APP_STEPS.findIndex(s => curStep.includes(s) || s.includes(curStep));
      const effectiveIdx = curIdx >= 0 ? curIdx : 0;
      const stepsHtml = APP_STEPS.map((step, i) => {
        let dotCls = 'pending', dotIcon = '';
        if (i < effectiveIdx) { dotCls = 'done'; dotIcon = '✓'; }
        else if (i === effectiveIdx) { dotCls = 'current'; dotIcon = '●'; }
        return `<div class="timeline-step">
          <div class="timeline-dot ${dotCls}">${dotIcon}</div>
          <div class="timeline-label">
            <span class="step-name" style="color:${i === effectiveIdx ? 'var(--primary)' : i < effectiveIdx ? '#10b981' : '#94a3b8'}">${step}</span>
            ${i === effectiveIdx ? '<span class="step-status">← 当前</span>' : ''}
          </div>
        </div>`;
      }).join('');
      const statusColor = { 'in_progress':'#3b82f6','completed':'#10b981','withdrawn':'#94a3b8' };
      return `<div class="card" style="margin-bottom:12px">
        <div style="font-size:13px;font-weight:700;margin-bottom:2px">${a.program_name}</div>
        <div style="font-size:11px;color:#64748b;margin-bottom:10px">
          🏫 ${a.university || ''}
          <span style="display:inline-block;margin-left:6px;padding:1px 6px;border-radius:4px;font-size:10px;background:${(statusColor[a.application_status] || '#94a3b8')}15;color:${statusColor[a.application_status] || '#94a3b8'}">${a.application_status || ''}</span>
        </div>
        <div class="timeline">${stepsHtml}</div>
      </div>`;
    }).join('');
  } catch (e) { /* ignore */ }
}

// ── 刷新未读提醒 ──
async function refreshReminders() {
  const id = Auth.userId();
  try {
    const r = await fetch(`${STUDENT_API}/reminders/${id}`);
    const data = await r.json();
    const reminders = data.reminders || [];
    el('reminderCount').textContent = reminders.length;
    el('reminderCount').style.display = reminders.length > 0 ? '' : 'none';
    el('reminderList').innerHTML = reminders.length === 0
      ? '<div class="list-item" style="justify-content:center;color:#94a3b8">暂无提醒</div>'
      : reminders.slice(0, 5).map(r => `
        <div class="list-item">
          <span style="font-size:12px;line-height:1.4;flex:1;margin-right:8px">
            <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--danger);margin-right:6px;vertical-align:middle"></span>
            ${r.message || r.remind_type || ''}
          </span>
          <button class="quick-action" onclick="markRead(${r.id})" style="flex-shrink:0">已读</button>
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
