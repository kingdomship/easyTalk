// @ts-check
// ═══════════════════════════════════════════════════════════════════════
// mood-panel.js — Mood tab: compact checkin → overview (radar+insight)
//                 → mini timeline → calendar
// ═══════════════════════════════════════════════════════════════════════

// ── State ──────────────────────────────────────────────────────────
var moodCalendarYear = new Date().getFullYear();
var moodCalendarMonth = new Date().getMonth(); // 0-based
var moodAllDates = []; // cached diary dates
var moodCheckinDates = {}; // {dateStr: [{emoji, intensity}]}
var moodRadarDateIdx = -1; // index into moodRadarData, -1 = latest
var moodRadarData = []; // cached affect_history array
var moodCheckinEmoji = '';
var moodCheckinIntensity = 5;

function moodDateKey(d) { return d.date || d; }

function extractMoodEmoji(text) {
  var emojiRegex = /[\p{Emoji_Presentation}\p{Extended_Pictographic}]/u;
  var match = text.match(emojiRegex);
  return match ? match[0] : '✨';
}

// ═══════════════════════════════════════════════════════════════════════
// Main entry point
// ═══════════════════════════════════════════════════════════════════════

async function loadMoodContent() {
  auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#6a6a8a;">加载情绪数据...</div>';
  try {
    var now = new Date();
    moodCalendarYear = now.getFullYear();
    moodCalendarMonth = now.getMonth();

    var _a = await Promise.all([
      fetch('/api/mood/calendar?days=366').then(function(r) { return r.json(); }),
      fetch('/api/mood/timeline?days=7').then(function(r) { return r.json(); }),
      fetch('/api/mood/affect-history?days=30').then(function(r) { return r.json(); }),
      fetch('/api/mood/checkins?days=366').then(function(r) { return r.json(); }),
    ]);
    var calData = _a[0], tlData = _a[1], affData = _a[2], checkinsData = _a[3];

    // Build checkin date index
    moodCheckinDates = {};
    (checkinsData || []).forEach(function(c) {
      var d = (c.date || '').slice(0, 10);
      if (!moodCheckinDates[d]) moodCheckinDates[d] = [];
      moodCheckinDates[d].push({ emoji: c.mood_emoji, intensity: c.intensity || 5 });
    });

    if (!calData.length && !checkinsData.length) {
      auxContent.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#6a6a8a;"><img src="/icons/smile-plus.svg" class="empty-state-icon" alt=""><br>还没有情绪数据<br><span style="font-size:0.65rem;">开始聊天或手动记录情绪吧</span></div>';
      return;
    }
    moodAllDates = calData;

    // Cache radar data, default to latest day
    moodRadarData = affData || [];
    moodRadarDateIdx = moodRadarData.length > 0 ? moodRadarData.length - 1 : -1;

    // Assemble page sections
    var htmlParts = [];

    // 1. Compact checkin (always visible)
    htmlParts.push(renderMoodCheckin());

    // 2. Radar card
    htmlParts.push(renderMoodRadarCard());

    // 3. Weekly overview (insight + timeline merged)
    htmlParts.push(renderMoodWeeklyOverview(tlData));

    // 4. Calendar
    htmlParts.push(renderMoodCalendarHTML());

    auxContent.innerHTML = htmlParts.join('');

    // Defer SVG radar — wait for DOM layout
    if (moodRadarData.length > 0) {
      setTimeout(function() { updateSvgRadar(); }, 50);
    }

    // Load insight async
    loadMoodInsight();
  } catch(e) {
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">加载失败: ' + escapeHtml(e.message) + '</div>';
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 1. Compact self-checkin panel
// ═══════════════════════════════════════════════════════════════════════

function renderMoodCheckin() {
  var emojis = ['😊', '😢', '😡', '😰', '😌', '🥳', '😴', '🤔'];
  var tags = ['焦虑', '工作', '关系', '健康', '家庭', '成长', '休闲', '其他'];

  var html = '<div class="mood-card mood-checkin-card mood-checkin-compact">';
  html += '<div class="mood-checkin-title">🎯 今日心情</div>';

  // Emoji selector — 36px, 8 in a row
  html += '<div class="mood-emoji-row">';
  emojis.forEach(function(e) {
    html += '<button class="mood-emoji-btn" data-emoji="' + e + '">' + e + '</button>';
  });
  html += '</div>';

  // Inline controls (hidden until emoji selected)
  html += '<div class="mood-checkin-controls" id="moodCheckinControls" style="display:none">';
  // Intensity slider + value + tags toggle + submit button — all inline
  html += '<div class="mood-checkin-inline">';
  html += '<input type="range" class="mood-intensity-slider" id="moodIntensitySlider" min="1" max="10" value="5" step="1">';
  html += '<span class="mood-intensity-val" id="moodIntensityVal">5</span>';
  html += '<button class="mood-tags-toggle" id="moodTagsToggle" type="button">标签 ▾</button>';
  html += '<button class="mood-checkin-submit" id="moodCheckinSubmit">记录</button>';
  html += '</div>';

  // Collapsible tags panel (CSS max-height transition)
  html += '<div class="mood-tags-panel" id="moodTagsPanel">';
  tags.forEach(function(t) {
    html += '<button class="mood-tag-btn" data-tag="' + t + '">' + t + '</button>';
  });
  html += '</div>';

  html += '<div class="mood-checkin-msg" id="moodCheckinMsg"></div>';
  html += '</div>'; // .mood-checkin-controls

  html += '</div>'; // .mood-card

  setTimeout(bindMoodCheckinEvents, 50);
  return html;
}

function bindMoodCheckinEvents() {
  var slider = /** @type {HTMLInputElement|null} */ (document.getElementById('moodIntensitySlider'));
  var valEl = document.getElementById('moodIntensityVal');
  var controls = document.getElementById('moodCheckinControls');
  var submit = /** @type {HTMLButtonElement|null} */ (document.getElementById('moodCheckinSubmit'));
  var msgEl = document.getElementById('moodCheckinMsg');
  var tagsToggle = document.getElementById('moodTagsToggle');
  var tagsPanel = document.getElementById('moodTagsPanel');

  // Emoji buttons
  document.querySelectorAll('.mood-emoji-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.mood-emoji-btn').forEach(function(b) { b.classList.remove('selected'); });
      btn.classList.add('selected');
      moodCheckinEmoji = btn.dataset.emoji || '';
      if (controls) controls.style.display = '';
      if (msgEl) msgEl.textContent = '';
    });
  });

  // Intensity slider
  if (slider && valEl) {
    slider.addEventListener('input', function() {
      moodCheckinIntensity = parseInt(slider.value);
      valEl.textContent = String(moodCheckinIntensity);
    });
  }

  // Tags toggle (CSS max-height transition)
  if (tagsToggle && tagsPanel) {
    tagsToggle.addEventListener('click', function() {
      var isOpen = tagsPanel.classList.toggle('open');
      tagsToggle.textContent = isOpen ? '标签 ▴' : '标签 ▾';
    });
  }

  // Tag buttons (multi-select toggle)
  document.querySelectorAll('.mood-tag-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      btn.classList.toggle('selected');
    });
  });

  // Submit
  if (submit) {
    submit.addEventListener('click', async function() {
      if (!moodCheckinEmoji) return;
      var selectedTags = [];
      document.querySelectorAll('.mood-tag-btn.selected').forEach(function(b) {
        selectedTags.push(b.dataset.tag || '');
      });
      submit.disabled = true;
      submit.textContent = '...';
      try {
        var resp = await fetch('/api/mood/checkin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mood_emoji: moodCheckinEmoji,
            intensity: moodCheckinIntensity,
            tags: selectedTags,
          }),
        });
        if (!resp.ok) throw new Error('记录失败');
        if (msgEl) { msgEl.textContent = '✓ 已记录'; msgEl.className = 'mood-checkin-msg success'; }
        // Refresh insight + calendar
        loadMoodInsight();
        setTimeout(async function() {
          var _a = await Promise.all([
            fetch('/api/mood/calendar?days=366').then(function(r) { return r.json(); }),
            fetch('/api/mood/checkins?days=366').then(function(r) { return r.json(); }),
          ]);
          moodAllDates = _a[0];
          var ckData = _a[1];
          moodCheckinDates = {};
          (ckData || []).forEach(function(c) {
            var d = (c.date || '').slice(0, 10);
            if (!moodCheckinDates[d]) moodCheckinDates[d] = [];
            moodCheckinDates[d].push({ emoji: c.mood_emoji, intensity: c.intensity || 5 });
          });
          renderMoodCalendar();
        }, 400);
      } catch(e) {
        if (msgEl) { msgEl.textContent = '失败: ' + e.message; msgEl.className = 'mood-checkin-msg error'; }
      } finally {
        submit.disabled = false;
        submit.textContent = '记录';
        setTimeout(function() {
          if (msgEl) { msgEl.textContent = ''; msgEl.className = 'mood-checkin-msg'; }
        }, 3000);
      }
    });
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 2. Overview: Radar + Insight (single card, stacked vertically)
// ═══════════════════════════════════════════════════════════════════════

