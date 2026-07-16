// @ts-check
// ═══════════════════════════════════════════
// Retro dialog
// ═══════════════════════════════════════════
let dlgTyping = false, dlgTimer = null, thinkingTimer = null;
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
  const emojiItems = reply.match(/[🎭🤪🔇🧠😏😌✨😂🤔🫂💪]/g);
  if (!emojiItems || emojiItems.length < 2) return;

  // Extract possible choices (emoji-prefixed segments)
  const segments = reply.split(/(?=[🎭🤪🔇🧠😏😌✨😂🤔🫂💪])/).filter(s => s.trim().length > 2 && s.trim().length < 40);
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
dlgBody.addEventListener('click', /** @param {MouseEvent} e */ e => {
  if (/** @type {Element} */ (e.target).closest('.news-ref')) return; // Don't interfere with link clicks
  if (dlgTyping) {
    skipTypewriter();
  }
});

dlgBody.addEventListener('dblclick', /** @param {MouseEvent} e */ e => {
  e.preventDefault();
  skipTypewriter();
});

// Dialog dragging
let dlgDragging = false, dlgOffX = 0, dlgOffY = 0;

dialog.querySelector('.dlg-header').addEventListener('pointerdown', /** @param {PointerEvent} e */ e => {
  if (e.target === dlgClose) return;
  dlgDragging = true;
  const rect = dialog.getBoundingClientRect();
  dlgOffX = e.clientX - rect.left;
  dlgOffY = e.clientY - rect.top;
  dialog.setPointerCapture(e.pointerId);
});

window.addEventListener('pointermove', /** @param {PointerEvent} e */ e => {
  if (!dlgDragging) return;
  dialog.style.left = (e.clientX - dlgOffX) + 'px';
  dialog.style.top = (e.clientY - dlgOffY) + 'px';
});

window.addEventListener('pointerup', () => { dlgDragging = false; });

