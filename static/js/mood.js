// @ts-check
// ═══════════════════════════════════════════
// Mood-driven atmosphere + color fields
// ═══════════════════════════════════════════

// Mood-driven atmosphere
var moodColor = { r: 22, g: 18, b: 42 };
var moodTarget = { r: 22, g: 18, b: 42 };

// AI-controlled color fields (Rothko-style abstract color regions)
var colorFields = [];
var colorFieldsTarget = [];

// AI-controlled background color override (hex string or null)
var bgColorTarget = null;
var bgColorCurrent = null;  // {r,g,b} for smooth lerp, or null

// AI whiteboard drawing commands
var whiteboardCommands = [];

function parseWhiteboardCommands(commands) {
  if (!commands || !Array.isArray(commands)) return;
  whiteboardCommands = commands.filter(function(c) {
    return c && c.type && (c.type === 'line' || c.type === 'circle' || c.type === 'dot');
  });
}

// AI-generated pixel sprites that fly out from the face
var pixelSprites = [];
var _landStackCount = 0;

// ═══════════════════════════════════════════
// Panksepp affect → mood color
// ═══════════════════════════════════════════
var currentAffect = null;
var emaAffect = null;

var AFFECT_COLORS = {
  seeking: { r: 58, g: 48, b: 32 },
  play:    { r: 42, g: 26, b: 48 },
  care:    { r: 42, g: 24, b: 40 },
  fear:    { r: 10, g: 22, b: 40 },
  rage:    { r: 32, g: 16, b: 24 },
  panic:   { r: 26, g: 16, b: 48 },
};

function updateMoodFromAffect(affect) {
  if (!affect) return;
  currentAffect = affect;
  var alpha = 0.3;
  if (!emaAffect) {
    emaAffect = {};
    for (var dim in affect) { emaAffect[dim] = affect[dim]; }
  } else {
    for (dim in AFFECT_COLORS) {
      emaAffect[dim] = (emaAffect[dim] || 0) * (1 - alpha) + (affect[dim] || 0) * alpha;
    }
  }
  var r = 0, g = 0, b = 0, totalWeight = 0;
  for (var d in AFFECT_COLORS) {
    var w = Math.max(0, emaAffect[d] || 0);
    var c = AFFECT_COLORS[d];
    r += c.r * w; g += c.g * w; b += c.b * w;
    totalWeight += w;
  }
  if (totalWeight > 0) {
    r /= totalWeight; g /= totalWeight; b /= totalWeight;
    var vals = [];
    for (d in emaAffect) { vals.push(emaAffect[d] || 0); }
    var maxAffect = Math.max.apply(Math, vals);
    var brightness = 0.85 + maxAffect * 0.15;
    moodTarget = { r: Math.round(r * brightness), g: Math.round(g * brightness), b: Math.round(b * brightness) };
  }
}

// Legacy fallback: emotion label → color
function updateMoodFromEmotion(label) {
  if (currentAffect) return;
  var warmLabels = ['开心','惊喜','喜欢','幸福','温暖','兴奋','感动','得意','满足'];
  var coolLabels = ['难过','悲伤','生气','愤怒','害怕','紧张','疲惫','失落','委屈'];
  var labelLower = (label || '').toLowerCase();
  var isWarm = warmLabels.some(function(w) { return labelLower.indexOf(w) !== -1; });
  var isCool = coolLabels.some(function(c) { return labelLower.indexOf(c) !== -1; });
  if (isWarm) moodTarget = { r: 22, g: 16, b: 40 };
  else if (isCool) moodTarget = { r: 8, g: 12, b: 32 };
}

// ═══════════════════════════════════════════
// Circadian rhythm
// ═══════════════════════════════════════════
function circadianBaseColor() {
  var h = new Date().getHours();
  if (h >= 5 && h < 8)  return { r: 75, g: 60, b: 95 };
  if (h >= 8 && h < 12)  return { r: 115, g: 95, b: 125 };
  if (h >= 12 && h < 17) return { r: 100, g: 85, b: 118 };
  if (h >= 17 && h < 20) return { r: 65, g: 52, b: 82 };
  if (h >= 20 && h < 23) return { r: 38, g: 30, b: 56 };
  return { r: 22, g: 18, b: 42 };
}

function circadianBrightness() {
  var h = new Date().getHours();
  if (h >= 5 && h < 8)  return 0.7;
  if (h >= 8 && h < 17) return 1.0;
  if (h >= 17 && h < 20) return 0.75;
  if (h >= 20 && h < 23) return 0.55;
  return 0.35;
}

// ═══════════════════════════════════════════
// Mood → CSS variable sync
// ═══════════════════════════════════════════
var _lastMoodCSS = { r: 0, g: 0, b: 0 };

function hexToRgb(hex) {
  if (!hex || typeof hex !== 'string' || hex.length < 7) return { r: 255, g: 255, b: 255 };
  var r = parseInt(hex.slice(1, 3), 16);
  var g = parseInt(hex.slice(3, 5), 16);
  var b = parseInt(hex.slice(5, 7), 16);
  return { r: isNaN(r) ? 255 : r, g: isNaN(g) ? 255 : g, b: isNaN(b) ? 255 : b };
}