function renderMoodRadarCard() {
  var html = '<div class="mood-card mood-radar-card">';
  html += '<div class="mood-card-title">📊 Panksepp 六维</div>';
  html += '<svg id="moodRadarSvg" class="mood-radar-svg" viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg"></svg>';
  html += '<div class="mood-radar-nav">';
  html += '<button class="mood-radar-nav-btn" id="moodRadarPrev" title="前一天">◀</button>';
  html += '<span class="mood-radar-date" id="moodRadarDate">—</span>';
  html += '<button class="mood-radar-nav-btn" id="moodRadarNext" title="后一天">▶</button>';
  html += '</div>';
  html += '</div>'; // .mood-card
  setTimeout(bindMoodRadarEvents, 50);
  return html;
}

function bindMoodRadarEvents() {
  var prevBtn = document.getElementById('moodRadarPrev');
  var nextBtn = document.getElementById('moodRadarNext');
  if (prevBtn) prevBtn.addEventListener('click', function() { moodRadarShift(-1); });
  if (nextBtn) nextBtn.addEventListener('click', function() { moodRadarShift(1); });
  updateRadarDateLabel();
}

function moodRadarShift(delta) {
  if (moodRadarData.length === 0) return;
  var newIdx = moodRadarDateIdx + delta;
  if (newIdx < 0 || newIdx >= moodRadarData.length) return;
  moodRadarDateIdx = newIdx;
  updateRadarDateLabel();
  updateSvgRadar();
}

