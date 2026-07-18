// @ts-check
// ═══════════════════════════════════════════
// Settings panel (LLM provider config)
// ═══════════════════════════════════════════

settingsOverlay.addEventListener('click', closeSettings);
settingsClose.addEventListener('click', closeSettings);

/** @type {Object<string, {name:string, base_url:string, default_model:string, models:string[]}>} */
var _presets = null;

providerSelect.addEventListener('change', function () {
  if (!_presets) return;
  var p = _presets[this.value];
  if (!p) return;
  baseUrlInput.value = p.base_url || '';
  modelInput.value = p.default_model || '';
  if (p.models && p.models.length > 0) {
    modelHint.textContent = '可选: ' + p.models.join(', ');
    modelHint.style.display = 'block';
  } else {
    modelHint.style.display = 'none';
  }
  if (this.value === 'custom') {
    baseUrlInput.placeholder = 'https://your-api.com/v1';
    modelInput.placeholder = 'your-model-name';
    modelHint.textContent = '输入任意 OpenAI 兼容接口地址和模型名';
    modelHint.style.display = 'block';
  }
});

settingsSave.addEventListener('click', async function () {
  var provider = providerSelect.value;
  var base_url = baseUrlInput.value.trim();
  var model = modelInput.value.trim();
  var api_key = apiKeyInput.value.trim();

  if (!api_key) { showStatus('请输入 API Key', 'error'); return; }
  if (!base_url) { showStatus('请输入 API Base URL', 'error'); return; }
  if (!model) { showStatus('请输入模型名称', 'error'); return; }

  try {
    var resp = await fetch('/api/config/llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: provider, base_url: base_url, model: model, api_key: api_key }),
    });
    if (resp.ok) {
      showStatus('✅ 配置已保存并生效', 'success');
      addDebugLog('info', '设置', 'LLM 配置已更新', provider + ' / ' + model);
    } else {
      showStatus('保存失败，请重试', 'error');
    }
  } catch (e) {
    showStatus('网络错误：' + e.message, 'error');
  }
});

settingsClear.addEventListener('click', async function () {
  try {
    await fetch('/api/config/llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: 'deepseek', base_url: '', model: '', api_key: '' }),
    });
    await loadSettings();
    showStatus('已恢复默认 DeepSeek 配置', 'success');
  } catch (e) {
    showStatus('网络错误：' + e.message, 'error');
  }
});

async function loadSettings() {
  try {
    var resp = await fetch('/api/config/llm');
    var data = await resp.json();
    _presets = data.presets || {};

    // Build provider dropdown
    providerSelect.innerHTML = '';
    var keys = Object.keys(_presets);
    for (var i = 0; i < keys.length; i++) {
      var p = _presets[keys[i]];
      var opt = document.createElement('option');
      opt.value = keys[i];
      opt.textContent = p.name;
      if (keys[i] === (data.provider || 'deepseek')) opt.selected = true;
      providerSelect.appendChild(opt);
    }

    baseUrlInput.value = data.base_url || '';
    modelInput.value = data.model || '';
    apiKeyInput.value = data.api_key || '';
    providerSelect.dispatchEvent(new Event('change'));
  } catch (e) {
    // Offline or server not ready — keep defaults
  }
}

async function openSettings() {
  settingsStatus.textContent = '';
  settingsStatus.className = 'settings-status';
  settingsModal.classList.add('open');
  await loadSettings();
}

function closeSettings() {
  settingsModal.classList.remove('open');
}

function showStatus(msg, type) {
  settingsStatus.textContent = msg;
  settingsStatus.className = 'settings-status ' + type;
  setTimeout(function () {
    settingsStatus.textContent = '';
    settingsStatus.className = 'settings-status';
  }, 3000);
}
