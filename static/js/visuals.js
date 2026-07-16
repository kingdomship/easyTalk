// @ts-check
// ═══════════════════════════════════════════
const NUM_STARS = 180;
let stars = [];
let functionalPoints = []; // {starIndex, type:'diary'|'news', data:{...}}
let faceCS = 10; // cell size for face rendering
let faceOx = 0, faceOy = 0; // face origin on canvas

function makeStar(overrides = {}) {
  return {
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    size: 0.8 + Math.random() * 2.2,
    brightness: 0.3 + Math.random() * 0.7,
    phase: Math.random() * Math.PI * 2,
    speed: 0.3 + Math.random() * 0.7,
    driftX: (Math.random() - 0.5) * 0.15,
    driftY: (Math.random() - 0.5) * 0.15,
    color: null, // null = white default
    isFunctional: false,
    funcType: null,
    funcData: null,
    // Convergence target
    targetX: null, targetY: null, targetColor: null,
    // Trail
    trail: [],
    ...overrides,
  };
}

let _starfieldGen = 0;

function initStarfield() {
  stars = [];
  for (let i = 0; i < NUM_STARS; i++) stars.push(makeStar());
  functionalPoints = [];
  // Generation counter prevents race condition on rapid re-init
  const gen = ++_starfieldGen;
  // Fetch diary and news data to create functional points
  fetch('/api/diary').then(r=>r.json()).then(diaries => {
    if (_starfieldGen !== gen) return;
    if (!Array.isArray(diaries) || diaries.length === 0) return;
    const recent = diaries.slice(0, 4);
    recent.forEach((d, i) => {
      if (i >= stars.length) return;
      const s = stars[i * 7 + 3]; // spread across starfield
      if (!s) return;
      s.isFunctional = true;
      s.funcType = 'diary';
      s.funcData = d;
      s.size = 2.5 + Math.random() * 1.5;
      s.color = '#ffd700';
      s.speed = 0.8 + Math.random() * 0.4;
      functionalPoints.push({ star: s, type: 'diary', data: d });
    });
  }).catch(()=>{});
  fetch('/api/news').then(r=>r.json()).then(news => {
    if (_starfieldGen !== gen) return;
    if (!Array.isArray(news) || news.length === 0) return;
    const top = news.slice(0, 7);
    top.forEach((n, i) => {
      const idx = 20 + i * 13;
      if (idx >= stars.length) return;
      const s = stars[idx];
      if (!s || s.isFunctional) return;
      s.isFunctional = true;
      s.funcType = 'news';
      s.funcData = n;
      s.size = 2 + Math.random() * 1.8;
      s.color = '#00e5ff';
      s.speed = 0.9 + Math.random() * 0.5;
      functionalPoints.push({ star: s, type: 'news', data: n });
    });
  }).catch(()=>{});
}

function recomputeFaceLayout() {
  faceCS = Math.min(canvas.width, canvas.height) / 76;
  faceOx = canvas.width / 2 - 32 * faceCS;
  faceOy = canvas.height / 2 - 32 * faceCS;
}

function updateFacePixelTargets() {
  recomputeFaceLayout();
  const facePixels = getFacePixels(curParams);
  // Shuffle and assign to stars
  const shuffled = [...facePixels];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  const count = Math.min(stars.length, shuffled.length);
  for (let i = 0; i < stars.length; i++) {
    if (i < count) {
      const fp = shuffled[i];
      stars[i].targetX = faceOx + fp.c * faceCS + faceCS / 2;
      stars[i].targetY = faceOy + fp.r * faceCS + faceCS / 2;
      stars[i].targetColor = fp.color;
    } else {
      // Fly outward
      const angle = Math.random() * Math.PI * 2;
      const dist = 300 + Math.random() * 500;
      stars[i].targetX = canvas.width / 2 + Math.cos(angle) * dist;
      stars[i].targetY = canvas.height / 2 + Math.sin(angle) * dist;
      stars[i].targetColor = null;
    }
  }
}

