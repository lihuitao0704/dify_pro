/**
 * utils.js — Toast + 通用工具
 */

function toast(msg, type = 'success', duration = 2500) {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    document.body.appendChild(container);
  }
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  // 触发 transition
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 250);
  }, duration);
}

function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  // 附带 Bearer Token
  const token = localStorage.getItem('customer_token');
  if (token) {
    headers['Authorization'] = 'Bearer ' + token;
  }
  return fetch(path, { ...opts, headers }).then(async r => {
    if (r.status === 401) {
      // token 过期 → 踢回登录页
      localStorage.removeItem('customer_token');
      localStorage.removeItem('customer_user');
      location.replace('login.html');
      throw new Error('登录已过期，请重新登录');
    }
    if (!r.ok) {
      const txt = await r.text().catch(() => '');
      throw new Error(`HTTP ${r.status}: ${txt.slice(0, 200)}`);
    }
    return r.json();
  });
}

function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (isNaN(d)) return ts;
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) {
    return d.toTimeString().slice(0, 5);
  }
  return `${d.getMonth() + 1}/${d.getDate()} ${d.toTimeString().slice(0, 5)}`;
}
