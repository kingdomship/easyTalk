// @ts-check
// ═══════════════════════════════════════════
// Face computation + expression parameters
// ═══════════════════════════════════════════
var GRID = 64;
var FACE_COLORS = { face:'#ffd54f', faceD:'#eec030', outline:'#c49818', dark:'#2d3436', light:'#ffffff', blush:'#ff8c69' };

function fd(r, c) { return Math.sqrt((r-32)*(r-32) + (c-32)*(c-32)); }
function lerp(a,b,t) { return a+(b-a)*t; }
function easeInOutCubic(t) { return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2; }
function easeOutElastic(t) {
  if (t === 0 || t === 1) return t;
  return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (2 * Math.PI) / 3) + 1;
}
function lerpH(c1, c2, t) {
  var h = function(s) { return parseInt(s, 16); };
  var r = Math.round(lerp(h(c1.slice(1,3)), h(c2.slice(1,3)), t));
  var g = Math.round(lerp(h(c1.slice(3,5)), h(c2.slice(3,5)), t));
  var b = Math.round(lerp(h(c1.slice(5,7)), h(c2.slice(5,7)), t));
  return '#'+[r,g,b].map(function(v){ return Math.max(0,Math.min(255,v)).toString(16).padStart(2,'0'); }).join('');
}