function updateRadarDateLabel() {
  var label = document.getElementById('moodRadarDate');
  if (!label) return;
  if (moodRadarData.length === 0 || moodRadarDateIdx < 0) {
    label.textContent = '—';
    return;
  }
  var d = moodRadarData[moodRadarDateIdx];
  label.textContent = (d.date || '').slice(5); // MM-DD
  var prevBtn = /** @type {HTMLButtonElement|null} */ (document.getElementById('moodRadarPrev'));
  var nextBtn = /** @type {HTMLButtonElement|null} */ (document.getElementById('moodRadarNext'));
  if (prevBtn) prevBtn.disabled = moodRadarDateIdx <= 0;
  if (nextBtn) nextBtn.disabled = moodRadarDateIdx >= moodRadarData.length - 1;
}

// ═══════════════════════════════════════════════════════════════════════
// 3. Panksepp 6-D Radar — SVG, viewBox=300×300, cx=150 cy=150 r=100
// ═══════════════════════════════════════════════════════════════════════

var RADAR_DIMS = [
  { key: 'seeking', label: '探索', color: 'rgb(100,180,255)' },
  { key: 'play', label: '嬉戏', color: 'rgb(255,200,100)' },
  { key: 'care', label: '关怀', color: 'rgb(255,130,160)' },
  { key: 'fear', label: '恐惧', color: 'rgb(160,120,200)' },
  { key: 'rage', label: '愤怒', color: 'rgb(255,100,100)' },
  { key: 'panic', label: '悲伤', color: 'rgb(130,160,210)' },
];
var RADAR_CX = 150, RADAR_CY = 150, RADAR_R = 100;
var RADAR_N = RADAR_DIMS.length;

