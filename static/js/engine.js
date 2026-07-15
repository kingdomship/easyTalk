// @ts-check
function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ═══════════════════════════════════════════
// DOM refs
// ═══════════════════════════════════════════
const canvas = document.getElementById('c'), ctx = canvas.getContext('2d');
const inputRow = document.getElementById('input-row');
const input = document.getElementById('input'), sendBtn = document.getElementById('sendBtn');
const dialog = document.getElementById('dialog'), dlgBody = document.getElementById('dlgBody');
const dlgClose = document.getElementById('dlgClose');
const topicBubbles = document.getElementById('topic-bubbles');
const auxPanel = document.getElementById('aux-panel'), auxContent = document.getElementById('auxContent');

// ═══════════════════════════════════════════
// Typing sound engine (Web Audio API)
// ═══════════════════════════════════════════
// Pre-generate WAV blobs at different frequencies for typing sound variety
var _blipBlobs = [];
function _makeBlipBlob(freq) {
  var sampleRate = 8000, duration = 0.04;
  var numSamples = Math.floor(sampleRate * duration);
  var dataSize = numSamples;
  var fileSize = 44 + dataSize;
  var buf = new ArrayBuffer(fileSize);
  var v = new DataView(buf);
  function w16(o, x) { v.setUint16(o, x, true); }
  function w32(o, x) { v.setUint32(o, x, true); }
  w32(0, 0x46464952); w32(4, fileSize - 8); w32(8, 0x45564157);
  w32(12, 0x20746d66); w32(16, 16); w16(20, 1); w16(22, 1);
  w32(24, sampleRate); w32(28, sampleRate); w16(32, 1); w16(34, 8);
  w32(36, 0x61746164); w32(40, dataSize);
  var u8 = new Uint8Array(buf, 44, dataSize);
  for (var i = 0; i < numSamples; i++) {
    u8[i] = Math.sin(2 * Math.PI * freq * i / sampleRate) > 0 ? 220 : 36;
  }
  return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
}
// Pre-generate 5 blips at different pitches for variety
[600, 900, 1100, 1400, 1800].forEach(function(f) {
  _blipBlobs.push(_makeBlipBlob(f));
});

function playTypingSound() {
  if (!soundOn) return;
  try {
    var blob = _blipBlobs[Math.floor(Math.random() * _blipBlobs.length)];
    var a = new Audio(blob);
    a.volume = 0.10;
    a.play().catch(function(){});
  } catch(e) {}
}
const auxBack = document.getElementById('auxBack');
const soundToggle = document.getElementById('sound-toggle');

// ═══════════════════════════════════════════
// State machine
// ═══════════════════════════════════════════
const STATE = { STARFIELD:'starfield', CONVERGING:'converging', CHAT:'chat', AUXILIARY:'auxiliary', CONSTELLATION:'constellation' };
let state = STATE.STARFIELD;

// ═══════════════════════════════════════════
// Debug panel (triple-click bottom-left corner)
// ═══════════════════════════════════════════
const debugTrigger = document.getElementById('debug-trigger');
const debugPanel = document.getElementById('debug-panel');
let debugClicks = 0, debugTimer = null;
const ERROR_PATTERNS = {
  'fetch': { cause: '网络请求被阻断或服务器未响应', fix: '检查容器运行状态: docker ps, 检查端口映射' },
  'HTTP 5': { cause: '服务器内部错误', fix: '查看容器日志: docker logs emoji-chat-app-1' },
  'HTTP 4': { cause: '请求参数错误或端点不存在', fix: '检查API路径和请求格式' },
  'timeout': { cause: '请求超时', fix: 'DeepSeek API 响应慢或网络延迟高，考虑降低max_tokens' },
  'rate': { cause: 'API 速率限制', fix: '等待几秒后重试，或检查API配额' },
  'API key': { cause: 'DeepSeek API Key 无效或过期', fix: '检查 DEEPSEEK_API_KEY 环境变量' },
  '嗯...': { cause: 'LLM 返回异常或 JSON 解析失败', fix: '检查 DeepSeek 控制台是否有报错，尝试简化 system prompt' },
};

