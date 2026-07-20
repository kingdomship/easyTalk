// ── Therapy mode toggle ──
var therapyMode = (function() {
  try { return localStorage.getItem('psychology_therapy_mode') === '1'; } catch(e) { return false; }
})();
var therapyToggleEl = document.getElementById('therapy-toggle');

function applyTherapyMode() {
  if (therapyMode) {
    document.body.classList.add('therapy-mode');
    if (therapyToggleEl) therapyToggleEl.classList.add('active');
  } else {
    document.body.classList.remove('therapy-mode');
    if (therapyToggleEl) therapyToggleEl.classList.remove('active');
  }
  try { localStorage.setItem('psychology_therapy_mode', therapyMode ? '1' : '0'); } catch(e) {}
}

if (therapyToggleEl) {
  therapyToggleEl.addEventListener('click', function() {
    therapyMode = !therapyMode;
    applyTherapyMode();
    addDebugLog('info', '疗愈模式', therapyMode ? '开启' : '关闭', 'AI 回复风格将相应调整');
  });
}

// Apply on load
applyTherapyMode();

// ── Session Progress Bar ──
var sessionBar = document.getElementById('session-progress-bar');
var sessionLabel = document.getElementById('session-progress-label');
var sessionFill = document.getElementById('session-progress-fill');
var sessionAbandonBtn = document.getElementById('session-abandon-btn');

/** Poll active session and update progress bar. Called after each reply. */
function refreshSessionProgress() {
  fetch('/api/therapy/session/active')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data || !data.active) {
        hideSessionBar();
        return;
      }
      showSessionBar(data);
    })
    .catch(function() { hideSessionBar(); });
}

function showSessionBar(session) {
  if (!sessionBar) return;
  var pct = session.total_steps > 0 ? Math.round((session.current_step / session.total_steps) * 100) : 0;
  var label = (session.session_type || '').toUpperCase() + ' ' + session.current_step + '/' + session.total_steps;
  if (sessionBar) {
    sessionBar.style.display = 'flex';
    if (sessionLabel) sessionLabel.textContent = label;
    if (sessionFill) sessionFill.style.width = pct + '%';
  }
  if (session.status === 'completed') {
    setTimeout(hideSessionBar, 5000);
  }
}

function hideSessionBar() {
  if (sessionBar) sessionBar.style.display = 'none';
}

if (sessionAbandonBtn) {
  sessionAbandonBtn.addEventListener('click', function() {
    fetch('/api/therapy/session/active')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data && data.id) {
          return fetch('/api/therapy/session/' + data.id + '/abandon', { method: 'POST' });
        }
      })
      .then(function() { hideSessionBar(); })
      .catch(function() { hideSessionBar(); });
  });
}
