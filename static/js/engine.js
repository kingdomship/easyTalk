// @ts-check
function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ═══════════════════════════════════════════
// DOM refs
// ═══════════════════════════════════════════
const canvas = /** @type {HTMLCanvasElement} */ (document.getElementById('c')), ctx = canvas.getContext('2d');
const inputRow = document.getElementById('input-row');
const textarea = /** @type {HTMLTextAreaElement} */ (document.getElementById('input')), sendBtn = /** @type {HTMLButtonElement} */ (document.getElementById('sendBtn'));
const kaomojiBtn = document.getElementById('kaomojiBtn'), kaomojiPanel = document.getElementById('kaomoji-panel');
const charCount = document.getElementById('charCount');
const dialog = document.getElementById('dialog'), dlgBody = document.getElementById('dlgBody');
const dlgClose = document.getElementById('dlgClose');
const topicBubbles = document.getElementById('topic-bubbles');
const auxPanel = document.getElementById('aux-panel'), auxContent = document.getElementById('auxContent');

// Settings
const settingsModal = document.getElementById('settings-modal');
const settingsOverlay = document.getElementById('settingsOverlay');
const settingsClose = document.getElementById('settingsClose');
const settingsSave = document.getElementById('settingsSave');
const settingsClear = document.getElementById('settingsClear');
const providerSelect = /** @type {HTMLSelectElement} */ (document.getElementById('providerSelect'));
const baseUrlInput = /** @type {HTMLInputElement} */ (document.getElementById('baseUrlInput'));
const modelInput = /** @type {HTMLInputElement} */ (document.getElementById('modelInput'));
const modelHint = /** @type {HTMLElement} */ (document.getElementById('modelHint'));
const apiKeyInput = /** @type {HTMLInputElement} */ (document.getElementById('apiKeyInput'));
const settingsStatus = /** @type {HTMLElement} */ (document.getElementById('settingsStatus'));

// ═══════════════════════════════════════════
// Typing sound engine (Web Audio API)
// ═══════════════════════════════════════════
// Synthesised soft mechanical keyboard click:
//   noise burst → bandpass filter → sharp attack / fast decay
// Much more pleasant than the old square-wave "bibibibi" beeps.
var _typeAudioCtx = null;
var _typeNoiseBuf = null;