function addDebugLog(level, title, msg, analysis) {
  const now = new Date().toLocaleTimeString();
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = `<span class="log-time">${now}</span><span class="log-${level}">[${level.toUpperCase()}] ${escapeHtml(title)}: ${escapeHtml(msg)}</span>`;
  if (analysis) {
    entry.innerHTML += `<div class="log-analysis">→ ${escapeHtml(analysis)}</div>`;
  }
  debugPanel.insertBefore(entry, debugPanel.firstChild);
  // Auto-analyze known error patterns
  if (!analysis && level === 'error') {
    for (const [pattern, info] of Object.entries(ERROR_PATTERNS)) {
      if (msg.toLowerCase().includes(pattern.toLowerCase())) {
        const analysisEntry = document.createElement('div');
        analysisEntry.className = 'log-analysis';
        analysisEntry.textContent = `→ 原因: ${info.cause} | 建议: ${info.fix}`;
        entry.appendChild(analysisEntry);
        break;
      }
    }
  }
}

debugTrigger.addEventListener('click', () => {
  debugClicks++;
  clearTimeout(debugTimer);
  debugTimer = setTimeout(() => { debugClicks = 0; }, 500);
  if (debugClicks >= 3) {
    debugClicks = 0;
    debugPanel.classList.toggle('visible');
  }
});

// Capture global errors and unhandled rejections
window.addEventListener('error', e => {
  addDebugLog('error', '全局异常', `${e.filename}:${e.lineno} ${e.message}`,
    '未捕获的JS错误，检查对应代码行');
});
window.addEventListener('unhandledrejection', e => {
  addDebugLog('error', '未处理的Promise拒绝', String(e.reason),
    '异步操作失败未catch，检查fetch/await调用');
});

// Override console.error to capture in debug panel
const _origConsoleError = console.error;
console.error = function(...args) {
  _origConsoleError.apply(console, args);
  addDebugLog('error', 'Console', args.map(a => typeof a === 'object' ? JSON.stringify(a).slice(0,200) : String(a)).join(' '));
};
const _origConsoleWarn = console.warn;
console.warn = function(...args) {
  _origConsoleWarn.apply(console, args);
  addDebugLog('warn', 'Console', args.map(a => String(a)).join(' '));
};

addDebugLog('info', '启动', '页面加载完成', '正常启动，等待用户交互');

// ═══════════════════════════════════════════
// Sound toggle (controls typing sound on/off)
// ═══════════════════════════════════════════
let soundOn = true;

soundToggle.addEventListener('click', () => {
  soundOn = !soundOn;
  soundToggle.textContent = soundOn ? '🔊' : '🔇';
  soundToggle.classList.toggle('muted', !soundOn);
});

// ═══════════════════════════════════════════
// Canvas sizing
// ═══════════════════════════════════════════
function resize() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  if (state === STATE.CHAT) updateFacePixelTargets();
}
window.addEventListener('resize', resize);
resize();

// ═══════════════════════════════════════════
// Face computation (ported from original)
// ═══════════════════════════════════════════
const GRID = 64;
const FACE_COLORS = { face:'#ffeaa7', faceD:'#f0d67a', outline:'#d4b84c', dark:'#2d3436', light:'#ffffff', blush:'#ff7799' };

function fd(r, c) { return Math.sqrt((r-32)**2 + (c-32)**2); }
function lerp(a,b,t) { return a+(b-a)*t; }
function easeInOutCubic(t) { return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2; }
function easeOutElastic(t) {
  if (t === 0 || t === 1) return t;
  return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (2 * Math.PI) / 3) + 1;
}
function lerpH(c1, c2, t) {
  const h = s => parseInt(s, 16);
  const r = Math.round(lerp(h(c1.slice(1,3)), h(c2.slice(1,3)), t));
  const g = Math.round(lerp(h(c1.slice(3,5)), h(c2.slice(3,5)), t));
  const b = Math.round(lerp(h(c1.slice(5,7)), h(c2.slice(5,7)), t));
  return '#'+[r,g,b].map(v=>Math.max(0,Math.min(255,v)).toString(16).padStart(2,'0')).join('');
}

