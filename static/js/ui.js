// @ts-check
// ═══════════════════════════════════════════
// Retro dialog
// ═══════════════════════════════════════════
let dlgTyping = false, dlgTimer = null;
let dlgText = '', dlgDisplayed = 0;

function showDialog(text, x, y) {
  // Position dialog near the face but not covering it
  const faceCenterX = canvas.width / 2;
  const faceCenterY = canvas.height / 2;
  const faceRadius = 29 * faceCS;
  const isNarrow = window.innerWidth < 600;
  const dlgW = isNarrow ? 260 : 340;

  // Try to place to the right of the face, or left if not enough space
  let dx = faceCenterX + faceRadius + 20;
  let dy = faceCenterY - 60;
  if (dx + dlgW > window.innerWidth - 20) {
    dx = Math.max(10, faceCenterX - faceRadius - dlgW);
  }
  // On very narrow screens, center below the face
  if (isNarrow && dx < 10) {
    dx = (window.innerWidth - dlgW) / 2;
    dy = faceCenterY + faceRadius + 30;
  }
  if (dy < 60) dy = faceCenterY + faceRadius + 20;
  if (dy + 120 > window.innerHeight - 20) dy = faceCenterY - 120;

  dialog.style.left = dx + 'px';
  dialog.style.top = dy + 'px';
  dialog.classList.add('visible');

  dlgText = text;
  dlgDisplayed = 0;
  dlgBody.innerHTML = '<span class="cursor-blink"></span>';
  dlgTyping = true;
  typeNextChar();
}

function typeNextChar() {
  if (!dlgTyping || dlgDisplayed >= dlgText.length) {
    dlgTyping = false;
    const cursors = dlgBody.querySelectorAll('.cursor-blink');
    cursors.forEach(c => c.remove());
    dlgBody.innerHTML = formatDialogText(dlgText) + '<span class="dlg-arrow">▼</span>';
    return;
  }
  dlgDisplayed++;
  const shown = dlgText.substring(0, dlgDisplayed);
  dlgBody.innerHTML = formatDialogText(shown) + '<span class="cursor-blink"></span>';
  const delay = 40 + Math.random() * 50;
  dlgTimer = setTimeout(typeNextChar, delay);
}

function skipTypewriter() {
  dlgTyping = false;
  clearTimeout(dlgTimer);
  dlgBody.innerHTML = formatDialogText(dlgText) + '<span class="dlg-arrow">▼</span>';
  dlgDisplayed = dlgText.length;
}

function formatDialogText(text) {
  // Escape HTML and add news link styling
  let escaped = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  // Highlight URLs as clickable news refs
  escaped = escaped.replace(/(https?:\/\/\S+)/g, '<span class="news-ref" data-url="$1">$1</span>');
  return escaped;
}

function hideDialog() {
  dlgTyping = false;
  clearTimeout(dlgTimer);
  dialog.classList.remove('visible');
  document.getElementById('choice-buttons')?.remove();
}

