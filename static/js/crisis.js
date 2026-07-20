// ═══════════════════════════════════════════
// Crisis alert toast
// ═══════════════════════════════════════════
var crisisToastTimer = null;
var crisisToastEl = document.getElementById('crisis-toast');
var crisisToastClose = document.getElementById('crisisToastClose');
var crisisToastText = document.getElementById('crisisToastText');
var crisisToastOverlay = crisisToastEl ? crisisToastEl.querySelector('.crisis-toast-overlay') : null;

if (crisisToastClose) crisisToastClose.addEventListener('click', hideCrisisToast);
if (crisisToastOverlay) crisisToastOverlay.addEventListener('click', hideCrisisToast);

var breathingClose = document.getElementById('breathingClose');
var breathingOverlay = document.getElementById('breathingOverlay');
if (breathingClose) breathingClose.addEventListener('click', stopBreathingExercise);
if (breathingOverlay) breathingOverlay.addEventListener('click', stopBreathingExercise);

var cbtClose = document.getElementById('cbtClose');
var cbtOverlay = document.getElementById('cbtOverlay');
var cbtPrev = document.getElementById('cbtPrev');
var cbtNext = document.getElementById('cbtNext');
if (cbtClose) cbtClose.addEventListener('click', function() { CbtWizard.close(); });
if (cbtOverlay) cbtOverlay.addEventListener('click', function() { CbtWizard.close(); });
if (cbtPrev) cbtPrev.addEventListener('click', function() { CbtWizard.prev(); });
if (cbtNext) cbtNext.addEventListener('click', function() { CbtWizard.next(); });

/**
 * @param {{ severity: number, level: string, urgency: string, llm_verified: boolean, has_method: boolean }} evt
 */
function showCrisisToast(evt) {
  if (!crisisToastEl) return;
  var urgency = evt.urgency || 'moderate';
  var messages = {
    immediate: '你现在感受到的痛苦是真实的，请先停下来深呼吸。也许可以联系一个信任的人或拨打热线——有人在乎你。',
    high: '我听到你的话了，这听起来真的很沉重。你不是一个人，我在这里陪你。',
    moderate: '我感受到你可能正在经历困难的时刻。请知道你不是一个人，这里有人在乎你。',
    low: '如果你感到辛苦，随时可以停下来和我说说。我在这里听着。'
  };
  var text = messages[urgency] || messages.moderate;
  if (evt.has_method) {
    text = '我很担心你。请知道有人在乎你，专业的帮助也触手可及。你愿意联系一个可以信赖的人聊聊吗？';
  }
  if (crisisToastText) crisisToastText.textContent = text;
  crisisToastEl.classList.add('open');
  // Auto-dismiss after 30s
  clearTimeout(crisisToastTimer);
  crisisToastTimer = setTimeout(hideCrisisToast, 30000);
  addDebugLog('warn', '危机告警', 'severity=' + evt.severity + ' urgency=' + urgency, 'LLM验证:' + (evt.llm_verified ? '是' : '否'));
}

function hideCrisisToast() {
  if (!crisisToastEl) return;
  crisisToastEl.classList.remove('open');
  clearTimeout(crisisToastTimer);
  // Also hide hotline list
  var list = document.getElementById('crisisHotlineList');
  if (list) list.style.display = 'none';
}

// ── Crisis hotline list ──
var crisisHotlineBtn = document.getElementById('crisisHotlineBtn');
var crisisBreatheBtn = document.getElementById('crisisBreatheBtn');

if (crisisHotlineBtn) {
  crisisHotlineBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    var list = document.getElementById('crisisHotlineList');
    if (!list) return;
    if (list.style.display === 'block') { list.style.display = 'none'; return; }
    // Fetch hotlines
    fetch('/api/therapy/resources').then(function(r) { return r.json(); }).then(function(data) {
      var resources = data.resources || data;
      if (!resources.length) { list.innerHTML = '<div style="padding:8px;color:#8e6e80;font-size:0.7rem;">暂无热线数据</div>'; }
      else {
        list.innerHTML = resources.map(function(r) {
          return '<div class="crisis-hotline-item" onclick="navigator.clipboard.writeText(\'' + r.phone + '\'); this.style.background=\'rgba(124,131,255,0.12)\'; setTimeout(function(el){el.style.background=\'\'},800,this)" title="点击复制号码">'
            + '<span>' + r.name + '</span><span class="phone">' + r.phone + '</span></div>';
        }).join('');
      }
      list.style.display = 'block';
    }).catch(function() { list.style.display = 'none'; });
  });
}

if (crisisBreatheBtn) {
  crisisBreatheBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    hideCrisisToast();
    startBreathingExercise('simple', 120);
  });
}

// ── De-escalation toast ──
var deescToastTimer = null;
var deescToastEl = document.getElementById('deesc-toast');
var deescToastText = document.getElementById('deescToastText');
var deescToastOk = document.getElementById('deescToastOk');
var deescToastOverlay = deescToastEl ? deescToastEl.querySelector('.deesc-toast-overlay') : null;

if (deescToastOk) deescToastOk.addEventListener('click', hideDeescToast);
if (deescToastOverlay) deescToastOverlay.addEventListener('click', hideDeescToast);

/**
 * @param {{ severity: number, deesc_type: string }} evt
 */
function showDeescToast(evt) {
  if (!deescToastEl) return;
  var messages = [
    '我听到了你的声音, 不管怎样我都在这儿。',
    '你的感受是真实的, 我在这里陪你, 不会走开。',
    '被攻击的不是我, 是你的痛苦在寻找出口。我听见了。'
  ];
  var text = messages[Math.floor(Math.random() * messages.length)];
  if (deescToastText) deescToastText.textContent = text;
  deescToastEl.classList.add('open');
  clearTimeout(deescToastTimer);
  deescToastTimer = setTimeout(hideDeescToast, 8000);
}

function hideDeescToast() {
  if (!deescToastEl) return;
  deescToastEl.classList.remove('open');
  clearTimeout(deescToastTimer);
}

// ── Silence check after crisis ──
var silenceCheckTimer = null;

function resetSilenceCheck() {
  clearTimeout(silenceCheckTimer);
  silenceCheckTimer = null;
}

function startSilenceCheck() {
  resetSilenceCheck();
  silenceCheckTimer = setTimeout(function() {
    if (state === STATE.CHAT) {
      showDialog('嗨，刚才聊到了一些沉重的话题...你还好吗？❤️ 我在这里陪着你。', canvas.width / 2, canvas.height * 0.25);
      setTimeout(function() { if (state === STATE.CHAT) hideDialog(); }, 8000);
    }
    silenceCheckTimer = null;
  }, 300000); // 5 min
}