function getFacePixels(params) {
  const p = params;
  const pixels = [];
  // Face circle (radius 29, outline 27, darker edge 24)
  for (let r = 0; r < GRID; r++)
    for (let cc = 0; cc < GRID; cc++) {
      const d = fd(r, cc);
      if (d > 29) continue;
      const color = d > 27 ? FACE_COLORS.outline : (d > 24 ? FACE_COLORS.faceD : FACE_COLORS.face);
      pixels.push({ r, c: cc, color });
    }
  // Blush — distinct pink circles on cheeks, always slightly visible
  const blushVal = p.blush || 0;
  const blushBlend = 0.08 + blushVal * 0.7;
  if (blushBlend > 0.02) {
    const blushColor = lerpH(FACE_COLORS.face, FACE_COLORS.blush, blushBlend);
    // Left cheek: center ~(27, 11), radius 8
    for (let r = 19; r <= 35; r++) {
      for (let cc = 3; cc <= 19; cc++) {
        if (Math.sqrt((r-27)**2 + (cc-11)**2) < 8) pixels.push({ r, c: cc, color: blushColor });
      }
    }
    // Right cheek: center ~(27, 53), radius 8
    for (let r = 19; r <= 35; r++) {
      for (let cc = 45; cc <= 61; cc++) {
        if (Math.sqrt((r-27)**2 + (cc-53)**2) < 8) pixels.push({ r, c: cc, color: blushColor });
      }
    }
  }
  // Eyebrows (pixel blocks)
  const baseR = Math.round(lerp(17, 8, p.brow_height));
  const asym = p.brow_asym || 0;
  const lOff = -Math.round(asym * 4), rOff = Math.round(asym * 4);
  for (let i = 0; i < 5; i++) {
    const cc = 14 + i, isInner = i >= 2;
    const rowOff = isInner ? -Math.round(p.brow_angle * 3) : Math.round(p.brow_angle * 3);
    pixels.push({ r: baseR + rowOff + lOff, c: cc, color: FACE_COLORS.dark });
  }
  for (let i = 0; i < 5; i++) {
    const cc = 43 + i, isInner = i <= 2;
    const rowOff = isInner ? -Math.round(p.brow_angle * 3) : Math.round(p.brow_angle * 3);
    pixels.push({ r: baseR + rowOff + rOff, c: cc, color: FACE_COLORS.dark });
  }
  // Eyes (pixel blocks, wink support)
  function eyePx(cc) {
    const px = [], bR = 20;
    let eyeOpen = p.eye_open;
    const wink = p.eye_wink || 0;
    if (wink < -0.5 && cc === 20) eyeOpen = 0.05;
    if (wink > 0.5 && cc === 43) eyeOpen = 0.05;
    const rows = eyeOpen < 0.2 ? 1 : (eyeOpen < 0.6 ? 2 : 3);
    if (rows === 1) {
      for (let c = cc - 5; c <= cc + 5 && px.length < 10; c++) px.push({ r: bR, c, color: FACE_COLORS.dark });
    } else if (rows === 2) {
      for (let c = cc - 3; c <= cc + 3; c++) px.push({ r: bR - 2, c, color: FACE_COLORS.dark });
      px.push({ r: bR + Math.round(-p.eye_curve * 4), c: cc - 3, color: FACE_COLORS.dark });
      px.push({ r: bR + Math.round(p.eye_curve * 2), c: cc, color: FACE_COLORS.dark });
      px.push({ r: bR + Math.round(-p.eye_curve * 4), c: cc + 3, color: FACE_COLORS.dark });
    } else {
      px.push({ r: bR - 4, c: cc - 4, color: FACE_COLORS.dark });
      px.push({ r: bR - 4, c: cc + 3, color: FACE_COLORS.dark });
      px.push({ r: bR - 2, c: cc - 4, color: FACE_COLORS.dark });
      px.push({ r: bR - 2, c: cc + 3, color: FACE_COLORS.dark });
      px.push({ r: bR, c: cc - 4, color: FACE_COLORS.dark });
      px.push({ r: bR, c: cc + 3, color: FACE_COLORS.dark });
    }
    const ps = Math.round((p.eye_pupil || 0) * 3.5);
    for (let k = 0; k < px.length; k++) px[k].c += ps;
    const hlR = rows === 1 ? bR : bR - 2;
    px.push({ r: hlR, c: cc + 3 + ps, color: lerpH(FACE_COLORS.dark, FACE_COLORS.light, p.sparkle) });
    return px;
  }
  pixels.push(...eyePx(20));
  pixels.push(...eyePx(43));
  // Tear
  if ((p.tear || 0) > 0.05) {
    const tearColor = lerpH('#ffffff', '#88ccff', p.tear);
    const tearR = 23 + Math.round(p.tear * 2);
    pixels.push({ r: tearR, c: 18, color: tearColor });
    pixels.push({ r: tearR + 1, c: 18, color: tearColor });
    pixels.push({ r: tearR, c: 19, color: tearColor });
    pixels.push({ r: tearR + 1, c: 19, color: tearColor });
  }
  // Mouth (pixel blocks, asymmetric)
  const mcc = 32, hw = Math.round(lerp(4, 11, p.mouth_width));
  const cs = mcc - hw, ce = mcc + hw;
  const ma = p.mouth_asym || 0;
  if (p.mouth_open < 0.25) {
    for (let c = cs; c <= ce && pixels.length < 2000; c++) {
      const t = (c - cs) / (ce - cs || 1), edgeF = Math.abs(t - 0.5) * 2;
      const asymOffset = Math.round(ma * (c - mcc) * 0.4);
      pixels.push({ r: 39 + Math.round(-p.mouth_curve * edgeF * 4) + asymOffset, c, color: FACE_COLORS.dark });
    }
  } else {
    const topR = 37 - Math.round(p.mouth_open * 1.6), botR = 39 + Math.round(p.mouth_open * 1.6);
    for (let c = 31; c <= 34; c++) pixels.push({ r: topR, c, color: FACE_COLORS.dark });
    for (let c = cs + 1; c <= ce - 1 && pixels.length < 2000; c++) {
      const isE = (c === cs + 1 || c === ce - 1);
      const asymOffset = Math.round(ma * (c - mcc) * 0.4);
      pixels.push({ r: botR + (isE ? Math.round(-p.mouth_curve * 2) : Math.round(p.mouth_curve * 0.7)) + asymOffset, c, color: FACE_COLORS.dark });
    }
  }
  return pixels;
}