function radarPoint(distance, i) {
  var angle = (Math.PI * 2 / RADAR_N) * i - Math.PI / 2;
  var x = (RADAR_CX + distance * Math.cos(angle)).toFixed(1);
  var y = (RADAR_CY + distance * Math.sin(angle)).toFixed(1);
  return { x: x, y: y, angle: angle };
}

function buildSvgRadar(data) {
  var parts = [];

  // 3 concentric grid rings
  for (var level = 1; level <= 3; level++) {
    var pts = [];
    for (var i = 0; i < RADAR_N; i++) {
      var p = radarPoint((RADAR_R / 3) * level, i);
      pts.push(p.x + ',' + p.y);
    }
    var alpha = (0.06 + level * 0.05).toFixed(2);
    parts.push('<polygon points="' + pts.join(' ') + '" fill="none" stroke="rgba(124,131,255,' + alpha + '" stroke-width="1"/>');
  }

  // 6 axis lines
  for (var i2 = 0; i2 < RADAR_N; i2++) {
    var ep = radarPoint(RADAR_R, i2);
    parts.push('<line x1="' + RADAR_CX + '" y1="' + RADAR_CY + '" x2="' + ep.x + '" y2="' + ep.y + '" stroke="rgba(124,131,255,0.1)" stroke-width="1"/>');
  }

  // Data polygon
  var dp = [];
  for (var i3 = 0; i3 < RADAR_N; i3++) {
    var val = Math.max(0.03, Math.min(1, data[RADAR_DIMS[i3].key] || 0));
    var dp2 = radarPoint(val * RADAR_R, i3);
    dp.push(dp2.x + ',' + dp2.y);
  }
  parts.push('<polygon points="' + dp.join(' ') + '" fill="rgba(124,131,255,0.15)" stroke="rgba(124,131,255,0.45)" stroke-width="1.5"/>');

  // Dots + labels
  for (var i4 = 0; i4 < RADAR_N; i4++) {
    var val4 = Math.max(0.03, Math.min(1, data[RADAR_DIMS[i4].key] || 0));
    var dotP = radarPoint(val4 * RADAR_R, i4);
    parts.push('<circle cx="' + dotP.x + '" cy="' + dotP.y + '" r="3" fill="' + RADAR_DIMS[i4].color + '" opacity="0.85"/>');

    var lblP = radarPoint(RADAR_R + 18, i4);
    var cosA = Math.cos(lblP.angle), sinA = Math.sin(lblP.angle);
    var anchor = Math.abs(cosA) < 0.15 ? 'middle' : (cosA > 0 ? 'start' : 'end');
    var baseline = Math.abs(sinA) < 0.15 ? 'central' : (sinA < 0 ? 'auto' : 'hanging');
    parts.push('<text x="' + lblP.x + '" y="' + lblP.y + '" text-anchor="' + anchor + '" dominant-baseline="' + baseline + '" fill="#9090b8" font-size="10" font-family="sans-serif">' + RADAR_DIMS[i4].label + '</text>');
  }

  return parts.join('');
}

