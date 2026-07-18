// @ts-check
// ═══════════════════════════════════════════
// Main loop + Init
// ═══════════════════════════════════════════

var lastT = performance.now();

function loop(t) {
  const dt = Math.min((t - lastT) / 1000, 0.1);
  lastT = t;

  switch (state) {
    case STATE.STARFIELD:
      updateStarfield(dt);
      drawStarfield();
      drawPokeSparkles();
      break;
    case STATE.CONVERGING:
      updateConvergence(dt);
      drawConvergence();
      break;
    case STATE.CHAT:
      updateChat(dt);
      drawChat();
      drawMeteors();
      drawMemoryStars();
      drawPokeSparkles();
      break;
    case STATE.AUXILIARY:
      // Static background
      ctx.fillStyle = '#0a0a1a';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      break;
    case STATE.BREATHING:
      updateBreathing(dt);
      drawStarfield(); // subtle background stars
      drawBreathing();
      break;
    default:
      // Corrupted state from localStorage — reset to starfield
      console.warn('Unknown state: ' + state + ', resetting to STARFIELD');
      state = STATE.STARFIELD;
      updateStarfield(dt);
      drawStarfield();
      break;
  }

  saveVisualState();

  requestAnimationFrame(loop);
}

// ═══════════════════════════════════════════
// Init
// ═══════════════════════════════════════════
initStarfield();
initMemoryStars();
recomputeFaceLayout();
initSparkleParticles();
// Restore visual state from before refresh (mood, face, atmosphere)
var restored = false;
if (typeof loadVisualState === 'function') {
  restored = loadVisualState();
}
// Initial face pixel computation for convergence targets (skip if restored)
if (!restored) {
  curParams = { eye_curve:0, eye_open:0.5, eye_pupil:0, eye_wink:0, eye_tension:0, iris_size:0.5, mouth_curve:0, mouth_open:0, mouth_width:0.8, mouth_asym:0, lip_pout:0, lip_stretch:0, lip_bite:0, jaw_drop:0, tongue_out:0, sparkle:0.5, brow_angle:0, brow_height:0.5, brow_asym:0, nose_wrinkle:0, cheek_raise:0, cheek_puff:0, blush:0.15, head_tilt:0, tear:0, sweat_drop:0, vein_pop:0 };
  tgtParams = { ...curParams };
}
	// Restore dialog bubble if we were in chat mode before refresh
	if (restored && dlgText && state === STATE.CHAT) {
	  var fcX = canvas.width / 2, fcY = canvas.height / 2, fcR = 29 * faceCS;
	  var isNr = window.innerWidth < 600, dW = isNr ? 260 : 340;
	  var dX = fcX + fcR + 20, dY = fcY - 60;
	  if (dX + dW > window.innerWidth - 20) dX = Math.max(10, fcX - fcR - dW);
	  if (isNr && dX < 10) { dX = (window.innerWidth - dW) / 2; dY = fcY + fcR + 30; }
	  if (dY < 60) dY = fcY + fcR + 20;
	  if (dY + 120 > window.innerHeight - 20) dY = fcY - 120;
	  dialog.style.left = dX + 'px';
	  dialog.style.top = dY + 'px';
	  dialog.classList.add('visible');
	  dlgBody.innerHTML = formatDialogText(dlgText) + '<span class="dlg-arrow">▼</span>';
	  dlgDisplayed = dlgText.length;
	  inputRow.classList.add('visible');
	}
	// Rebuild story continue button if we were paused before refresh
	if (restored && storyPaused) {
	  showStoryContinueBtn();
	}
	// Auto-enter chat mode on fresh visit so the face renders immediately
	if (restored && state === STATE.CHAT) {
	  // Restored chat: snap stars to face contour
	  updateFacePixelTargets();
	  for (var _s = 0; _s < stars.length; _s++) {
	    var _st = stars[_s];
	    _st.trail = [];
	    if (_st.targetX != null) { _st.x = _st.targetX; _st.y = _st.targetY; }
	    else {
	      var _ang = Math.random() * Math.PI * 2;
	      _st.x = canvas.width / 2 + Math.cos(_ang) * (50 + Math.random() * 150);
	      _st.y = canvas.height / 2 + Math.sin(_ang) * (50 + Math.random() * 150);
	    }
	  }
	  inputRow.classList.add('visible');
	} else if (!restored) {
	  // Fresh visit: skip convergence, jump directly to CHAT
	  state = STATE.CHAT;
	  recomputeFaceLayout();
	  updateFacePixelTargets();
	  for (_s = 0; _s < stars.length; _s++) {
	    _st = stars[_s];
	    _st.trail = [];
	    if (_st.targetX != null) { _st.x = _st.targetX; _st.y = _st.targetY; }
	    else {
	      _ang = Math.random() * Math.PI * 2;
	      _st.x = canvas.width / 2 + Math.cos(_ang) * (50 + Math.random() * 150);
	      _st.y = canvas.height / 2 + Math.sin(_ang) * (50 + Math.random() * 150);
	    }
	  }
	  inputRow.classList.add('visible');
	  loadTopics();
	  textarea.focus();
	}
requestAnimationFrame(loop);

// Check for idle thoughts and missing-you on load
(async function checkOnLoad() {
  try {
    // First check if user was away for a long time
    const myResp = await fetch('/api/missing-you');
    const my = await myResp.json();
    if (my.away && my.thoughts && my.thoughts.length > 0) {
      setTimeout(() => {
        if (state === STATE.STARFIELD) {
          const days = Math.round(my.hours / 24);
          const timeStr = my.hours < 48
            ? Math.round(my.hours) + '个小时'
            : days + '天';
          const msg = '你回来了～已经过了' + timeStr
            + '。你不在的时候，我在星空里想了一些事情...\n\n'
            + my.thoughts.slice(0, 3).join('\n');
          showDialog(msg, canvas.width / 2, canvas.height * 0.25);
          setTimeout(() => { if (state === STATE.STARFIELD) hideDialog(); }, 10000);
        }
      }, 2500);
      return;
    }

    // Otherwise check for recent idle thought
    const resp = await fetch('/api/idle-thought');
    const data = await resp.json();
    if (data.thought) {
      setTimeout(() => {
        if (state === STATE.STARFIELD) {
          showDialog('💭 ' + data.thought, canvas.width / 2, canvas.height * 0.3);
          setTimeout(() => { if (state === STATE.STARFIELD) hideDialog(); }, 5000);
        }
      }, 2000);
    }
  } catch (e) {}
})();
