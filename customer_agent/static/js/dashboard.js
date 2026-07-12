/**
 * dashboard.js — 客服工作台主逻辑
 */

// ============================================================
// 初始化
// ============================================================
const CURRENT_CONV = 'default';
let USER = { name: '管理员', role: '管理员', id: 1 };

document.addEventListener('DOMContentLoaded', async () => {
  // 用户信息
  try {
    const stored = JSON.parse(localStorage.getItem('customer_user') || '{}');
    USER = { ...USER, ...stored };
  } catch (e) {}
  document.getElementById('sidebarName').textContent = USER.name;
  document.getElementById('sidebarRole').textContent = USER.role;
  document.getElementById('sidebarAvatar').textContent = (USER.name || 'A').slice(0, 1).toUpperCase();

  bindNav();
  bindChat();
  bindControls();
  await healthCheck();
  await loadKBInfo();
  await loadProjectStatus();
});

// ============================================================
// Tab 切换
// ============================================================
function bindNav() {
  const tabs = { overview: '概览', chat: 'AI对话', knowledge: '知识库', sessions: '会话管理' };
  document.querySelectorAll('.nav-item[data-tab]').forEach(el => {
    el.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      el.classList.add('active');
      const key = el.getAttribute('data-tab');
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      document.getElementById('tab-' + key).classList.add('active');
      document.getElementById('topbarTitle').textContent = tabs[key] || key;
    });
  });

  document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('customer_token');
    localStorage.removeItem('customer_user');
    location.replace('login.html');
  });

  document.getElementById('reloadBtn').addEventListener('click', reloadKB);
}

// ============================================================
// 健康检查 + KB 状态
// ============================================================
async function healthCheck() {
  const setPill = (id, ok) => {
    const el = document.getElementById(id);
    el.className = 'pill ' + (ok ? 'pill-success' : 'pill-danger');
    el.textContent = ok ? '在线' : '离线';
  };
  // study_abroad
  try {
    await api('/health');
    setPill('saStatus', true);
  } catch (e) {
    setPill('saStatus', false);
  }
  // Event&Lecture (bridge/test) -> use /health on agent itself
  try {
    await fetch('/health', { method: 'GET' });
    setPill('apiStatus', true);
    document.getElementById('apiStatus').textContent = 'API: 在线';
    document.getElementById('apiStatus').className = 'pill pill-info';
  } catch (e) {
    setPill('apiStatus', false);
    document.getElementById('apiStatus').textContent = 'API: 离线';
    document.getElementById('apiStatus').className = 'pill pill-danger';
  }
  // LLM status — 用 /chat 一次轻量请求判断
  try {
    const r = await api('/chat', { method: 'POST', body: { message: 'ping' } });
    setPill('llmStatus', r.reply && r.reply !== '[OFFLINE]' && r.reply.length > 5);
  } catch (e) {
    setPill('llmStatus', false);
  }
}

// ============================================================
// 知识库
// ============================================================
async function loadKBInfo() {
  try {
    const data = await api('/admin/kb-status');
    document.getElementById('kbDocs').textContent = data.doc_count ?? '--';
    document.getElementById('kbChunks').textContent = data.chunks ?? '--';
    document.getElementById('kbFaq').textContent = data.faq_count ?? '--';
    document.getElementById('kbPath').textContent = data.knowledge_path ?? '--';
    document.getElementById('statDocs').textContent = data.doc_count ?? '--';
    document.getElementById('statChunks').textContent = data.chunks ?? '--';
    document.getElementById('statFaq').textContent = data.faq_count ?? '--';
  } catch (e) {
    document.getElementById('kbPath').textContent = '加载失败: ' + e.message;
  }
}

async function reloadKB() {
  toast('正在热身知识库...', 'warning', 1500);
  try {
    await api('/admin/kb-reload', { method: 'POST' });
    await loadKBInfo();
    toast('知识库热身成功！', 'success');
  } catch (e) {
    toast('热身失败：' + e.message, 'error');
  }
}