// Click on news ref links
dlgBody.addEventListener('click', /** @param {MouseEvent} e */ e => {
	  const ref = /** @type {HTMLElement | null} */ (/** @type {HTMLElement} */ (e.target).closest('.news-ref'));
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
  topicBubbles.classList.remove('visible');
  document.querySelectorAll('.aux-tab').forEach(/** @param {HTMLElement} t */ t => t.classList.toggle('active', t.dataset.tab === tab));
  loadAuxContent();
}

function closeAuxiliary() {
  auxPanel.classList.remove('open');
  state = STATE.STARFIELD;
  chatFadeIn = 0;
  topicBubbles.classList.remove('visible');
  // Clean up constellation overlay if present
  var overlay = document.querySelector('.constellation-overlay');
  if (overlay) {
    if (typeof Constellation !== 'undefined') Constellation.detach();
    overlay.remove();
    auxContent.innerHTML = '';
  }
  initStarfield();
  inputRow.classList.remove('visible');
}

auxBack.addEventListener('click', closeAuxiliary);
document.querySelectorAll('.aux-tab').forEach(/** @param {HTMLElement} tab */ tab => {
  tab.addEventListener('click', () => {
    auxTab = tab.dataset.tab;
    document.querySelectorAll('.aux-tab').forEach(/** @param {HTMLElement} t */ t => t.classList.toggle('active', t.dataset.tab === auxTab));
    if (auxTab === 'settings') {
      openSettings();
    } else {
      loadAuxContent();
    }
  });
});

function loadAuxContent() {
  // Detach constellation canvas and remove overlay when switching away
  if (auxTab !== 'constellation' && typeof Constellation !== 'undefined') {
    Constellation.detach();
  }
  if (auxTab !== 'constellation') {
    var overlay = document.querySelector('.constellation-overlay');
    if (overlay) overlay.remove();
    auxContent.innerHTML = '';
  }
  if (auxTab === 'diary') loadDiaryContent(true);
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
        <div class="memory-label"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg> AI 人设</div>
        <div class="memory-card">${escapeHtml(persona.content || '未设定').replace(/\n/g, '<br>')}</div>
      </div>
      <div class="memory-section" style="margin-top:24px;">
        <div class="memory-label"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 15H7a4 4 0 0 0-4 4v2"/><path d="M21.378 16.626a1 1 0 0 0-3.004-3.004l-4.01 4.012a2 2 0 0 0-.506.854l-.837 2.87a.5.5 0 0 0 .62.62l2.87-.837a2 2 0 0 0 .854-.506z"/><circle cx="10" cy="7" r="4"/></svg> 用户画像</div>
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
      auxContent.innerHTML = '';
    }
    function onKey(e) { if (e.key === "Escape") closeOverlay(); }
    document.addEventListener("keydown", onKey);

    /** @type {HTMLElement} */ (overlay.querySelector(".constellation-overlay-close")).onclick = closeOverlay;
    // Click background (not canvas) to close
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeOverlay();
    });

    // Star detail handlers — chat bubble style popup
    window._closeBubbleHandler = null;
    window._onConstellationStarClick = function(star) {
      const bubble = document.getElementById('constellationBubble');
      // Clean up previous close handler
      if (window._closeBubbleHandler) {
        document.removeEventListener('click', window._closeBubbleHandler);
        window._closeBubbleHandler = null;
      }
      if (!star) {
        // Click on blank — close bubble
        bubble.style.display = 'none';
        return;
      }
      document.getElementById('bubbleGalaxy').textContent = '🌌 ' + (star.galaxyName || star.galaxy || '记忆');
      document.getElementById('bubbleGalaxy').style.color = star.color || '#a78bfa';
      document.getElementById('bubbleTag').textContent = star.tag;
      document.getElementById('bubbleBody').textContent = star.summary || '(暂无详情)';
      const imp = star.importance || 0;
      const pct = Math.round(imp * 100);
      document.getElementById('bubbleImportance').innerHTML =
        '⭐ 重要性 <b style="color:' + (star.color || '#a78bfa') + '">' + pct + '%</b>';
      bubble.style.display = 'block';
      // Click outside bubble to close (debounced to avoid immediate close on same click)
      setTimeout(function() {
        window._closeBubbleHandler = function _closeBubble(/** @type {MouseEvent} */ e) {
          var tgt = /** @type {Element} */ (e.target);
          if (!bubble.contains(tgt) && tgt.tagName !== 'CANVAS') {
            bubble.style.display = 'none';
            document.removeEventListener('click', _closeBubble);
            window._closeBubbleHandler = null;
            if (typeof Constellation !== 'undefined') Constellation.clearSelection();
          }
        };
        document.addEventListener('click', window._closeBubbleHandler);
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
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">星图加载失败: ' + escapeHtml(e.message) + '</div>';
  }
}

// ── Mood calendar ──
var moodCalendarYear = new Date().getFullYear();
var moodCalendarMonth = new Date().getMonth(); // 0-based
var moodAllDates = []; // cached list of all dates with diary data for quick lookup

function moodDateKey(d) { return d.date || d; }

async function loadMoodContent() {
  auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#6a6a8a;">加载情绪数据...</div>';
  try {
    var now = new Date();
    moodCalendarYear = now.getFullYear();
    moodCalendarMonth = now.getMonth();
    // Fetch all mood data for quick navigation (no date range limit)
    var resp = await fetch('/api/mood/calendar?days=366');
    var data = await resp.json();
    if (!data.length) {
      auxContent.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#6a6a8a;"><img src="/icons/smile-plus.svg" class="empty-state-icon" alt=""><br>还没有情绪数据</div>';
      return;
    }
    moodAllDates = data;
    renderMoodCalendar();
  } catch(e) {
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">加载失败</div>';
  }
}

function renderMoodCalendar() {
  var byDate = {};
  moodAllDates.forEach(function(d) { byDate[d.date] = d; });

  // Build calendar for moodCalendarYear / moodCalendarMonth
  var firstDay = new Date(moodCalendarYear, moodCalendarMonth, 1);
  var lastDay = new Date(moodCalendarYear, moodCalendarMonth + 1, 0);
  var startDow = firstDay.getDay(); // 0=Sun
  var daysInMonth = lastDay.getDate();
  var todayStr = new Date().toISOString().slice(0, 10);

  // Month nav with year pills
  var nowYear = new Date().getFullYear();
  var yrHtml = '<div class="yr-pill-row" id="moodYrRow">';
  for (var y = nowYear; y >= 2026; y--) {
    var cls = 'yr-pill';
    if (y === moodCalendarYear) cls += ' active';
    if (y === nowYear) cls += ' current';
    yrHtml += '<button class="' + cls + '" onclick="moodPickYear(' + y + ')">' + y + '</button>';
  }
  yrHtml += '</div>';
  var html = '<div class="mood-month-nav">';
  html += '<button class="mood-nav-btn" onclick="moodPrevMonth()"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg></button>';
  html += '<span class="mood-month-label">' + (moodCalendarMonth + 1) + '月</span>';
  html += '<button class="mood-nav-btn" onclick="moodNextMonth()"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg></button>';
  html += '</div>';
  // Year pills on their own row
  html += yrHtml;

  // Day-of-week header
  html += '<div class="mood-weekdays">' + ['日','一','二','三','四','五','六'].map(function(w) {
    return '<span class="mood-dow">' + w + '</span>';
  }).join('') + '</div>';

  // Calendar grid
  html += '<div class="mood-cal-grid">';
  // Empty cells before first day
  for (var i = 0; i < startDow; i++) {
    html += '<div class="mood-cal-cell empty"></div>';
  }
  for (var d = 1; d <= daysInMonth; d++) {
    var ds = moodCalendarYear + '-' + String(moodCalendarMonth + 1).padStart(2,'0') + '-' + String(d).padStart(2,'0');
    var entry = byDate[ds];
    var cls = 'mood-cal-cell';
    var emoji = '';
    var title = ds;
    var onClick = '';
    if (entry) {
      cls += ' has-data';
      emoji = entry.mood_emoji || '✨';
      title = ds + ' · ' + entry.chat_count + '次对话';
      if (entry.has_diary) {
        cls += ' clickable';
        onClick = ' onclick="openDiaryModal(\'' + ds + '\')"';
      }
    }
    if (ds === todayStr) cls += ' today';
    html += '<div class="' + cls + '" title="' + title + '"' + onClick + '>' +
            '<span class="mood-cal-day">' + d + '</span>' +
            (emoji ? '<span class="mood-cal-emoji">' + emoji + '</span>' : '') +
            '</div>';
  }
  html += '</div>';

  // Emotion stats
  var emojiCount = {};
  moodAllDates.forEach(function(d) {
    var em = d.mood_emoji || '✨';
    emojiCount[em] = (emojiCount[em] || 0) + 1;
  });
  var sorted = Object.entries(emojiCount).sort(function(a, b) { return b[1] - a[1]; });
  if (sorted.length) {
    html += '<div class="mood-stats">';
    html += '<div class="mood-stats-label">情绪分布</div><div class="mood-stats-bar">';
    var total = sorted.reduce(function(s, p) { return s + p[1]; }, 0);
    sorted.forEach(function(pair) {
      var pct = (pair[1] / total * 100).toFixed(0);
      html += '<div class="mood-stat-item"><span>' + pair[0] + '</span><span class="mood-stat-count">' + pair[1] + '</span></div>';
    });
    html += '</div></div>';
  }

  auxContent.innerHTML = html;
}

function moodPrevMonth() {
  // Find earliest year in data to prevent navigating before data exists
  var minYear = 2026;
  if (moodAllDates.length) {
    minYear = new Date(moodAllDates[0].date).getFullYear();
  }
  if (moodCalendarMonth === 0) {
    if (moodCalendarYear <= minYear) return;
    moodCalendarYear--; moodCalendarMonth = 11;
  }
  else { moodCalendarMonth--; }
  renderMoodCalendar();
}
function moodNextMonth() {
  var now = new Date();
  if (moodCalendarYear === now.getFullYear() && moodCalendarMonth === now.getMonth()) return;
  if (moodCalendarMonth === 11) { moodCalendarYear++; moodCalendarMonth = 0; }
  else { moodCalendarMonth++; }
  renderMoodCalendar();
}
function moodYearChanged(val) {
  if (!val) return;
  moodCalendarYear = parseInt(val);
  renderMoodCalendar();
}
function moodPickYear(y) {
  moodCalendarYear = y;
  renderMoodCalendar();
}

// ── Diary list ──
var diarySearch = '';
var diaryDatePreset = 'all'; // 'week' | 'month' | 'all'
var diaryYear = 0; // 0 means not using year-month picker
var diaryMonth = 0; // 0-based
var diaryOffset = 0;
var diaryLimit = 15;
var diaryHasMore = true;
var diaryAllDates = []; // cached sorted date list for modal prev/next
var diarySearchTimer = null; // debounce timer
var diaryComposing = false; // IME composition flag

function diaryPrevYear() {
  var now = new Date().getFullYear();
  var y = (diaryYear > 0 ? diaryYear : now) - 1;
  if (y < 2026) return;
  diaryYear = y; diaryMonth = 0;
  diaryDatePreset = 'all';
  updateDiaryToolbarUI();
  loadDiaryContent(true);
}
function diaryNextYear() {
  var now = new Date().getFullYear();
  var y = (diaryYear > 0 ? diaryYear : now) + 1;
  if (y > now) return;
  diaryYear = y; diaryMonth = 0;
  diaryDatePreset = 'all';
  updateDiaryToolbarUI();
  loadDiaryContent(true);
}
function diaryPickYear(y) {
  diaryYear = y;
  if (diaryMonth < 0) diaryMonth = 0;
  diaryDatePreset = 'all';
  updateDiaryToolbarUI();
  loadDiaryContent(true);
}
function diaryPickMonth(m) {
  if (diaryYear === 0) diaryYear = new Date().getFullYear();
  diaryMonth = m;
  diaryDatePreset = 'all';
  updateDiaryToolbarUI();
  loadDiaryContent(true);
}
function diaryShiftYear(delta) {
  var now = new Date().getFullYear();
  var newYear = (diaryYear || now) + delta;
  if (newYear < 2026 || newYear > now) return;
  diaryPickYear(newYear);
}

function _renderYearPills(selectedYear, idPrefix) {
  var now = new Date().getFullYear();
  var html = '<div class="yr-pill-row" id="' + idPrefix + 'YrRow">';
  for (var y = now; y >= 2026; y--) {
    var cls = 'yr-pill';
    if (y === selectedYear) cls += ' active';
    if (y === now) cls += ' current';
    html += '<button class="' + cls + '" onclick="' + idPrefix + 'PickYear(' + y + ')">' + y + '</button>';
  }
  html += '</div>';
  return html;
}

function _renderMonthGrid(selectedYear, selectedMonth) {
  var now = new Date();
  var nowYear = now.getFullYear();
  var nowMonth = now.getMonth();
  var html = '<div class="mo-grid" id="diaryMonthGrid">';
  for (var m = 0; m < 12; m++) {
    var cls = 'mo-cell';
    if (selectedYear > 0 && m === selectedMonth) cls += ' active';
    if (selectedYear === nowYear && m === nowMonth) cls += ' today';
    html += '<button class="' + cls + '" onclick="diaryPickMonth(' + m + ')">' + (m + 1) + '月</button>';
  }
  html += '</div>';
  return html;
}

function updateDiaryToolbarUI() {
  var clear = document.getElementById('diaryMonthClear');
  if (clear) clear.style.display = diaryYear > 0 ? '' : 'none';
  // Update year label
  var yrLabel = document.querySelector('.diary-yr-label');
  if (yrLabel) {
    var now = new Date().getFullYear();
    yrLabel.textContent = (diaryYear > 0 ? diaryYear : now) + '年';
  }
  // Update month grid
  var moGrid = document.getElementById('diaryMonthGrid');
  if (moGrid) {
    moGrid.querySelectorAll('.mo-cell').forEach(function(cell, i) {
      cell.classList.toggle('active', diaryYear > 0 && i === diaryMonth);
    });
  }
}

function buildDiaryToolbar() {
  var now = new Date().getFullYear();
  var displayYear = diaryYear > 0 ? diaryYear : now;
  var html = '<div class="diary-toolbar" id="diaryToolbar">';
  // Search row
  html += '<div class="diary-search-row">';
  html += '<svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="position:absolute;left:10px;top:50%;transform:translateY(-50%);color:#5a5a7a;"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>';
  html += '<input type="text" class="diary-search-input" placeholder="搜索日记内容..." value="' + escapeHtml(diarySearch) + '" id="diarySearchInput">';
  html += '</div>';
  // Year nav: ◀◀ 2026年 ▶▶ [清除]
  html += '<div class="diary-yr-row">';
  html += '<button class="diary-yr-nav" id="diaryYrPrev" title="上一年"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/></svg></button>';
  html += '<span class="diary-yr-label">' + displayYear + '年</span>';
  html += '<button class="diary-yr-nav" id="diaryYrNext" title="下一年"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m13 17 5-5-5-5"/><path d="m6 17 5-5-5-5"/></svg></button>';
  if (diaryYear > 0) html += '<button class="diary-month-clear" id="diaryMonthClear">清除</button>';
  html += '</div>';
  // Month grid
  html += _renderMonthGrid(diaryYear, diaryMonth);
  // Filter pills
  html += '<div class="diary-filter-pills">';
  html += '<button class="diary-pill' + (diaryDatePreset === 'week' ? ' active' : '') + '" data-preset="week">近一周</button>';
  html += '<button class="diary-pill' + (diaryDatePreset === 'month' ? ' active' : '') + '" data-preset="month">近一月</button>';
  html += '<button class="diary-pill' + (diaryDatePreset === 'all' ? ' active' : '') + '" data-preset="all">全部</button>';
  html += '</div></div>';
  return html;
}

function bindDiaryEvents() {
  var searchInput = /** @type {HTMLInputElement|null} */ (document.getElementById('diarySearchInput'));
  if (searchInput) {
    searchInput.addEventListener('compositionstart', function() { diaryComposing = true; });
    searchInput.addEventListener('compositionend', function() {
      diaryComposing = false;
      diarySearch = this.value;
      clearTimeout(diarySearchTimer);
      diarySearchTimer = setTimeout(function() { loadDiaryContent(true); }, 500);
    });
    searchInput.addEventListener('input', function() {
      diarySearch = this.value;
      if (diaryComposing) return; // wait for IME composition to finish
      clearTimeout(diarySearchTimer);
      diarySearchTimer = setTimeout(function() { loadDiaryContent(true); }, 500);
    });
  }

  var yrPrev = document.getElementById('diaryYrPrev');
  var yrNext = document.getElementById('diaryYrNext');
  var monthClear = document.getElementById('diaryMonthClear');
  if (yrPrev) yrPrev.addEventListener('click', function() {
    var now = new Date().getFullYear();
    if (diaryYear === 0) diaryYear = now;
    if (diaryYear <= 2026) return;
    diaryYear--; diaryMonth = 0;
    diaryDatePreset = 'all';
    updateDiaryToolbarUI();
    loadDiaryContent(true);
  });
  if (yrNext) yrNext.addEventListener('click', function() {
    var now = new Date().getFullYear();
    if (diaryYear === 0) diaryYear = now;
    if (diaryYear >= now) return;
    diaryYear++; diaryMonth = 0;
    diaryDatePreset = 'all';
    updateDiaryToolbarUI();
    loadDiaryContent(true);
  });
  if (monthClear) monthClear.addEventListener('click', function() {
    diaryYear = 0; diaryMonth = 0;
    updateDiaryToolbarUI();
    loadDiaryContent(true);
  });
  document.querySelectorAll('.diary-pill').forEach(function(btn) {
    btn.addEventListener('click', function() {
      diaryDatePreset = this.dataset.preset;
      diaryYear = 0; diaryMonth = 0;
      updateDiaryToolbarUI();
      document.querySelectorAll('.diary-pill').forEach(function(b) { b.classList.remove('active'); });
      this.classList.add('active');
      loadDiaryContent(true);
    });
  });
  var loadMore = document.getElementById('loadMoreDiary');
  if (loadMore) {
    loadMore.addEventListener('click', function() {
      diaryOffset += diaryLimit;
      loadDiaryContent(false);
    });
  }
  /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('.tl-node')).forEach(function(node) {
    node.addEventListener('click', function() {
      openDiaryModal(node.dataset.date);
    });
  });
}