function getFacePixels(params) {
  var p = params;
  var pixels = [];
  var cheekPuff = p.cheek_puff || 0;
  for (var r = 0; r < GRID; r++)
    for (var cc = 0; cc < GRID; cc++) {
      var d = fd(r, cc);
      var cheekFactor = 0;
      if (cheekPuff > 0) {
        var lDist = Math.sqrt((r-27)*(r-27) + (cc-11)*(cc-11));
        var rDist = Math.sqrt((r-27)*(r-27) + (cc-53)*(cc-53));
        var cheekDist = Math.min(lDist, rDist);
        if (cheekDist < 14) cheekFactor = Math.max(0, 1 - cheekDist/14);
      }
      var radius = 29 + cheekPuff * 3 * cheekFactor;
      if (d > radius) continue;
      var color = d > 27 ? FACE_COLORS.outline : (d > 24 ? FACE_COLORS.faceD : FACE_COLORS.face);
      pixels.push({ r: r, c: cc, color: color });
    }
  // Blush
  var blushVal = p.blush || 0;
  var cheekRaise = p.cheek_raise || 0;
  var blushBlend = 0.08 + blushVal * 0.7;
  if (blushBlend > 0.02) {
    var blushColor = lerpH(FACE_COLORS.face, FACE_COLORS.blush, blushBlend);
    var blushCenterR = Math.round(27 - cheekRaise * 5);
    var blushVR = Math.round(8 - cheekRaise * 3);
    for (var rr = blushCenterR - blushVR; rr <= blushCenterR + blushVR; rr++) {
      for (var cc = 3; cc <= 19; cc++) {
        var vrDist = (rr - blushCenterR) / Math.max(1, blushVR);
        if (Math.sqrt((rr-blushCenterR)*(rr-blushCenterR) + (cc-11)*(cc-11)) < blushVR && vrDist > -1.2)
          pixels.push({ r: rr, c: cc, color: blushColor });
      }
    }
    for (rr = blushCenterR - blushVR; rr <= blushCenterR + blushVR; rr++) {
      for (cc = 45; cc <= 61; cc++) {
        vrDist = (rr - blushCenterR) / Math.max(1, blushVR);
        if (Math.sqrt((rr-blushCenterR)*(rr-blushCenterR) + (cc-53)*(cc-53)) < blushVR && vrDist > -1.2)
          pixels.push({ r: rr, c: cc, color: blushColor });
      }
    }
  }
  // Nose wrinkle (AU9)
  var noseWrinkle = p.nose_wrinkle || 0;
  if (noseWrinkle > 0.05) {
    var nwColor = lerpH(FACE_COLORS.face, FACE_COLORS.dark, noseWrinkle * 0.6);
    for (var c = 30; c <= 33; c++) pixels.push({ r: 15, c: c, color: nwColor });
    for (c = 29; c <= 34; c++) pixels.push({ r: 16, c: c, color: nwColor });
  }
  // Eyebrows
  var baseR = Math.round(lerp(18, 10, p.brow_height));
  var asym = p.brow_asym || 0;
  var lOff = -Math.round(asym * 4), rOff = Math.round(asym * 4);
  for (var i = 0; i < 5; i++) {
    var cc = 14 + i;
    var archOff = (i === 1 || i === 2) ? -1 : 0;
    var tiltOff = Math.round((cc - 16) * (p.brow_angle||0) * 2);
    pixels.push({ r: baseR + archOff + tiltOff + lOff, c: cc, color: FACE_COLORS.dark });
  }
  for (i = 0; i < 5; i++) {
    cc = 45 + i;
    archOff = (i === 1 || i === 2) ? -1 : 0;
    tiltOff = Math.round((cc - 47) * (p.brow_angle||0) * 2);
    pixels.push({ r: baseR + archOff + tiltOff + rOff, c: cc, color: FACE_COLORS.dark });
  }
  // Eyes
  function eyePx(cc) {
    var px = [], bR = 20;
    var eyeOpen = p.eye_open;
    var wink = p.eye_wink || 0;
    if (wink < -0.5 && cc === 20) eyeOpen = 0.05;
    if (wink > 0.5 && cc === 43) eyeOpen = 0.05;
    var rows = eyeOpen < 0.2 ? 1 : (eyeOpen < 0.6 ? 2 : 4);
    var outerDir = cc < 30 ? 1 : -1;
    var ec = p.eye_curve || 0;
    var tension = p.eye_tension || 0;
    var t = Math.round(tension * 2);
    if (rows === 1) {
      for (var c = cc - 2; c <= cc + 1; c++) px.push({ r: bR, c: c, color: FACE_COLORS.dark });
      px.push({ r: bR - 1, c: cc + outerDir * 2, color: FACE_COLORS.dark });
      if (ec > 0.3) px.push({ r: bR - 1, c: cc + outerDir * 3, color: FACE_COLORS.dark });
    } else if (rows === 2) {
      var tw = Math.round(tension * 1.5);
      for (c = cc - 3 + tw; c <= cc + 2 - tw; c++) px.push({ r: bR - 2, c: c, color: FACE_COLORS.dark });
      for (c = cc - 2; c <= cc + 1; c++) px.push({ r: bR, c: c, color: FACE_COLORS.dark });
    } else {
      var tTop = Math.round(tension);
      var tcOff = ec > 0 ? Math.round(ec) : 0;
      var bcOff = ec < 0 ? Math.round(-ec) : 0;
      for (c = cc - 2 + tTop; c <= cc + 1 - tTop; c++) {
        var rowOff = (ec > 0 && (c === cc-2 || c === cc+1)) ? tcOff : 0;
        px.push({ r: bR - 4 + rowOff, c: c, color: FACE_COLORS.dark });
      }
      for (c = cc - 4 + t; c <= cc + 3 - t; c++) px.push({ r: bR - 3, c: c, color: FACE_COLORS.dark });
      for (c = cc - 4 + t; c <= cc + 3 - t; c++) px.push({ r: bR - 2, c: c, color: FACE_COLORS.dark });
      for (c = cc - 3 + t; c <= cc + 2 - t; c++) {
        rowOff = (ec < 0 && (c === cc-3 || c === cc+2)) ? bcOff : 0;
        px.push({ r: bR - 1 + rowOff, c: c, color: FACE_COLORS.dark });
      }
    }
    var ps = Math.round((p.eye_pupil || 0) * 3);
    for (var k = 0; k < px.length; k++) px[k].c += ps;
    var iris = p.iris_size != null ? p.iris_size : 0.5;
    var sparkle = p.sparkle || 0;
    var hlR = rows === 1 ? bR : (rows === 2 ? bR - 2 : bR - 3);
    px.push({ r: hlR, c: cc + 2 + ps, color: lerpH(FACE_COLORS.dark, FACE_COLORS.light, sparkle) });
    if (rows >= 2) {
      var hlSpread = Math.round(iris * 2);
      px.push({ r: hlR + 1, c: cc + 2 + hlSpread + ps, color: lerpH(FACE_COLORS.dark, FACE_COLORS.light, sparkle * 0.5 * iris) });
    }
    if (rows >= 3 && iris > 0.6) {
      px.push({ r: hlR, c: cc + 4 + ps, color: lerpH(FACE_COLORS.dark, FACE_COLORS.light, sparkle * 0.25 * iris) });
    }
    return px;
  }
  pixels.push.apply(pixels, eyePx(20));
  pixels.push.apply(pixels, eyePx(43));
  // Tear
  if ((p.tear || 0) > 0.05) {
    var tearColor = lerpH('#ffffff', '#88ccff', p.tear);
    var tearR = 23 + Math.round(p.tear * 2);
    pixels.push({ r: tearR, c: 18, color: tearColor });
    pixels.push({ r: tearR + 1, c: 18, color: tearColor });
    pixels.push({ r: tearR, c: 19, color: tearColor });
    pixels.push({ r: tearR + 1, c: 19, color: tearColor });
  }
  // Sweat drop
  var sweat = p.sweat_drop || 0;
  if (sweat > 0.05) {
    var sweatColor = lerpH(FACE_COLORS.face, '#ccddff', sweat);
    pixels.push({ r: 9, c: 7, color: sweatColor });
    pixels.push({ r: 10, c: 6, color: sweatColor });
    pixels.push({ r: 10, c: 7, color: sweatColor });
    pixels.push({ r: 10, c: 8, color: sweatColor });
    pixels.push({ r: 11, c: 7, color: sweatColor });
  }
  // Vein pop
  var vein = p.vein_pop || 0;
  if (vein > 0.05) {
    var veinColor = lerpH(FACE_COLORS.face, '#8b0000', vein * 0.8);
    for (c = 7; c <= 9; c++) pixels.push({ r: 9, c: c, color: veinColor });
    for (rr = 8; rr <= 10; rr++) pixels.push({ r: rr, c: 8, color: veinColor });
  }
  // Mouth
  var mcc = 32;
  var lipStretch = p.lip_stretch || 0;
  var mouthW = p.mouth_width || 0.6;
  var hw = Math.round(lerp(4, 11, mouthW));
  var stretchExtra = Math.round(lipStretch * 3);
  var cs = mcc - hw - stretchExtra, ce = mcc + hw + stretchExtra;
  var ma = p.mouth_asym || 0;
  var jawDrop = p.jaw_drop || 0;
  var lipPout = p.lip_pout || 0;
  var lipBite = p.lip_bite || 0;
  var tongueOut = p.tongue_out || 0;
  var effMouthOpen = Math.max(p.mouth_open || 0, tongueOut > 0.3 ? 0.2 : 0);

  if (effMouthOpen < 0.25) {
    var biteShift = Math.round(lipBite * 3);
    var baseR2 = 39;
    for (c = cs; c <= ce && pixels.length < 2000; c++) {
      var t2 = (c - cs) / (ce - cs || 1), edgeF = Math.abs(t2 - 0.5) * 2;
      var asymOffset = Math.round(ma * (c - mcc) * 0.4);
      var curveAtten = Math.max(0, 1 - lipStretch * 0.7);
      pixels.push({ r: baseR2 + Math.round(-p.mouth_curve * edgeF * 4 * curveAtten) + asymOffset - biteShift, c: c, color: FACE_COLORS.dark });
    }
    if (lipBite > 0.2) {
      var toothColor = lerpH(FACE_COLORS.dark, FACE_COLORS.light, 0.6);
      pixels.push({ r: baseR2 - 2 - biteShift, c: mcc, color: toothColor });
      pixels.push({ r: baseR2 - 2 - biteShift, c: mcc + 1, color: toothColor });
    }
    if (lipPout > 0.1) {
      var poutRows = Math.round(lipPout * 2);
      for (c = cs + 1; c <= ce - 1 && pixels.length < 2000; c++) {
        for (var pr = 1; pr <= poutRows; pr++) {
          pixels.push({ r: baseR2 + pr - biteShift, c: c, color: FACE_COLORS.dark });
        }
      }
    }
  } else {
    var topR = 37 - Math.round(effMouthOpen * 1.6) - Math.round(jawDrop * 2);
    var botR = 39 + Math.round(effMouthOpen * 1.6) + Math.round(jawDrop * 5);
    for (c = cs + 1; c <= ce - 1; c++) pixels.push({ r: topR, c: c, color: FACE_COLORS.dark });
    for (c = cs + 1; c <= ce - 1 && pixels.length < 2000; c++) {
      var isE = (c === cs + 1 || c === ce - 1);
      asymOffset = Math.round(ma * (c - mcc) * 0.4);
      curveAtten = Math.max(0, 1 - lipStretch * 0.7);
      pixels.push({ r: botR + (isE ? Math.round(-p.mouth_curve * 2 * curveAtten) : Math.round(p.mouth_curve * 0.7 * curveAtten)) + asymOffset, c: c, color: FACE_COLORS.dark });
      if (lipPout > 0.1 && !isE) {
        poutRows = Math.round(lipPout * 2);
        for (pr = 1; pr <= poutRows; pr++) {
          pixels.push({ r: botR + pr + asymOffset, c: c, color: FACE_COLORS.dark });
        }
      }
    }
    if (tongueOut > 0.1) {
      var tongueColor = lerpH('#ff7799', '#ff5577', tongueOut);
      var tongueBase = botR + 2;
      var tongueW = Math.round(lerp(1, 3, tongueOut));
      for (rr = 0; rr <= Math.round(tongueOut * 3); rr++) {
        var rw = tongueW - (rr > 0 ? Math.round(rr * 0.5) : 0);
        for (c = mcc - rw; c <= mcc + rw; c++) {
          pixels.push({ r: tongueBase + rr, c: c, color: tongueColor });
        }
      }
    }
  }
  return pixels;
}

