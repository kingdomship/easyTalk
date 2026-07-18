// ── Breathing exercise ──
function startBreathingExercise(pattern, durationSec) {
  var modal = document.getElementById('breathing-modal');
  if (!modal) return;
  switch (pattern) {
    case 'box': breathingPattern = { inhale: 4, hold: 4, exhale: 4, pause: 0 }; break;
    case '4-7-8': breathingPattern = { inhale: 4, hold: 7, exhale: 8, pause: 0 }; break;
    default: breathingPattern = { inhale: 4, hold: 2, exhale: 5, pause: 2 }; break; // 'simple'
  }
  breathingDuration = durationSec || 120;
  breathingPhase = 'inhale';
  breathingTimer = 0;
  breathingStartTime = Date.now();
  state = STATE.BREATHING;
  modal.classList.add('open');
  document.getElementById('breathingPhaseText').textContent = '吸气...';
}

function stopBreathingExercise() {
  state = STATE.CHAT;
  var modal = document.getElementById('breathing-modal');
  if (modal) modal.classList.remove('open');
}

function updateBreathing(dt) {
  breathingTimer += dt;
  var phaseDur = breathingPattern[breathingPhase] || 4;
  if (breathingTimer >= phaseDur) {
    breathingTimer -= phaseDur;
    // Advance phase
    switch (breathingPhase) {
      case 'inhale':
        breathingPhase = breathingPattern.hold > 0 ? 'hold' : 'exhale';
        break;
      case 'hold':
        breathingPhase = 'exhale';
        break;
      case 'exhale':
        breathingPhase = breathingPattern.pause > 0 ? 'pause' : 'inhale';
        break;
      case 'pause':
        breathingPhase = 'inhale';
        break;
    }
    // Update phase text
    var phaseEl = document.getElementById('breathingPhaseText');
    if (phaseEl) {
      var texts = {
        inhale: '吸气...', hold: '屏息...', exhale: '呼气...', pause: '自然停顿...'
      };
      phaseEl.textContent = texts[breathingPhase] || '';
    }
  }
  // Auto-stop after duration
  var elapsed = (Date.now() - breathingStartTime) / 1000;
  if (elapsed >= breathingDuration) {
    stopBreathingExercise();
  }
}

function drawBreathing() {
  var cx = canvas.width / 2;
  var cy = canvas.height / 2;
  var phaseDur = breathingPattern[breathingPhase] || 4;
  var progress = breathingTimer / phaseDur; // 0..1 within current phase

  // Compute ring radius based on phase
  var rMin = 40, rMax = 140;
  var r;
  switch (breathingPhase) {
    case 'inhale':
      r = rMin + (rMax - rMin) * progress;
      break;
    case 'hold':
      r = rMax;
      break;
    case 'exhale':
      r = rMax - (rMax - rMin) * progress;
      break;
    case 'pause':
      r = rMin;
      break;
    default:
      r = rMin;
  }

  // Outer glow ring
  ctx.beginPath();
  ctx.arc(cx, cy, r + 6, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(200,150,180,0.06)';
  ctx.fill();

  // Main ring
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  var alpha = 0.25 + 0.1 * Math.sin(progress * Math.PI);
  ctx.fillStyle = 'rgba(180,160,200,' + alpha.toFixed(2) + ')';
  ctx.fill();
  ctx.strokeStyle = 'rgba(200,170,210,0.35)';
  ctx.lineWidth = 2;
  ctx.stroke();

  // Center dot
  ctx.beginPath();
  ctx.arc(cx, cy, 6, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(220,190,210,0.6)';
  ctx.fill();
}
