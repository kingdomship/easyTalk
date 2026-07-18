// @ts-check
// ═══════════════════════════════════════════
// Typing sound engine (Web Audio API)
// ═══════════════════════════════════════════
// Synthesised soft mechanical keyboard click:
//   noise burst → bandpass filter → sharp attack / fast decay
var _typeAudioCtx = null;
var _typeNoiseBuf = null;

function _ensureAudioCtx() {
  if (!_typeAudioCtx) {
    _typeAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (_typeAudioCtx.state === 'suspended') {
    _typeAudioCtx.resume();
  }
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
    var actx = _ensureAudioCtx();
    var now = actx.currentTime;

    var src = actx.createBufferSource();
    src.buffer = _typeNoiseBuf;

    var bp = actx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.setValueAtTime(1800 + Math.random() * 2400, now); // 1.8-4.2kHz
    bp.Q.setValueAtTime(0.7 + Math.random() * 0.6, now);          // 0.7-1.3

    var gain = actx.createGain();
    gain.gain.setValueAtTime(0.001, now);
    gain.gain.exponentialRampToValueAtTime(0.12, now + 0.002);    // sharp attack 2ms
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.025 + Math.random() * 0.02); // decay 25-45ms

    src.connect(bp);
    bp.connect(gain);
    gain.connect(actx.destination);
    src.start(now);
    src.stop(now + 0.08);
  } catch (e) {}
}
