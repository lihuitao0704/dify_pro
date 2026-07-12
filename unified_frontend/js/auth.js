/**
 * auth.js — 统一鉴权模块
 * 管理 JWT token、登录状态、角色判断
 */

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

  // ── 学生登录（统一账户密码，查 account 表） ──
  async studentLogin(username, password) {
    const urls = [
      `/auth/login`,
    ];
    for (const url of urls) {
      try {
        const r = await fetch(url, {
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
        continue;
      }
    }
    return { success: false, message: '无法连接学生服务' };
  },

  // ── 员工登录 ──
  async employeeLogin(username, password) {
    const urls = [
      `/auth/login`,
    ];
    for (const url of urls) {
      try {
        const r = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        });
        const data = await r.json();
        if (data.success || data.code === 0) {
          this.set({
            role: 'employee',
            user_id: data.user_id || data.data?.user_id || 0,
            user_name: username,
            token: data.token || '',
            user_type: data.user_type || data.data?.user_type || '员工',
            exp: data.exp || (Date.now()/1000 + 86400),
          });
          return { success: true };
        }
        // Fallback: demo login
        if (username === 'admin' && password === 'admin123') {
          this.set({
            role: 'employee',
            user_id: 1,
            user_name: 'admin',
            token: 'demo-token',
            user_type: '管理者',
            exp: Date.now()/1000 + 86400,
          });
          return { success: true };
        }
        return { success: false, message: data.msg || data.message || '用户名或密码错误' };
      } catch (e) {
        // fallback
        if (username === 'admin' && password === 'admin123') {
          this.set({
            role: 'employee',
            user_id: 1,
            user_name: 'admin',
            token: 'demo-token',
            user_type: '管理者',
            exp: Date.now()/1000 + 86400,
          });
          return { success: true };
        }
        continue;
      }
    }
    return { success: false, message: '无法连接企业服务' };
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
  setTimeout(() => { el.remove(); }, duration);
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