// JRPG-style choice buttons
function checkChoices(reply) {
  const existing = document.getElementById('choice-buttons');
  if (existing) existing.remove();

  // Detect choice patterns: emoji + text pairs, numbered items, or "/" separated
  const emojiItems = reply.match(/[🎭🤪🔇🧠😏😌✨😂🤔]/g);
  if (!emojiItems || emojiItems.length < 2) return;

  // Extract possible choices (emoji-prefixed segments)
  const segments = reply.split(/(?=[🎭🤪🔇🧠😌😂🤔🫂💪])/).filter(s => s.trim().length > 2 && s.trim().length < 40);
  if (segments.length < 2) return;

  const container = document.createElement('div');
  container.id = 'choice-buttons';
  container.style.cssText = 'position:fixed;z-index:25;display:flex;gap:6px;flex-wrap:wrap;max-width:300px;';
  const dlgRect = dialog.getBoundingClientRect();
  container.style.left = dlgRect.left + 'px';
  container.style.top = (dlgRect.bottom + 8) + 'px';

  segments.forEach(seg => {
    const btn = document.createElement('button');
    btn.textContent = seg.trim();
    btn.style.cssText = 'background:rgba(18,18,42,0.9);border:1px solid rgba(124,131,255,0.3);border-radius:12px;padding:6px 12px;color:#c8c8e0;font-size:0.7rem;cursor:pointer;font-family:inherit;letter-spacing:0.03em;transition:all 0.2s;';
    btn.onmouseenter = () => { btn.style.borderColor = 'var(--accent)'; btn.style.background = 'rgba(124,131,255,0.15)'; };
    btn.onmouseleave = () => { btn.style.borderColor = 'rgba(124,131,255,0.3)'; btn.style.background = 'rgba(18,18,42,0.9)'; };
    btn.addEventListener('click', () => {
      input.value = seg.trim();
      container.remove();
      sendMessage();
    });
    container.appendChild(btn);
  });

  document.body.appendChild(container);
  // Auto-remove after 15 seconds
  setTimeout(() => container.remove(), 15000);
}

dlgClose.addEventListener('click', hideDialog);

// Click dialog to advance / double-click to skip
dlgBody.addEventListener('click', e => {
  if (e.target.closest('.news-ref')) return; // Don't interfere with link clicks
  if (dlgTyping) {
    skipTypewriter();
  }
});

dlgBody.addEventListener('dblclick', e => {
  e.preventDefault();
  skipTypewriter();
});

// Dialog dragging
let dlgDragging = false, dlgOffX = 0, dlgOffY = 0;

dialog.querySelector('.dlg-header').addEventListener('pointerdown', e => {
  if (e.target === dlgClose) return;
  dlgDragging = true;
  const rect = dialog.getBoundingClientRect();
  dlgOffX = e.clientX - rect.left;
  dlgOffY = e.clientY - rect.top;
  dialog.setPointerCapture(e.pointerId);
});

window.addEventListener('pointermove', e => {
  if (!dlgDragging) return;
  dialog.style.left = (e.clientX - dlgOffX) + 'px';
  dialog.style.top = (e.clientY - dlgOffY) + 'px';
});

window.addEventListener('pointerup', () => { dlgDragging = false; });

// Click on news ref links
dlgBody.addEventListener('click', e => {
  const ref = e.target.closest('.news-ref');
  if (ref && ref.dataset.url) window.open(ref.dataset.url, '_blank');
});

// ═══════════════════════════════════════════
// Auxiliary panel
// ═══════════════════════════════════════════
let auxTab = 'diary';

function openAuxiliary(tab = 'diary') {
  state = STATE.AUXILIARY;
  auxPanel.classList.add('open');
  auxTab = tab;
  document.querySelectorAll('.aux-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  loadAuxContent();
}

function closeAuxiliary() {
  auxPanel.classList.remove('open');
  state = STATE.STARFIELD;
  chatFadeIn = 0;
  initStarfield();
  inputRow.classList.remove('visible');
}

auxBack.addEventListener('click', closeAuxiliary);
document.querySelectorAll('.aux-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    auxTab = tab.dataset.tab;
    document.querySelectorAll('.aux-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === auxTab));
    loadAuxContent();
  });
});

function loadAuxContent() {
  // Detach constellation canvas when switching away
  if (auxTab !== 'constellation' && typeof Constellation !== 'undefined') {
    Constellation.stop();
  }
  if (auxTab === 'diary') loadDiaryContent();
  else if (auxTab === 'news') loadNewsContent();
  else if (auxTab === 'mood') loadMoodContent();
  else if (auxTab === 'memory') loadMemoryContent();
  else if (auxTab === 'constellation') loadConstellationContent();
}

