/**
 * chat.js — 通用聊天组件
 * 可在任意页面嵌入，绑定到指定的消息容器和输入框
 *
 * 用法:
 *   const chat = new ChatWidget({
 *     apiUrl: 'http://localhost:8000/chat',
 *     container: '#chatMessages',
 *     input: '#chatInput',
 *     sendBtn: '#sendBtn',
 *     onPreSend: (msg) => ({ student_id: Auth.userId(), message: msg }),
 *   });
 */

class ChatWidget {
  constructor(opts) {
    this.apiUrl = opts.apiUrl;
    this.container = document.querySelector(opts.container);
    this.input = document.querySelector(opts.input);
    this.sendBtn = document.querySelector(opts.sendBtn);
    this.onPreSend = opts.onPreSend || ((msg) => ({ message: msg }));
    this.onReply = opts.onReply || (() => {});
    this.sessionId = null;
    this.isProcessing = false;

    this._bindEvents();
    if (opts.welcome) this._addWelcome(opts.welcome);
  }

  _bindEvents() {
    this.sendBtn?.addEventListener('click', () => this.send());
    this.input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    });
  }

  _addWelcome(msg) {
    this._addMsg(msg, 'bot');
  }

  async send() {
    const text = this.input.value.trim();
    if (!text || this.isProcessing) return;

    this.input.value = '';
    this.isProcessing = true;
    if (this.sendBtn) this.sendBtn.disabled = true;

    this._addMsg(text, 'user');

    const typingEl = this._addTyping();

    try {
      const payload = this.onPreSend(text);
      const r = await fetch(this.apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await r.json();

      typingEl.remove();

      const reply = data.reply || data.answer || data.msg || '(未收到回复)';
      this.sessionId = data.session_id || this.sessionId;
      this._addMsg(reply, 'bot', data.intents || []);

      this.onReply(data);
    } catch (err) {
      typingEl.remove();
      this._addMsg('连接失败，请稍后重试～\n(' + err.message.slice(0, 80) + ')', 'bot');
    } finally {
      this.isProcessing = false;
      if (this.sendBtn) this.sendBtn.disabled = false;
      this.input?.focus();
    }
  }

  _addMsg(text, who, intents = []) {
    const div = document.createElement('div');
    div.className = `msg ${who}`;

    const avatarIcon = who === 'user' ? '👤' : '🤖';
    const avatarHtml = `<div class="avatar">${avatarIcon}</div>`;

    let bubbleContent = escapeHTML(text).replace(/\n/g, '<br/>');
    let intentHtml = '';
    if (intents.length > 0) {
      const names = intents.map(i => i.intent || i).join(', ');
      intentHtml = `<div class="meta">意图: ${names}</div>`;
    }

    if (who === 'user') {
      div.innerHTML = `<div class="bubble">${bubbleContent}</div>${avatarHtml}`;
    } else {
      div.innerHTML = `${avatarHtml}<div class="bubble">${bubbleContent}${intentHtml}</div>`;
    }

    this.container.appendChild(div);
    this._scrollBottom();
  }

  _addTyping() {
    const div = document.createElement('div');
    div.className = 'msg bot typing';
    div.innerHTML = '<div class="avatar">🤖</div><div class="bubble"><span></span><span></span><span></span></div>';
    this.container.appendChild(div);
    this._scrollBottom();
    return div;
  }

  _scrollBottom() {
    this.container.scrollTop = this.container.scrollHeight;
  }

  /** 外部可直接调用添加消息 */
  addMessage(text, who = 'bot') {
    this._addMsg(text, who);
  }
}
