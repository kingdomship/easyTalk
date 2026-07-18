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
    // Fetch calendar + timeline + affect history in parallel
    var calResp = await fetch('/api/mood/calendar?days=366');
    var calData = await calResp.json();
    var tlResp = await fetch('/api/mood/timeline?days=7');
    var tlData = await tlResp.json();
    var affResp = await fetch('/api/mood/affect-history?days=7');
    var affData = await affResp.json();
    if (!calData.length) {
      auxContent.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#6a6a8a;"><img src="/icons/smile-plus.svg" class="empty-state-icon" alt=""><br>还没有情绪数据</div>';
      return;
    }
    moodAllDates = calData;
    // Render timeline + radar + calendar
    var htmlParts = [];
    if (tlData && tlData.length) {
      htmlParts.push(renderMoodTimeline(tlData));
    }
    if (affData && affData.length) {
      // Use latest day's data for radar
      var latestAff = affData[affData.length - 1];
      htmlParts.push(renderMoodRadar(latestAff));
    }
    htmlParts.push(renderMoodCalendarHTML());
    auxContent.innerHTML = htmlParts.join('');
  } catch(e) {
    auxContent.innerHTML = '<div style="text-align:center;padding:40px;color:#f44336;">加载失败</div>';
  }
}

function renderMoodCalendarHTML() {
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

  return html;
}

function renderMoodCalendar() {
  auxContent.innerHTML = renderMoodCalendarHTML();
}

// ── 7-day mood timeline SVG chart ──
/**
 * @param {Array<{date:string, total:number, dominant:string, labels:Object<string,number>}>} data
 * @returns {string} SVG HTML string
 */
function renderMoodTimeline(data) {
  // Map emotion labels to emoji
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

  // Sort dates ascending (oldest first)
  var sorted = data.slice().sort(function(a, b) { return a.date.localeCompare(b.date); });
  if (sorted.length === 0) return '';

  var maxTotal = 1;
  sorted.forEach(function(d) { if (d.total > maxTotal) maxTotal = d.total; });

  var w = 330, h = 110;
  var padL = 8, padR = 8, padT = 20, padB = 22;
  var plotW = w - padL - padR;
  var plotH = h - padT - padB;
  var cy = padT + plotH / 2;  // center Y for dots

  // Build SVG
  var svg = '<svg class="mood-timeline-svg" viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg">';
  // Subtle grid line
  svg += '<line x1="' + padL + '" y1="' + cy + '" x2="' + (w - padR) + '" y2="' + cy + '" stroke="rgba(124,131,255,0.08)" stroke-width="1"/>';

  // Compute dot positions
  var points = [];
  sorted.forEach(function(d, i) {
    var x = padL + (sorted.length === 1 ? plotW / 2 : (i / (sorted.length - 1)) * plotW);
    var r = 4 + (d.total / maxTotal) * 10; // radius 4-14
    var emoji = toEmoji(d.dominant);
    points.push({ x: x, y: cy, r: r, emoji: emoji, date: d.date, total: d.total, dominant: d.dominant });
  });

  // Connecting lines
  if (points.length > 1) {
    var lineD = points.map(function(p, i) { return (i === 0 ? 'M' : 'L') + p.x + ',' + p.y; }).join(' ');
    svg += '<path d="' + lineD + '" fill="none" stroke="rgba(124,131,255,0.18)" stroke-width="1.5" stroke-dasharray="3,3"/>';
  }

  // Dots + emoji + date labels
  var labelDates = [];
  points.forEach(function(p) {
    // Glow ring
    svg += '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + (p.r + 2) + '" fill="none" stroke="rgba(124,131,255,0.12)" stroke-width="1"/>';
    // Dot
    svg += '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + p.r + '" fill="rgba(124,131,255,0.15)" stroke="rgba(124,131,255,0.25)" stroke-width="1"/>';
    // Emoji label
    svg += '<text x="' + p.x + '" y="' + (p.y + 4) + '" text-anchor="middle" font-size="' + Math.round(10 + p.r * 0.5) + '" fill="#e0e0f0">' + p.emoji + '</text>';
    // Date label (every other if >4 points)
    labelDates.push({ x: p.x, date: p.date });
  });

  // Date labels (show all, use compact format mm/dd)
  var showLabels = labelDates.length <= 7;
  if (showLabels) {
    labelDates.forEach(function(ld) {
      var parts = ld.date.split('-');
      var shortDate = parts[1] + '/' + parts[2]; // mm/dd
      svg += '<text x="' + ld.x + '" y="' + (h - 4) + '" text-anchor="middle" font-size="9" fill="#6a6a9a" font-family="\'Courier New\', monospace">' + shortDate + '</text>';
    });
  }

  svg += '</svg>';

  var title = '<div class="mood-timeline-title">7日情绪波动</div>';
  return '<div class="mood-timeline-wrap">' + title + svg + '</div>';
}

