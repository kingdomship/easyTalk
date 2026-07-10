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

function initStarfield() {
  stars = [];
  for (let i = 0; i < NUM_STARS; i++) stars.push(makeStar());
  // Assign functional points
  functionalPoints = [];
  // Fetch diary and news data to create functional points
  fetch('/api/diary').then(r=>r.json()).then(diaries => {
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
  faceCS = Math.min(canvas.width, canvas.height) / 38;
  faceOx = canvas.width / 2 - 16 * faceCS;
  faceOy = canvas.height / 2 - 16 * faceCS;
}

function updateFacePixelTargets() {
  recomputeFaceLayout();
  const facePixels = getFacePixels(curParams);
  // Shuffle and assign to stars
  const shuffled = [...facePixels].sort(() => Math.random() - 0.5);
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
      openAuxiliary('diary');
      // Scroll to that date if possible
      setTimeout(() => {
        const cards = auxContent.querySelectorAll('.card');
        for (const card of cards) {
          if (card.textContent.includes(ms.date)) {
            card.scrollIntoView({ behavior: 'smooth' });
            card.style.borderColor = '#ffd700';
            setTimeout(() => { card.style.borderColor = ''; }, 2000);
            break;
          }
        }
      }, 500);
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

  const t = performance.now() / 1000;
  const circBright = circadianBrightness();
  for (const s of stars) {
    const twinkle = 0.5 + 0.5 * Math.sin(t * s.speed + s.phase);
    s.brightness = (0.3 + twinkle * 0.7) * circBright;
    if (s.isFunctional) s.brightness = (0.6 + twinkle * 0.4) * circBright;
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
let faceBob = 0, faceFrame = 0;

let sparkleParticles = [];
const NUM_SPARKLES = 55;
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
  if (microTimer !== null) microTimer -= dt;
  if (microTimer === null || microTimer <= 0) {
    microTimer = 2 + Math.random() * 4; // every 2-6 seconds
    // Brief micro-movement on a random param
    const microKeys = ['eye_pupil', 'brow_asym', 'mouth_width'];
    const key = microKeys[Math.floor(Math.random() * microKeys.length)];
    const orig = tgtParams[key];
    const offset = (Math.random() - 0.5) * 0.04;
    tgtParams[key] = orig + offset;
    setTimeout(() => { tgtParams[key] = orig; }, 300 + Math.random() * 200);
  }

  // Lerp params — faster speed since tgtParams already has eased interpolation
  const speed = 0.25;
  for (const k of Object.keys(curParams)) curParams[k] = lerp(curParams[k], tgtParams[k], speed);

  updateSequence(dt);
  updateAtmosphere(dt);
  recomputeFaceLayout();
}

function drawFaceOnCanvas(params, oy) {
  // Draw the face using the original grid-based approach
  // Shadow
  const cx = canvas.width / 2, cy = canvas.height / 2 + 5 * faceCS + oy;
  ctx.fillStyle = 'rgba(0,0,0,0.12)';
  ctx.beginPath();
  ctx.ellipse(cx, cy, 13 * faceCS, 6 * faceCS, 0, 0, Math.PI * 2);
  ctx.fill();

  // Face circle
  for (let r = 0; r < GRID; r++)
    for (let cc = 0; cc < GRID; cc++) {
      const d = fd(r, cc);
      if (d > 14.5) continue;
      ctx.fillStyle = d > 13 ? FACE_COLORS.outline : (d > 12 ? FACE_COLORS.faceD : FACE_COLORS.face);
      ctx.fillRect(faceOx + cc * faceCS, faceOy + r * faceCS + oy, faceCS, faceCS);
    }

  // Eyebrows
  const baseR = Math.round(lerp(9, 4, params.brow_height));
  const asym = params.brow_asym || 0;
  const lOff = -Math.round(asym * 2), rOff = Math.round(asym * 2);
  for (let i = 0; i < 4; i++) {
    const cc = 7 + i, isInner = i >= 2;
    const rowOff = isInner ? -Math.round(params.brow_angle * 1.5) : Math.round(params.brow_angle * 1.5);
    ctx.fillStyle = FACE_COLORS.dark;
    ctx.fillRect(faceOx + cc * faceCS, faceOy + (baseR + rowOff + lOff) * faceCS + oy, faceCS, faceCS);
  }
  for (let i = 0; i < 4; i++) {
    const cc = 21 + i, isInner = i <= 1;
    const rowOff = isInner ? -Math.round(params.brow_angle * 1.5) : Math.round(params.brow_angle * 1.5);
    ctx.fillStyle = FACE_COLORS.dark;
    ctx.fillRect(faceOx + cc * faceCS, faceOy + (baseR + rowOff + rOff) * faceCS + oy, faceCS, faceCS);
  }

  // Eyes
  function drawEye(cc) {
    const bR = 10, rows = params.eye_open < 0.2 ? 1 : (params.eye_open < 0.6 ? 2 : 3);
    const px = [];
    if (rows === 1) {
      for (let c = cc - 3; c <= cc + 3 && px.length < 6; c++) px.push({ r: bR, c });
    } else if (rows === 2) {
      for (let c = cc - 1; c <= cc + 1; c++) px.push({ r: bR - 1, c });
      px.push({ r: bR + Math.round(-params.eye_curve * 2), c: cc - 1 });
      px.push({ r: bR + Math.round(params.eye_curve), c: cc });
      px.push({ r: bR + Math.round(-params.eye_curve * 2), c: cc + 1 });
    } else {
      px.push({ r: bR - 2, c: cc - 2 }); px.push({ r: bR - 2, c: cc + 1 });
      px.push({ r: bR - 1, c: cc - 2 }); px.push({ r: bR - 1, c: cc + 1 });
      px.push({ r: bR, c: cc - 2 }); px.push({ r: bR, c: cc + 1 });
    }
    const ps = Math.round((params.eye_pupil || 0) * 1.5);
    for (let k = 0; k < px.length; k++) px[k].c += ps;
    const hlR = rows === 1 ? bR : bR - 1;
    px.push({ r: hlR, c: cc + 1 + ps, hl: true });
    for (const ep of px) {
      ctx.fillStyle = ep.hl ? lerpH(FACE_COLORS.dark, FACE_COLORS.light, params.sparkle) : FACE_COLORS.dark;
      ctx.fillRect(faceOx + ep.c * faceCS, faceOy + ep.r * faceCS + oy, faceCS, faceCS);
    }
  }
  drawEye(10); drawEye(21);

  // Mouth
  const mcc = 16, hw = Math.round(lerp(2, 5.5, params.mouth_width));
  const cs = mcc - hw, ce = mcc + hw;
  ctx.fillStyle = FACE_COLORS.dark;
  if (params.mouth_open < 0.25) {
    for (let c = cs; c <= ce; c++) {
      const t = (c - cs) / (ce - cs || 1), edgeF = Math.abs(t - 0.5) * 2;
      ctx.fillRect(faceOx + c * faceCS, faceOy + (19 + Math.round(-params.mouth_curve * edgeF * 2)) * faceCS + oy, faceCS, faceCS);
    }
  } else {
    const topR = 18 - Math.round(params.mouth_open * 0.8), botR = 19 + Math.round(params.mouth_open * 0.8);
    for (let c = 15; c <= 17; c++) ctx.fillRect(faceOx + c * faceCS, faceOy + topR * faceCS + oy, faceCS, faceCS);
    for (let c = cs + 1; c <= ce - 1; c++) {
      const isE = (c === cs + 1 || c === ce - 1);
      ctx.fillRect(faceOx + c * faceCS, faceOy + (botR + (isE ? Math.round(-params.mouth_curve) : Math.round(params.mouth_curve * 0.3))) * faceCS + oy, faceCS, faceCS);
    }
  }
}

function drawSparkleOverlay(oy) {
  const t = performance.now() / 1000;
  const facePixels = getFacePixels(curParams);
  const fps = facePixels;
  for (const sp of sparkleParticles) {
    const fpIdx = Math.floor(sp.idx / NUM_SPARKLES * fps.length) % fps.length;
    const fp = fps[fpIdx];
    const sparkle = 0.15 + 0.2 * Math.sin(t * sp.speed + sp.phase);
    if (sparkle < 0.05) continue;
    const sx = faceOx + fp.c * faceCS;
    const sy = faceOy + fp.r * faceCS + oy;
    ctx.fillStyle = '#ffffff';
    ctx.globalAlpha = sparkle;
    ctx.fillRect(sx + faceCS * 0.25, sy + faceCS * 0.25, faceCS * 0.5, faceCS * 0.5);
  }
  ctx.globalAlpha = 1;
}

function drawChat() {
  ctx.fillStyle = '#0a0a1e';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Draw dim background stars
  const t = performance.now() / 1000;
  for (let i = 0; i < 25; i++) {
    const s = stars[i];
    const twinkle = 0.5 + 0.5 * Math.sin(t * 1.5 + s.phase);
    ctx.fillStyle = '#ffffff';
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