var _diaryLoading = false;
async function loadDiaryContent(reset) {
  if (_diaryLoading) return;
  _diaryLoading = true;
  try {
  if (reset) {
    diaryOffset = 0;
    diaryHasMore = true;
    diaryAllDates = [];
  }
  if (!reset && !diaryHasMore) return;

  // Only rebuild toolbar if it doesn't exist yet
  var toolbar = document.getElementById('diaryToolbar');
  if (!toolbar) {
    auxContent.innerHTML = buildDiaryToolbar() + '<div id="diaryResults"><div style="text-align:center;padding:40px;color:#6a6a8a;">加载日记中...</div></div>';
    bindDiaryEvents();
  }

  var results = document.getElementById('diaryResults');
  if (!results) return;
  if (reset) results.innerHTML = '<div style="text-align:center;padding:20px;color:#6a6a8a;">搜索中...</div>';

  try {
    var params = 'limit=' + diaryLimit + '&offset=' + diaryOffset;
    if (diarySearch) params += '&search=' + encodeURIComponent(diarySearch);
    if (diaryYear > 0) {
      var firstDay = diaryYear + '-' + String(diaryMonth + 1).padStart(2,'0') + '-01';
      var lastDayDate = new Date(diaryYear, diaryMonth + 1, 0);
      var lastDay = diaryYear + '-' + String(diaryMonth + 1).padStart(2,'0') + '-' + String(lastDayDate.getDate()).padStart(2,'0');
      params += '&date_from=' + firstDay + '&date_to=' + lastDay;
    } else if (diaryDatePreset === 'week') {
      var d = new Date(); d.setDate(d.getDate() - 7);
      params += '&date_from=' + d.toISOString().slice(0,10);
    } else if (diaryDatePreset === 'month') {
      var m = new Date(); m.setDate(m.getDate() - 30);
      params += '&date_from=' + m.toISOString().slice(0,10);
    }

    var resp = await fetch('/api/diary?' + params);
    var diaries = await resp.json();

    if (!Array.isArray(diaries)) {
      results.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#6a6a8a;line-height:2;"><img src="/icons/book-open.svg" class="empty-state-icon" alt=""><br>还没有日记<br><span style="font-size:0.7rem;">每天凌晨4点自动生成</span></div>';
      return;
    }

    if (diaries.length < diaryLimit) diaryHasMore = false;

    // Collect all dates for modal navigation
    if (reset) diaryAllDates = [];
    diaries.forEach(function(d) { diaryAllDates.push(d.date); });

    if (reset && diaries.length === 0) {
      results.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#6a6a8a;line-height:2;"><img src="/icons/book-open.svg" class="empty-state-icon" alt=""><br>该月份暂无日记<br><span style="font-size:0.65rem;">尝试其他月份或点「清除」返回</span></div>';
      return;
    }

    // Build results HTML
    var html = '';
    if (reset) {
      html += '<div id="onThisDay" style="margin-bottom:20px;"></div>';
      html += '<div class="timeline" id="diaryTimeline">';
    }

    html += diaries.map(function(d) {
      var emoji = d.mood_emoji || extractMoodEmoji(d.content);
      var preview = escapeHtml((d.content || '').substring(0, 80));
      if (diarySearch) {
        var re = new RegExp('(' + diarySearch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        preview = preview.replace(re, '<mark class="search-highlight">$1</mark>');
      }
      return '<div class="tl-node" data-date="' + d.date + '">' +
        '<div class="tl-dot">' + emoji + '</div>' +
        '<div class="tl-date">' + d.date + ' · ' + d.chat_count + '次对话</div>' +
        '<div class="tl-preview">' + preview + '...</div>' +
        '</div>';
    }).join('');

    if (reset) {
      html += '</div>';
      if (diaryHasMore) {
        html += '<div style="text-align:center;margin-top:16px;"><button class="load-more-btn" id="loadMoreDiary">加载更多</button></div>';
      }
      results.innerHTML = html;
    } else {
      var timeline = document.getElementById('diaryTimeline');
      if (timeline) timeline.insertAdjacentHTML('beforeend', html);
      var loadMore = document.getElementById('loadMoreDiary');
      if (loadMore) loadMore.style.display = diaryHasMore ? '' : 'none';
    }

    // Bind timeline clicks
    /** @type {NodeListOf<HTMLElement>} */ (results.querySelectorAll('.tl-node')).forEach(function(node) {
      if (!node.dataset.bound) {
        node.dataset.bound = '1';
        node.addEventListener('click', function() { openDiaryModal(node.dataset.date); });
      }
    });

    // Bind load-more
    var loadMoreBtn = document.getElementById('loadMoreDiary');
    if (loadMoreBtn && !loadMoreBtn.dataset.bound) {
      loadMoreBtn.dataset.bound = '1';
      loadMoreBtn.addEventListener('click', function() {
        diaryOffset += diaryLimit;
        loadDiaryContent(false);
      });
    }

    // Handle pending diary date (from memory star click)
    if (reset && window._pendingDiaryDate) {
      var pendingDate = window._pendingDiaryDate;
      window._pendingDiaryDate = null;
      setTimeout(function() {
        var nodes = results.querySelectorAll('.tl-node');
        for (var i = 0; i < nodes.length; i++) {
          var node = /** @type {HTMLElement} */ (nodes[i]);
          if (node.dataset.date === pendingDate) {
            node.scrollIntoView({ behavior: 'smooth', block: 'center' });
            node.classList.add('glow');
            setTimeout(function() { node.classList.remove('glow'); }, 2500);
            setTimeout(function() { openDiaryModal(pendingDate); }, 400);
            break;
          }
        }
      }, 100);
    }

    // Load on-this-day (only on reset)
    if (reset) {
      (async function() {
        try {
          var r = await fetch('/api/diary/on-this-day');
          var past = await r.json();
          if (past.length) {
            var otd = document.getElementById('onThisDay');
            if (otd) {
              otd.innerHTML = '<div class="on-this-day-label"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> 去年的今天</div>' +
                past.map(function(p) {
                  return '<div class="tl-clickable" style="font-size:0.7rem;color:#a0a0c0;margin-bottom:6px;line-height:1.6;cursor:pointer;" data-date="' + escapeHtml(p.date) + '">' + escapeHtml(p.date) + ' · ' + escapeHtml((p.content||'').substring(0,60)) + '...</div>';
                }).join('');
              /** @type {NodeListOf<HTMLElement>} */ (otd.querySelectorAll('.tl-clickable')).forEach(function(el) {
                el.addEventListener('click', function() { openDiaryModal(el.dataset.date); });
              });
            }
          }
        } catch(e) { addDebugLog('info', '去年今日', '加载失败'); }
      })();
    }
  } catch(e) {
    if (reset) {
      results.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">加载失败</div>';
    }
  }
  } finally {
    _diaryLoading = false;
  }
}


// ── Diary Modal ──

var diaryModalData = null;
var diaryActivePerspective = 'ai';

function openDiaryModal(date) {
  if (!date) return;
  diaryModalData = null;
  diaryActivePerspective = 'ai';
  var modal = document.getElementById('diary-modal');
  var dateEl = document.getElementById('diaryDate');
  var body = document.getElementById('diaryBody');
  var tabs = document.querySelectorAll('.diary-tab');

  // Build header with prev/next nav
  var idx = diaryAllDates.indexOf(date);
  var prevDate = idx > 0 ? diaryAllDates[idx - 1] : null;
  var nextDate = idx >= 0 && idx < diaryAllDates.length - 1 ? diaryAllDates[idx + 1] : null;

  dateEl.innerHTML = (prevDate ? '<button class="diary-nav-btn" id="diaryPrevBtn"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg></button>' : '<span class="diary-nav-spacer"></span>') +
    '<span class="diary-date-text">' + date + '</span>' +
    (nextDate ? '<button class="diary-nav-btn" id="diaryNextBtn"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg></button>' : '<span class="diary-nav-spacer"></span>');

  body.innerHTML = '<div class="diary-placeholder"><img src="/icons/book-open.svg" class="svg-icon" alt=""> 加载日记内容...</div>';

  // Reset tabs
  tabs.forEach(function(t) { t.classList.remove('active'); });
  var aiTab = document.querySelector('.diary-tab[data-perspective="ai"]');
  if (aiTab) aiTab.classList.add('active');

  modal.classList.add('open');

  // Use event delegation on the date header to avoid per-instance listener leaks
  var dateHeader = dateEl;
  if (dateHeader._navHandler) dateHeader.removeEventListener('click', dateHeader._navHandler);
  dateHeader._navHandler = function(e) {
    var btn = /** @type {HTMLElement} */ (e.target).closest('.diary-nav-btn');
    if (!btn) return;
    e.stopPropagation();
    var targetDate = btn.id === 'diaryPrevBtn' ? prevDate : nextDate;
    if (targetDate) openDiaryModal(targetDate);
  };
  dateHeader.addEventListener('click', dateHeader._navHandler);

  // Fetch full entry
  fetch('/api/diary/' + date)
    .then(function(r) { return r.json(); })
    .then(function(entry) {
      if (entry.error) {
        body.innerHTML = '<div class="diary-empty-state"><img src="/icons/book-open.svg" class="empty-state-icon" alt=""><br>该日期的日记尚未生成</div>';
        return;
      }
      diaryModalData = entry;
      renderDiaryPerspective('ai');

      // Show user tab
      var userTab = /** @type {HTMLElement} */ (document.querySelector('.diary-tab[data-perspective="user"]'));
      if (userTab) {
        userTab.style.display = '';
      }
    })
    .catch(function() {
      body.innerHTML = '<div class="diary-empty-state">❌<br>加载失败</div>';
    });
}

function renderDiaryPerspective(perspective) {
  var body = document.getElementById('diaryBody');
  if (!diaryModalData) {
    body.innerHTML = '<div class="diary-placeholder"><img src="/icons/book-open.svg" class="svg-icon" alt=""> 加载日记内容...</div>';
    return;
  }

  if (perspective === 'ai') {
    var mood = diaryModalData.mood_emoji || extractMoodEmoji(diaryModalData.content);
    var content = diaryModalData.content || '今天什么也没发生... ✨';
    body.innerHTML = '<div class="diary-mood">' + mood + '</div><div>' + escapeHtml(content).replace(/\n/g, '<br>') + '</div>';
  } else if (perspective === 'user') {
    if (diaryModalData.has_user_diary && diaryModalData.user_content) {
      var uMood = diaryModalData.user_mood_emoji || '';
      body.innerHTML = (uMood ? '<div class="diary-mood">' + uMood + '</div>' : '') + '<div>' + escapeHtml(diaryModalData.user_content).replace(/\n/g, '<br>') + '</div>';
    } else {
      body.innerHTML = '<div class="diary-empty-state"><img src="/icons/user-pen.svg" class="empty-state-icon" alt=""><br>今天没有值得记录的对话<br><span style="font-size:0.65rem;color:#4a4a6a;">有实质内容的聊天才会被记录</span></div>';
    }
  }
}

// Tab switching
document.querySelectorAll('.diary-tab').forEach(/** @param {HTMLElement} tab */ function(tab) {
  tab.addEventListener('click', function() {
    var perspective = tab.dataset.perspective;
    if (perspective === diaryActivePerspective) return;
    diaryActivePerspective = perspective;
    document.querySelectorAll('.diary-tab').forEach(/** @param {HTMLElement} t */ function(t) { t.classList.remove('active'); });
    tab.classList.add('active');
    renderDiaryPerspective(perspective);
  });
});

// Close modal
document.getElementById('diaryClose').addEventListener('click', closeDiaryModal);
document.getElementById('diaryOverlay').addEventListener('click', closeDiaryModal);

function closeDiaryModal() {
  document.getElementById('diary-modal').classList.remove('open');
  diaryModalData = null;
}

// Keyboard close
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    var modal = document.getElementById('diary-modal');
    if (modal.classList.contains('open')) closeDiaryModal();
  }
});