function _ensureAudioCtx() {
  if (!_typeAudioCtx) {
    _typeAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (_typeAudioCtx.state === 'suspended') {
    _typeAudioCtx.resume();
  }
  // Lazy-create a short stereo noise buffer (shared, ~80ms)
  if (!_typeNoiseBuf) {
    var sr = _typeAudioCtx.sampleRate;
    var len = Math.floor(sr * 0.08); // 80ms
    _typeNoiseBuf = _typeAudioCtx.createBuffer(1, len, sr);
    var d = _typeNoiseBuf.getChannelData(0);
    for (var i = 0; i < len; i++) {
      d[i] = Math.random() * 2 - 1;
    }
  }
  return _typeAudioCtx;
}

function initAudio() {
  _ensureAudioCtx();
}

function playTypingSound() {
  if (!soundOn) return;
  try {
    var ctx = _ensureAudioCtx();
    var now = ctx.currentTime;

    // Noise source → bandpass → gain envelope
    var src = ctx.createBufferSource();
    src.buffer = _typeNoiseBuf;

    var bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.setValueAtTime(1800 + Math.random() * 2400, now); // 1.8-4.2kHz
    bp.Q.setValueAtTime(0.7 + Math.random() * 0.6, now);          // 0.7-1.3

    var gain = ctx.createGain();
    gain.gain.setValueAtTime(0.001, now);
    gain.gain.exponentialRampToValueAtTime(0.12, now + 0.002);    // sharp attack 2ms
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.025 + Math.random() * 0.02); // decay 25-45ms

    src.connect(bp);
    bp.connect(gain);
    gain.connect(ctx.destination);
    src.start(now);
    src.stop(now + 0.08);
  } catch (e) {}
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
  'API key': { cause: 'API Key 无效或过期', fix: '检查 ⚙️ 设置中的 API Key 配置' },
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
  addDebugLog('error', 'Console', args.map(a => {
    if (typeof a === 'object') {
      try { return JSON.stringify(a).slice(0, 200); }
      catch (_) { return String(a); }
    }
    return String(a);
  }).join(' '));
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
const FACE_COLORS = { face:'#ffd54f', faceD:'#eec030', outline:'#c49818', dark:'#2d3436', light:'#ffffff', blush:'#ff8c69' };

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
  const cheekPuff = p.cheek_puff || 0;
  for (let r = 0; r < GRID; r++)
    for (let cc = 0; cc < GRID; cc++) {
      const d = fd(r, cc);
      // Cheek puff: expand face in cheek regions
      let cheekFactor = 0;
      if (cheekPuff > 0) {
        const lDist = Math.sqrt((r-27)**2 + (cc-11)**2);
        const rDist = Math.sqrt((r-27)**2 + (cc-53)**2);
        const cheekDist = Math.min(lDist, rDist);
        if (cheekDist < 14) cheekFactor = Math.max(0, 1 - cheekDist/14);
      }
      const radius = 29 + cheekPuff * 3 * cheekFactor;
      if (d > radius) continue;
      const color = d > 27 ? FACE_COLORS.outline : (d > 24 ? FACE_COLORS.faceD : FACE_COLORS.face);
      pixels.push({ r, c: cc, color });
    }
  // Blush — with cheek_raise shifting circles up and compressing vertically
  const blushVal = p.blush || 0;
  const cheekRaise = p.cheek_raise || 0;
  const blushBlend = 0.08 + blushVal * 0.7;
  if (blushBlend > 0.02) {
    const blushColor = lerpH(FACE_COLORS.face, FACE_COLORS.blush, blushBlend);
    const blushCenterR = Math.round(27 - cheekRaise * 5);
    const blushVR = Math.round(8 - cheekRaise * 3);
    // Left cheek
    for (let r = blushCenterR - blushVR; r <= blushCenterR + blushVR; r++) {
      for (let cc = 3; cc <= 19; cc++) {
        const vrDist = (r - blushCenterR) / Math.max(1, blushVR);
        if (Math.sqrt((r-blushCenterR)**2 + (cc-11)**2) < blushVR && vrDist > -1.2)
          pixels.push({ r, c: cc, color: blushColor });
      }
    }
    // Right cheek
    for (let r = blushCenterR - blushVR; r <= blushCenterR + blushVR; r++) {
      for (let cc = 45; cc <= 61; cc++) {
        const vrDist = (r - blushCenterR) / Math.max(1, blushVR);
        if (Math.sqrt((r-blushCenterR)**2 + (cc-53)**2) < blushVR && vrDist > -1.2)
          pixels.push({ r, c: cc, color: blushColor });
      }
    }
  }
  // Nose wrinkle (AU9) — dark horizontal lines at nose bridge
  const noseWrinkle = p.nose_wrinkle || 0;
  if (noseWrinkle > 0.05) {
    const nwColor = lerpH(FACE_COLORS.face, FACE_COLORS.dark, noseWrinkle * 0.6);
    // Two short horizontal lines between eyes
    for (let c = 30; c <= 33; c++) pixels.push({ r: 15, c, color: nwColor });
    for (let c = 29; c <= 34; c++) pixels.push({ r: 16, c, color: nwColor });
  }
  // Eyebrows — 5px wide with visible arch peak
  const baseR = Math.round(lerp(18, 10, p.brow_height));
  const asym = p.brow_asym || 0;
  const lOff = -Math.round(asym * 4), rOff = Math.round(asym * 4);
  for (let i = 0; i < 5; i++) {
    const cc = 14 + i;
    const archOff = (i === 1 || i === 2) ? -1 : 0;
    const tiltOff = Math.round((cc - 16) * (p.brow_angle||0) * 2);
    pixels.push({ r: baseR + archOff + tiltOff + lOff, c: cc, color: FACE_COLORS.dark });
  }
  for (let i = 0; i < 5; i++) {
    const cc = 45 + i;
    const archOff = (i === 1 || i === 2) ? -1 : 0;
    const tiltOff = Math.round((cc - 47) * (p.brow_angle||0) * 2);
    pixels.push({ r: baseR + archOff + tiltOff + rOff, c: cc, color: FACE_COLORS.dark });
  }
  // Eyes — with eye_curve, eye_tension, iris_size
  function eyePx(cc) {
    const px = [], bR = 20;
    let eyeOpen = p.eye_open;
    const wink = p.eye_wink || 0;
    if (wink < -0.5 && cc === 20) eyeOpen = 0.05;
    if (wink > 0.5 && cc === 43) eyeOpen = 0.05;
    const rows = eyeOpen < 0.2 ? 1 : (eyeOpen < 0.6 ? 2 : 4);
    const outerDir = cc < 30 ? 1 : -1;
    const ec = p.eye_curve || 0;       // eyelid curvature
    const tension = p.eye_tension || 0; // horizontal narrowing
    const t = Math.round(tension * 2); // 0..2 px shrink per side
    if (rows === 1) {
      // Closed: thin line arched up at outer corner (smiling squint)
      for (let c = cc - 2; c <= cc + 1; c++) px.push({ r: bR, c, color: FACE_COLORS.dark });
      px.push({ r: bR - 1, c: cc + outerDir * 2, color: FACE_COLORS.dark });
      // eye_curve in closed eyes: shift the arch
      if (ec > 0.3) px.push({ r: bR - 1, c: cc + outerDir * 3, color: FACE_COLORS.dark });
    } else if (rows === 2) {
      // Half open: upper bar + thin lower line
      const tw = Math.round(tension * 1.5); // 0..2 px shrink
      for (let c = cc - 3 + tw; c <= cc + 2 - tw; c++) px.push({ r: bR - 2, c, color: FACE_COLORS.dark });
      for (let c = cc - 2; c <= cc + 1; c++) px.push({ r: bR, c, color: FACE_COLORS.dark });
    } else {
      // Full open: oval eye with eye_curve and eye_tension
      const tTop = Math.round(tension); // top row less affected
      // Top row (bR-4): narrowest, eye_curve affects vertical
      const tcOff = ec > 0 ? Math.round(ec) : 0;
      const bcOff = ec < 0 ? Math.round(-ec) : 0;
      for (let c = cc - 2 + tTop; c <= cc + 1 - tTop; c++) {
        const rowOff = (ec > 0 && (c === cc-2 || c === cc+1)) ? tcOff : 0;
        px.push({ r: bR - 4 + rowOff, c, color: FACE_COLORS.dark });
      }
      // Middle rows (bR-3, bR-2): widest, tension narrows
      for (let c = cc - 4 + t; c <= cc + 3 - t; c++) px.push({ r: bR - 3, c, color: FACE_COLORS.dark });
      for (let c = cc - 4 + t; c <= cc + 3 - t; c++) px.push({ r: bR - 2, c, color: FACE_COLORS.dark });
      // Bottom row (bR-1): slightly narrower, eye_curve affects
      for (let c = cc - 3 + t; c <= cc + 2 - t; c++) {
        const rowOff = (ec < 0 && (c === cc-3 || c === cc+2)) ? bcOff : 0;
        px.push({ r: bR - 1 + rowOff, c, color: FACE_COLORS.dark });
      }
    }
    const ps = Math.round((p.eye_pupil || 0) * 3);
    for (let k = 0; k < px.length; k++) px[k].c += ps;
    // Iris size controls highlight spread
    const iris = p.iris_size != null ? p.iris_size : 0.5;
    const sparkle = p.sparkle || 0;
    const hlR = rows === 1 ? bR : (rows === 2 ? bR - 2 : bR - 3);
    // Main highlight
    px.push({ r: hlR, c: cc + 2 + ps, color: lerpH(FACE_COLORS.dark, FACE_COLORS.light, sparkle) });
    // Secondary highlight — spread increases with iris_size
    if (rows >= 2) {
      const hlSpread = Math.round(iris * 2);
      px.push({ r: hlR + 1, c: cc + 2 + hlSpread + ps, color: lerpH(FACE_COLORS.dark, FACE_COLORS.light, sparkle * 0.5 * iris) });
    }
    // Third highlight for large iris (excited/attracted)
    if (rows >= 3 && iris > 0.6) {
      px.push({ r: hlR, c: cc + 4 + ps, color: lerpH(FACE_COLORS.dark, FACE_COLORS.light, sparkle * 0.25 * iris) });
    }
    return px;
  }
  pixels.push(...eyePx(20));
  pixels.push(...eyePx(43));
  // Tear — left eye (cc=20 area)
  if ((p.tear || 0) > 0.05) {
    const tearColor = lerpH('#ffffff', '#88ccff', p.tear);
    const tearR = 23 + Math.round(p.tear * 2);
    pixels.push({ r: tearR, c: 18, color: tearColor });
    pixels.push({ r: tearR + 1, c: 18, color: tearColor });
    pixels.push({ r: tearR, c: 19, color: tearColor });
    pixels.push({ r: tearR + 1, c: 19, color: tearColor });
  }
  // Sweat drop — left temple (anime style)
  const sweat = p.sweat_drop || 0;
  if (sweat > 0.05) {
    const sweatColor = lerpH(FACE_COLORS.face, '#ccddff', sweat);
    pixels.push({ r: 9, c: 7, color: sweatColor });
    pixels.push({ r: 10, c: 6, color: sweatColor });
    pixels.push({ r: 10, c: 7, color: sweatColor });
    pixels.push({ r: 10, c: 8, color: sweatColor });
    pixels.push({ r: 11, c: 7, color: sweatColor });
  }
  // Vein pop — temple cross/cruciform (anime anger marker)
  const vein = p.vein_pop || 0;
  if (vein > 0.05) {
    const veinColor = lerpH(FACE_COLORS.face, '#8b0000', vein * 0.8);
    // Cross shape: horizontal + vertical bar
    for (let c = 7; c <= 9; c++) pixels.push({ r: 9, c, color: veinColor });
    for (let r = 8; r <= 10; r++) pixels.push({ r, c: 8, color: veinColor });
  }
  // Mouth — with lip_pout, lip_stretch, lip_bite, jaw_drop, tongue_out
  const mcc = 32;
  const lipStretch = p.lip_stretch || 0;
  const mouthW = p.mouth_width || 0.6;
  let hw = Math.round(lerp(4, 11, mouthW));
  const stretchExtra = Math.round(lipStretch * 3);
  const cs = mcc - hw - stretchExtra, ce = mcc + hw + stretchExtra;
  const ma = p.mouth_asym || 0;
  const jawDrop = p.jaw_drop || 0;
  const lipPout = p.lip_pout || 0;
  const lipBite = p.lip_bite || 0;
  const tongueOut = p.tongue_out || 0;

  // Effective mouth_open: base + auto-open when tongue out
  const effMouthOpen = Math.max(p.mouth_open || 0, tongueOut > 0.3 ? 0.2 : 0);

  if (effMouthOpen < 0.25) {
    // Closed mouth: apply lip_bite (shift r up), lip_pout (add below), stretch
    const biteShift = Math.round(lipBite * 3);
    const baseR = 39;
    for (let c = cs; c <= ce && pixels.length < 2000; c++) {
      const t = (c - cs) / (ce - cs || 1), edgeF = Math.abs(t - 0.5) * 2;
      const asymOffset = Math.round(ma * (c - mcc) * 0.4);
      // Stretch attenuates curve (stretched mouth = flat, not arched)
      const curveAtten = Math.max(0, 1 - lipStretch * 0.7);
      pixels.push({ r: baseR + Math.round(-p.mouth_curve * edgeF * 4 * curveAtten) + asymOffset - biteShift, c, color: FACE_COLORS.dark });
    }
    // Lip bite: add white "tooth" marks above the shifted lip
    if (lipBite > 0.2) {
      const toothColor = lerpH(FACE_COLORS.dark, FACE_COLORS.light, 0.6);
      pixels.push({ r: baseR - 2 - biteShift, c: mcc, color: toothColor });
      pixels.push({ r: baseR - 2 - biteShift, c: mcc + 1, color: toothColor });
    }
    // Lip pout (closed): add thickness below lip line
    if (lipPout > 0.1) {
      const poutRows = Math.round(lipPout * 2);
      for (let c = cs + 1; c <= ce - 1 && pixels.length < 2000; c++) {
        for (let pr = 1; pr <= poutRows; pr++) {
          pixels.push({ r: baseR + pr - biteShift, c, color: FACE_COLORS.dark });
        }
      }
    }
  } else {
    // Open mouth
    const topR = 37 - Math.round(effMouthOpen * 1.6) - Math.round(jawDrop * 2);
    const botR = 39 + Math.round(effMouthOpen * 1.6) + Math.round(jawDrop * 5);
    // Upper lip
    for (let c = cs + 1; c <= ce - 1; c++) pixels.push({ r: topR, c, color: FACE_COLORS.dark });
    // Lower lip with jaw_drop and lip_pout
    for (let c = cs + 1; c <= ce - 1 && pixels.length < 2000; c++) {
      const isE = (c === cs + 1 || c === ce - 1);
      const asymOffset = Math.round(ma * (c - mcc) * 0.4);
      const curveAtten = Math.max(0, 1 - lipStretch * 0.7);
      pixels.push({ r: botR + (isE ? Math.round(-p.mouth_curve * 2 * curveAtten) : Math.round(p.mouth_curve * 0.7 * curveAtten)) + asymOffset, c, color: FACE_COLORS.dark });
      // Lip pout (open): add thickness below lower lip
      if (lipPout > 0.1 && !isE) {
        const poutRows = Math.round(lipPout * 2);
        for (let pr = 1; pr <= poutRows; pr++) {
          pixels.push({ r: botR + pr + asymOffset, c, color: FACE_COLORS.dark });
        }
      }
    }
    // Tongue out: pink oval below lower lip center
    if (tongueOut > 0.1) {
      const tongueColor = lerpH('#ff7799', '#ff5577', tongueOut);
      const tongueBase = botR + 2;
      const tongueW = Math.round(lerp(1, 3, tongueOut));
      for (let rr = 0; rr <= Math.round(tongueOut * 3); rr++) {
        const rw = tongueW - (rr > 0 ? Math.round(rr * 0.5) : 0);
        for (let c = mcc - rw; c <= mcc + rw; c++) {
          pixels.push({ r: tongueBase + rr, c, color: tongueColor });
        }
      }
    }
  }
  return pixels;
}