async function loadMemoryContent() {
  auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#6a6a8a;">加载记忆中...</div>';
  try {
    const [personaR, profileR] = await Promise.all([
      fetch('/api/memory/persona'),
      fetch('/api/memory/profile')
    ]);
    const persona = await personaR.json();
    const profile = await profileR.json();

    auxContent.innerHTML = `
      <div class="memory-section">
        <div class="memory-label">🤖 AI 人设</div>
        <div class="memory-card">${escapeHtml(persona.content || '未设定').replace(/\n/g, '<br>')}</div>
      </div>
      <div class="memory-section" style="margin-top:24px;">
        <div class="memory-label">👤 用户画像</div>
        <div class="memory-card">${escapeHtml(profile.content || '未设定').replace(/\n/g, '<br>')}</div>
      </div>
      <div style="text-align:center;margin-top:24px;font-size:0.6rem;color:#4a4a6a;letter-spacing:0.04em;">
        仅通过对话逐渐拟合，不可手动编辑
      </div>
    `;
  } catch(e) {
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">加载失败</div>';
  }
}

// ── Constellation star map (full-screen overlay) ──
async function loadConstellationContent() {
  auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#6a6a8a;">绘制星图中...</div>';
  try {
    const resp = await fetch('/api/constellation');
    const data = await resp.json();

    // Build full-screen overlay
    const overlay = document.createElement("div");
    overlay.className = "constellation-overlay";
    overlay.innerHTML = `
      <button class="constellation-overlay-close" title="关闭 (Esc)">✕</button>
      <div class="constellation-overlay-legend">
        ${(data.galaxies || []).map(g =>
          `<span class="constellation-legend-item">
            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${g.color};"></span>
            ${g.label}(${g.star_count})
          </span>`
        ).join('')}
        <span style="margin-left:12px;opacity:0.4;font-size:0.65rem;">滚轮缩放 · 拖拽平移 · 拖动节点 · 双击复位</span>
      </div>
      <div class="constellation-overlay-canvas" id="constellationCanvas"></div>
      <div class="constellation-bubble" id="constellationBubble" style="display:none;">
        <div class="constellation-bubble-galaxy" id="bubbleGalaxy"></div>
        <div class="constellation-bubble-tag" id="bubbleTag"></div>
        <div class="constellation-bubble-body" id="bubbleBody"></div>
        <div class="constellation-bubble-meta">
          <span class="bubble-importance" id="bubbleImportance"></span>
        </div>
        <button class="constellation-bubble-close" id="bubbleClose">✕</button>
      </div>
    `;
    document.body.appendChild(overlay);

    // Close helpers
    function closeOverlay() {
      if (typeof Constellation !== 'undefined') Constellation.detach();
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      document.removeEventListener("keydown", onKey);
    }
    function onKey(e) { if (e.key === "Escape") closeOverlay(); }
    document.addEventListener("keydown", onKey);

    overlay.querySelector(".constellation-overlay-close").onclick = closeOverlay;
    // Click background (not canvas) to close
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeOverlay();
    });

    // Star detail handlers — chat bubble style popup
    window._onConstellationStarClick = function(star) {
      const bubble = document.getElementById('constellationBubble');
      if (!star) {
        // Click on blank — close bubble
        bubble.style.display = 'none';
        return;
      }
      document.getElementById('bubbleGalaxy').textContent = '🌌 ' + (star.galaxyName || star.galaxy || '记忆');
      document.getElementById('bubbleGalaxy').style.color = star.color || '#a78bfa';
      document.getElementById('bubbleTag').textContent = star.tag;
      document.getElementById('bubbleBody').textContent = star.summary || '(暂无详情)';
      // Importance bar
      const imp = star.importance || 0;
      const pct = Math.round(imp * 100);
      document.getElementById('bubbleImportance').innerHTML =
        '⭐ 重要性 <b style="color:' + (star.color || '#a78bfa') + '">' + pct + '%</b>';
      bubble.style.display = 'block';
      // Click outside bubble to close
      setTimeout(() => {
        document.addEventListener('click', function _closeBubble(e) {
          if (!bubble.contains(e.target) && e.target.tagName !== 'CANVAS') {
            bubble.style.display = 'none';
            document.removeEventListener('click', _closeBubble);
            if (typeof Constellation !== 'undefined') Constellation.clearSelection();
          }
        });
      }, 100);
    };
    document.getElementById('bubbleClose').onclick = function() {
      document.getElementById('constellationBubble').style.display = 'none';
      if (typeof Constellation !== 'undefined') Constellation.clearSelection();
    };

    // Attach canvas renderer
    const container = document.getElementById('constellationCanvas');
    if (container && typeof Constellation !== 'undefined') {
      Constellation.init(data);
      Constellation.attach(container);
    }

    // Restore sidebar neutral state
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#6a6a8a;">🌌 星图已打开<br><small>关闭全屏窗口即可返回</small></div>';
  } catch(e) {
    console.error('[Constellation] load failed:', e);
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">星图加载失败: ' + e.message + '</div>';
  }
}