async function loadNewsContent() {
  auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#6a6a8a;">加载新闻中...</div>';
  try {
    const resp = await fetch('/api/news');
    const news = await resp.json();
    if (!Array.isArray(news) || news.length === 0) {
      auxContent.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#6a6a8a;line-height:2;"><img src="/icons/newspaper.svg" class="empty-state-icon" alt=""><br>还没有新闻<br><button id="fetchNewsBtn" style="margin-top:12px;background:var(--accent);color:#fff;border:none;padding:8px 20px;border-radius:16px;cursor:pointer;font-family:inherit;">立即拉取</button></div>';
      const btn = /** @type {HTMLButtonElement} */ (document.getElementById('fetchNewsBtn'));
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
    auxContent.querySelectorAll('.news-card').forEach(/** @param {HTMLElement} card */ card => {
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

  topicBubbles.classList.remove('visible');
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
            clearInterval(thinkingTimer);
            setSequence(evt.emotions, '');
            if (evt.affect) updateMoodFromAffect(evt.affect);
            else updateMoodFromEmotion(evt.label || '');
            if (evt.color_fields && Array.isArray(evt.color_fields)) {
              colorFieldsTarget = evt.color_fields.map(function(f) {
                return {
                  color: f.color,
                  cx: f.cx || 0.5, cy: f.cy || 0.5,
                  radius: f.radius || 0.5,
                  blend: f.blend || 'soft-light',
                  opacity: f.opacity != null ? f.opacity : 0.9,
                  blur: f.blur || 0,
                  pulse: f.pulse || null,
                  drift: f.drift || null
                };
              });
            }
          } else if (evt.type === 'pixel_sprites') {
            if (evt.sprites && Array.isArray(evt.sprites) && typeof spawnPixelSprites === 'function') {
              spawnPixelSprites(evt.sprites);
            }
          } else if (evt.type === 'thinking') {
            dlgBody.innerHTML = '<span class="thinking-indicator">思考中<span class="thinking-dots">...</span></span>';
            var dotsEl = dlgBody.querySelector('.thinking-dots');
            var dotFrames = ['', '.', '..', '...'];
            var dotIdx = 0;
            clearInterval(thinkingTimer);
            thinkingTimer = setInterval(function() {
              dotIdx = (dotIdx + 1) % 4;
              if (dotsEl) dotsEl.textContent = dotFrames[dotIdx];
            }, 400);
          } else if (evt.type === 'text') {
            clearInterval(thinkingTimer);
            streamedReply += evt.text;
            playTypingSound();
            dlgBody.innerHTML = escapeHtml(streamedReply) + '<span class="cursor-blink"></span>';
          } else if (evt.type === 'error') {
            clearInterval(thinkingTimer);
            streamedReply = evt.text;
            dlgBody.innerHTML = escapeHtml(streamedReply);
            addDebugLog('error', 'LLM调用失败', evt.text, 'DeepSeek API 可能超时或返回异常，检查 API Key 和网络连接');
          } else if (evt.type === 'done') {
            clearInterval(thinkingTimer);
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
    clearInterval(thinkingTimer);
    dlgText = '嗯...出了点问题 😢';
    dlgBody.innerHTML = dlgText;
    dlgTyping = false;
    addDebugLog('error', '请求失败', err.message, '检查容器是否运行、网络是否正常、DeepSeek API 是否可达');
  } finally {
    clearInterval(thinkingTimer);
    pending = false; sendBtn.disabled = false; input.focus();
    if (streamedReply) {
      dlgText = streamedReply;
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
    topicBubbles.querySelectorAll('.topic-bubble').forEach(/** @param {HTMLElement} b */ b => {
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

  saveVisualState();

  requestAnimationFrame(loop);
}

// ═══════════════════════════════════════════
// Init
// ═══════════════════════════════════════════
initStarfield();
initMemoryStars();
recomputeFaceLayout();
initSparkleParticles();
// Restore visual state from before refresh (mood, face, atmosphere)
var restored = false;
if (typeof loadVisualState === 'function') {
  restored = loadVisualState();
}
// Initial face pixel computation for convergence targets (skip if restored)
if (!restored) {
  curParams = { eye_curve:0, eye_open:0.5, eye_pupil:0, eye_wink:0, eye_tension:0, iris_size:0.5, mouth_curve:0, mouth_open:0, mouth_width:0.8, mouth_asym:0, lip_pout:0, lip_stretch:0, lip_bite:0, jaw_drop:0, tongue_out:0, sparkle:0.5, brow_angle:0, brow_height:0.5, brow_asym:0, nose_wrinkle:0, cheek_raise:0, cheek_puff:0, blush:0.15, head_tilt:0, tear:0, sweat_drop:0, vein_pop:0 };
  tgtParams = { ...curParams };
}
	// Restore dialog bubble if we were in chat mode before refresh
	if (restored && dlgText && state === STATE.CHAT) {
	  var fcX = canvas.width / 2, fcY = canvas.height / 2, fcR = 29 * faceCS;
	  var isNr = window.innerWidth < 600, dW = isNr ? 260 : 340;
	  var dX = fcX + fcR + 20, dY = fcY - 60;
	  if (dX + dW > window.innerWidth - 20) dX = Math.max(10, fcX - fcR - dW);
	  if (isNr && dX < 10) { dX = (window.innerWidth - dW) / 2; dY = fcY + fcR + 30; }
	  if (dY < 60) dY = fcY + fcR + 20;
	  if (dY + 120 > window.innerHeight - 20) dY = fcY - 120;
	  dialog.style.left = dX + 'px';
	  dialog.style.top = dY + 'px';
	  dialog.classList.add('visible');
	  dlgBody.innerHTML = formatDialogText(dlgText) + '<span class="dlg-arrow">▼</span>';
	  dlgDisplayed = dlgText.length;
	}
requestAnimationFrame(loop);

// ═══════════════════════════════════════════
// Settings panel (LLM provider config)
// ═══════════════════════════════════════════
settingsOverlay.addEventListener('click', closeSettings);
settingsClose.addEventListener('click', closeSettings);

/** @type {Object<string, {name:string, base_url:string, default_model:string, models:string[]}>} */
var _presets = null;

providerSelect.addEventListener('change', function () {
  if (!_presets) return;
  var p = _presets[this.value];
  if (!p) return;
  baseUrlInput.value = p.base_url || '';
  modelInput.value = p.default_model || '';
  if (p.models && p.models.length > 0) {
    modelHint.textContent = '可选: ' + p.models.join(', ');
    modelHint.style.display = 'block';
  } else {
    modelHint.style.display = 'none';
  }
  if (this.value === 'custom') {
    baseUrlInput.placeholder = 'https://your-api.com/v1';
    modelInput.placeholder = 'your-model-name';
    modelHint.textContent = '输入任意 OpenAI 兼容接口地址和模型名';
    modelHint.style.display = 'block';
  }
});

settingsSave.addEventListener('click', async function () {
  var provider = providerSelect.value;
  var base_url = baseUrlInput.value.trim();
  var model = modelInput.value.trim();
  var api_key = apiKeyInput.value.trim();

  if (!api_key) { showStatus('请输入 API Key', 'error'); return; }
  if (!base_url) { showStatus('请输入 API Base URL', 'error'); return; }
  if (!model) { showStatus('请输入模型名称', 'error'); return; }

  try {
    var resp = await fetch('/api/config/llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: provider, base_url: base_url, model: model, api_key: api_key }),
    });
    if (resp.ok) {
      showStatus('✅ 配置已保存并生效', 'success');
      addDebugLog('info', '设置', 'LLM 配置已更新', provider + ' / ' + model);
    } else {
      showStatus('保存失败，请重试', 'error');
    }
  } catch (e) {
    showStatus('网络错误：' + e.message, 'error');
  }
});

settingsClear.addEventListener('click', async function () {
  try {
    await fetch('/api/config/llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: 'deepseek', base_url: '', model: '', api_key: '' }),
    });
    await loadSettings();
    showStatus('已恢复默认 DeepSeek 配置', 'success');
  } catch (e) {
    showStatus('网络错误：' + e.message, 'error');
  }
});

async function loadSettings() {
  try {
    var resp = await fetch('/api/config/llm');
    var data = await resp.json();
    _presets = data.presets || {};

    // Build provider dropdown
    providerSelect.innerHTML = '';
    var keys = Object.keys(_presets);
    for (var i = 0; i < keys.length; i++) {
      var p = _presets[keys[i]];
      var opt = document.createElement('option');
      opt.value = keys[i];
      opt.textContent = p.name;
      if (keys[i] === (data.provider || 'deepseek')) opt.selected = true;
      providerSelect.appendChild(opt);
    }

    baseUrlInput.value = data.base_url || '';
    modelInput.value = data.model || '';
    apiKeyInput.value = data.api_key || '';
    providerSelect.dispatchEvent(new Event('change'));
  } catch (e) {
    // Offline or server not ready — keep defaults
  }
}

async function openSettings() {
  settingsStatus.textContent = '';
  settingsStatus.className = 'settings-status';
  settingsModal.classList.add('open');
  await loadSettings();
}

function closeSettings() {
  settingsModal.classList.remove('open');
}

function showStatus(msg, type) {
  settingsStatus.textContent = msg;
  settingsStatus.className = 'settings-status ' + type;
  setTimeout(function () {
    settingsStatus.textContent = '';
    settingsStatus.className = 'settings-status';
  }, 3000);
}

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
