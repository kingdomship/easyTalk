// @ts-check
// ═══════════════════════════════════════════════════════════════════════
// personality.js — AI Personality Adjustment UI Controller
// ═══════════════════════════════════════════════════════════════════════

var personalityModal = document.getElementById('personality-modal');
var personalityOverlay = document.getElementById('personalityOverlay');
var personalityClose = document.getElementById('personalityClose');
var personalityStatus = document.getElementById('personalityStatus');
var personalityGenerate = document.getElementById('personalityGenerate');
var personalitySave = document.getElementById('personalitySave');
var personalityReset = document.getElementById('personalityReset');

// ── Dimension definitions ──────────────────────────────────────────

var OCEAN_DIMS = [
  { key: 'openness', label: '经验开放性', low: '保守传统', high: '好奇探索', min: 0.1, max: 0.9, step: 0.01 },
  { key: 'conscientiousness', label: '尽责性', low: '随性自由', high: '严谨有条理', min: 0.1, max: 0.9, step: 0.01 },
  { key: 'extraversion', label: '外向性', low: '内敛安静', high: '外向活泼', min: 0.1, max: 0.9, step: 0.01 },
  { key: 'agreeableness', label: '宜人性', low: '直言不讳', high: '温暖共情', min: 0.1, max: 0.9, step: 0.01 },
  { key: 'neuroticism', label: '情绪敏感性', low: '稳定平和', high: '敏感情绪化', min: 0.1, max: 0.9, step: 0.01 },
];

var EXPR_DIMS = [
  { key: 'amplitude_baseline', label: '表达幅度', low: '含蓄内敛', high: '夸张外放', min: 0, max: 1, step: 0.01 },
  { key: 'warmth_bias', label: '温暖偏向', low: '冷静理性', high: '温暖关怀', min: 0, max: 1, step: 0.01 },
  { key: 'humor_bias', label: '幽默偏向', low: '严肃认真', high: '俏皮幽默', min: 0, max: 1, step: 0.01 },
  { key: 'formality', label: '正式度', low: '随性口语', high: '正式考究', min: 0, max: 1, step: 0.01 },
];

// ── Slider live sync ──────────────────────────────────────────────
// Event delegation: update --pct and displayed percentage on drag

var _slidersContainer = document.querySelector('.personality-sliders');
if (_slidersContainer) {
  _slidersContainer.addEventListener('input', function (e) {
  var el = e.target;
  if (!el.classList.contains('personality-range')) return;
  var min = parseFloat(el.min);
  var max = parseFloat(el.max);
  var val = parseFloat(el.value);
  var pct = Math.round(((val - min) / (max - min)) * 100);
  el.style.setProperty('--pct', pct + '%');
  // Update the percentage label next to the slider header
  var row = el.closest('.personality-slider-row');
  if (row) {
    var valSpan = row.querySelector('.personality-slider-val');
    if (valSpan) valSpan.textContent = Math.round(val * 100) + '%';
  }
  });
}

// ── Open / Close ──

function openPersonalityModal() {
  personalityModal.classList.add('open');
  loadPersonality();
}

function closePersonalityModal() {
  personalityModal.classList.remove('open');
}

personalityOverlay.addEventListener('click', closePersonalityModal);
personalityClose.addEventListener('click', closePersonalityModal);

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape' && personalityModal.classList.contains('open')) {
    closePersonalityModal();
  }
});

// ── Render Sliders ──

function buildSlider(dim, group, value) {
  var pct = Math.round(((value - dim.min) / (dim.max - dim.min)) * 100);
  return '<div class="personality-slider-row">' +
    '<div class="personality-slider-header">' +
      '<span class="personality-slider-label">' + dim.label + '</span>' +
      '<span class="personality-slider-val">' + Math.round(value * 100) + '%</span>' +
    '</div>' +
    '<div class="personality-slider-range">' +
      '<span class="personality-slider-low">' + dim.low + '</span>' +
      '<input type="range" class="personality-range" data-group="' + group + '" data-key="' + dim.key +
        '" min="' + dim.min + '" max="' + dim.max + '" step="' + dim.step +
        '" value="' + value + '" style="--pct:' + pct + '%">' +
      '<span class="personality-slider-high">' + dim.high + '</span>' +
    '</div>' +
  '</div>';
}

function renderAllSliders(ocean, expr) {
  var html = '';
  for (var i = 0; i < OCEAN_DIMS.length; i++) {
    var d = OCEAN_DIMS[i];
    html += buildSlider(d, 'ocean', ocean[d.key] !== undefined ? ocean[d.key] : 0.5);
  }
  document.getElementById('oceanSliders').innerHTML = html;

  html = '';
  for (var j = 0; j < EXPR_DIMS.length; j++) {
    var e = EXPR_DIMS[j];
    html += buildSlider(e, 'expr', expr[e.key] !== undefined ? expr[e.key] : 0.0);
  }
  document.getElementById('exprSliders').innerHTML = html;
}

