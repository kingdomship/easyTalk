// @ts-check
// ═══════════════════════════════════════════
// Visual state persistence — save every 2s so refresh recovers mood + face
// ═══════════════════════════════════════════
var _lastSaveTime = 0;
var _SAVE_INTERVAL = 2; // seconds

function saveVisualState() {
  var now = performance.now() / 1000;
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
      whiteboardCommands: whiteboardCommands,
      colorFields: colorFields.map(function(cf) { return { r:cf.r, g:cf.g, b:cf.b, cx:cf.cx, cy:cf.cy, radius:cf.radius, alpha:cf.alpha, blend:cf.blend, opacity:cf.opacity, blur:cf.blur, pulse:cf.pulse, drift:cf.drift }; }),
      sequence: sequence,
      seqIdx: seqIdx,
      seqElapsed: seqElapsed,
      replyText: replyText,
      dlgText: (typeof dlgText !== 'undefined' ? dlgText : ''),
      // Only persist STARFIELD and CHAT — transient modals (AUXILIARY, CONVERGING, BREATHING) reset to STARFIELD
      state: (typeof state !== 'undefined' && (state === STATE.STARFIELD || state === STATE.CHAT) ? state : STATE.STARFIELD),
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
    if (saved.whiteboardCommands && saved.whiteboardCommands.length) whiteboardCommands = saved.whiteboardCommands;
    if (saved.colorFields && saved.colorFields.length) colorFields = saved.colorFields;
    if (saved.sequence) { sequence = saved.sequence; seqIdx = saved.seqIdx || 0; seqElapsed = saved.seqElapsed || 0; replyText = saved.replyText || ''; }
    if (saved.dlgText && typeof dlgText !== 'undefined') dlgText = saved.dlgText;
    if (saved.state === STATE.STARFIELD || saved.state === STATE.CHAT) state = saved.state;
    // AUXILIARY / CONVERGING / BREATHING are transient — reset to STARFIELD on refresh
    if (saved.storyPaused && typeof storyPaused !== 'undefined') storyPaused = saved.storyPaused;
    if (saved.storyBuffer && typeof storyBuffer !== 'undefined') storyBuffer = saved.storyBuffer;
    return true;
  } catch(e) { return false; }
}