// ═══════════════════════════════════════════
// Face parameters
// ═══════════════════════════════════════════
let curParams = { eye_curve:0, eye_open:0.7, eye_pupil:0, eye_wink:0, eye_tension:0, iris_size:0.5, mouth_curve:0.15, mouth_open:0, mouth_width:0.6, mouth_asym:0, lip_pout:0, lip_stretch:0, lip_bite:0, jaw_drop:0, tongue_out:0, sparkle:0.6, brow_angle:0.2, brow_height:0.65, brow_asym:0, nose_wrinkle:0, cheek_raise:0, cheek_puff:0, blush:0.1, head_tilt:0, tear:0, sweat_drop:0, vein_pop:0 };
let tgtParams = { ...curParams };

// Mood-driven atmosphere
let moodColor = { r: 22, g: 18, b: 42 };
let moodTarget = { r: 22, g: 18, b: 42 };

// AI-controlled color fields (Rothko-style abstract color regions)
let colorFields = [];
let colorFieldsTarget = [];

// AI-controlled background color override (hex string or null)
let bgColorTarget = null;
let bgColorCurrent = null;  // {r,g,b} for smooth lerp, or null

// AI-generated pixel sprites that fly out from the face
let pixelSprites = [];
var _landStackCount = 0; // tracks how many heavy sprites have landed (for stacking offset)