function getCurrentOcean() {
  var result = {};
  document.querySelectorAll('.personality-range[data-group="ocean"]').forEach(function (el) {
    result[el.dataset.key] = parseFloat(el.value);
  });
  return result;
}

function getCurrentExpr() {
  var result = {};
  document.querySelectorAll('.personality-range[data-group="expr"]').forEach(function (el) {
    result[el.dataset.key] = parseFloat(el.value);
  });
  return result;
}

// ── Load / Set ──

async function loadPersonality() {
  try {
    var resp = await fetch('/api/personality');
    if (!resp.ok) throw new Error('加载失败');
    var data = await resp.json();
    var p = data.personality;
    var ocean = p.ocean || {};
    var expr = p.expression_modulation || {};
    renderAllSliders(ocean, expr);

    // Update generated info
    document.getElementById('personalityMbti').textContent = p.mbti || '—';
    document.getElementById('personalityArchetype').textContent = p.archetype || '—';
    document.getElementById('personalityInterests').textContent = (p.interests || []).join('、') || '—';

    showStatus('', '');
  } catch (e) {
    showStatus('加载当前人格配置失败: ' + e.message, 'error');
  }
}

// ── Generate ──

personalityGenerate.addEventListener('click', async function () {
  var desc = document.getElementById('personalityDesc').value.trim();
  if (!desc) {
    showStatus('请输入 AI 角色描述', 'error');
    return;
  }
  if (desc.length < 5) {
    showStatus('描述太短，请至少输入 5 个字', 'error');
    return;
  }

  personalityGenerate.disabled = true;
  personalityGenerate.textContent = '⏳ 正在分析...';
  showStatus('', '');

  try {
    var resp = await fetch('/api/personality/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: desc }),
    });

    if (!resp.ok) {
      var errData = await resp.json();
      throw new Error(errData.detail || '生成失败');
    }

    var data = await resp.json();
    if (!data.ok) throw new Error('生成失败');

    // Update sliders with generated values
    var p = data.personality;
    renderAllSliders(p.ocean, p.expression_modulation);

    // Show generated info
    document.getElementById('personalityMbti').textContent = p.mbti || '—';
    document.getElementById('personalityArchetype').textContent = p.archetype || '—';
    document.getElementById('personalityInterests').textContent = (p.interests || []).join('、') || '—';
    document.getElementById('personalityGenerated').style.display = 'block';

    showStatus('✨ 人格生成完成，你可以拖动滑块微调后保存', 'success');
  } catch (e) {
    showStatus('生成失败: ' + e.message, 'error');
  } finally {
    personalityGenerate.disabled = false;
    personalityGenerate.textContent = '✨ AI 生成人格';
  }
});

// ── Save ──

personalitySave.addEventListener('click', async function () {
  var ocean = getCurrentOcean();
  var expr = getCurrentExpr();

  personalitySave.disabled = true;
  personalitySave.textContent = '⏳ 保存中...';

  try {
    var resp = await fetch('/api/personality', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ocean: ocean,
        mbti: document.getElementById('personalityMbti').textContent !== '—' ? document.getElementById('personalityMbti').textContent : 'ENFP',
        archetype: document.getElementById('personalityArchetype').textContent !== '—' ? document.getElementById('personalityArchetype').textContent : '探索者',
        interests: (document.getElementById('personalityInterests').textContent !== '—' ? document.getElementById('personalityInterests').textContent : '').split('、').filter(Boolean),
        expression_modulation: expr,
      }),
    });
    if (!resp.ok) throw new Error('保存失败');
    showStatus('✅ 人格设置已保存', 'success');
  } catch (e) {
    showStatus('保存失败: ' + e.message, 'error');
  } finally {
    personalitySave.disabled = false;
    personalitySave.textContent = '💾 保存设置';
  }
});

// ── Reset ──

personalityReset.addEventListener('click', function () {
  var defaults = { openness: 0.75, conscientiousness: 0.60, extraversion: 0.70, agreeableness: 0.80, neuroticism: 0.25 };
  var exprDefaults = { amplitude_baseline: 1.0, warmth_bias: 0.0, humor_bias: 0.1, formality: 0.2 };
  renderAllSliders(defaults, exprDefaults);
  document.getElementById('personalityMbti').textContent = 'ENFP';
  document.getElementById('personalityArchetype').textContent = '探索者';
  document.getElementById('personalityInterests').textContent = '—';
  showStatus('已恢复默认值，点击"保存"生效', '');
});

// ── Helpers ──

function showPersonalityStatus(msg, type) {
  if (!personalityStatus) return;
  personalityStatus.textContent = msg;
  personalityStatus.className = 'personality-status ' + (type || '');
  if (msg) {
    setTimeout(function () {
      personalityStatus.textContent = '';
      personalityStatus.className = 'personality-status';
    }, 4000);
  }
}

// Alias for consistency with other modules
var showStatus = showPersonalityStatus;
