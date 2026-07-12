/**
 * auth.js — 统一鉴权模块
 * 管理 JWT token、登录状态、角色判断
 * 学生 → 学生端(8000)  |  员工 → 企业端(8001)
 */

// 学生登录 → 走当前服务器自身（8000 或 9000 都有 /auth/login + 角色校验）
// 员工登录 → 始终走企业端 8001（有 JWT + bcrypt + 角色校验）
const STUDENT_AUTH_URL = '/auth/login';
const EMPLOYEE_AUTH_URL = 'http://localhost:8001/auth/login';

const Auth = {
  STORAGE_KEY: 'dify_auth',

  /** 获取存储的认证信息 */
  get() {
    try {
      const raw = localStorage.getItem(this.STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  },

  /** 保存认证信息 */
  set(data) {
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(data));
  },

  /** 清除认证信息 */
  clear() {
    localStorage.removeItem(this.STORAGE_KEY);
  },

  /** 是否已登录 */
  isLoggedIn() {
    const auth = this.get();
    if (!auth) return false;
    // 检查 token 是否过期
    if (auth.exp && Date.now() > auth.exp * 1000) {
      this.clear();
      return false;
    }
    return true;
  },

  /** 当前角色 */
  role() {
    const auth = this.get();
    return auth ? auth.role : null;
  },

  /** 当前用户ID */
  userId() {
    const auth = this.get();
    return auth ? auth.user_id : null;
  },

  /** 当前用户名 */
  userName() {
    const auth = this.get();
    return auth ? auth.user_name : '';
  },

  /** 获取 Bearer Token */
  token() {
    const auth = this.get();
    return auth ? auth.token : null;
  },

  /** 获取请求头 */
  headers() {
    const t = this.token();
    const h = { 'Content-Type': 'application/json' };
    if (t) h['Authorization'] = `Bearer ${t}`;
    return h;
  },

  // ── 学生登录（仅学生端 8000，仅允许 user_type=学员）──
  async studentLogin(username, password) {
    try {
      const r = await fetch(STUDENT_AUTH_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await r.json();
      if (data.success) {
        const s = data.student;
        this.set({
          role: 'student',
          user_id: s.id,
          user_name: s.name,
          token: data.token || '',
          student: s,
          user_type: s.user_type || '',
          exp: data.exp || (Date.now()/1000 + 86400),
        });
        return { success: true };
      }
      return { success: false, message: data.message || '用户名或密码不正确' };
    } catch (e) {
      return { success: false, message: '无法连接学生服务，请确认服务已启动' };
    }
  },

  // ── 员工登录（仅企业端 8001，拒绝 user_type=学员）──
  async employeeLogin(username, password) {
    try {
      const r = await fetch(EMPLOYEE_AUTH_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await r.json();
      if (data.success) {
        this.set({
          role: 'employee',
          user_id: data.user_id || 0,
          user_name: data.real_name || username,
          token: data.token || '',
          user_type: data.user_type || '员工',
          exp: data.expire_hours
            ? (Date.now() / 1000 + data.expire_hours * 3600)
            : (Date.now() / 1000 + 86400),
        });
        return { success: true };
      }
      return { success: false, message: data.message || '用户名或密码错误' };
    } catch (e) {
      return { success: false, message: '无法连接企业服务，请确认服务已启动' };
    }
  },

  /** 退出登录 */
  logout() {
    this.clear();
    window.location.href = '/portal';
  },

  /** 检查并重定向（未登录跳回首页） */
  requireRole(expectedRole) {
    if (!this.isLoggedIn() || this.role() !== expectedRole) {
      window.location.href = '/portal';
      return false;
    }
    return true;
  },
};

// ── 全局 Toast ──
function toast(msg, type = 'info', duration = 3000) {
  const container = document.getElementById('toastContainer') || (() => {
    const c = document.createElement('div');
    c.id = 'toastContainer';
    document.body.appendChild(c);
    return c;
  })();
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 250);
  }, duration);
}

// ── 转义 HTML ──
function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── API 调用封装 ──
async function api(url, opts = {}) {
  const headers = { ...Auth.headers(), ...(opts.headers || {}) };
  const r = await fetch(url, { ...opts, headers });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
