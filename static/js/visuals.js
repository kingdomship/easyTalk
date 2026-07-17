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

// Subtle dot-grid pattern overlay — adds warmth without competing with content
let _patternCanvas = null;

function getDotPattern() {
  if (_patternCanvas) return _patternCanvas;
  _patternCanvas = document.createElement('canvas');
  _patternCanvas.width = 32;
  _patternCanvas.height = 32;
  const pctx = _patternCanvas.getContext('2d');
  pctx.fillStyle = '#ffffff';
  pctx.beginPath();
  pctx.arc(16, 16, 0.5, 0, Math.PI * 2);
  pctx.fill();
  return _patternCanvas;
}

function drawSubtlePattern() {
  if (!canvas || canvas.width === 0) return;
  const pattern = ctx.createPattern(getDotPattern(), 'repeat');
  if (!pattern) return;
  ctx.save();
  ctx.fillStyle = pattern;
  const brightness = (moodColor.r + moodColor.g + moodColor.b) / (3 * 255);
  const alpha = 0.015 + brightness * 0.025;
  ctx.globalAlpha = alpha;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
}

// Render AI-controlled color fields as soft radial glows (Rothko-style)
function drawColorFields() {
  if (colorFields.length === 0) return;
  const t = performance.now() / 1000;
  for (const cf of colorFields) {
    if (cf.alpha < 0.01) continue;
    ctx.save();

    // Per-field blend mode
    ctx.globalCompositeOperation = cf.blend || 'soft-light';

    // Gaussian blur for soft atmospheric edges
    const blurPx = cf.blur || 0;
    if (blurPx > 0.5) ctx.filter = 'blur(' + blurPx.toFixed(1) + 'px)';

    // Drift offset — slow autonomous movement
    let dx = 0, dy = 0;
    if (cf.drift) {
      const range = (cf.drift.range || 0.06) * Math.max(canvas.width, canvas.height);
      dx = Math.sin(t * (cf.drift.speed || 0.3) + (cf._driftPhase || 0)) * range;
      dy = Math.cos(t * (cf.drift.speed || 0.3) * 0.73 + (cf._driftPhase || 0)) * range;
    }

    const x = cf.cx * canvas.width + dx;
    const y = cf.cy * canvas.height + dy;
    const r = cf.radius * Math.max(canvas.width, canvas.height);

    const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
    const cr = Math.round(cf.r), cg = Math.round(cf.g), cb = Math.round(cf.b);

    // Base opacity from cf.opacity (AI-controlled), modulate with pulse
    let baseAlpha = cf.alpha * (cf.opacity != null ? cf.opacity : 0.9);
    if (cf.pulse) {
      const p = cf.pulse;
      baseAlpha *= 1 + Math.sin(t * (p.speed || 0.5) + (cf._pulsePhase || 0)) * (p.amplitude || 0.1);
      baseAlpha = Math.max(0, Math.min(1, baseAlpha));
    }

    grad.addColorStop(0, 'rgba(' + cr + ',' + cg + ',' + cb + ',' + (baseAlpha * 0.50).toFixed(3) + ')');
    grad.addColorStop(0.35, 'rgba(' + cr + ',' + cg + ',' + cb + ',' + (baseAlpha * 0.25).toFixed(3) + ')');
    grad.addColorStop(1, 'rgba(' + cr + ',' + cg + ',' + cb + ',0)');

    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.restore();
  }
}

// ═══════════════════════════════════════════
// Pixel Sprites — AI-generated pixel art that flies out from the face
// Uses offscreen-canvas pre-render for GPU-accelerated drawImage (not fillRect loops)
// ═══════════════════════════════════════════