// ═══════════════════════════════════════════
// Face parameters
// ═══════════════════════════════════════════
var curParams = { eye_curve:0, eye_open:0.7, eye_pupil:0, eye_wink:0, eye_tension:0, iris_size:0.5, mouth_curve:0.15, mouth_open:0, mouth_width:0.6, mouth_asym:0, lip_pout:0, lip_stretch:0, lip_bite:0, jaw_drop:0, tongue_out:0, sparkle:0.6, brow_angle:0.2, brow_height:0.65, brow_asym:0, nose_wrinkle:0, cheek_raise:0, cheek_puff:0, blush:0.1, head_tilt:0, tear:0, sweat_drop:0, vein_pop:0 };
var tgtParams = { eye_curve:0, eye_open:0.7, eye_pupil:0, eye_wink:0, eye_tension:0, iris_size:0.5, mouth_curve:0.15, mouth_open:0, mouth_width:0.6, mouth_asym:0, lip_pout:0, lip_stretch:0, lip_bite:0, jaw_drop:0, tongue_out:0, sparkle:0.6, brow_angle:0.2, brow_height:0.65, brow_asym:0, nose_wrinkle:0, cheek_raise:0, cheek_puff:0, blush:0.1, head_tilt:0, tear:0, sweat_drop:0, vein_pop:0 };

