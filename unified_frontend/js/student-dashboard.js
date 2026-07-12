/**
 * student-dashboard.js — 学生工作台逻辑
 * 依赖: auth.js, chat.js
 */

const STUDENT_API = 'http://localhost:8000';
let chat;
// Chart.js 实例引用
let trendChart = null;
let distChart = null;

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
    streamUrl: `${STUDENT_API}/chat/stream`,
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

// ── 销毁已有图表 ──
function destroyCharts() {
  if (trendChart) { trendChart.destroy(); trendChart = null; }
  if (distChart) { distChart.destroy(); distChart = null; }
}

// ── 渲染情绪趋势折线图 ──
function renderEmotionTrend(history) {
  const canvas = el('emotionTrendChart');
  const empty = el('trendEmpty');
  if (!canvas) return;

  if (!history || history.length < 2) {
    canvas.style.display = 'none';
    if (empty) empty.style.display = '';
    return;
  }
  canvas.style.display = '';
  if (empty) empty.style.display = 'none';

  const recent = history.slice(-14);
  const labels = recent.map(h => (h.date || '').slice(-5)); // MM-DD
  const scores = recent.map(h => h.score || 0);

  // 根据平均风险分确定渐变主色
  const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length;
  let mainColor;
  if (avgScore < 30) mainColor = '#10b981';
  else if (avgScore < 60) mainColor = '#f59e0b';
  else if (avgScore < 80) mainColor = '#f97316';
  else mainColor = '#dc2626';

  const ctx = canvas.getContext('2d');
  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: '风险分数',
        data: scores,
        borderColor: mainColor,
        backgroundColor: mainColor + '20',
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: mainColor,
        pointBorderColor: '#fff',
        pointBorderWidth: 1,
        pointHoverRadius: 5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `风险分: ${ctx.parsed.y}/100`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { size: 10 }, color: '#94a3b8', maxRotation: 0 }
        },
        y: {
          min: 0,
          max: 100,
          grid: { color: '#f1f5f9' },
          ticks: { font: { size: 10 }, color: '#94a3b8', stepSize: 25, callback: v => v }
        }
      },
      interaction: { intersect: false, mode: 'index' }
    }
  });
}

// ── 渲染情绪分布环形图 ──
function renderEmotionDist(history) {
  const canvas = el('emotionDistChart');
  const empty = el('distEmpty');
  if (!canvas) return;

  if (!history || history.length === 0) {
    canvas.style.display = 'none';
    if (empty) empty.style.display = '';
    return;
  }
  canvas.style.display = '';
  if (empty) empty.style.display = 'none';

  // 统计各情绪出现次数
  const countMap = {};
  history.forEach(h => {
    const e = h.emotion || '未知';
    countMap[e] = (countMap[e] || 0) + 1;
  });

  const DIST_COLORS = {
    '正常': '#10b981', '积极': '#06b6d4', '焦虑': '#f59e0b',
    '低落': '#64748b', '孤独': '#8b5cf6', '适应困难': '#f97316',
    '高危': '#dc2626', '未知': '#cbd5e1'
  };
  const labels = Object.keys(countMap);
  const data = Object.values(countMap);
  const colors = labels.map(l => DIST_COLORS[l] || '#94a3b8');

  const ctx = canvas.getContext('2d');
  distChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: colors,
        borderColor: '#fff',
        borderWidth: 2,
        hoverBorderWidth: 3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      cutout: '60%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            font: { size: 10 },
            padding: 12,
            usePointStyle: true,
            pointStyleWidth: 8,
          }
        },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed}次`
          }
        }
      }
    }
  });
}

// ── 更新个性化建议 ──
function updateSuggestion(riskLevel) {
  const box = el('suggestionBox');
  const text = el('suggestionText');
  if (!box || !text) return;

  const config = {
    low:     { cls: 'suggestion-low',     text: '🎉 当前状态良好，保持积极心态！' },
    medium:  { cls: 'suggestion-medium',  text: '💪 最近有些压力，注意自我调节～需要的话可以随时和我聊聊 💙' },
    high:    { cls: 'suggestion-high',    text: '⚠️ 情绪波动较大，建议多关注自己的感受，也可以找信任的老师或朋友倾诉' },
    critical:{ cls: 'suggestion-critical',text: '🚨 如果你感到非常难受，请不要一个人扛着。寻求专业心理支持是勇敢的表现，你不是一个人 💙' },
  };
  const c = config[riskLevel] || config['low'];
  box.className = 'suggestion-box ' + c.cls;
  text.textContent = c.text;
}

// ── 刷新我的状态 ──
async function refreshProfile() {
  const id = Auth.userId();
  try {
    const r = await fetch(`${STUDENT_API}/my/profile/${id}`);
    const data = await r.json();
    const mental = data.mental || {};
    const emotion = mental.emotion || '正常';
    const riskLevel = mental.risk_level || 'low';
    const score = mental.risk_score || 0;
    const history = mental.emotion_history || [];

    const riskPct = Math.min(100, Math.max(0, score));
    const card = el('emotionCard');
    card.className = 'card risk-' + riskLevel;

    // 情绪概览
    el('emotionEmoji').textContent = EMOJI_MAP[emotion] || '😊';
    el('emotionStatus').textContent = emotion;
    el('emotionStatus').style.color = { low:'#10b981', medium:'#f59e0b', high:'#f97316', critical:'#dc2626' }[riskLevel] || '#10b981';
    el('emotionRisk').textContent = `风险评分 ${score}/100  ·  ${riskLevel === 'low' ? '状态良好' : riskLevel === 'medium' ? '需关注' : riskLevel === 'high' ? '⚠️ 高风险' : '🚨 危急'}`;
    el('riskFill').style.width = riskPct + '%';

    // 预警提醒
    const alertBox = el('alertReminder');
    if (alertBox) {
      alertBox.style.display = (mental.recent_alert && mental.recent_alert.follow_up_status === 'pending') ? '' : 'none';
    }

    // 趋势图
    destroyCharts();
    renderEmotionTrend(history);
    // 分布图
    renderEmotionDist(history);

    // 关键指标
    const negKw = mental.negative_keywords_count || 0;
    const consDays = mental.consecutive_negative_days || 0;
    const lastAssess = mental.last_assessment_at;

    const negEl = el('metricNegKeywords');
    const consEl = el('metricConsDays');
    const assessEl = el('metricLastAssess');
    if (negEl) {
      negEl.textContent = negKw;
      negEl.parentElement.className = 'metric-item' + (negKw > 10 ? ' danger' : negKw > 5 ? ' warn' : '');
    }
    if (consEl) {
      consEl.textContent = consDays;
      consEl.parentElement.className = 'metric-item' + (consDays > 3 ? ' danger' : consDays > 1 ? ' warn' : '');
    }
    if (assessEl) {
      assessEl.textContent = lastAssess ? timeAgo(lastAssess) : '--';
    }

    // 个性化建议
    updateSuggestion(riskLevel);

    // 升学意向
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
