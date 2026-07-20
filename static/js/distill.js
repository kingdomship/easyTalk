// @ts-check
// ═══════════════════════════════════════════════════════════════════════
// distill.js — Style Distillation UI Controller
// ═══════════════════════════════════════════════════════════════════════

var distillModal = document.getElementById('distill-modal');
var distillOverlay = document.getElementById('distillOverlay');
var distillClose = document.getElementById('distillClose');
var distillEmpty = document.getElementById('distillEmpty');
var distillList = document.getElementById('distillList');
var distillProfileList = document.getElementById('distillProfileList');
var distillUploadForm = document.getElementById('distillUploadForm');
var distillProgress = document.getElementById('distillProgress');
var distillResult = document.getElementById('distillResult');
var distillStatus = document.getElementById('distillStatus');

var distillFileInput = document.getElementById('distillFileInput');
var distillDropzone = document.getElementById('distillDropzone');
var distillNameInput = document.getElementById('distillNameInput');
var distillFormSubmit = document.getElementById('distillFormSubmit');
var distillFormCancel = document.getElementById('distillFormCancel');

var distillUploadBtn = document.getElementById('distillUploadBtn');
var distillAddBtn = document.getElementById('distillAddBtn');

// ── Open / Close ──

function openDistillModal() {
  distillModal.classList.add('open');
  loadProfiles();
}

function closeDistillModal() {
  distillModal.classList.remove('open');
  resetAllViews();
}

distillOverlay.addEventListener('click', closeDistillModal);
distillClose.addEventListener('click', closeDistillModal);

// ── View State Management ──

function resetAllViews() {
  distillEmpty.style.display = 'none';
  distillList.style.display = 'none';
  distillUploadForm.style.display = 'none';
  distillProgress.style.display = 'none';
  distillResult.style.display = 'none';
}

function showView(viewId) {
  resetAllViews();
  var el = document.getElementById(viewId);
  if (el) el.style.display = 'block';
}

// ── Load Profiles ──

async function loadProfiles() {
  try {
    var resp = await fetch('/api/distill/profiles');
    if (!resp.ok) throw new Error('加载失败');
    var data = await resp.json();
    renderProfiles(data.profiles || []);
  } catch (e) {
    // Show empty state on error
    showView('distillEmpty');
  }
}

function renderProfiles(profiles) {
  if (profiles.length === 0) {
    showView('distillEmpty');
    return;
  }
  showView('distillList');

  distillProfileList.innerHTML = profiles.map(function(p) {
    var activeClass = p.active ? ' distill-card-active' : '';
    var badge = p.active
      ? '<span class="distill-card-active-badge">使用中</span>'
      : '';
    var activateBtn = !p.active
      ? '<button class="distill-card-activate" data-id="' + p.id + '">启用</button>'
      : '<button class="distill-card-deactivate" data-id="' + p.id + '">停用</button>';
    return '<div class="distill-card' + activeClass + '" data-id="' + p.id + '">' +
      '<div class="distill-card-info">' +
        '<div class="distill-card-name">' + escapeHtml(p.name) + '</div>' +
        '<div class="distill-card-meta">' + p.sample_count + ' 条消息 · ' + p.source + '</div>' +
      '</div>' +
      '<div class="distill-card-actions">' +
        badge + activateBtn +
        '<button class="distill-card-delete" data-id="' + p.id + '" title="删除">✕</button>' +
      '</div>' +
    '</div>';
  }).join('');

  // Attach activate handlers
  distillProfileList.querySelectorAll('.distill-card-activate').forEach(function(btn) {
    btn.addEventListener('click', function() { activateProfile(this.dataset.id); });
  });
  distillProfileList.querySelectorAll('.distill-card-deactivate').forEach(function(btn) {
    btn.addEventListener('click', function() { deactivateProfile(); });
  });
  distillProfileList.querySelectorAll('.distill-card-delete').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      if (confirm('确定删除这个风格人设吗？')) deleteProfile(this.dataset.id);
    });
  });
}

// ── Activate / Deactivate ──

async function activateProfile(id) {
  try {
    var resp = await fetch('/api/distill/profiles/' + encodeURIComponent(id) + '/activate', { method: 'POST' });
    var data = await resp.json();
    if (data.ok) {
      if (typeof addDebugLog === 'function') {
        addDebugLog('info', '风格蒸馏', '已启用风格', data.active ? data.active.name : '');
      }
      loadProfiles();
    }
  } catch (e) {
    showStatus('切换失败: ' + e.message, 'error');
  }
}

async function deactivateProfile() {
  try {
    var resp = await fetch('/api/distill/deactivate', { method: 'POST' });
    var data = await resp.json();
    if (data.ok) {
      if (typeof addDebugLog === 'function') {
        addDebugLog('info', '风格蒸馏', '已停用', '恢复默认风格');
      }
      loadProfiles();
    }
  } catch (e) {
    showStatus('操作失败: ' + e.message, 'error');
  }
}

async function deleteProfile(id) {
  try {
    var resp = await fetch('/api/distill/profiles/' + encodeURIComponent(id), { method: 'DELETE' });
    if (resp.ok) {
      loadProfiles();
    }
  } catch (e) {
    showStatus('删除失败: ' + e.message, 'error');
  }
}

// ── Upload Flow ──

distillUploadBtn.addEventListener('click', function() {
  showView('distillUploadForm');
});

if (distillAddBtn) {
  distillAddBtn.addEventListener('click', function() {
    showView('distillUploadForm');
  });
}

distillFormCancel.addEventListener('click', function() {
  // Reset file input state
  distillFileInput.value = '';
  var fileInfo = document.getElementById('distillFileInfo');
  if (fileInfo) fileInfo.style.display = 'none';
  distillFormSubmit.disabled = true;
  loadProfiles(); // Go back to list or empty view
});