// ── Mood calendar ──
async function loadMoodContent() {
  auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#6a6a8a;">加载情绪数据...</div>';
  try {
    const resp = await fetch('/api/mood/calendar?days=60');
    const data = await resp.json();
    if (!data.length) {
      auxContent.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#6a6a8a;">🎭<br>还没有情绪数据</div>';
      return;
    }
    let html = '<div class="mood-grid">';
    for (const d of data) {
      const intensity = Math.min(1, d.chat_count / 20);
      const alpha = 0.15 + intensity * 0.6;
      html += `<div class="mood-cell" title="${d.date} · ${d.chat_count}次对话" style="background:rgba(124,131,255,${alpha.toFixed(2)})">${d.mood_emoji}</div>`;
    }
    html += '</div><div style="text-align:center;margin-top:16px;font-size:0.6rem;color:#5a5a7a;">颜色深浅 = 当日对话活跃度</div>';
    auxContent.innerHTML = html;
  } catch(e) {
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">加载失败</div>';
  }
}

async function loadDiaryContent() {
  auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#6a6a8a;">加载日记中...</div>';
  try {
    const resp = await fetch('/api/diary');
    const diaries = await resp.json();
    if (!Array.isArray(diaries) || diaries.length === 0) {
      auxContent.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#6a6a8a;line-height:2;">📖<br>还没有日记<br><span style="font-size:0.7rem;">每天凌晨4点自动生成</span></div>';
      return;
    }
    const now = new Date();
    let html = '';

    // On-this-day section
    html += '<div id="onThisDay" style="margin-bottom:20px;"></div>';

    html += '<div class="timeline">' + diaries.map((d, i) => {
      const emoji = extractMoodEmoji(d.content);
      return `
        <div class="tl-node" data-date="${d.date}">
          <div class="tl-dot">${emoji}</div>
          <div class="tl-date">${d.date} · ${d.chat_count}次对话</div>
          <div class="tl-preview">${escapeHtml(d.content.substring(0, 80))}...</div>
        </div>`;
    }).join('') + '</div>';
    auxContent.innerHTML = html;

    // Load on-this-day
    (async () => {
      try {
        const r = await fetch('/api/diary/on-this-day');
        const past = await r.json();
        if (past.length) {
          const otd = document.getElementById('onThisDay');
          otd.innerHTML = '<div style="font-size:0.65rem;color:#ffd700;margin-bottom:8px;letter-spacing:0.04em;">🕰️ 去年的今天</div>' +
            past.map(p => `<div style="font-size:0.7rem;color:#a0a0c0;margin-bottom:6px;line-height:1.6;">${escapeHtml(p.date)} · ${escapeHtml((p.content||'').substring(0,60))}...</div>`).join('');
        }
      } catch(e) {}
    })();

    // Click to expand
    auxContent.querySelectorAll('.tl-node').forEach(node => {
      node.addEventListener('click', async () => {
        if (node.classList.contains('expanded')) {
          node.classList.remove('expanded');
          return;
        }
        const date = node.dataset.date;
        try {
          const r = await fetch('/api/diary/' + date);
          const full = await r.json();
          if (full.content) {
            node.querySelector('.tl-preview').textContent = full.content;
            node.classList.add('expanded');
          }
        } catch(e) {}
      });
    });
  } catch(e) {
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">加载失败</div>';
  }
}