// ============================================================
// ACT2026 项目进度
// ============================================================
async function loadProjectStatus() {
  try {
    const d = await api('/admin/project-status');
    document.getElementById('overallPct').textContent = (d.overall_pct || 0) + '%';
    document.getElementById('phaseName').textContent = d.phase_name || d.phase || '';
    document.getElementById('progressPhase').textContent = d.phase || '';
    const bar = document.getElementById('overallBar');
    bar.style.width = (d.overall_pct || 0) + '%';

    // 里程碑列表
    const box = document.getElementById('milestonesList');
    box.innerHTML = '';
    (d.milestones || []).forEach(m => {
      const cls = m.status === 'done' ? 'done' : (m.status === 'doing' ? 'doing' : 'todo');
      const wrap = document.createElement('div');
      wrap.className = 'milestone';
      wrap.innerHTML = `
        <div class="milestone-head">
          <span class="milestone-name">${escapeHTML(m.name)}</span>
          <span class="milestone-pct">${m.pct}%</span>
        </div>
        <div class="milestone-bar"><div class="${cls}" style="width:${m.pct}%"></div></div>`;
      box.appendChild(wrap);
    });

    // 健康检查小药丸
    const hc = document.getElementById('healthChecks');
    hc.innerHTML = '';
    const h = d.health_checks || {};
    const mk = (label, ok) => {
      const s = document.createElement('span');
      s.className = 'pill ' + (ok ? 'pill-success' : ok === false ? 'pill-danger' : 'pill-info');
      s.textContent = label + ': ' + (ok ? '✓ 在线' : ok === false ? '✗ 离线' : '…');
      hc.appendChild(s);
    };
    mk('MySQL', h.mysql);
    mk('LLM', h.llm);
  } catch (e) {
    document.getElementById('phaseName').textContent = '加载失败: ' + e.message;
  }
}

async function testKBSearch() {
  const q = document.getElementById('kbSearchInput').value.trim();
  if (!q) return toast('请输入检索问题', 'warning');
  const box = document.getElementById('kbSearchResults');
  box.innerHTML = '<span style="color:var(--text-tertiary)">检索中...</span>';
  try {
    // 调用 chat 让 Agent 内部走 knowledge 搜索，看通过 reply 推断命中
    // 但更好的做法：开一个轻量 /kb/search 端点。这里暂时通过 chat 做体验
    const r = await api('/chat', { method: 'POST', body: { message: q } });
    box.innerHTML = `<p style="margin-bottom:8px"><strong>Agent 回复：</strong></p>
      <div class="msg bot" style="max-width:100%;align-self:auto">${escapeHTML(r.reply)}</div>
      <p style="margin-top:12px;font-size:12px;color:var(--text-tertiary)">
        命中意图：${(r.intents || []).map(i => i.intent).join(', ') || 'chat'}
      </p>`;
  } catch (e) {
    box.innerHTML = '<span style="color:var(--danger)">出错：' + escapeHTML(e.message) + '</span>';
  }
}

// ============================================================
// AI 对话
// ============================================================
let ACTIVE_SESSION = null;

function bindChat() {
  const input = document.getElementById('chatInput');
  const btn = document.getElementById('sendBtn');

  document.getElementById('newConv').addEventListener('click', () => {
    // 清空当前
    const list = document.getElementById('msgList');
    list.innerHTML = '<div class="msg bot">开始新对话啦～有什么想了解的直接问我哦 😊</div>';
    ACTIVE_SESSION = null;
    toast('已开启新对话', 'success');
  });
}

async function sendMsg() {
  const input = document.getElementById('chatInput');
  const btn = document.getElementById('sendBtn');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  btn.disabled = true;
  addMsg(text, 'user');
  addMsg('正在思考中...', 'system', 'typing-tmp');

  try {
    const r = await api('/chat', { method: 'POST', body: {
      message: text,
      session_id: ACTIVE_SESSION,
    }});
    ACTIVE_SESSION = r.session_id;
    removeTyping();
    addMsg(r.reply || '(Agent 无回复)', 'bot');

    // 意图标签展示
    const businessIntents = (r.intents || []).filter(i => i.intent !== 'chat');
    if (businessIntents.length) {
      const tag = `[${businessIntents.map(i => i.intent).join(', ')}]`;
      addMsg(tag, 'system');
    }
  } catch (e) {
    removeTyping();
    addMsg('网络出错：' + e.message, 'system');
  } finally {
    btn.disabled = false;
  }
}

function addMsg(text, who, id) {
  const list = document.getElementById('msgList');
  const div = document.createElement('div');
  div.className = 'msg ' + who;
  div.textContent = text;
  if (id) div.id = id;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById('typing-tmp');
  if (el) el.remove();
}

function quickSend(msg) {
  // 切换到对话 Tab
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelector('.nav-item[data-tab="chat"]').classList.add('active');
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-chat').classList.add('active');
  document.getElementById('topbarTitle').textContent = 'AI对话';

  document.getElementById('chatInput').value = msg;
  sendMsg();
}

// ============================================================
// 右上角知识库热身 / 退出
// ============================================================
function bindControls() {
  // 已绑定在 bindNav 中
}