function spawnPixelSprites(data) {
  const spawnX = 0.5, spawnY = 0.35;
  for (const s of data) {
    if (!s.grid || !s.palette) { console.warn('[sprite] skip: no grid or palette', s.name); continue; }
    // Accept grid as array-of-strings, array-of-numbers, OR flat string (LLMs occasionally output any)
    var gridRows = Array.isArray(s.grid) ? s.grid : [];
    if (gridRows.length === 0 && typeof s.grid === 'string') {
      // Flat string: chunk into rows of 'size' characters
      var gs = s.size || 16;
      for (var r = 0; r < gs; r++) {
        gridRows.push(s.grid.substring(r * gs, (r + 1) * gs));
      }
    }
    // Normalize each row to a 16-char string (handles LLM outputting numbers)
    for (var ri = 0; ri < gridRows.length; ri++) {
      var row = gridRows[ri];
      if (typeof row === 'number') {
        row = String(row).padStart(16, '0');
      } else if (typeof row === 'string' && row.length < 16) {
        row = row.padStart(16, '0');
      }
      gridRows[ri] = row;
    }
    if (gridRows.length === 0) { console.warn('[sprite] skip: empty grid', s.name); continue; }
    const gridSize = gridRows.length;  // use actual row count instead of s.size
    const spread = s.spread != null ? s.spread : 0.8;
    const weight = s.weight != null ? Math.max(0, Math.min(1, s.weight)) : 0.3;
    const baseDuration = Math.min(s.duration || 3, 12);
    var count = Math.max(1, Math.min(s.count || 1, 50)); // clamp 1-50

    // Safety net: if LLM under-counted a sky effect (light sprite with low count),
    // auto-boost to ensure visible density. Catches rain/snow/petal failures.
    // Skip anchored sprites — they stay as single copies (umbrella, hat, etc.)
    if (!s.anchor && weight < 0.4 && count <= 3) {
      count = 12 + Math.floor(Math.random() * 7); // 12-18
    }

    // Pre-render sprite texture ONCE (shared by all copies)
    const texSize = gridSize * 4;
    const oc = document.createElement('canvas');
    oc.width = texSize;
    oc.height = texSize;
    const octx = oc.getContext('2d');
    const texCell = texSize / gridSize;
    var texPixels = 0;
    for (let row = 0; row < gridSize; row++) {
      const line = gridRows[row] || '';
      for (let col = 0; col < line.length; col++) {
        const idx = parseInt(line[col], 10);
        if (idx === 0 || isNaN(idx) || idx >= s.palette.length) continue;
        const color = s.palette[idx];
        if (color === 'transparent' || color === 'rgba(0,0,0,0)') continue;
        octx.fillStyle = color;
        octx.fillRect(col * texCell, row * texCell, texCell, texCell);
        texPixels++;
      }
    }
    console.log('[sprite] spawned:', s.name || '?', 'count=' + count, 'grid=' + gridSize + '×' + gridSize, 'pixels=' + texPixels, 'weight=' + weight, 'anchor=' + (s.anchor || 'no'), 'grid[0]=' + (gridRows[0] || '').substring(0, 20), 'palette_len=' + s.palette.length, 'palette[1]=' + s.palette[1]);
    if (texPixels === 0) { console.warn('[sprite] skip: zero visible pixels', s.name); continue; }

    // Spawn 'count' copies with randomized physics
    var isAnchored = !!s.anchor;
    for (var ci = 0; ci < count; ci++) {
      var angle = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * spread - weight * 0.35;
      var speed = 0.05 + (1 - weight) * 0.10 + Math.random() * 0.05;
      // Vary cell_scale slightly for visual variety (less for anchored)
      var cs = isAnchored ? (s.cell_scale || 1) : (s.cell_scale || 1) * (0.8 + Math.random() * 0.4);

      var landX = 0.2 + Math.random() * 0.6;
      var stackOffset = 0;
      if (weight >= 0.5) {
        stackOffset = _landStackCount % 5;
        _landStackCount++;
      }

      // For anchored sprites: minimum 3s total (0.4 emerge + 1.6 hold + 1.0 fade)
      if (isAnchored) baseDuration = Math.max(baseDuration, 3.0);
      var initLanded = isAnchored ? true : false;
      var initDecayDelay = isAnchored ? baseDuration : (1.0 + Math.random() * 2.5);
      var initLife = isAnchored ? 0.5 : 0;

      pixelSprites.push({
        _tex: oc,
        gridSize: gridSize,
        cellScale: cs,
        name: s.name || '',
        x: spawnX, y: spawnY,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        life: initLife,
        duration: baseDuration + Math.random() * baseDuration * 0.5,
        rotation: (Math.random() - 0.5) * 0.6,
        rotSpeed: (Math.random() - 0.5) * 0.4,
        wobble: Math.random() * Math.PI * 2,
        weight: isAnchored ? 0 : weight,
        landX: landX,
        stackOffset: stackOffset,
        landed: initLanded,
        landY: 0,
        decayTime: 0,
        decayDelay: initDecayDelay,
        bounceVel: 0,
        anchor: s.anchor || null,
        anchor_rx: s.anchor_rx != null ? s.anchor_rx : 0,
        anchor_ry: s.anchor_ry != null ? s.anchor_ry : -18,
      });
    }
  }
}