async function loadNewsContent() {
  auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#6a6a8a;">加载新闻中...</div>';
  try {
    const resp = await fetch('/api/news');
    const news = await resp.json();
    if (!Array.isArray(news) || news.length === 0) {
      auxContent.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#6a6a8a;line-height:2;">📡<br>还没有新闻<br><button id="fetchNewsBtn" style="margin-top:12px;background:var(--accent);color:#fff;border:none;padding:8px 20px;border-radius:16px;cursor:pointer;font-family:inherit;">立即拉取</button></div>';
      const btn = document.getElementById('fetchNewsBtn');
      if (btn) btn.addEventListener('click', async () => {
        btn.textContent = '拉取中...'; btn.disabled = true;
        await fetch('/api/news/fetch', { method: 'POST' });
        loadNewsContent();
      });
      return;
    }
    auxContent.innerHTML = news.map(n => `
      <div class="news-card" data-url="${escapeHtml(n.url || '')}">
        <div class="news-title">${escapeHtml(n.title)}</div>
        <div class="news-meta">
          <span class="news-tag ${n.source}">${n.source}</span>
          <span style="color:#6a6a8a">#${n.rank}</span>
        </div>
      </div>
    `).join('');
    auxContent.querySelectorAll('.news-card').forEach(card => {
      card.addEventListener('click', () => {
        const url = card.dataset.url;
        if (url) window.open(url, '_blank');
      });
    });
  } catch(e) {
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">加载失败</div>';
  }
}

function extractMoodEmoji(text) {
  const emojiRegex = /[\p{Emoji_Presentation}\p{Extended_Pictographic}]/u;
  const match = text.match(emojiRegex);
  return match ? match[0] : '✨';
}

// ═══════════════════════════════════════════
// Long press detection
// ═══════════════════════════════════════════
let pressTimer = null, pressStartX = 0, pressStartY = 0;
const LONG_PRESS_DURATION = 1000;
const MOVE_THRESHOLD = 10;

canvas.addEventListener('pointerdown', e => {
  pressStartX = e.clientX;
  pressStartY = e.clientY;
  pressTimer = setTimeout(() => {
    if (state === STATE.STARFIELD || state === STATE.CHAT) {
      openAuxiliary('diary');
    }
  }, LONG_PRESS_DURATION);
});

canvas.addEventListener('pointermove', e => {
  if (!pressTimer) return;
  const dx = e.clientX - pressStartX;
  const dy = e.clientY - pressStartY;
  if (Math.abs(dx) > MOVE_THRESHOLD || Math.abs(dy) > MOVE_THRESHOLD) {
    clearTimeout(pressTimer);
    pressTimer = null;
  }
});

canvas.addEventListener('pointerup', () => {
  clearTimeout(pressTimer);
  pressTimer = null;
});

// Cursor tracking for constellation interaction
canvas.addEventListener('pointermove', e => {
  const r = canvas.getBoundingClientRect();
  cursorX = e.clientX - r.left;
  cursorY = e.clientY - r.top;
});

canvas.addEventListener('pointerleave', () => {
  clearTimeout(pressTimer);
  pressTimer = null;
  cursorX = null; cursorY = null;
});

// ═══════════════════════════════════════════
// Click to interact
// ═══════════════════════════════════════════
let clickCount = 0, clickTimer = null;