// ═══════════════════════════════════════════
// Poke reaction
// ═══════════════════════════════════════════
var pokeActive = false, pokeTimer = 0, pokeSparkles = [];
var POKE_EXPRESSIONS = [
  { eye_open:0.9, mouth_open:0.5, mouth_curve:0.7, sparkle:1, brow_height:0.9, iris_size:0.8, cheek_raise:0.3, duration_ms:400 },
  { eye_curve:0.8, mouth_curve:0.9, sparkle:0.9, brow_height:0.6, iris_size:0.7, cheek_raise:0.5, blush:0.2, duration_ms:300 },
  { eye_open:0.3, mouth_open:0.3, mouth_curve:0.5, sparkle:0.7, brow_asym:0.6, lip_pout:0.3, duration_ms:350 },
];

// ═══════════════════════════════════════════
// Sequence player
// ═══════════════════════════════════════════
var sequence = [], seqIdx = 0, seqElapsed = 0;
var replyText = '';

function setSequence(emotions, reply) {
  sequence = emotions.map(function(e) { return {
    params: {
      eye_curve:e.eye_curve, eye_open:e.eye_open, eye_pupil:e.eye_pupil||0, eye_wink:e.eye_wink||0,
      eye_tension:e.eye_tension||0, iris_size:e.iris_size != null ? e.iris_size : 0.5,
      mouth_curve:e.mouth_curve, mouth_open:e.mouth_open, mouth_width:e.mouth_width, mouth_asym:e.mouth_asym||0,
      lip_pout:e.lip_pout||0, lip_stretch:e.lip_stretch||0, lip_bite:e.lip_bite||0,
      jaw_drop:e.jaw_drop||0, tongue_out:e.tongue_out||0,
      sparkle:e.sparkle, brow_angle:e.brow_angle, brow_height:e.brow_height, brow_asym:e.brow_asym||0,
      nose_wrinkle:e.nose_wrinkle||0,
      cheek_raise:e.cheek_raise||0, cheek_puff:e.cheek_puff||0,
      blush:e.blush != null ? e.blush : curParams.blush, head_tilt:e.head_tilt||0,
      tear:e.tear||0, sweat_drop:e.sweat_drop||0, vein_pop:e.vein_pop||0,
    },
    duration: e.duration_ms || 3000,
    label: e.label || '',
  }; });
  seqIdx = 0; seqElapsed = 0;
  if (typeof microTimer !== 'undefined') microTimer = 2;
  replyText = reply || '';
}