function updatePixelSprites(dt) {
  try {
  var spriteDt = Math.min(dt, 0.2);
  for (let i = pixelSprites.length - 1; i >= 0; i--) {
    const s = pixelSprites[i];

    // Anchored sprites: skip all physics, just decay-timer cleanup
    if (s.anchor) {
      s.decayTime += spriteDt;
      if (s.decayTime >= s.decayDelay) { pixelSprites.splice(i, 1); }
      continue;
    }

    if (s.landed) {
      // Bounce settle (spring-like decay toward landY)
      if (s.bounceVel < 0) {
        s.y += s.bounceVel * spriteDt;
        s.bounceVel += 0.6 * spriteDt;
        if (s.bounceVel >= 0 || s.y >= s.landY) { s.y = s.landY; s.bounceVel = 0; }
      }
      // Decay timer on ground — life frozen during display phase
      s.decayTime += spriteDt;
      if (s.decayTime < s.decayDelay) {
        // Sit still on ground, fully visible
        s.life = 0.5; // mid-life = full alpha/scale in draw
      } else {
        // Fade-out phase
        var fadeDuration = 1.2;
        s.life = 0.85 + Math.min(1, (s.decayTime - s.decayDelay) / fadeDuration) * 0.15;
      }
      if (s.life >= 1) {
        pixelSprites.splice(i, 1);
        if (_landStackCount > 0) _landStackCount--;
        continue;
      }
    } else {
      // In-flight physics
      s.life += spriteDt / s.duration;
      // Gravity proportional to weight
      s.vy += 0.22 * s.weight * spriteDt;
      // Air resistance: light things slow faster
      var drag = 0.998 - s.weight * 0.003;
      s.vx *= drag;
      s.vy *= drag;
      // Float wobble for light sprites
      if (s.weight < 0.3) {
        s.y -= Math.sin(s.life * 8 + s.wobble) * 0.008;
      }
      // Position update
      s.x += s.vx * spriteDt;
      s.y += s.vy * spriteDt;

      // Check landing for heavy sprites
      if (s.weight >= 0.5) {
        var floorY = 0.82 + s.stackOffset * 0.035;
        if (s.y >= floorY) {
          s.y = floorY;
          s.landY = floorY;
          s.landed = true;
          s.bounceVel = -Math.abs(s.vy) * 0.35;
          s.x += (s.landX - s.x) * 0.3;
        }
      }

      // Remove if off-screen or lifetime expired
      if (s.life >= 1 || s.x < -0.3 || s.x > 1.3 || s.y > 1.1) {
        pixelSprites.splice(i, 1);
      }
    }
  }
  // Safety: force-clean excess sprites
  if (pixelSprites.length > 30) {
    pixelSprites.splice(0, pixelSprites.length - 30);
  }
  } catch(e) { console.error('[sprite] update error:', e); }
}

function drawPixelSprites() {
  if (pixelSprites.length === 0) return;
  try {
  const prevSmoothing = ctx.imageSmoothingEnabled;
  ctx.imageSmoothingEnabled = false;

  var hasLanded = false;

  for (const s of pixelSprites) {
    // Anchored sprites: face-relative with emerge→hold→fade animation
    if (s.anchor) {
      var t2 = performance.now() / 1000;
      var headBob2 = Math.sin(t2 * 0.78) * 0.03;
      var tiltX2 = ((curParams.head_tilt || 0) + headBob2) * 3 * faceCS;
      var faceCX = faceOx + 32 * faceCS + tiltX2;
      var faceCY = faceOy + 32 * faceCS + faceBob;
      var anchorPx = faceCX + (s.anchor_rx || 0) * faceCS;
      var anchorPy = faceCY + (s.anchor_ry || 0) * faceCS;

      // Three-phase: emerge (elastic scale-in) → hold (gentle sway) → fade
      var age = s.decayTime;
      var emergeDur = 0.4;
      var fadeDur = 1.0;
      var holdDur = Math.max(0.5, s.decayDelay - emergeDur - fadeDur);
      var aScale, aAlpha;
      if (age < emergeDur) {
        var et = age / emergeDur;
        // easeOutBack
        var c1 = 1.70158, c3 = c1 + 1;
        aScale = 1 + c3 * Math.pow(et - 1, 3) + c1 * Math.pow(et - 1, 2);
        aAlpha = et;
      } else if (age < emergeDur + holdDur) {
        aScale = 1 + Math.sin(age * 2.5) * 0.03;
        aAlpha = 1;
      } else {
        var ft = Math.min(1, (age - emergeDur - holdDur) / fadeDur);
        aScale = 1 - ft * 0.2;
        aAlpha = 1 - ft;
      }

      var anchorCell = Math.max(canvas.width, canvas.height) * 0.005 * (s.cellScale || 1);
      var anchorW = s.gridSize * anchorCell * aScale;
      var anchorH = s.gridSize * anchorCell * aScale;
      ctx.save();
      ctx.globalAlpha = Math.max(0, Math.min(1, aAlpha));
      ctx.drawImage(s._tex, anchorPx - anchorW / 2, anchorPy - anchorH / 2, anchorW, anchorH);
      ctx.restore();
      continue;
    }
    var scale, alpha;
    if (s.landed) {
      hasLanded = true;
      // Landed sprites: no fly-in/out animation, just sit and fade
      if (s.decayTime < s.decayDelay) {
        scale = 1; alpha = 1;
      } else {
        var fade = Math.min(1, (s.decayTime - s.decayDelay) / 1.2);
        scale = 1 - fade * 0.3;
        alpha = 1 - fade;
      }
      // Gently drift toward landing X
      s.x += (s.landX - s.x) * 0.08;
    } else {
      if (s.life < 0.15) {
        scale = s.life / 0.15;
        alpha = scale;
      } else if (s.life > 0.85) {
        var fade2 = (s.life - 0.85) / 0.15;
        scale = 1 - fade2 * 0.4;
        alpha = 1 - fade2;
      } else {
        scale = 1;
        alpha = 1;
      }
    }

    var px = s.x * canvas.width;
    var py = s.y * canvas.height;
    var cellSize = Math.max(canvas.width, canvas.height) * 0.005 * scale * (s.cellScale || 1);
    var totalW = s.gridSize * cellSize;
    var totalH = s.gridSize * cellSize;

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.translate(px, py);
    if (!s.landed) {
      ctx.rotate(s.rotation + s.rotSpeed * s.life * 5);
    }
    ctx.drawImage(s._tex, -totalW / 2, -totalH / 2, totalW, totalH);
    ctx.restore();
  }

  ctx.imageSmoothingEnabled = prevSmoothing;

  // Draw landing shelf if any sprites have landed
  if (hasLanded) drawLandingShelf();
  } catch(e) { console.error('[sprite] draw error:', e); }
}