canvas.addEventListener('click', e => {
  if (state === STATE.AUXILIARY) return;
  const rect = canvas.getBoundingClientRect();
  const cx = e.clientX - rect.left, cy = e.clientY - rect.top;

  if (pressTimer === null && Math.abs(e.clientX - pressStartX) < MOVE_THRESHOLD) {
    // Check face click (poke interaction)
    if (state === STATE.CHAT) {
      const faceCX = canvas.width / 2;
      const faceCY = canvas.height / 2 + 5 * faceCS + faceBob;
      const faceR = 14 * faceCS;
      const dfx = cx - faceCX, dfy = cy - faceCY;
      if (Math.sqrt(dfx*dfx + dfy*dfy) < faceR) {
        triggerPokeReaction(cx, cy);
        return;
      }
    }

    // Check memory star click
    if ((state === STATE.STARFIELD || state === STATE.CHAT) && checkMemoryStarClick(cx, cy)) return;

    // Check if clicked a functional point in starfield
    if (state === STATE.STARFIELD) {
      for (const fp of functionalPoints) {
        const s = fp.star;
        const dx = cx - s.x, dy = cy - s.y;
        if (Math.sqrt(dx*dx + dy*dy) < s.size * 3) {
          openAuxiliary(fp.type === 'diary' ? 'diary' : 'news');
          return;
        }
      }
    }

    // Count clicks for convergence trigger
    clickCount++;
    clearTimeout(clickTimer);
    clickTimer = setTimeout(() => { clickCount = 0; }, 600);
    if (clickCount >= 3 && state === STATE.STARFIELD) {
      clickCount = 0;
      startConvergence();
    }
  }
});

// ═══════════════════════════════════════════
// Input / Chat
// ═══════════════════════════════════════════
let pending = false;

input.addEventListener('keydown', e => {
  if (e.key === 'Enter') sendMessage();
  if (state === STATE.STARFIELD) startConvergence();
});

input.addEventListener('focus', () => {
  if (state === STATE.STARFIELD) startConvergence();
});

async function sendMessage() {
  const text = input.value.trim();
  if (!text || pending) return;
  if (state !== STATE.CHAT) return;

  input.value = ''; pending = true; sendBtn.disabled = true;

  // Position dialog (responsive)
  const faceCenterX = canvas.width / 2;
  const faceCenterY = canvas.height / 2;
  const faceRadius = 29 * faceCS;
  const isNarrow = window.innerWidth < 600;
  const dlgW = isNarrow ? 260 : 340;
  let dx = faceCenterX + faceRadius + 20;
  let dy = faceCenterY - 60;
  if (dx + dlgW > window.innerWidth - 20) dx = Math.max(10, faceCenterX - faceRadius - dlgW);
  if (isNarrow && dx < 10) { dx = (window.innerWidth - dlgW) / 2; dy = faceCenterY + faceRadius + 30; }
  if (dy < 60) dy = faceCenterY + faceRadius + 20;
  if (dy + 120 > window.innerHeight - 20) dy = faceCenterY - 120;
  dialog.style.left = dx + 'px';
  dialog.style.top = dy + 'px';
  dialog.classList.add('visible');
  dlgBody.innerHTML = '<span class="cursor-blink"></span>';
  let streamedReply = '';

  try {
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      const lines = buffer.split('\n');
      buffer = '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) { buffer = line; continue; }
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === 'emotions') {
            setSequence(evt.emotions, '');
            updateMoodFromEmotion(evt.label || '');
          } else if (evt.type === 'thinking') {
            dlgBody.innerHTML = '<span class="thinking-indicator">思考中<span class="thinking-dots"></span></span>';
          } else if (evt.type === 'text') {
            streamedReply += evt.text;
            playTypingSound();
            dlgBody.innerHTML = escapeHtml(streamedReply) + '<span class="cursor-blink"></span>';
          } else if (evt.type === 'error') {
            streamedReply = evt.text;
            dlgBody.innerHTML = escapeHtml(streamedReply);
            addDebugLog('error', 'LLM调用失败', evt.text, 'DeepSeek API 可能超时或返回异常，检查 API Key 和网络连接');
          } else if (evt.type === 'done') {
            dlgBody.innerHTML = escapeHtml(streamedReply);
            checkChoices(streamedReply);
          }
        } catch(e) {
          // Partial JSON, keep in buffer
          buffer = line;
        }
      }
    }
  } catch(err) {
    dlgBody.innerHTML = '嗯...出了点问题 😢';
    addDebugLog('error', '请求失败', err.message, '检查容器是否运行、网络是否正常、DeepSeek API 是否可达');
  } finally {
    pending = false; sendBtn.disabled = false; input.focus();
    if (streamedReply) {
      dlgText = streamedReply;
      dlgTyping = false;
    }
  }
}

