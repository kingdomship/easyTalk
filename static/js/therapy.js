// ── Therapy mode toggle ──
var therapyMode = (function() {
  try { return localStorage.getItem('easytalk_therapy_mode') === '1'; } catch(e) { return false; }
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
  try { localStorage.setItem('easytalk_therapy_mode', therapyMode ? '1' : '0'); } catch(e) {}
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