function updateSvgRadar() {
  var svg = /** @type {SVGElement|null} */ (document.getElementById('moodRadarSvg'));
  if (!svg || moodRadarData.length === 0 || moodRadarDateIdx < 0) return;
  svg.innerHTML = buildSvgRadar(moodRadarData[moodRadarDateIdx]);
}

// ═══════════════════════════════════════════════════════════════════════
// 4. Weekly overview card (insight + compact timeline merged)
// ═══════════════════════════════════════════════════════════════════════

function renderMoodWeeklyOverview(tlData) {
  var html = '<div class="mood-card mood-weekly-overview">';
  html += '<div class="mood-card-title">📈 本周概览</div>';
  html += '<div class="mood-weekly-grid">';
  // Left: insight placeholder (loaded async)
  html += '<div class="weekly-insight" id="moodWeeklyInsight">';
  html += '<div class="mood-insight-loading">加载洞察中...</div>';
  html += '</div>';
  // Right: compact sparkline (if data)
  html += '<div class="weekly-sparkline" id="moodWeeklySparkline">';
  if (tlData && tlData.length) {
    html += renderCompactTimeline(tlData);
  }
  html += '</div>';
  html += '</div></div>';
  return html;
}

function renderCompactTimeline(data) {
  var emojiMap = {
    'happy': '😊', 'sad': '😢', 'angry': '😠', 'fear': '😨',
    'surprise': '😲', 'disgust': '😖', 'neutral': '😐',
    'sheepish': '😳', 'playful': '😜', 'love': '🥰',
    'excited': '🤩', 'tired': '😴', 'anxious': '😰',
    'grateful': '🙏', 'hopeful': '🌟', 'lonely': '💧',
    'proud': '✨', 'guilty': '😞', 'jealous': '😒',
    'bored': '😑', 'confident': '💪', 'confused': '😕',
    'calm': '😌', 'nostalgic': '🥺', 'determined': '🔥',
    'embarrassed': '😳', 'hopeless': '💔', 'relieved': '😮‍💨',
    'satisfied': '😌', 'curious': '🤔', 'warm': '💕'
  };
  function toEmoji(label) {
    if (!label) return '✨';
    return emojiMap[label] || '✨';
  }

  var sorted = data.slice().sort(function(a, b) { return a.date.localeCompare(b.date); });
  if (sorted.length === 0) return '';

  var maxTotal = 1;
  sorted.forEach(function(d) { if (d.total > maxTotal) maxTotal = d.total; });

  var w = 140, h = 60;
  var padL = 4, padR = 4, padT = 10, padB = 14;
  var plotW = w - padL - padR;
  var plotH = h - padT - padB;
  var cy = padT + plotH / 2;

  var svg = '<svg class="mood-timeline-svg" viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg">';
  // Baseline
  svg += '<line x1="' + padL + '" y1="' + cy + '" x2="' + (w - padR) + '" y2="' + cy + '" stroke="rgba(124,131,255,0.06)" stroke-width="1"/>';

  var points = [];
  sorted.forEach(function(d, i) {
    var x = padL + (sorted.length === 1 ? plotW / 2 : (i / (sorted.length - 1)) * plotW);
    var r = 1.5 + (d.total / maxTotal) * 5;
    var emoji = toEmoji(d.dominant);
    points.push({ x: x, y: cy, r: r, emoji: emoji, date: d.date });
  });

  // Connecting line
  if (points.length > 1) {
    var lineD = points.map(function(p, i) { return (i === 0 ? 'M' : 'L') + p.x + ',' + p.y; }).join(' ');
    svg += '<path d="' + lineD + '" fill="none" stroke="rgba(124,131,255,0.12)" stroke-width="1" stroke-dasharray="2,2"/>';
  }

  // Dots + emoji
  points.forEach(function(p) {
    var hasCheckin = moodCheckinDates[p.date] && moodCheckinDates[p.date].length > 0;
    svg += '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + p.r + '" fill="' + (hasCheckin ? 'rgba(180,160,255,0.35)' : 'rgba(124,131,255,0.1)') + '" stroke="rgba(124,131,255,0.25)" stroke-width="' + (hasCheckin ? '1' : '0.6') + '"/>';
    svg += '<text x="' + p.x + '" y="' + (p.y + 2) + '" text-anchor="middle" font-size="' + Math.round(6 + p.r * 0.3) + '" fill="#c8c8e0">' + p.emoji + '</text>';
  });

  // Date labels (sparse for compact space)
  if (sorted.length <= 7) {
    sorted.forEach(function(d, i) {
      var x = padL + (sorted.length === 1 ? plotW / 2 : (i / (sorted.length - 1)) * plotW);
      if (sorted.length > 4 && i % 2 !== 0 && i !== sorted.length - 1) return;
      var parts = d.date.split('-');
      var shortDate = parts[1] + '/' + parts[2];
      svg += '<text x="' + x + '" y="' + (h - 2) + '" text-anchor="middle" font-size="7" fill="#5a5a8a" font-family="\'Courier New\', monospace">' + shortDate + '</text>';
    });
  }

  svg += '</svg>';
  return svg;
}