// ═══════════════════════════════════════════
// Face parameters
// ═══════════════════════════════════════════
let curParams = { eye_curve:0, eye_open:0.5, eye_pupil:0, eye_wink:0, mouth_curve:0, mouth_open:0, mouth_width:0.8, mouth_asym:0, sparkle:0.5, brow_angle:0, brow_height:0.5, brow_asym:0, blush:0.15, head_tilt:0, tear:0 };
let tgtParams = { ...curParams };

// Mood-driven atmosphere
let moodColor = { r: 13, g: 13, b: 36 };
let moodTarget = { r: 13, g: 13, b: 36 };
let pokeActive = false, pokeTimer = 0, pokeSparkles = [];
const POKE_EXPRESSIONS = [
  { eye_open:0.9, mouth_open:0.5, mouth_curve:0.7, sparkle:1, brow_height:0.9, duration_ms:400 },
  { eye_curve:0.8, mouth_curve:0.9, sparkle:0.9, brow_height:0.6, duration_ms:300 },
  { eye_open:0.3, mouth_open:0.3, mouth_curve:0.5, sparkle:0.7, brow_asym:0.6, duration_ms:350 },
];

// Sequence player
let sequence = [], seqIdx = 0, seqElapsed = 0;
let replyText = '';

function setSequence(emotions, reply) {
  sequence = emotions.map(e => ({
    params: {
      eye_curve:e.eye_curve, eye_open:e.eye_open, eye_pupil:e.eye_pupil||0, eye_wink:e.eye_wink||0,
      mouth_curve:e.mouth_curve, mouth_open:e.mouth_open, mouth_width:e.mouth_width, mouth_asym:e.mouth_asym||0,
      sparkle:e.sparkle, brow_angle:e.brow_angle, brow_height:e.brow_height, brow_asym:e.brow_asym||0,
      blush:e.blush??curParams.blush, head_tilt:e.head_tilt||0, tear:e.tear||0,
    },
    duration: e.duration_ms || 3000,
    label: e.label || '',
  }));
  seqIdx = 0; seqElapsed = 0;
  microTimer = 2; // Reset micro-expression cooldown on new expression
  replyText = reply || '';
}

