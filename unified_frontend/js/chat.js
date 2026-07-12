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
    this.streamUrl = opts.streamUrl || null;
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
    const payload = this.onPreSend(text);

    // 优先流式
    if (this.streamUrl) {
      try {
        await this._streamSend(payload, typingEl);
      } catch (err) {
        typingEl.remove();
        this._addMsg('连接失败，请稍后重试～', 'bot');
      } finally {
        this.isProcessing = false;
        if (this.sendBtn) this.sendBtn.disabled = false;
        this.input?.focus();
      }
      return;
    }

    // 非流式 fallback
    try {
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

  async _streamSend(payload, typingEl) {
    const r = await fetch(this.streamUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let replyText = '';
    let bubbleEl = null;
    let meta = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line in buffer

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.slice(6));

        if (data.type === 'meta') {
          meta = data;
          this.sessionId = data.session_id || this.sessionId;
          continue;
        }
        if (data.type === 'token') {
          if (!bubbleEl) {
            typingEl.remove();
            bubbleEl = this._createStreamBubble();
          }
          replyText += data.text;
          bubbleEl.innerHTML = this._renderMarkdown(replyText);
          this._scrollBottom();
          continue;
        }
        if (data.type === 'done') {
          if (!bubbleEl && meta) {
            // 空回复兜底
            typingEl.remove();
            bubbleEl = this._createStreamBubble();
            bubbleEl.innerHTML = '(收到空回复)';
          }
          if (bubbleEl) {
            if (meta && meta.intents && meta.intents.length > 0) {
              const names = meta.intents.map(i => i.intent || i).join(', ');
              bubbleEl.innerHTML += `<div class="meta">意图: ${names}</div>`;
            }
          }
        }
      }
    }
    // 处理剩余 buffer
    if (buffer.startsWith('data: ')) {
      try {
        const data = JSON.parse(buffer.slice(6));
        if (data.type === 'done' && !bubbleEl) {
          typingEl.remove();
          this._addMsg('(收到空回复)', 'bot', meta?.intents || []);
        }
      } catch(e) {}
    }

    if (meta) {
      this.onReply({
        reply: replyText,
        intents: meta.intents || [],
        emotion: meta.emotion || {},
        session_id: meta.session_id || '',
      });
    }
  }

  _createStreamBubble() {
    const div = document.createElement('div');
    div.className = 'msg bot';
    div.innerHTML = '<div class="avatar">🤖</div><div class="bubble stream-bubble"></div>';
    this.container.appendChild(div);
    return div.querySelector('.stream-bubble');
  }

  _renderMarkdown(text) {
    let html = escapeHTML(text);
    // 简单 markdown 渲染
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/^- (.+)$/gm, '· $1');
    html = html.replace(/^(#{1,3})\s+(.+)$/gm, (_, h, t) => {
      const sz = [20, 17, 15][h.length - 1] || 14;
      return `<div style="font-size:${sz}px;font-weight:700;margin:8px 0 4px">${t}</div>`;
    });
    html = html.replace(/\n/g, '<br/>');
    return html;
  }

  _scrollBottom() {
    this.container.scrollTop = this.container.scrollHeight;
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

  /** 外部可直接调用添加消息 */
  addMessage(text, who = 'bot') {
    this._addMsg(text, who);
  }
}