let pokeActive = false, pokeTimer = 0, pokeSparkles = [];
const POKE_EXPRESSIONS = [
  { eye_open:0.9, mouth_open:0.5, mouth_curve:0.7, sparkle:1, brow_height:0.9, iris_size:0.8, cheek_raise:0.3, duration_ms:400 },
  { eye_curve:0.8, mouth_curve:0.9, sparkle:0.9, brow_height:0.6, iris_size:0.7, cheek_raise:0.5, blush:0.2, duration_ms:300 },
  { eye_open:0.3, mouth_open:0.3, mouth_curve:0.5, sparkle:0.7, brow_asym:0.6, lip_pout:0.3, duration_ms:350 },
];

// Sequence player
let sequence = [], seqIdx = 0, seqElapsed = 0;
let replyText = '';

function setSequence(emotions, reply) {
  sequence = emotions.map(e => ({
    params: {
      eye_curve:e.eye_curve, eye_open:e.eye_open, eye_pupil:e.eye_pupil||0, eye_wink:e.eye_wink||0,
      eye_tension:e.eye_tension||0, iris_size:e.iris_size??0.5,
      mouth_curve:e.mouth_curve, mouth_open:e.mouth_open, mouth_width:e.mouth_width, mouth_asym:e.mouth_asym||0,
      lip_pout:e.lip_pout||0, lip_stretch:e.lip_stretch||0, lip_bite:e.lip_bite||0,
      jaw_drop:e.jaw_drop||0, tongue_out:e.tongue_out||0,
      sparkle:e.sparkle, brow_angle:e.brow_angle, brow_height:e.brow_height, brow_asym:e.brow_asym||0,
      nose_wrinkle:e.nose_wrinkle||0,
      cheek_raise:e.cheek_raise||0, cheek_puff:e.cheek_puff||0,
      blush:e.blush??curParams.blush, head_tilt:e.head_tilt||0,
      tear:e.tear||0, sweat_drop:e.sweat_drop||0, vein_pop:e.vein_pop||0,
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

let currentAffect = null;
let emaAffect = null;  // EMA-smoothed Panksepp 6D vector

// Panksepp 6D → RGB color mapping
const AFFECT_COLORS = {
  seeking: { r: 58, g: 48, b: 32 },  // warm gold-brown
  play:    { r: 42, g: 26, b: 48 },  // pink-purple
  care:    { r: 42, g: 24, b: 40 },  // soft pink
  fear:    { r: 10, g: 22, b: 40 },  // cold blue
  rage:    { r: 32, g: 16, b: 24 },  // dark red
  panic:   { r: 26, g: 16, b: 48 },  // deep purple
};

function updateMoodFromAffect(affect) {
  if (!affect) return;
  currentAffect = affect;

  // EMA smoothing: blend new affect into running average to prevent color flicker
  const alpha = 0.3;  // 30% new, 70% history — single spike fades to 2.7% after 3 updates
  if (!emaAffect) {
    emaAffect = { ...affect };
  } else {
    for (const dim of Object.keys(AFFECT_COLORS)) {
      emaAffect[dim] = emaAffect[dim] * (1 - alpha) + (affect[dim] || 0) * alpha;
    }
  }

  // Compute moodTarget from smoothed affect
  let r = 0, g = 0, b = 0, totalWeight = 0;
  for (const [dim, color] of Object.entries(AFFECT_COLORS)) {
    const w = Math.max(0, emaAffect[dim] || 0);
    r += color.r * w; g += color.g * w; b += color.b * w;
    totalWeight += w;
  }
  if (totalWeight > 0) {
    r /= totalWeight; g /= totalWeight; b /= totalWeight;
    const maxAffect = Math.max(...Object.values(emaAffect));
    const brightness = 0.85 + maxAffect * 0.15;
    r = Math.round(r * brightness); g = Math.round(g * brightness); b = Math.round(b * brightness);
    moodTarget = { r, g, b };
  }
}

// Legacy fallback: emotion label → color for when affect data not available
function updateMoodFromEmotion(label) {
  if (currentAffect) return; // prefer affect-based if available
  const warmLabels = ['开心','惊喜','喜欢','幸福','温暖','兴奋','感动','得意','满足'];
  const coolLabels = ['难过','悲伤','生气','愤怒','害怕','紧张','疲惫','失落','委屈'];
  const labelLower = (label || '').toLowerCase();
  const isWarm = warmLabels.some(w => labelLower.includes(w));
  const isCool = coolLabels.some(c => labelLower.includes(c));
  if (isWarm) moodTarget = { r: 22, g: 16, b: 40 };
  else if (isCool) moodTarget = { r: 8, g: 12, b: 32 };
}

function circadianBaseColor() {
  const h = new Date().getHours();
  if (h >= 5 && h < 8)  return { r: 75, g: 60, b: 95 };   // dawn — soft lavender emerging from darkness
  if (h >= 8 && h < 12)  return { r: 115, g: 95, b: 125 }; // morning — bright, warm purple-tinged
  if (h >= 12 && h < 17) return { r: 100, g: 85, b: 118 }; // afternoon — neutral, slightly cool
  if (h >= 17 && h < 20) return { r: 65, g: 52, b: 82 };   // dusk — deepening toward calm
  if (h >= 20 && h < 23) return { r: 38, g: 30, b: 56 };   // evening — calm, retains color character
  return { r: 22, g: 18, b: 42 };                            // night — deep but not pure black
}

function circadianBrightness() {
  const h = new Date().getHours();
  if (h >= 5 && h < 8)  return 0.7;
  if (h >= 8 && h < 17) return 1.0;
  if (h >= 17 && h < 20) return 0.75;
  if (h >= 20 && h < 23) return 0.55;
  return 0.35;
}

// ── Mood → CSS variable sync ──
let _lastMoodCSS = { r: 0, g: 0, b: 0 };

function updateMoodCSS() {
  const eff = getEffectiveMoodColor();
  const r = Math.round(eff.r);
  const g = Math.round(eff.g);
  const b = Math.round(eff.b);
  if (r === _lastMoodCSS.r && g === _lastMoodCSS.g && b === _lastMoodCSS.b) return;
  _lastMoodCSS = { r, g, b };

  const root = document.documentElement;
  root.style.setProperty('--mood-r', String(r));
  root.style.setProperty('--mood-g', String(g));
  root.style.setProperty('--mood-b', String(b));

  // Shift accent color based on mood warmth
  // Warm (r > b) → shift toward warmer purple; Cool (b > r) → shift toward blue
  const warmth = (eff.r - eff.b) / 60;
  const clampedWarmth = Math.max(-0.5, Math.min(0.5, warmth));
  const accentR = Math.round(Math.min(255, Math.max(100, 124 + clampedWarmth * 50)));
  const accentG = Math.round(Math.min(255, Math.max(110, 131 - Math.abs(clampedWarmth) * 30)));
  const accentB = Math.round(Math.min(255, Math.max(180, 255 - clampedWarmth * 50)));
  root.style.setProperty('--accent', `rgb(${accentR},${accentG},${accentB})`);

  // Dynamic --bg and --surface: follow effective color so UI panels match canvas
  const bgR = Math.round(eff.r * 0.20);
  const bgG = Math.round(eff.g * 0.20);
  const bgB = Math.round(eff.b * 0.20);
  root.style.setProperty('--bg', `rgb(${bgR},${bgG},${bgB})`);
  const srR = Math.round(eff.r * 0.40);
  const srG = Math.round(eff.g * 0.40);
  const srB = Math.round(eff.b * 0.40);
  root.style.setProperty('--surface', `rgb(${srR},${srG},${srB})`);
}

// ── AI-controlled color fields (Rothko-style) ──
function hexToRgb(hex) {
  if (!hex || typeof hex !== 'string' || hex.length < 7) return { r: 255, g: 255, b: 255 };
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return { r: isNaN(r) ? 255 : r, g: isNaN(g) ? 255 : g, b: isNaN(b) ? 255 : b };
}

function getEffectiveMoodColor() {
  if (!bgColorCurrent) return moodColor;
  // Blend 70% toward AI background, 30% mood/circadian keeps emotional + time-of-day influence
  return {
    r: lerp(moodColor.r, bgColorCurrent.r, 0.7),
    g: lerp(moodColor.g, bgColorCurrent.g, 0.7),
    b: lerp(moodColor.b, bgColorCurrent.b, 0.7),
  };
}

function updateColorFields(dt) {
  if (colorFieldsTarget.length === 0 && colorFields.length === 0) return;

  const speed = 0.03;
  while (colorFields.length < colorFieldsTarget.length) {
    const tgt = colorFieldsTarget[colorFields.length];
    colorFields.push({
      r: hexToRgb(tgt.color).r, g: hexToRgb(tgt.color).g, b: hexToRgb(tgt.color).b,
      cx: tgt.cx, cy: tgt.cy, radius: tgt.radius,
      blend: tgt.blend || 'soft-light',
      opacity: tgt.opacity != null ? tgt.opacity : 0.9,
      blur: tgt.blur || 0,
      pulse: tgt.pulse || null,
      drift: tgt.drift || null,
      _driftPhase: Math.random() * Math.PI * 2,
      _pulsePhase: Math.random() * Math.PI * 2,
      alpha: 0,
    });
  }
  while (colorFields.length > colorFieldsTarget.length) {
    const cf = colorFields[colorFields.length - 1];
    cf.alpha = lerp(cf.alpha, 0, speed * 2);
    if (cf.alpha < 0.01) { colorFields.pop(); }
    else break;
  }

  for (let i = 0; i < Math.min(colorFields.length, colorFieldsTarget.length); i++) {
    const cf = colorFields[i];
    const tgt = colorFieldsTarget[i];
    const tgtColor = hexToRgb(tgt.color);
    cf.r = lerp(cf.r, tgtColor.r, speed);
    cf.g = lerp(cf.g, tgtColor.g, speed);
    cf.b = lerp(cf.b, tgtColor.b, speed);
    cf.cx = lerp(cf.cx, tgt.cx, speed);
    cf.cy = lerp(cf.cy, tgt.cy, speed);
    cf.radius = lerp(cf.radius, tgt.radius, speed);
    cf.opacity = lerp(cf.opacity, tgt.opacity != null ? tgt.opacity : 0.9, speed);
    cf.blur = lerp(cf.blur, tgt.blur || 0, speed);
    cf.blend = tgt.blend || 'soft-light';
    cf.pulse = tgt.pulse || null;
    cf.drift = tgt.drift || null;
    cf.alpha = lerp(cf.alpha, 1, speed);
  }
}

function updateAtmosphere(dt) {
  // Blend circadian base color with mood color
  const circ = circadianBaseColor();
  const circWeight = 0.5;
  const moodSpeed = 0.025;
  moodColor.r = lerp(moodColor.r, moodTarget.r * (1 - circWeight) + circ.r * circWeight, moodSpeed);
  moodColor.g = lerp(moodColor.g, moodTarget.g * (1 - circWeight) + circ.g * circWeight, moodSpeed);
  moodColor.b = lerp(moodColor.b, moodTarget.b * (1 - circWeight) + circ.b * circWeight, moodSpeed);

  // Decay mood toward neutral
  moodTarget.r = lerp(moodTarget.r, circ.r, 0.005);
  moodTarget.g = lerp(moodTarget.g, circ.g, 0.005);
  moodTarget.b = lerp(moodTarget.b, circ.b, 0.005);

  // Lerp bgColorCurrent toward AI-specified background target
  if (bgColorTarget) {
    const tgtRgb = hexToRgb(bgColorTarget);
    if (!bgColorCurrent) {
      bgColorCurrent = { r: moodColor.r, g: moodColor.g, b: moodColor.b };
    }
    const bgSpeed = 0.025; // ~1.3s to converge at 60fps
    bgColorCurrent.r = lerp(bgColorCurrent.r, tgtRgb.r, bgSpeed);
    bgColorCurrent.g = lerp(bgColorCurrent.g, tgtRgb.g, bgSpeed);
    bgColorCurrent.b = lerp(bgColorCurrent.b, tgtRgb.b, bgSpeed);
  } else if (bgColorCurrent) {
    // Decay back to moodColor when AI clears background
    const decaySpeed = 0.04;
    bgColorCurrent.r = lerp(bgColorCurrent.r, moodColor.r, decaySpeed);
    bgColorCurrent.g = lerp(bgColorCurrent.g, moodColor.g, decaySpeed);
    bgColorCurrent.b = lerp(bgColorCurrent.b, moodColor.b, decaySpeed);
    const diff = Math.abs(bgColorCurrent.r - moodColor.r)
               + Math.abs(bgColorCurrent.g - moodColor.g)
               + Math.abs(bgColorCurrent.b - moodColor.b);
    if (diff < 1.5) bgColorCurrent = null;
  }

  // Sync mood color to CSS variables for global UI linkage
  updateMoodCSS();

  // Lerp color fields toward target
  updateColorFields(dt);

  // Update pixel sprites (fly-out animation)
  updatePixelSprites(dt);

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
// Visual state persistence — save every 2s so refresh recovers mood + face
// ═══════════════════════════════════════════
let _lastSaveTime = 0;
const _SAVE_INTERVAL = 2; // seconds

function saveVisualState() {
  const now = performance.now() / 1000;
  if (now - _lastSaveTime < _SAVE_INTERVAL) return;
  _lastSaveTime = now;
  try {
    var st = {
      ts: Date.now(),
      curParams: curParams,
      tgtParams: tgtParams,
      moodColor: moodColor,
      moodTarget: moodTarget,
      bgColorTarget: bgColorTarget,
      bgColorCurrent: bgColorCurrent,
      colorFields: colorFields.map(function(cf) { return { r:cf.r, g:cf.g, b:cf.b, cx:cf.cx, cy:cf.cy, radius:cf.radius, alpha:cf.alpha, blend:cf.blend, opacity:cf.opacity, blur:cf.blur, pulse:cf.pulse, drift:cf.drift }; }),
      sequence: sequence,
      seqIdx: seqIdx,
      seqElapsed: seqElapsed,
      replyText: replyText,
      dlgText: (typeof dlgText !== 'undefined' ? dlgText : ''),
      state: (typeof state !== 'undefined' ? state : STATE.STARFIELD),
      storyPaused: (typeof storyPaused !== 'undefined' ? storyPaused : false),
      storyBuffer: (typeof storyBuffer !== 'undefined' ? storyBuffer : []),
    };
    localStorage.setItem('easytalk_visual', JSON.stringify(st));
  } catch(e) { /* quota exceeded, ignore */ }
}

function loadVisualState() {
  try {
    var raw = localStorage.getItem('easytalk_visual');
    if (!raw) return false;
    var saved = JSON.parse(raw);
    if (Date.now() - saved.ts > 5 * 60 * 1000) { localStorage.removeItem('easytalk_visual'); return false; }
    if (saved.curParams) curParams = saved.curParams;
    if (saved.tgtParams) tgtParams = saved.tgtParams;
    if (saved.moodColor) moodColor = saved.moodColor;
    if (saved.moodTarget) moodTarget = saved.moodTarget;
    if (saved.bgColorTarget !== undefined) bgColorTarget = saved.bgColorTarget;
    if (saved.bgColorCurrent) bgColorCurrent = saved.bgColorCurrent;
    if (saved.colorFields && saved.colorFields.length) colorFields = saved.colorFields;
    if (saved.sequence) { sequence = saved.sequence; seqIdx = saved.seqIdx || 0; seqElapsed = saved.seqElapsed || 0; replyText = saved.replyText || ''; }
    if (saved.dlgText && typeof dlgText !== 'undefined') dlgText = saved.dlgText;
    if (saved.state && typeof state !== 'undefined') state = saved.state;
    if (saved.storyPaused && typeof storyPaused !== 'undefined') storyPaused = saved.storyPaused;
    if (saved.storyBuffer && typeof storyBuffer !== 'undefined') storyBuffer = saved.storyBuffer;
    return true;
  } catch(e) { return false; }
}

// ═══════════════════════════════════════════
// Kaomoji data — 8 categories, ~200 curated emoticons
// ═══════════════════════════════════════════
var KAOMOJI_DATA = {
  happy: { label: '开心', items: [
    '(◕‿◕)', '(≧◡≦)', 'ヽ(>∀<☆)ノ', '(｡◕‿◕｡)', '╰(▔∀▔)╯',
    '(◍•ᴗ•◍)', '(｡•̀ᴗ-́)✧', '(ﾉ◕ヮ◕)ﾉ', '٩(◕‿◕｡)۶', '(๑˃̵ᴗ˂̵)و',
    '(￣▽￣)ノ', '(●´ω｀●)', '♪(´▽｀)', '( ＾∇＾)', '(⌒▽⌒)',
    'ヾ(☆▽☆)', '＼(^ω^＼)', '(ﾉ´ヮ´)ﾉ*:･ﾟ✧', '(◠‿◠✿)', '(๑•̀ㅂ•́)و✧',
    '(｡･ω･｡)ﾉ♡', '☆*:.｡.o(≧▽≦)o.｡.:*☆', '(づ｡◕‿‿◕｡)づ', '(✿◠‿◠)', '╰(*´︶`*)╯',
    'o(≧∇≦o)', '(ﾟ∀ﾟ)', '(´｡• ᵕ •｡`)', '(｡ﾉω＼｡)', '(*^▽^*)'
  ]},
  sad: { label: '难过', items: [
    '(╥﹏╥)', '(´；ω；`)', '(｡•́︿•̀｡)', '(╯︵╰)', '(｡ŏ﹏ŏ)',
    '(´-﹏-`；)', 'ಥ_ಥ', '(´°̥̥̥̥̥̥̥̥ω°̥̥̥̥̥̥̥̥｀)', '(╥_╥)', '(｡T ω T｡)',
    '(´；Д；｀)', '(´;︵;`)', '(｡•́__ก̀｡)', '˚‧º·(˚ ˃̣̣̥᷄⌓˂̣̣̥᷅ )‧º·˚', '(´°ω°｀)',
    '｡ﾟ(ﾟ´Д｀ﾟ)ﾟ｡', '┗( T﹏T )┛', '(｡╯︵╰｡)', '（；へ：）', '(´-ι_-｀)',
    '｡ﾟ･ (>﹏<) ･ﾟ｡', '(:´༎ຶД༎ຶ`)', '。゜゜(´Ｏ`) ゜゜。', '(｡•̩̩̩́ ᆺ •̩̩̩̀｡)', 'o(╥﹏╥)o'
  ]},
  surprise: { label: '惊讶', items: [
    'Σ(°△°)', '(⊙_⊙)', '(゜ロ゜)', '∑(O_O；)', '(;ﾟ∇ﾟ)',
    'w(°ｏ°)w', '(⊙﹏⊙)', '(」゜ロ゜)」', 'ヽ(°〇°)ﾉ', 'Σ(ﾟДﾟ)',
    '(°ロ°)', '(屮ﾟДﾟ)屮', 'щ(゜ロ゜щ)', 'Σ(●ﾟдﾟ●)', '(º ロ º)',
    '(((╹д╹;)))', '(Ω_Ω)', 'ミ●﹏☉ミ', '（○Ａ○）', '＼(º □ º l|l)/'
  ]},
  cute: { label: '可爱', items: [
    '✿◕ ‿ ◕✿', '(◍•ᴗ•◍)', '(｡♥‿♥｡)', '(◕ᴗ◕✿)', 'ʕ•ᴥ•ʔ',
    '(◕‿◕✿)', '(◍•ᴗ•◍)❤', '(｡･ω･｡)', '(✿ ♥‿♥)', '✿♥‿♥✿',
    '(づ￣ ³￣)づ', '(｡’▽’｡)♡', '(•ө•)♡', '(๑>ᴗ<๑)', '(｡ꏿ﹏ꏿ｡)',
    '(◠ω◠✿)', '(◡‿◡✿)', '(｡✿‿✿｡)', '(ﾉ´ з `)ノ', '(♡˙︶˙♡)',
    '꒰◍ᐡᐤᐡ◍꒱', '(ᵔ◡ᵔ)', '(◕‿◕)♡', '✧(｡•̀ᴗ-)✧', '◝(⁰▿⁰)◜',
    '(๑˘︶˘๑)', '(◡ ω ◡)', '(.❛ ᴗ ❛.)', '(｡´ ‿｀｡)♡', '(◍˃̶ᗜ˂̶◍)✩'
  ]},
  angry: { label: '生气', items: [
    '(╬ Ò﹏Ó)', '(＃`Д´)', '(ノಠ益ಠ)ノ', '(ꐦ°᷄д°᷅)', '(╯°□°）╯',
    '(｀Д´)', '(ㆆ_ㆆ)', '(;¬_¬)', '(◣_◢)', '(-_-メ)',
    '(｀へ´)', '(╬ﾟ◥益◤ﾟ)', '(҂ ｰ̀дｰ́ )', '(◔ д ◔)', '(≖_≖ )',
    '(ヽ´ω`)', '(V●ᴥ●V)??', '(╯ಠ_ರೃ)╯', '（▼へ▼メ）', '(`皿´＃)'
  ]},
  daily: { label: '日常', items: [
    '(・ω・)ノ', '(￣▽￣)', '(´-ω-`)', '( ・◇・)', '(￣ω￣)',
    '（￣▽￣）', '(ーー;)', '(´▽｀;)', '(￣～￣)', '(=_=)',
    '(～﹃～)~zZ', 'φ(．．)', '(*￣▽￣)b', '(o゜▽゜)o☆', '╮(￣▽￣)╭',
    '(´･ω･`)', '(´∀｀)', '(。-ω-)zzz', '( ˘ ³˘)♥', '(￣ε￣")',
    '( ´ ▽ ` )', '⇨ (╹◡╹)', 'ψ(｀∇´)ψ', 'щ(º∀º)щ', '(*´▽｀*)'
  ]},
  animal: { label: '动物', items: [
    'ʕ•ᴥ•ʔ', '(=^・ω・^=)', '(￣(工)￣)', '(ﾐㅇㅅㅆ)', '(=｀ェ´=)',
    '／(=･ｪ･=)＼', '(=^ ◡ ^=)', '(ᵔᴥᵔ)', '∪･ω･∪', 'V●ᴥ●V',
    'ฅ^•ﻌ•^ฅ', 'ʕ·͡ᴥ·ʔ', '(≡^∇^≡)', '(=①ω①=)', '(=;ω;=)',
    '₍ᐢ•ﻌ•ᐢ₎*･ﾟ✧', '꒰ ⸝⸝ɞ̴̶̷ ·̮ ɞ̴̶̷⸝⸝꒱', 'ଘ(๑•ᴗ•๑)ଓ', '／(≧ x ≦)＼', '₍ᐢɞ̴̶̷ᗜɞ̴̶̷ᐢ₎',
    '(◕ᴥ◕)', '（＾・ω・＾✿）', '(ﾐ´لﻌﾐ)', 'ᵔᴥᵔ', '◕〖▪ ڿ ▪〗◕'
  ]},
  special: { label: '特殊', items: [
    '(╯°□°)╯︵ ┻━┻', '(☞ﾟヮﾟ)☞', '¯\\_(ツ)_/¯', '( ͡° ͜ʖ ͡°)', '┬─┬ノ( º _ ºノ)',
    '(シ_ _)シ', 'ಠ_ಠ', '(￣ー￣)ﾆﾔﾘ', '(≖ ‿ ≖)', '~(˘▾˘~)',
    'ᕙ(⇀‸↼‶)ᕗ', '(๑•̀ㅁ•́ฅ)', '♪～(´ε｀ )', '( う-´)づ︻╦̵̵̿╤──', '(⌐■_■)',
    '(。･∀･)ﾉ゛', '━╤デ╦︻(▀̿Ĺ̯▀̿ ̿)', '(˵¯͒〰¯͒˵)', 'ᕦ(ò_óˇ)ᕤ', '( •_•)>⌐■-■',
    '(´~`)', '(∩｀-´)⊃━☆ﾟ.*･｡ﾟ', '( ﾟ▽ﾟ)/', '(；一_一)', '⚆ _ ⚆'
  ]}
};
var KAOMOJI_CATEGORIES = Object.keys(KAOMOJI_DATA).map(function(k) {
  return { id: k, label: KAOMOJI_DATA[k].label };
});
var activeKaomojiCat = 'happy';

// ═══════════════════════════════════════════
// Particles / Stars