// Topic bubbles
async function loadTopics() {
  try {
    const resp = await fetch('/api/news/topics');
    const topics = await resp.json();
    if (!topics.length) { topicBubbles.classList.remove('visible'); return; }
    topicBubbles.innerHTML = topics.map(t =>
      `<span class="topic-bubble" data-prompt="${escapeHtml(t.prompt)}">${escapeHtml(t.prompt)}</span>`
    ).join('');
    topicBubbles.classList.add('visible');
    topicBubbles.querySelectorAll('.topic-bubble').forEach(b => {
      b.addEventListener('click', () => {
        const prompt = b.dataset.prompt;
        input.value = prompt;
        topicBubbles.classList.remove('visible');
        sendMessage();
      });
    });
  } catch(e) { topicBubbles.classList.remove('visible'); }
}

sendBtn.addEventListener('click', sendMessage);

// ═══════════════════════════════════════════
// Main loop
// ═══════════════════════════════════════════
let lastT = performance.now();

function loop(t) {
  const dt = Math.min((t - lastT) / 1000, 0.1);
  lastT = t;

  switch (state) {
    case STATE.STARFIELD:
      updateStarfield(dt);
      drawStarfield();
      drawPokeSparkles();
      break;
    case STATE.CONVERGING:
      updateConvergence(dt);
      drawConvergence();
      break;
    case STATE.CHAT:
      updateChat(dt);
      drawChat();
      drawMeteors();
      drawMemoryStars();
      drawPokeSparkles();
      break;
    case STATE.AUXILIARY:
      // Static background
      ctx.fillStyle = '#0a0a1a';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      break;
  }

  requestAnimationFrame(loop);
}

// ═══════════════════════════════════════════
// Init
// ═══════════════════════════════════════════
initStarfield();
initMemoryStars();
recomputeFaceLayout();
initSparkleParticles();
// Initial face pixel computation for convergence targets
curParams = { eye_curve:0, eye_open:0.5, eye_pupil:0, eye_wink:0, mouth_curve:0, mouth_open:0, mouth_width:0.8, mouth_asym:0, sparkle:0.5, brow_angle:0, brow_height:0.5, brow_asym:0, blush:0.15, head_tilt:0, tear:0 };
tgtParams = { ...curParams };
requestAnimationFrame(loop);

// Check for idle thoughts and missing-you on load
(async function checkOnLoad() {
  try {
    // First check if user was away for a long time
    const myResp = await fetch('/api/missing-you');
    const my = await myResp.json();
    if (my.away && my.thoughts && my.thoughts.length > 0) {
      setTimeout(() => {
        if (state === STATE.STARFIELD) {
          const days = Math.round(my.hours / 24);
          const timeStr = my.hours < 48
            ? Math.round(my.hours) + '个小时'
            : days + '天';
          const msg = '你回来了～已经过了' + timeStr
            + '。你不在的时候，我在星空里想了一些事情...\n\n'
            + my.thoughts.slice(0, 3).join('\n');
          showDialog(msg, canvas.width / 2, canvas.height * 0.25);
          setTimeout(() => { if (state === STATE.STARFIELD) hideDialog(); }, 10000);
        }
      }, 2500);
      return;
    }

    // Otherwise check for recent idle thought
    const resp = await fetch('/api/idle-thought');
    const data = await resp.json();
    if (data.thought) {
      setTimeout(() => {
        if (state === STATE.STARFIELD) {
          showDialog('💭 ' + data.thought, canvas.width / 2, canvas.height * 0.3);
          setTimeout(() => { if (state === STATE.STARFIELD) hideDialog(); }, 5000);
        }
      }, 2000);
    }
  } catch (e) {}
})();