// File input / drag-drop
distillDropzone.addEventListener('click', function() {
  distillFileInput.click();
});

distillFileInput.addEventListener('change', function() {
  if (distillFileInput.files && distillFileInput.files.length > 0) {
    handleFileSelected(distillFileInput.files[0]);
  }
});

distillDropzone.addEventListener('dragover', function(e) {
  e.preventDefault();
  distillDropzone.classList.add('drag-over');
});

distillDropzone.addEventListener('dragleave', function() {
  distillDropzone.classList.remove('drag-over');
});

distillDropzone.addEventListener('drop', function(e) {
  e.preventDefault();
  distillDropzone.classList.remove('drag-over');
  if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    handleFileSelected(e.dataTransfer.files[0]);
  }
});

function handleFileSelected(file) {
  var ext = '.' + file.name.split('.').pop().toLowerCase();
  if (['.txt', '.json'].indexOf(ext) === -1) {
    showStatus('仅支持 .txt 或 .json 文件', 'error');
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    showStatus('文件大小超过 5MB 限制', 'error');
    return;
  }
  // Show file info
  var info = document.getElementById('distillFileInfo');
  document.getElementById('distillFileName').textContent = file.name;
  var sizeKB = Math.round(file.size / 1024);
  var sizeText = sizeKB < 1024 ? sizeKB + ' KB' : (sizeKB / 1024).toFixed(1) + ' MB';
  document.getElementById('distillFileSize').textContent = sizeText;
  info.style.display = 'block';
  distillFormSubmit.disabled = false;
}

distillFormSubmit.addEventListener('click', function() {
  if (!distillFileInput.files || distillFileInput.files.length === 0) return;
  var name = (distillNameInput.value || '').trim() || '未命名风格';
  startUpload(distillFileInput.files[0], name);
});

async function startUpload(file, name) {
  showView('distillProgress');
  distillFormSubmit.disabled = true;
  showStatus('', '');

  try {
    var formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);

    var resp = await fetch('/api/distill/upload', {
      method: 'POST',
      body: formData,
    });

    var data = await resp.json();

    if (!resp.ok) {
      throw new Error(data.detail || '上传失败');
    }

    showResult(data);
  } catch (e) {
    showView('distillUploadForm');
    distillFormSubmit.disabled = false;
    showStatus('分析失败: ' + e.message, 'error');
  }
}

// ── Result Display ──

function showResult(data) {
  showView('distillResult');

  var profile = data.profile;
  var stats = data.stats;
  document.getElementById('distillResultName').textContent = profile.name;
  var countHtml = '分析 <strong>' + profile.sample_count + '</strong> 条消息';
  if (stats && stats.total_messages) {
    countHtml += '（文件共 ' + stats.total_messages + ' 条';
    if (stats.total_messages > profile.sample_count) {
      countHtml += '，取最近 ' + profile.sample_count + ' 条';
    }
    countHtml += '）';
  }
  document.getElementById('distillResultCount').innerHTML = countHtml;

  // Style dimensions
  var sv = profile.style_vector;
  var dimLabels = {
    formality: '正式度', warmth: '温暖度', humor: '幽默感', verbosity: '繁简度',
    figurative: '修辞度', emotionality: '情绪表达', directness: '直接度', empathy: '共情倾向'
  };
  var dimsHtml = Object.keys(dimLabels).map(function(key) {
    var val = sv[key] !== undefined ? sv[key] : 0.5;
    var pct = Math.round(val * 100);
    var color = val > 0.7 ? '#7cff7c' : val < 0.3 ? '#ff7c7c' : '#ffd700';
    return '<div class="distill-dim">' +
      '<span class="distill-dim-label">' + dimLabels[key] + '</span>' +
      '<div class="distill-dim-bar"><div class="distill-dim-fill" style="width:' + pct + '%;background:' + color + '"></div></div>' +
      '<span class="distill-dim-val">' + pct + '%</span>' +
    '</div>';
  }).join('');
  document.getElementById('distillResultDims').innerHTML = dimsHtml;

  // Markers
  var markers = profile.linguistic_markers || [];
  var vocab = profile.vocabulary || [];
  var markersHtml = '';
  if (markers.length > 0) {
    markersHtml += '<div class="distill-section-title">语言特征</div>' +
      markers.map(function(m) { return '<span class="distill-tag">' + escapeHtml(m) + '</span>'; }).join(' ');
  }
  if (vocab.length > 0) {
    markersHtml += '<div class="distill-section-title">高频词汇</div>' +
      vocab.map(function(v) { return '<span class="distill-tag vocab">' + escapeHtml(v) + '</span>'; }).join(' ');
  }
  document.getElementById('distillResultMarkers').innerHTML = markersHtml;

  // Activate button
  var activateBtn = document.getElementById('distillResultActivate');
  activateBtn.onclick = function() {
    activateProfile(profile.id);
    closeDistillModal();
  };

  var closeBtn = document.getElementById('distillResultClose');
  closeBtn.onclick = function() {
    loadProfiles();
  };
}

// ── Helpers ──

function showStatus(msg, type) {
  if (!distillStatus) return;
  distillStatus.textContent = msg;
  distillStatus.className = 'distill-status ' + (type || '');
  if (msg) {
    setTimeout(function() {
      distillStatus.textContent = '';
      distillStatus.className = 'distill-status';
    }, 5000);
  }
}

// ── Keyboard shortcut: Escape to close ──
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && distillModal.classList.contains('open')) {
    closeDistillModal();
  }
});