// ═══════════════════════════════════════════════════════════════════════
// 4b. Weekly insight (loaded async into weekly overview left column)
// ═══════════════════════════════════════════════════════════════════════

async function loadMoodInsight() {
  var insightDiv = document.getElementById('moodWeeklyInsight');
  if (!insightDiv) return;
  try {
    var resp = await fetch('/api/mood/insight?days=7');
    var data = await resp.json();
    insightDiv.innerHTML =
      '<div class="mood-insight-body">' +
        '<div class="mood-insight-row"><span class="mood-insight-label">主导</span><span class="mood-insight-value">' + escapeHtml(data.dominant_mood) + '</span></div>' +
        '<div class="mood-insight-row"><span class="mood-insight-label">趋势</span><span class="mood-insight-value">' + escapeHtml(data.trend) + '</span></div>' +
        '<div class="mood-insight-suggestion">' + escapeHtml(data.suggestion) + '</div>' +
        '<div class="mood-insight-summary">' + escapeHtml(data.summary) + '</div>' +
      '</div>';
  } catch(e) {
    insightDiv.innerHTML =
      '<div class="mood-insight-body" style="color:#5a5a7a;">洞察暂不可用</div>';
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 5. Monthly calendar
// ═══════════════════════════════════════════════════════════════════════

function renderMoodCalendarHTML() {
  var byDate = {};
  moodAllDates.forEach(function(d) { byDate[d.date] = d; });

  var firstDay = new Date(moodCalendarYear, moodCalendarMonth, 1);
  var lastDay = new Date(moodCalendarYear, moodCalendarMonth + 1, 0);
  var startDow = firstDay.getDay();
  var daysInMonth = lastDay.getDate();
  var todayStr = new Date().toISOString().slice(0, 10);

  // Year pills
  var nowYear = new Date().getFullYear();
  var yrHtml = '<div class="yr-pill-row" id="moodYrRow">';
  for (var y = nowYear; y >= 2026; y--) {
    var cls = 'yr-pill';
    if (y === moodCalendarYear) cls += ' active';
    if (y === nowYear) cls += ' current';
    yrHtml += '<button class="' + cls + '" onclick="moodPickYear(' + y + ')">' + y + '</button>';
  }
  yrHtml += '</div>';

  var html = '<div class="mood-card mood-calendar-section">';

  // Month nav
  html += '<div class="mood-month-nav">';
  html += '<button class="mood-nav-btn" onclick="moodPrevMonth()"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg></button>';
  html += '<span class="mood-month-label">' + moodCalendarYear + '年 ' + (moodCalendarMonth + 1) + '月</span>';
  html += '<button class="mood-nav-btn" onclick="moodNextMonth()"><svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg></button>';
  html += '</div>';
  html += yrHtml;

  // Day-of-week header
  html += '<div class="mood-weekdays">' + ['日','一','二','三','四','五','六'].map(function(w) {
    return '<span class="mood-dow">' + w + '</span>';
  }).join('') + '</div>';

  // Calendar grid
  html += '<div class="mood-cal-grid">';
  for (var i = 0; i < startDow; i++) {
    html += '<div class="mood-cal-cell empty"></div>';
  }
  for (var d = 1; d <= daysInMonth; d++) {
    var ds = moodCalendarYear + '-' + String(moodCalendarMonth + 1).padStart(2,'0') + '-' + String(d).padStart(2,'0');
    var entry = byDate[ds];
    var checkins = moodCheckinDates[ds] || [];
    var cls = 'mood-cal-cell';
    var emoji = '';
    var title = ds;
    var onClick = '';

    var bgStyle = '';
    if (checkins.length > 0) {
      cls += ' has-checkin';
      var avgIntensity = checkins.reduce(function(s, c) { return s + c.intensity; }, 0) / checkins.length;
      var alpha = 0.08 + (avgIntensity / 10) * 0.2;
      bgStyle = 'background:rgba(180,160,255,' + alpha.toFixed(2) + ');';
      emoji = checkins[checkins.length - 1].emoji;
    }

    if (entry) {
      cls += ' has-data';
      if (!emoji) emoji = entry.mood_emoji || '✨';
      title = ds + ' · ' + entry.chat_count + '次对话';
      if (checkins.length) {
        title += ' · ' + checkins.length + '次自检';
      }
      if (entry.has_diary) {
        cls += ' clickable';
        onClick = ' onclick="openDiaryModal(\'' + ds + '\')"';
      }
    }
    if (ds === todayStr) cls += ' today';

    var checkinDot = '';
    if (checkins.length > 0) {
      checkinDot = '<span class="mood-cal-checkin-dot" title="' + checkins.length + '次自检"></span>';
    }

    html += '<div class="' + cls + '" title="' + title + '" style="' + bgStyle + '"' + onClick + '>' +
            '<span class="mood-cal-day">' + d + checkinDot + '</span>' +
            (emoji ? '<span class="mood-cal-emoji">' + emoji + '</span>' : '') +
            '</div>';
  }
  html += '</div>';

  // Emotion stats bar
  var emojiCount = {};
  moodAllDates.forEach(function(d2) {
    var em = d2.mood_emoji || '✨';
    emojiCount[em] = (emojiCount[em] || 0) + 1;
  });
  Object.values(moodCheckinDates).forEach(function(arr) {
    arr.forEach(function(c) {
      emojiCount[c.emoji] = (emojiCount[c.emoji] || 0) + 1;
    });
  });
  var sortedEmoji = Object.entries(emojiCount).sort(function(a, b) { return b[1] - a[1]; });
  if (sortedEmoji.length) {
    html += '<div class="mood-stats">';
    html += '<div class="mood-stats-label">情绪分布</div><div class="mood-stats-bar">';
    sortedEmoji.forEach(function(pair) {
      html += '<div class="mood-stat-item"><span>' + pair[0] + '</span><span class="mood-stat-count">' + pair[1] + '</span></div>';
    });
    html += '</div></div>';
  }

  html += '</div>'; // .mood-calendar-section
  return html;
}

function renderMoodCalendar() {
  var newCalHTML = renderMoodCalendarHTML();
  var existing = document.querySelector('.mood-calendar-section');
  if (existing) {
    existing.outerHTML = newCalHTML;
  }
}

// ── Calendar navigation ────────────────────────────────────────────

function moodPrevMonth() {
  var minYear = 2026;
  if (moodAllDates.length) {
    minYear = new Date(moodAllDates[0].date).getFullYear();
  }
  if (moodCalendarMonth === 0) {
    if (moodCalendarYear <= minYear) return;
    moodCalendarYear--; moodCalendarMonth = 11;
  } else { moodCalendarMonth--; }
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