function updateSequence(dt) {
  if (sequence.length === 0) return;

  seqElapsed += dt * 1000;
  const curFrame = sequence[seqIdx];

  if (sequence.length === 1) {
    // Single frame: smooth transition toward it
    tgtParams = { ...curFrame.params };
    return;
  }

  // Interpolate between current frame and next frame over the frame's duration
  const nextFrame = sequence[Math.min(seqIdx + 1, sequence.length - 1)];
  const rawT = Math.min(seqElapsed / curFrame.duration, 1);
  const t = easeInOutCubic(rawT);

  for (const k of Object.keys(curFrame.params)) {
    tgtParams[k] = lerp(curFrame.params[k], nextFrame.params[k], t);
  }

  if (seqElapsed >= curFrame.duration && seqIdx < sequence.length - 1) {
    seqElapsed -= curFrame.duration;
    seqIdx++;
  }
}

function triggerPokeReaction(cx, cy) {
  if (pokeActive) return;
  pokeActive = true; pokeTimer = 0;
  // Pick a random poke expression
  const ex = POKE_EXPRESSIONS[Math.floor(Math.random() * POKE_EXPRESSIONS.length)];
  sequence = [{
    params: { ...curParams, ...ex },
    duration: ex.duration_ms,
    label: 'poke',
  }];
  seqIdx = 0; seqElapsed = 0;
  // Burst sparkles from click point
  for (let i = 0; i < 12; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 2 + Math.random() * 5;
    pokeSparkles.push({
      x: cx, y: cy,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      life: 1,
      size: 1 + Math.random() * 3,
    });
  }
}

function updateMoodFromEmotion(label) {
  // Map emotion labels to color shifts
  const warmLabels = ['开心','惊喜','喜欢','幸福','温暖','兴奋','感动','得意','满足'];
  const coolLabels = ['难过','悲伤','生气','愤怒','害怕','紧张','疲惫','失落','委屈'];
  const labelLower = (label || '').toLowerCase();
  const isWarm = warmLabels.some(w => labelLower.includes(w));
  const isCool = coolLabels.some(c => labelLower.includes(c));
  if (isWarm) moodTarget = { r: 22, g: 16, b: 40 };  // warm purple-gold
  else if (isCool) moodTarget = { r: 8, g: 12, b: 32 }; // cool deep blue
  // else stay neutral
}

function circadianBaseColor() {
  const h = new Date().getHours();
  if (h >= 5 && h < 8)  return { r: 18, g: 15, b: 35 };  // dawn
  if (h >= 8 && h < 12)  return { r: 15, g: 15, b: 38 };  // morning
  if (h >= 12 && h < 17) return { r: 13, g: 13, b: 36 };  // afternoon (neutral)
  if (h >= 17 && h < 20) return { r: 18, g: 14, b: 33 };  // dusk
  if (h >= 20 && h < 23) return { r: 10, g: 11, b: 30 };  // evening
  return { r: 7, g: 8, b: 22 };                             // night
}

function circadianBrightness() {
  const h = new Date().getHours();
  if (h >= 5 && h < 8)  return 0.7;
  if (h >= 8 && h < 17) return 1.0;
  if (h >= 17 && h < 20) return 0.75;
  if (h >= 20 && h < 23) return 0.55;
  return 0.35;
}

function updateAtmosphere(dt) {
  // Blend circadian base color with mood color
  const circ = circadianBaseColor();
  const circWeight = 0.6;
  const moodSpeed = 0.02;
  moodColor.r = lerp(moodColor.r, moodTarget.r * (1 - circWeight) + circ.r * circWeight, moodSpeed);
  moodColor.g = lerp(moodColor.g, moodTarget.g * (1 - circWeight) + circ.g * circWeight, moodSpeed);
  moodColor.b = lerp(moodColor.b, moodTarget.b * (1 - circWeight) + circ.b * circWeight, moodSpeed);

  // Decay mood toward neutral
  moodTarget.r = lerp(moodTarget.r, circ.r, 0.005);
  moodTarget.g = lerp(moodTarget.g, circ.g, 0.005);
  moodTarget.b = lerp(moodTarget.b, circ.b, 0.005);

  // Poke timer
  if (pokeActive) {
    pokeTimer += dt * 1000;
    if (pokeTimer > 600) { pokeActive = false; pokeTimer = 0; }
    for (const s of pokeSparkles) {
      s.x += s.vx; s.y += s.vy; s.life -= dt * 2;
    }
    pokeSparkles = pokeSparkles.filter(s => s.life > 0);
  }
}

// ═══════════════════════════════════════════
// Particles / Stars
