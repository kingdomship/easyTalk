// @ts-check
// ═══════════════════════════════════════════
// Retro dialog
// ═══════════════════════════════════════════
let dlgTyping = false, dlgTimer = null, thinkingTimer = null;
let dlgText = '', dlgDisplayed = 0;

function showDialog(text, x, y) {
  // Position dialog near the face but not covering it
  const faceCenterX = canvas.width / 2;
  const faceCenterY = canvas.height / 2;
  const faceRadius = 29 * faceCS;
  const isNarrow = window.innerWidth < 600;
  const dlgW = isNarrow ? 260 : 340;

  // Try to place to the right of the face, or left if not enough space
  let dx = faceCenterX + faceRadius + 20;
  let dy = faceCenterY - 60;
  if (dx + dlgW > window.innerWidth - 20) {
    dx = Math.max(10, faceCenterX - faceRadius - dlgW);
  }
  // On very narrow screens, center below the face
  if (isNarrow && dx < 10) {
    dx = (window.innerWidth - dlgW) / 2;
    dy = faceCenterY + faceRadius + 30;
  }
  if (dy < 60) dy = faceCenterY + faceRadius + 20;
  if (dy + 120 > window.innerHeight - 20) dy = faceCenterY - 120;

  dialog.style.left = dx + 'px';
  dialog.style.top = dy + 'px';
  dialog.classList.add('visible');

  dlgText = text;
  dlgDisplayed = 0;
  dlgBody.innerHTML = '<span class="cursor-blink"></span>';
  dlgTyping = true;
  typeNextChar();
}

function typeNextChar() {
  if (!dlgTyping || dlgDisplayed >= dlgText.length) {
    dlgTyping = false;
    const cursors = dlgBody.querySelectorAll('.cursor-blink');
    cursors.forEach(c => c.remove());
    dlgBody.innerHTML = formatDialogText(dlgText) + '<span class="dlg-arrow">▼</span>';
    return;
  }
  dlgDisplayed++;
  const shown = dlgText.substring(0, dlgDisplayed);
  dlgBody.innerHTML = formatDialogText(shown) + '<span class="cursor-blink"></span>';
  const delay = 40 + Math.random() * 50;
  dlgTimer = setTimeout(typeNextChar, delay);
}

function skipTypewriter() {
  dlgTyping = false;
  clearTimeout(dlgTimer);
  dlgBody.innerHTML = formatDialogText(dlgText) + '<span class="dlg-arrow">▼</span>';
  dlgDisplayed = dlgText.length;
}

function formatDialogText(text) {
  let escaped = escapeHtml(text);
  escaped = escaped.replace(/(https?:\/\/\S+)/g, '<span class="news-ref" data-url="$1">$1</span>');
  return escaped;
}

function hideDialog() {
  dlgTyping = false;
  clearTimeout(dlgTimer);
  dialog.classList.remove('visible');
  document.getElementById('choice-buttons')?.remove();
  if (abortController) { abortController.abort(); abortController = null; }
  storyPaused = false; storyBuffer = []; batchMode = false;
  var btn = document.getElementById('story-continue-btn');
  if (btn) btn.remove();
  pending = false; sendBtn.disabled = false;
}

// JRPG-style choice buttons — only trigger when emoji appear at line-start
function checkChoices(reply) {
  const existing = document.getElementById('choice-buttons');
  if (existing) existing.remove();

  // Only treat emoji-at-line-start as a choice marker, not inline emoji
  var lines = reply.split('\n');
  var choices = [];
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (EMOJI_RE.test(line) && line.search(EMOJI_RE) === 0) {
      var text = line.replace(EMOJI_RE, '').trim();
      if (text.length >= 2 && text.length <= 30) {
        choices.push({ emoji: line.match(EMOJI_RE)[0], text: text });
      }
    }
  }
  if (choices.length < 2) return;

  const container = document.createElement('div');
  container.id = 'choice-buttons';
  container.style.cssText = 'position:fixed;z-index:25;display:flex;gap:6px;flex-wrap:wrap;max-width:300px;';
  const dlgRect = dialog.getBoundingClientRect();
  container.style.left = dlgRect.left + 'px';
  container.style.top = (dlgRect.bottom + 8) + 'px';

  choices.forEach(function(ch) {
    const btn = document.createElement('button');
    btn.textContent = ch.emoji + ' ' + ch.text;
    btn.style.cssText = 'background:rgba(18,18,42,0.9);border:1px solid rgba(124,131,255,0.3);border-radius:12px;padding:6px 12px;color:#c8c8e0;font-size:0.7rem;cursor:pointer;font-family:inherit;letter-spacing:0.03em;transition:all 0.2s;';
    btn.onmouseenter = function() { btn.style.borderColor = 'var(--accent)'; btn.style.background = 'rgba(124,131,255,0.15)'; };
    btn.onmouseleave = function() { btn.style.borderColor = 'rgba(124,131,255,0.3)'; btn.style.background = 'rgba(18,18,42,0.9)'; };
    btn.addEventListener('click', function() {
      textarea.value = ch.text;
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      container.remove();
      sendMessage();
    });
    container.appendChild(btn);
  });

  document.body.appendChild(container);
  setTimeout(function() { container.remove(); }, 15000);
}

dlgClose.addEventListener('click', hideDialog);

// Click dialog to advance / double-click to skip
dlgBody.addEventListener('click', /** @param {MouseEvent} e */ e => {
  if (/** @type {Element} */ (e.target).closest('.news-ref')) return; // Don't interfere with link clicks
  if (dlgTyping) {
    skipTypewriter();
  }
});

dlgBody.addEventListener('dblclick', /** @param {MouseEvent} e */ e => {
  e.preventDefault();
  skipTypewriter();
});

// Dialog dragging
let dlgDragging = false, dlgOffX = 0, dlgOffY = 0;

dialog.querySelector('.dlg-header').addEventListener('pointerdown', /** @param {PointerEvent} e */ e => {
  if (e.target === dlgClose) return;
  dlgDragging = true;
  const rect = dialog.getBoundingClientRect();
  dlgOffX = e.clientX - rect.left;
  dlgOffY = e.clientY - rect.top;
  dialog.setPointerCapture(e.pointerId);
});

window.addEventListener('pointermove', /** @param {PointerEvent} e */ e => {
  if (!dlgDragging) return;
  dialog.style.left = (e.clientX - dlgOffX) + 'px';
  dialog.style.top = (e.clientY - dlgOffY) + 'px';
});

window.addEventListener('pointerup', () => { dlgDragging = false; });

// Click on news ref links
dlgBody.addEventListener('click', /** @param {MouseEvent} e */ e => {
	  const ref = /** @type {HTMLElement | null} */ (/** @type {HTMLElement} */ (e.target).closest('.news-ref'));
  if (ref && ref.dataset.url) window.open(ref.dataset.url, '_blank');
});