function getEffectiveMoodColor() {
  if (!bgColorCurrent) return moodColor;
  return {
    r: lerp(moodColor.r, bgColorCurrent.r, 0.7),
    g: lerp(moodColor.g, bgColorCurrent.g, 0.7),
    b: lerp(moodColor.b, bgColorCurrent.b, 0.7),
  };
}

function updateMoodCSS() {
  var eff = getEffectiveMoodColor();
  var r = Math.round(eff.r), g = Math.round(eff.g), b = Math.round(eff.b);
  if (r === _lastMoodCSS.r && g === _lastMoodCSS.g && b === _lastMoodCSS.b) return;
  _lastMoodCSS = { r: r, g: g, b: b };
  var root = document.documentElement;
  root.style.setProperty('--mood-r', String(r));
  root.style.setProperty('--mood-g', String(g));
  root.style.setProperty('--mood-b', String(b));
  var warmth = (eff.r - eff.b) / 60;
  var clampedWarmth = Math.max(-0.5, Math.min(0.5, warmth));
  var accentR = Math.round(Math.min(255, Math.max(100, 124 + clampedWarmth * 50)));
  var accentG = Math.round(Math.min(255, Math.max(110, 131 - Math.abs(clampedWarmth) * 30)));
  var accentB = Math.round(Math.min(255, Math.max(180, 255 - clampedWarmth * 50)));
  root.style.setProperty('--accent', 'rgb(' + accentR + ',' + accentG + ',' + accentB + ')');
  var bgR = Math.round(eff.r * 0.20), bgG = Math.round(eff.g * 0.20), bgB = Math.round(eff.b * 0.20);
  root.style.setProperty('--bg', 'rgb(' + bgR + ',' + bgG + ',' + bgB + ')');
  var srR = Math.round(eff.r * 0.40), srG = Math.round(eff.g * 0.40), srB = Math.round(eff.b * 0.40);
  root.style.setProperty('--surface', 'rgb(' + srR + ',' + srG + ',' + srB + ')');
}

function updateColorFields(dt) {
  if (colorFieldsTarget.length === 0 && colorFields.length === 0) return;
  var speed = 0.03;
  while (colorFields.length < colorFieldsTarget.length) {
    var tgt = colorFieldsTarget[colorFields.length];
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
    var cf = colorFields[colorFields.length - 1];
    cf.alpha = lerp(cf.alpha, 0, speed * 2);
    if (cf.alpha < 0.01) { colorFields.pop(); }
    else break;
  }
  for (var i = 0; i < Math.min(colorFields.length, colorFieldsTarget.length); i++) {
    cf = colorFields[i];
    tgt = colorFieldsTarget[i];
    var tgtColor = hexToRgb(tgt.color);
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
  var circ = circadianBaseColor();
  var circWeight = 0.5;
  var moodSpeed = 0.025;
  moodColor.r = lerp(moodColor.r, moodTarget.r * (1 - circWeight) + circ.r * circWeight, moodSpeed);
  moodColor.g = lerp(moodColor.g, moodTarget.g * (1 - circWeight) + circ.g * circWeight, moodSpeed);
  moodColor.b = lerp(moodColor.b, moodTarget.b * (1 - circWeight) + circ.b * circWeight, moodSpeed);

  moodTarget.r = lerp(moodTarget.r, circ.r, 0.005);
  moodTarget.g = lerp(moodTarget.g, circ.g, 0.005);
  moodTarget.b = lerp(moodTarget.b, circ.b, 0.005);

  if (bgColorTarget) {
    var tgtRgb = hexToRgb(bgColorTarget);
    if (!bgColorCurrent) {
      bgColorCurrent = { r: moodColor.r, g: moodColor.g, b: moodColor.b };
    }
    var bgSpeed = 0.025;
    bgColorCurrent.r = lerp(bgColorCurrent.r, tgtRgb.r, bgSpeed);
    bgColorCurrent.g = lerp(bgColorCurrent.g, tgtRgb.g, bgSpeed);
    bgColorCurrent.b = lerp(bgColorCurrent.b, tgtRgb.b, bgSpeed);
  } else if (bgColorCurrent) {
    var decaySpeed = 0.04;
    bgColorCurrent.r = lerp(bgColorCurrent.r, moodColor.r, decaySpeed);
    bgColorCurrent.g = lerp(bgColorCurrent.g, moodColor.g, decaySpeed);
    bgColorCurrent.b = lerp(bgColorCurrent.b, moodColor.b, decaySpeed);
    var diff = Math.abs(bgColorCurrent.r - moodColor.r)
             + Math.abs(bgColorCurrent.g - moodColor.g)
             + Math.abs(bgColorCurrent.b - moodColor.b);
    if (diff < 1.5) bgColorCurrent = null;
  }

  updateMoodCSS();
  updateColorFields(dt);

  // Update pixel sprites (fly-out animation) — defined in visuals.js
  if (typeof updatePixelSprites === 'function') updatePixelSprites(dt);

  // Poke timer
  if (pokeActive) {
    pokeTimer += dt * 1000;
    if (pokeTimer > 600) { pokeActive = false; pokeTimer = 0; }
    for (var i = 0; i < pokeSparkles.length; i++) {
      var s = pokeSparkles[i];
      s.x += s.vx; s.y += s.vy; s.life -= dt * 2;
    }
    pokeSparkles = pokeSparkles.filter(function(s) { return s.life > 0; });
  }
}