function updateSequence(dt) {
  if (sequence.length === 0) return;
  seqElapsed += dt * 1000;
  var curFrame = sequence[seqIdx];
  if (sequence.length === 1) {
    tgtParams = {};
    for (var k in curFrame.params) { tgtParams[k] = curFrame.params[k]; }
    return;
  }
  var nextFrame = sequence[Math.min(seqIdx + 1, sequence.length - 1)];
  var rawT = Math.min(seqElapsed / curFrame.duration, 1);
  var t = easeInOutCubic(rawT);
  for (var kk in curFrame.params) {
    tgtParams[kk] = lerp(curFrame.params[kk], nextFrame.params[kk], t);
  }
  if (seqElapsed >= curFrame.duration && seqIdx < sequence.length - 1) {
    seqElapsed -= curFrame.duration;
    seqIdx++;
  }
}

function triggerPokeReaction(cx, cy) {
  if (pokeActive) return;
  pokeActive = true; pokeTimer = 0;
  var ex = POKE_EXPRESSIONS[Math.floor(Math.random() * POKE_EXPRESSIONS.length)];
  var pokeParams = {};
  for (var k in curParams) { pokeParams[k] = curParams[k]; }
  for (k in ex) { if (k !== 'duration_ms') pokeParams[k] = ex[k]; }
  sequence = [{ params: pokeParams, duration: ex.duration_ms, label: 'poke' }];
  seqIdx = 0; seqElapsed = 0;
  for (var i = 0; i < 12; i++) {
    var angle = Math.random() * Math.PI * 2;
    var speed = 2 + Math.random() * 5;
    pokeSparkles.push({
      x: cx, y: cy,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      life: 1,
      size: 1 + Math.random() * 3,
    });
  }
}