function drawLandingShelf() {
  var shelfY = canvas.height * 0.83;
  var grad = ctx.createLinearGradient(0, shelfY - 4, 0, shelfY + 1);
  grad.addColorStop(0, 'rgba(124,131,255,0)');
  grad.addColorStop(0.5, 'rgba(124,131,255,0.12)');
  grad.addColorStop(1, 'rgba(124,131,255,0.04)');

  ctx.save();
  ctx.fillStyle = grad;
  ctx.fillRect(0, shelfY - 4, canvas.width, 5);

  // Subtle glow line
  ctx.strokeStyle = 'rgba(124,131,255,0.15)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(canvas.width * 0.05, shelfY);
  ctx.lineTo(canvas.width * 0.95, shelfY);
  ctx.stroke();
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
  // Blends AI background override with mood/circadian for topic-aware atmosphere
  const eff = getEffectiveMoodColor();
  const r = Math.round(eff.r), g = Math.round(eff.g), b = Math.round(eff.b);
  const grad = ctx.createRadialGradient(canvas.width/2, canvas.height/3.5, 0, canvas.width/2, canvas.height*0.8, canvas.height * 0.75);
  grad.addColorStop(0, `rgb(${r},${g},${b})`);
  grad.addColorStop(0.35, `rgb(${Math.round(r*0.72)},${Math.round(g*0.70)},${Math.round(b*0.74)})`);
  grad.addColorStop(0.65, `rgb(${Math.round(r*0.40)},${Math.round(g*0.38)},${Math.round(b*0.44)})`);
  grad.addColorStop(1, `rgb(${Math.round(r*0.10)},${Math.round(g*0.08)},${Math.round(b*0.15)})`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Overlay AI-controlled color fields (Rothko-style abstract regions)
  drawColorFields();
  drawSubtlePattern();

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

  // AI pixel sprites
  drawPixelSprites();
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
    textarea.focus();
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
  // Blends AI background override with mood/circadian for topic-aware atmosphere
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  const eff = getEffectiveMoodColor();
  const mr = Math.round(eff.r), mg = Math.round(eff.g), mb = Math.round(eff.b);
  const grad = ctx.createRadialGradient(cx, cy * 0.6, 0, cx, cy * 0.3, Math.max(canvas.width, canvas.height) * 0.72);
  grad.addColorStop(0, 'rgb(' + mr + ',' + mg + ',' + mb + ')');
  grad.addColorStop(0.3, 'rgb(' + Math.round(mr * 0.88) + ',' + Math.round(mg * 0.86) + ',' + Math.round(mb * 0.90) + ')');
  grad.addColorStop(0.6, 'rgb(' + Math.round(mr * 0.55) + ',' + Math.round(mg * 0.52) + ',' + Math.round(mb * 0.58) + ')');
  grad.addColorStop(1, 'rgb(' + Math.round(mr * 0.20) + ',' + Math.round(mg * 0.18) + ',' + Math.round(mb * 0.25) + ')');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Overlay AI-controlled color fields (Rothko-style abstract regions)
  drawColorFields();
  drawSubtlePattern();

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

  // AI pixel sprites flying out from face
  drawPixelSprites();
}