// ═══════════════════════════════════════════
// Drawing helpers
// ═══════════════════════════════════════════
function drawStar(s, alpha = 1) {
  const a = s.brightness * alpha;
  if (a < 0.02) return;
  const color = s.color || '#ffffff';
  ctx.fillStyle = color;
  ctx.globalAlpha = a;
  ctx.beginPath();
  ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
  ctx.fill();
  // Glow for functional points
  if (s.isFunctional && s.size > 1.8) {
    ctx.fillStyle = color;
    ctx.globalAlpha = a * 0.2;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.size * 2.5, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

// Mood-driven star color temperature — warm mood → warmer white, cool mood → cooler white
function moodStarTint() {
  const warmth = (moodColor.r - moodColor.b) / 255;
  const strength = 0.12;
  const tr = Math.round(255 + warmth * 255 * strength);
  const tg = Math.round(255 - Math.abs(warmth) * 255 * strength * 0.5);
  const tb = Math.round(255 - warmth * 255 * strength);
  return 'rgb(' + Math.min(255, Math.max(220, tr)) + ',' + Math.min(255, Math.max(220, tg)) + ',' + Math.min(255, Math.max(220, tb)) + ')';
}

// Render AI-controlled color fields as soft radial glows (Rothko-style)
function drawColorFields() {
  if (colorFields.length === 0) return;
  ctx.save();
  ctx.globalCompositeOperation = 'screen';
  for (const cf of colorFields) {
    if (cf.alpha < 0.01) continue;
    const x = cf.cx * canvas.width;
    const y = cf.cy * canvas.height;
    const r = cf.radius * Math.max(canvas.width, canvas.height) * 0.7;
    const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
    const cr = Math.round(cf.r), cg = Math.round(cf.g), cb = Math.round(cf.b);
    grad.addColorStop(0, 'rgba(' + cr + ',' + cg + ',' + cb + ',' + (cf.alpha * 0.35).toFixed(2) + ')');
    grad.addColorStop(0.5, 'rgba(' + cr + ',' + cg + ',' + cb + ',' + (cf.alpha * 0.12).toFixed(2) + ')');
    grad.addColorStop(1, 'rgba(' + cr + ',' + cg + ',' + cb + ',0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }
  ctx.restore();
}

// ═══════════════════════════════════════════
// Meteor showers
// ═══════════════════════════════════════════
let meteors = [];
let meteorShowerTimer = 15 + Math.random() * 30; // seconds until next shower
let meteorShowerActive = false;
let showerMeteorsLeft = 0;
let showerCooldown = 0;

function spawnMeteor() {
  const x = Math.random() * canvas.width;
  const y = Math.random() * canvas.height * 0.4;
  const len = 80 + Math.random() * 150;
  const angle = Math.PI / 6 + Math.random() * Math.PI / 5;
  meteors.push({
    x, y,
    vx: Math.cos(angle) * (400 + Math.random() * 300),
    vy: Math.sin(angle) * (400 + Math.random() * 300),
    life: 1.0,
    len,
    angle,
    hue: Math.random() < 0.3 ? 40 + Math.random() * 20 : 0, // occasional gold meteor
  });
}

function updateMeteors(dt) {
  // Shower timer
  meteorShowerTimer -= dt;
  if (meteorShowerTimer <= 0 && !meteorShowerActive) {
    meteorShowerActive = true;
    showerMeteorsLeft = 5 + Math.floor(Math.random() * 8);
    showerCooldown = 0;
    meteorShowerTimer = 25 + Math.random() * 40;
  }

  // Spawn meteors during shower
  if (meteorShowerActive) {
    showerCooldown -= dt;
    if (showerCooldown <= 0 && showerMeteorsLeft > 0) {
      spawnMeteor();
      showerMeteorsLeft--;
      showerCooldown = 0.15 + Math.random() * 0.35;
    }
    if (showerMeteorsLeft <= 0 && meteors.length === 0) {
      meteorShowerActive = false;
    }
  } else if (Math.random() < 0.004) {
    // Occasional lone meteor outside showers
    spawnMeteor();
  }

  // Update active meteors
  for (const m of meteors) {
    m.x += m.vx * dt;
    m.y += m.vy * dt;
    m.life -= dt * 0.8;
  }
  meteors = meteors.filter(m => m.life > 0 &&
    m.x > -200 && m.x < canvas.width + 200 && m.y > -200 && m.y < canvas.height + 200);
}

function drawMeteors() {
  for (const m of meteors) {
    const x2 = m.x - Math.cos(m.angle) * m.len * m.life;
    const y2 = m.y - Math.sin(m.angle) * m.len * m.life;
    const grad = ctx.createLinearGradient(m.x, m.y, x2, y2);
    const hue = m.hue || 0;
    const headColor = hue > 0
      ? `hsla(${hue}, 80%, 70%, ${m.life})`
      : `rgba(255,255,255,${m.life * 0.9})`;
    grad.addColorStop(0, headColor);
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.strokeStyle = grad;
    ctx.lineWidth = 1.5 * m.life;
    ctx.beginPath();
    ctx.moveTo(m.x, m.y);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    // Head glow
    ctx.fillStyle = hue > 0
      ? `hsla(${hue}, 80%, 80%, ${m.life * 0.6})`
      : `rgba(255,255,255,${m.life * 0.5})`;
    ctx.beginPath();
    ctx.arc(m.x, m.y, 2 * m.life, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ═══════════════════════════════════════════
// Memory stars — persistent diary markers
// ═══════════════════════════════════════════
let memoryStars = [];

function hashToPosition(dateStr, idx) {
  let h = 0;
  for (let i = 0; i < dateStr.length; i++) h = ((h << 5) - h) + dateStr.charCodeAt(i) | 0;
  const angle = ((h * 137 + idx * 53) % 1000) / 1000 * Math.PI * 2;
  const dist = 0.15 + ((h * 71 + idx * 37) % 1000) / 1000 * 0.55; // 15%-70% of screen
  return {
    x: canvas.width / 2 + Math.cos(angle) * canvas.width * dist,
    y: canvas.height / 3 + Math.sin(angle) * canvas.height * dist,
  };
}

async function initMemoryStars() {
  try {
    const resp = await fetch('/api/diary?limit=30');
    const diaries = await resp.json();
    if (!Array.isArray(diaries)) return;
    for (let i = 0; i < diaries.length; i++) {
      const d = diaries[i];
      const pos = hashToPosition(d.date, i);
      memoryStars.push({
        x: pos.x, y: pos.y,
        date: d.date,
        mood: d.content ? (d.content.match(/[\p{Emoji_Presentation}]/u) || ['✨'])[0] : '✨',
        chat_count: d.chat_count || 0,
        baseSize: 1.2 + Math.min(d.chat_count / 10, 2.5),
        phase: Math.random() * Math.PI * 2,
        color: d.chat_count > 10 ? '#ffd700' : d.chat_count > 5 ? '#ffb74d' : '#88ccff',
      });
    }
  } catch(e) { /* silent */ }
}

function drawMemoryStars() {
  const t = performance.now() / 1000;
  for (const ms of memoryStars) {
    const pulse = 0.6 + 0.4 * Math.sin(t * 1.5 + ms.phase);
    const alpha = 0.4 + 0.3 * pulse;
    ctx.fillStyle = ms.color;
    ctx.globalAlpha = alpha;
    ctx.beginPath();
    ctx.arc(ms.x, ms.y, ms.baseSize * pulse, 0, Math.PI * 2);
    ctx.fill();
    // Outer glow
    ctx.fillStyle = ms.color;
    ctx.globalAlpha = alpha * 0.25;
    ctx.beginPath();
    ctx.arc(ms.x, ms.y, ms.baseSize * pulse * 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }
}

function checkMemoryStarClick(cx, cy) {
  for (const ms of memoryStars) {
    const dx = cx - ms.x, dy = cy - ms.y;
    if (Math.sqrt(dx*dx + dy*dy) < ms.baseSize * 4) {
      window._pendingDiaryDate = ms.date;
      openAuxiliary('diary');
      return true;
    }
  }
  return false;
}

// ═══════════════════════════════════════════
// State: STARFIELD
// ═══════════════════════════════════════════
function updateStarfield(dt) {
  updateMeteors(dt);
  for (const s of stars) {
    s.x += s.driftX * dt * 60;
    s.y += s.driftY * dt * 60;
    // Wrap around
    if (s.x < -20) s.x = canvas.width + 20;
    if (s.x > canvas.width + 20) s.x = -20;
    if (s.y < -20) s.y = canvas.height + 20;
    if (s.y > canvas.height + 20) s.y = -20;
    // Reset convergence targets
    s.targetX = null; s.targetY = null; s.targetColor = null;
    // Slowly drift functional stars back toward random area
    if (s.isFunctional && s.driftX === 0 && s.driftY === 0) {
      s.driftX = (Math.random() - 0.5) * 0.1;
      s.driftY = (Math.random() - 0.5) * 0.1;
    }
  }
}

function drawConstellations(mx, my) {
  const MAX_DIST = 120;
  const lines = [];
  for (let i = 0; i < stars.length; i++) {
    for (let j = i + 1; j < stars.length; j++) {
      const dx = stars[i].x - stars[j].x;
      const dy = stars[i].y - stars[j].y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < MAX_DIST) {
        const alpha = (1 - dist / MAX_DIST) * 0.12;
        lines.push({ i, j, alpha });
      }
    }
  }
  for (const l of lines) {
    ctx.strokeStyle = `rgba(124,131,255,${l.alpha})`;
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(stars[l.i].x, stars[l.i].y);
    ctx.lineTo(stars[l.j].x, stars[l.j].y);
    ctx.stroke();
  }
  // Cursor-connected stars
  if (mx != null) {
    const NEAR = 100;
    for (const s of stars) {
      const dx = s.x - mx, dy = s.y - my;
      const dist = Math.sqrt(dx*dx+dy*dy);
      if (dist < NEAR) {
        const alpha = (1 - dist / NEAR) * 0.15;
        ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
        ctx.lineWidth = 0.3;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(mx, my);
        ctx.stroke();
        s.brightness = Math.max(s.brightness, 0.7);
      }
    }
  }
}

let cursorX = null, cursorY = null;

function drawStarfield() {
  // Mood-driven gradient — shifts warm/cool based on conversation sentiment
  const r = Math.round(moodColor.r), g = Math.round(moodColor.g), b = Math.round(moodColor.b);
  const grad = ctx.createRadialGradient(canvas.width/2, canvas.height/3, 0, canvas.width/2, canvas.height, canvas.height);
  grad.addColorStop(0, `rgb(${r},${g},${b})`);
  grad.addColorStop(0.5, `rgb(${Math.round(r*0.6)},${Math.round(g*0.6)},${Math.round(b*0.7)})`);
  grad.addColorStop(1, `rgb(${Math.round(r*0.15)},${Math.round(g*0.15)},${Math.round(b*0.15)})`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Overlay AI-controlled color fields (Rothko-style abstract regions)
  drawColorFields();

  const t = performance.now() / 1000;
  const breathe = 1 + 0.06 * Math.sin(t * 0.52); // ~12s breathing cycle
  const circBright = circadianBrightness();
  const starTint = moodStarTint();
  for (const s of stars) {
    const twinkle = 0.5 + 0.5 * Math.sin(t * s.speed + s.phase);
    if (s.isFunctional) {
      s.brightness = (0.6 + twinkle * 0.4) * circBright * breathe;
      // Keep identity color (gold/cyan) — don't override
    } else {
      s.brightness = (0.3 + twinkle * 0.7) * circBright * breathe;
      s.color = starTint;  // mood-tinted white
    }
    drawStar(s);
  }
  drawConstellations(cursorX, cursorY);
  drawMeteors();
  drawMemoryStars();
}

// ═══════════════════════════════════════════
// State: CONVERGING
// ═══════════════════════════════════════════
let convergeStart = 0;
const CONVERGE_DURATION = 1.5; // seconds

function startConvergence() {
  state = STATE.CONVERGING;
  convergeStart = performance.now() / 1000;
  chatFadeIn = 0;
  initSparkleParticles();
  updateFacePixelTargets();
  for (const s of stars) {
    s.trail = [];
  }
}

function updateConvergence(dt) {
  const elapsed = performance.now() / 1000 - convergeStart;
  const progress = Math.min(1, elapsed / CONVERGE_DURATION);
  // Ease-out
  const t = 1 - Math.pow(1 - progress, 3);

  for (const s of stars) {
    if (s.targetX == null) continue;
    const startX = s.x, startY = s.y;
    s.x = lerp(startX, s.targetX, t);
    s.y = lerp(startY, s.targetY, t);
    s.brightness = 0.5 + 0.5 * Math.sin(performance.now()/1000 * 3 + s.phase);

    // Trail
    s.trail.push({ x: s.x, y: s.y, life: 1 });
    if (s.trail.length > 8) s.trail.shift();
    for (const tr of s.trail) tr.life -= dt * 4;
    s.trail = s.trail.filter(tr => tr.life > 0);

    if (s.targetColor && progress > 0.3) {
      s.color = s.targetColor;
    }
  }

  if (progress >= 1) {
    state = STATE.CHAT;
    // Move non-face stars off-screen, keep face stars in position
    for (const s of stars) {
      if (s.targetX != null) { s.x = s.targetX; s.y = s.targetY; }
      s.trail = [];
    }
    // Scatter non-face stars outward for background use
    for (let i = 0; i < stars.length; i++) {
      if (stars[i].targetColor == null) {
        const angle = Math.random() * Math.PI * 2;
        const dist = 50 + Math.random() * 150;
        stars[i].x = canvas.width / 2 + Math.cos(angle) * dist;
        stars[i].y = canvas.height / 2 + Math.sin(angle) * dist;
      }
    }
    inputRow.classList.add('visible');
    loadTopics();
    input.focus();
  }
}

function drawPokeSparkles() {
  for (const s of pokeSparkles) {
    ctx.fillStyle = `rgba(255,215,0,${s.life})`;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.size * s.life, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawConvergence() {
  // Background
  ctx.fillStyle = '#080818';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (const s of stars) {
    // Draw trails
    for (const tr of s.trail) {
      ctx.fillStyle = s.color || '#ffffff';
      ctx.globalAlpha = tr.life * 0.3;
      ctx.beginPath();
      ctx.arc(tr.x, tr.y, s.size * 0.6, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    drawStar(s);
  }
}

// ═══════════════════════════════════════════
// State: CHAT
// ═══════════════════════════════════════════
let blinkTimer = 0, isBlinking = false;
let microTimer = null; // micro-expression cooldown
let microExprKey = '';  // key being micro-expressed
let microExprOffset = 0;  // offset amount
let microExprRemaining = 0;  // seconds remaining
let faceBob = 0, faceFrame = 0;

let sparkleParticles = [];
const NUM_SPARKLES = 80;
let chatFadeIn = 0; // 0-1 fade-in for face after convergence

function initSparkleParticles() {
  sparkleParticles = [];
  for (let i = 0; i < NUM_SPARKLES; i++) {
    sparkleParticles.push({
      idx: i,
      phase: Math.random() * Math.PI * 2,
      speed: 0.5 + Math.random() * 1.5,
    });
  }
}

function updateChat(dt) {
  faceFrame++;
  faceBob = Math.sin(faceFrame * 0.02) * 2;

  // Fade in face from convergence
  if (chatFadeIn < 1) chatFadeIn = Math.min(1, chatFadeIn + dt * 2);

  // Blink
  blinkTimer -= dt;
  if (!isBlinking && blinkTimer <= 0) {
    isBlinking = true;
    setTimeout(() => { isBlinking = false; }, 120);
    blinkTimer = 2.5 + Math.random() * 3;
  }

  // Micro-expressions: subtle idle movements when no active sequence
  // Use time-based decay instead of setTimeout to avoid conflicts with lerp
  if (microExprRemaining > 0) {
    microExprRemaining -= dt;
    if (microExprRemaining <= 0) {
      // Decay complete — apply final blend back to neutral
      tgtParams[microExprKey] = (tgtParams[microExprKey] || 0) - microExprOffset * 0.5;
      microExprKey = '';
      microExprOffset = 0;
    }
  }
  if (microTimer !== null) microTimer -= dt;
  if (microTimer === null || microTimer <= 0) {
    microTimer = 2 + Math.random() * 4; // every 2-6 seconds
    const microKeys = ['eye_pupil', 'brow_asym', 'mouth_width', 'blush', 'head_tilt', 'cheek_raise', 'eye_tension', 'iris_size'];
    microExprKey = microKeys[Math.floor(Math.random() * microKeys.length)];
    microExprOffset = (Math.random() - 0.5) * 0.04;
    microExprRemaining = 0.3 + Math.random() * 0.2; // 300-500ms
    tgtParams[microExprKey] = (tgtParams[microExprKey] || 0) + microExprOffset;
  }

  // Lerp params — faster speed since tgtParams already has eased interpolation
  const speed = 0.25;
  for (const k of Object.keys(curParams)) curParams[k] = lerp(curParams[k], tgtParams[k], speed);

  updateSequence(dt);
  updateAtmosphere(dt);
  recomputeFaceLayout();
}

function drawFaceOnCanvas(params, oy) {
  // Head tilt — pixel shift instead of rotation
  // Add subtle ~8s breathing oscillation
  const t = performance.now() / 1000;
  const headBob = Math.sin(t * 0.78) * 0.03;
  const tiltX = ((params.head_tilt || 0) + headBob) * 3 * faceCS;
  const ox = faceOx + tiltX;

  // Shadow
  const shx = canvas.width / 2 + tiltX, shy = canvas.height / 2 + 10 * faceCS + oy;
  ctx.fillStyle = 'rgba(0,0,0,0.12)';
  ctx.beginPath();
  ctx.ellipse(shx, shy, 25 * faceCS, 10 * faceCS, 0, 0, Math.PI * 2);
  ctx.fill();

  // Face circle (radius 29, outline 27, darker edge 24) — with cheek_puff
  const cheekPuff = params.cheek_puff || 0;
  for (let r = 0; r < GRID; r++)
    for (let cc = 0; cc < GRID; cc++) {
      const d = fd(r, cc);
      let cheekFactor = 0;
      if (cheekPuff > 0) {
        const lDist = Math.sqrt((r-27)**2 + (cc-11)**2);
        const rDist = Math.sqrt((r-27)**2 + (cc-53)**2);
        const cheekDist = Math.min(lDist, rDist);
        if (cheekDist < 14) cheekFactor = Math.max(0, 1 - cheekDist/14);
      }
      const radius = 29 + cheekPuff * 3 * cheekFactor;
      if (d > radius) continue;
      ctx.fillStyle = d > 27 ? FACE_COLORS.outline : (d > 24 ? FACE_COLORS.faceD : FACE_COLORS.face);
      ctx.fillRect(ox + cc * faceCS, faceOy + r * faceCS + oy, faceCS, faceCS);
    }

  // Blush — with cheek_raise shifting circles up
  const blushVal = params.blush || 0;
  const cheekRaise = params.cheek_raise || 0;
  const blushAlpha = 0.08 + blushVal * 0.7;
  if (blushAlpha > 0.02) {
    ctx.globalAlpha = blushAlpha;
    ctx.fillStyle = FACE_COLORS.blush;
    const blushCenterR = Math.round(27 - cheekRaise * 5);
    const blushVR = Math.round(8 - cheekRaise * 3);
    for (let r = blushCenterR - blushVR; r <= blushCenterR + blushVR; r++) {
      for (let cc = 3; cc <= 19; cc++) {
        const vrDist = (r - blushCenterR) / Math.max(1, blushVR);
        if (Math.sqrt((r-blushCenterR)**2 + (cc-11)**2) < blushVR && vrDist > -1.2)
          ctx.fillRect(ox + cc * faceCS, faceOy + r * faceCS + oy, faceCS, faceCS);
      }
    }
    for (let r = blushCenterR - blushVR; r <= blushCenterR + blushVR; r++) {
      for (let cc = 45; cc <= 61; cc++) {
        const vrDist = (r - blushCenterR) / Math.max(1, blushVR);
        if (Math.sqrt((r-blushCenterR)**2 + (cc-53)**2) < blushVR && vrDist > -1.2)
          ctx.fillRect(ox + cc * faceCS, faceOy + r * faceCS + oy, faceCS, faceCS);
      }
    }
    ctx.globalAlpha = 1;
  }

  // Nose wrinkle (AU9) — dark lines at nose bridge
  const noseWrinkle = params.nose_wrinkle || 0;
  if (noseWrinkle > 0.05) {
    ctx.globalAlpha = noseWrinkle * 0.6;
    ctx.fillStyle = FACE_COLORS.dark;
    for (let c = 30; c <= 33; c++) ctx.fillRect(ox + c * faceCS, faceOy + 15 * faceCS + oy, faceCS, faceCS);
    for (let c = 29; c <= 34; c++) ctx.fillRect(ox + c * faceCS, faceOy + 16 * faceCS + oy, faceCS, faceCS);
    ctx.globalAlpha = 1;
  }

  // Eyebrows — 5px wide with visible arch peak
  const baseR = Math.round(lerp(18, 10, params.brow_height));
  const asym = params.brow_asym || 0;
  const lOff = -Math.round(asym * 4), rOff = Math.round(asym * 4);
  ctx.fillStyle = FACE_COLORS.dark;
  for (let i = 0; i < 5; i++) {
    const cc = 14 + i;
    const archOff = (i === 1 || i === 2) ? -1 : 0;
    const tiltOff = Math.round((cc - 16) * (params.brow_angle||0) * 2);
    ctx.fillRect(ox + cc * faceCS, faceOy + (baseR + archOff + tiltOff + lOff) * faceCS + oy, faceCS, faceCS);
  }
  for (let i = 0; i < 5; i++) {
    const cc = 45 + i;
    const archOff = (i === 1 || i === 2) ? -1 : 0;
    const tiltOff = Math.round((cc - 47) * (params.brow_angle||0) * 2);
    ctx.fillRect(ox + cc * faceCS, faceOy + (baseR + archOff + tiltOff + rOff) * faceCS + oy, faceCS, faceCS);
  }

  // Eyes — with eye_curve, eye_tension, iris_size
  function drawEye(cc) {
    const bR = 20;
    let eyeOpen = params.eye_open;
    const wink = params.eye_wink || 0;
    if (wink < -0.5 && cc === 20) eyeOpen = 0.05;
    if (wink > 0.5 && cc === 43) eyeOpen = 0.05;
    const rows = eyeOpen < 0.2 ? 1 : (eyeOpen < 0.6 ? 2 : 4);
    const outerDir = cc < 30 ? 1 : -1;
    const ec = params.eye_curve || 0;
    const tension = params.eye_tension || 0;
    const tc = Math.round(tension * 2); // 0..2 px shrink
    const px = [];
    if (rows === 1) {
      for (let c = cc - 2; c <= cc + 1; c++) px.push({ r: bR, c });
      px.push({ r: bR - 1, c: cc + outerDir * 2 });
      if (ec > 0.3) px.push({ r: bR - 1, c: cc + outerDir * 3 });
    } else if (rows === 2) {
      const tw = Math.round(tension * 1.5);
      for (let c = cc - 3 + tw; c <= cc + 2 - tw; c++) px.push({ r: bR - 2, c });
      for (let c = cc - 2; c <= cc + 1; c++) px.push({ r: bR, c });
    } else {
      const tTop = Math.round(tension);
      const ecUp = ec > 0 ? Math.round(ec) : 0;
      const ecDn = ec < 0 ? Math.round(-ec) : 0;
      for (let c = cc - 2 + tTop; c <= cc + 1 - tTop; c++) {
        const rowOff = (ec > 0 && (c === cc-2 || c === cc+1)) ? ecUp : 0;
        px.push({ r: bR - 4 + rowOff, c });
      }
      for (let c = cc - 4 + tc; c <= cc + 3 - tc; c++) px.push({ r: bR - 3, c });
      for (let c = cc - 4 + tc; c <= cc + 3 - tc; c++) px.push({ r: bR - 2, c });
      for (let c = cc - 3 + tc; c <= cc + 2 - tc; c++) {
        const rowOff = (ec < 0 && (c === cc-3 || c === cc+2)) ? ecDn : 0;
        px.push({ r: bR - 1 + rowOff, c });
      }
    }
    const ps = Math.round((params.eye_pupil || 0) * 3);
    for (let k = 0; k < px.length; k++) px[k].c += ps;
    const iris = params.iris_size != null ? params.iris_size : 0.5;
    const sparkle = params.sparkle || 0;
    const hlR = rows === 1 ? bR : (rows === 2 ? bR - 2 : bR - 3);
    px.push({ r: hlR, c: cc + 2 + ps, hl: true });
    if (rows >= 2) {
      const hlSpread = Math.round(iris * 2);
      px.push({ r: hlR + 1, c: cc + 2 + hlSpread + ps, hl: true, hl2: true });
    }
    if (rows >= 3 && iris > 0.6) {
      px.push({ r: hlR, c: cc + 4 + ps, hl: true, hl3: true });
    }
    for (const ep of px) {
      if (ep.hl3) ctx.fillStyle = lerpH(FACE_COLORS.dark, FACE_COLORS.light, sparkle * 0.25 * iris);
      else if (ep.hl2) ctx.fillStyle = lerpH(FACE_COLORS.dark, FACE_COLORS.light, sparkle * 0.5 * iris);
      else if (ep.hl) ctx.fillStyle = lerpH(FACE_COLORS.dark, FACE_COLORS.light, sparkle);
      else ctx.fillStyle = FACE_COLORS.dark;
      ctx.fillRect(ox + ep.c * faceCS, faceOy + ep.r * faceCS + oy, faceCS, faceCS);
    }
  }
  drawEye(20); drawEye(43);

  // Tear — small blue pixel block
  if ((params.tear || 0) > 0.05) {
    const tearColor = lerpH('#ffffff', '#88ccff', params.tear);
    ctx.fillStyle = tearColor;
    const tearR = 23 + Math.round(params.tear * 2);
    ctx.fillRect(ox + 18 * faceCS, faceOy + tearR * faceCS + oy, faceCS, faceCS);
    ctx.fillRect(ox + 19 * faceCS, faceOy + tearR * faceCS + oy, faceCS, faceCS);
    ctx.fillRect(ox + 18 * faceCS, faceOy + (tearR + 1) * faceCS + oy, faceCS, faceCS);
    ctx.fillRect(ox + 19 * faceCS, faceOy + (tearR + 1) * faceCS + oy, faceCS, faceCS);
  }

  // Sweat drop — left temple (anime style)
  const sweat = params.sweat_drop || 0;
  if (sweat > 0.05) {
    ctx.fillStyle = lerpH(FACE_COLORS.face, '#ccddff', sweat);
    ctx.fillRect(ox + 7 * faceCS, faceOy + 9 * faceCS + oy, faceCS, faceCS);
    ctx.fillRect(ox + 6 * faceCS, faceOy + 10 * faceCS + oy, faceCS, faceCS);
    ctx.fillRect(ox + 7 * faceCS, faceOy + 10 * faceCS + oy, faceCS, faceCS);
    ctx.fillRect(ox + 8 * faceCS, faceOy + 10 * faceCS + oy, faceCS, faceCS);
    ctx.fillRect(ox + 7 * faceCS, faceOy + 11 * faceCS + oy, faceCS, faceCS);
  }

  // Vein pop — temple cross/cruciform
  const vein = params.vein_pop || 0;
  if (vein > 0.05) {
    ctx.globalAlpha = vein * 0.8;
    ctx.fillStyle = '#8b0000';
    for (let c = 7; c <= 9; c++) ctx.fillRect(ox + c * faceCS, faceOy + 9 * faceCS + oy, faceCS, faceCS);
    for (let r = 8; r <= 10; r++) ctx.fillRect(ox + 8 * faceCS, faceOy + r * faceCS + oy, faceCS, faceCS);
    ctx.globalAlpha = 1;
  }

  // Mouth — with lip_pout, lip_stretch, lip_bite, jaw_drop, tongue_out
  const mcc = 32;
  const lipStretch = params.lip_stretch || 0;
  let hw = Math.round(lerp(4, 11, params.mouth_width || 0.6));
  const stretchExtra = Math.round(lipStretch * 3);
  const cs = mcc - hw - stretchExtra, ce = mcc + hw + stretchExtra;
  const ma = params.mouth_asym || 0;
  const jawDrop = params.jaw_drop || 0;
  const lipPout = params.lip_pout || 0;
  const lipBite = params.lip_bite || 0;
  const tongueOut = params.tongue_out || 0;
  const effMouthOpen = Math.max(params.mouth_open || 0, tongueOut > 0.3 ? 0.2 : 0);

  ctx.fillStyle = FACE_COLORS.dark;
  if (effMouthOpen < 0.25) {
    const biteShift = Math.round(lipBite * 3);
    const baseR = 39;
    for (let c = cs; c <= ce; c++) {
      const t = (c - cs) / (ce - cs || 1), edgeF = Math.abs(t - 0.5) * 2;
      const asymOffset = Math.round(ma * (c - mcc) * 0.4);
      const curveAtten = Math.max(0, 1 - lipStretch * 0.7);
      ctx.fillRect(ox + c * faceCS, faceOy + (baseR + Math.round(-(params.mouth_curve||0) * edgeF * 4 * curveAtten) + asymOffset - biteShift) * faceCS + oy, faceCS, faceCS);
    }
    // Lip bite tooth marks
    if (lipBite > 0.2) {
      ctx.fillStyle = lerpH(FACE_COLORS.dark, FACE_COLORS.light, 0.6);
      ctx.fillRect(ox + mcc * faceCS, faceOy + (baseR - 2 - biteShift) * faceCS + oy, faceCS, faceCS);
      ctx.fillRect(ox + (mcc+1) * faceCS, faceOy + (baseR - 2 - biteShift) * faceCS + oy, faceCS, faceCS);
      ctx.fillStyle = FACE_COLORS.dark;
    }
    // Lip pout (closed)
    if (lipPout > 0.1) {
      const poutRows = Math.round(lipPout * 2);
      for (let c = cs + 1; c <= ce - 1; c++)
        for (let pr = 1; pr <= poutRows; pr++)
          ctx.fillRect(ox + c * faceCS, faceOy + (baseR + pr - biteShift) * faceCS + oy, faceCS, faceCS);
    }
  } else {
    const topR = 37 - Math.round(effMouthOpen * 1.6) - Math.round(jawDrop * 2);
    const botR = 39 + Math.round(effMouthOpen * 1.6) + Math.round(jawDrop * 5);
    for (let c = cs + 1; c <= ce - 1; c++) ctx.fillRect(ox + c * faceCS, faceOy + topR * faceCS + oy, faceCS, faceCS);
    for (let c = cs + 1; c <= ce - 1; c++) {
      const isE = (c === cs + 1 || c === ce - 1);
      const asymOffset = Math.round(ma * (c - mcc) * 0.4);
      const curveAtten = Math.max(0, 1 - lipStretch * 0.7);
      ctx.fillRect(ox + c * faceCS, faceOy + (botR + (isE ? Math.round(-(params.mouth_curve||0) * 2 * curveAtten) : Math.round((params.mouth_curve||0) * 0.7 * curveAtten)) + asymOffset) * faceCS + oy, faceCS, faceCS);
      if (lipPout > 0.1 && !isE) {
        const poutRows = Math.round(lipPout * 2);
        for (let pr = 1; pr <= poutRows; pr++)
          ctx.fillRect(ox + c * faceCS, faceOy + (botR + pr + asymOffset) * faceCS + oy, faceCS, faceCS);
      }
    }
    // Tongue out
    if (tongueOut > 0.1) {
      ctx.fillStyle = lerpH('#ff7799', '#ff5577', tongueOut);
      const tongueBase = botR + 2;
      const tongueW = Math.round(lerp(1, 3, tongueOut));
      for (let rr = 0; rr <= Math.round(tongueOut * 3); rr++) {
        const rw = tongueW - (rr > 0 ? Math.round(rr * 0.5) : 0);
        for (let c = mcc - rw; c <= mcc + rw; c++)
          ctx.fillRect(ox + c * faceCS, faceOy + (tongueBase + rr) * faceCS + oy, faceCS, faceCS);
      }
    }
  }
}

function drawSparkleOverlay(oy) {
  const t = performance.now() / 1000;
  const headBob = Math.sin(t * 0.78) * 0.03;
  const tiltX = ((curParams.head_tilt || 0) + headBob) * 3 * faceCS;
  const ox = faceOx + tiltX;
  const facePixels = getFacePixels(curParams);
  if (!facePixels.length) return;
  const fps = facePixels;
  for (const sp of sparkleParticles) {
    const fpIdx = Math.floor(sp.idx / NUM_SPARKLES * fps.length) % fps.length;
    const fp = fps[fpIdx];
    const sparkle = 0.15 + 0.2 * Math.sin(t * sp.speed + sp.phase);
    if (sparkle < 0.05) continue;
    const sx = ox + fp.c * faceCS;
    const sy = faceOy + fp.r * faceCS + oy;
    ctx.fillStyle = '#ffffff';
    ctx.globalAlpha = sparkle;
    ctx.fillRect(sx + faceCS * 0.25, sy + faceCS * 0.25, faceCS * 0.5, faceCS * 0.5);
  }
  ctx.globalAlpha = 1;
}

function drawChat() {
  // Mood-driven radial gradient centered near face position
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  const mr = Math.round(moodColor.r), mg = Math.round(moodColor.g), mb = Math.round(moodColor.b);
  const grad = ctx.createRadialGradient(cx, cy * 0.65, 0, cx, cy, Math.max(canvas.width, canvas.height) * 0.65);
  grad.addColorStop(0, 'rgb(' + mr + ',' + mg + ',' + mb + ')');
  grad.addColorStop(0.5, 'rgb(' + Math.round(mr * 0.8) + ',' + Math.round(mg * 0.8) + ',' + Math.round(mb * 0.82) + ')');
  grad.addColorStop(1, 'rgb(' + Math.round(mr * 0.35) + ',' + Math.round(mg * 0.35) + ',' + Math.round(mb * 0.38) + ')');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Overlay AI-controlled color fields (Rothko-style abstract regions)
  drawColorFields();

  // Draw dim background stars with mood-tinted color
  const t = performance.now() / 1000;
  const starTint = moodStarTint();
  for (let i = 0; i < 25; i++) {
    const s = stars[i];
    const twinkle = 0.5 + 0.5 * Math.sin(t * 1.5 + s.phase);
    ctx.fillStyle = starTint;
    ctx.globalAlpha = 0.05 + twinkle * 0.08;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.size * 0.5, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  // Draw the face properly
  const displayParams = isBlinking ? { ...curParams, eye_open: 0.05 } : curParams;
  drawFaceOnCanvas(displayParams, faceBob);

  // Overlay sparkle particles
  drawSparkleOverlay(faceBob);
}