// ── Panksepp 6-D Radar Chart ──
/**
 * @param {{ date:string, seeking:number, play:number, care:number, fear:number, rage:number, panic:number }} data
 * @returns {string} HTML with canvas
 */
function renderMoodRadar(data) {
  if (!data) return '';
  var dims = [
    { key: 'seeking', label: '探索', color: 'rgba(100,180,255,0.6)' },
    { key: 'play', label: '嬉戏', color: 'rgba(255,200,100,0.6)' },
    { key: 'care', label: '关怀', color: 'rgba(255,130,160,0.6)' },
    { key: 'fear', label: '恐惧', color: 'rgba(160,120,200,0.6)' },
    { key: 'rage', label: '愤怒', color: 'rgba(255,100,100,0.6)' },
    { key: 'panic', label: '悲伤', color: 'rgba(130,160,210,0.6)' }
  ];
  var html = '<div class="mood-radar-wrap"><div class="mood-timeline-title">Panksepp 情绪六维</div>'
    + '<canvas id="moodRadarCanvas" width="280" height="280" class="mood-radar-canvas"></canvas></div>';
  // Defer drawing to after DOM insert
  setTimeout(function() {
    var c = document.getElementById('moodRadarCanvas');
    if (!c) return;
    var ctx2 = c.getContext('2d');
    var cx = 140, cy = 140, r = 110;
    var n = dims.length;
    // Draw grid
    for (var level = 1; level <= 4; level++) {
      ctx2.beginPath();
      for (var i = 0; i < n; i++) {
        var angle = (Math.PI * 2 / n) * i - Math.PI / 2;
        var lr = (r / 4) * level;
        var lx = cx + lr * Math.cos(angle);
        var ly = cy + lr * Math.sin(angle);
        if (i === 0) ctx2.moveTo(lx, ly);
        else ctx2.lineTo(lx, ly);
      }
      ctx2.closePath();
      ctx2.strokeStyle = 'rgba(124,131,255,' + (0.06 + level * 0.04) + ')';
      ctx2.lineWidth = 1;
      ctx2.stroke();
    }
    // Draw axes
    for (var i = 0; i < n; i++) {
      var angle = (Math.PI * 2 / n) * i - Math.PI / 2;
      ctx2.beginPath();
      ctx2.moveTo(cx, cy);
      ctx2.lineTo(cx + r * Math.cos(angle), cy + r * Math.sin(angle));
      ctx2.strokeStyle = 'rgba(124,131,255,0.1)';
      ctx2.stroke();
    }
    // Draw data polygon
    ctx2.beginPath();
    for (var i = 0; i < n; i++) {
      var val = data[dims[i].key] || 0;
      var angle = (Math.PI * 2 / n) * i - Math.PI / 2;
      var dr = Math.max(0.05, Math.min(1, val)) * r;
      var dx = cx + dr * Math.cos(angle);
      var dy = cy + dr * Math.sin(angle);
      if (i === 0) ctx2.moveTo(dx, dy);
      else ctx2.lineTo(dx, dy);
    }
    ctx2.closePath();
    ctx2.fillStyle = 'rgba(124,131,255,0.12)';
    ctx2.fill();
    ctx2.strokeStyle = 'rgba(124,131,255,0.35)';
    ctx2.lineWidth = 2;
    ctx2.stroke();
    // Draw dots and labels
    for (var i = 0; i < n; i++) {
      var val = data[dims[i].key] || 0;
      var angle = (Math.PI * 2 / n) * i - Math.PI / 2;
      var dr = Math.max(0.05, Math.min(1, val)) * r;
      var dx = cx + dr * Math.cos(angle);
      var dy = cy + dr * Math.sin(angle);
      // Dot
      ctx2.beginPath();
      ctx2.arc(dx, dy, 3.5, 0, Math.PI * 2);
      ctx2.fillStyle = dims[i].color;
      ctx2.fill();
      // Label
      var lx2 = cx + (r + 22) * Math.cos(angle);
      var ly2 = cy + (r + 22) * Math.sin(angle);
      ctx2.fillStyle = '#a0a0c0';
      ctx2.font = '11px sans-serif';
      ctx2.textAlign = 'center';
      ctx2.textBaseline = 'middle';
      ctx2.fillText(dims[i].label + ' ' + (val * 100).toFixed(0), lx2, ly2);
    }
  }, 50);
  return html;
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
