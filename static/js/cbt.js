// ── CBT Thought Record Wizard ──
var CbtWizard = {
  step: 0,
  data: { situation: '', autoThought: '', evidenceFor: '', evidenceAgainst: '', alternative: '', reframed: '' },

  open: function(thought) {
    this.step = 0;
    this.data = { situation: '', autoThought: thought || '', evidenceFor: '', evidenceAgainst: '', alternative: '', reframed: '' };
    var modal = document.getElementById('cbt-modal');
    if (modal) modal.classList.add('open');
    this._render();
  },

  close: function() {
    var modal = document.getElementById('cbt-modal');
    if (modal) modal.classList.remove('open');
  },

  next: function() {
    if (this.step < 3) {
      this._saveStep();
      this.step++;
      this._render();
    } else {
      this.submit();
    }
  },

  prev: function() {
    if (this.step > 0) {
      this._saveStep();
      this.step--;
      this._render();
    }
  },

  _saveStep: function() {
    switch (this.step) {
      case 0: this.data.autoThought = document.getElementById('cbtAutoThought')?.value || ''; break;
      case 1:
        this.data.evidenceFor = document.getElementById('cbtEvidenceFor')?.value || '';
        this.data.evidenceAgainst = document.getElementById('cbtEvidenceAgainst')?.value || '';
        break;
      case 2: this.data.alternative = document.getElementById('cbtAlternative')?.value || ''; break;
    }
  },

  _render: function() {
    var body = document.getElementById('cbtBody');
    var prevBtn = document.getElementById('cbtPrev');
    var nextBtn = document.getElementById('cbtNext');
    var label = document.getElementById('cbtStepLabel');
    if (!body) return;

    var html = '';
    switch (this.step) {
      case 0:
        html = '<label>💭 自动思维 — 当事情发生时，你脑海里闪过了什么想法？</label>'
          + '<textarea id="cbtAutoThought" placeholder="例如：我肯定做不好...没有人会喜欢我...">' + escapeHtml(this.data.autoThought) + '</textarea>'
          + '<div class="cbt-ai-hint">提示：自动思维通常是瞬间出现的、不经思考的判断。试着捕捉它。</div>';
        break;
      case 1:
        html = '<label>📋 证据检验</label>'
          + '<div class="cbt-two-col"><div><label>✅ 支持这个想法的证据</label>'
          + '<textarea id="cbtEvidenceFor" placeholder="有哪些事实支持这个想法？">' + escapeHtml(this.data.evidenceFor) + '</textarea></div>'
          + '<div><label>❌ 反对这个想法的证据</label>'
          + '<textarea id="cbtEvidenceAgainst" placeholder="有哪些事实不支持这个想法？">' + escapeHtml(this.data.evidenceAgainst) + '</textarea></div></div>';
        break;
      case 2:
        html = '<label>🔄 替代视角 — 如果换一个更平衡的眼光来看...</label>'
          + '<textarea id="cbtAlternative" placeholder="例如：虽然这次没做好，但不代表每次都做不好...">' + escapeHtml(this.data.alternative) + '</textarea>'
          + '<div class="cbt-ai-hint">提示：不要追求"正能量"，追求更客观、更全面的视角。</div>';
        break;
      case 3:
        var summary = '📌 自动思维：' + (this.data.autoThought || '（未填写）') + '\n\n'
          + '✅ 支持证据：' + (this.data.evidenceFor || '（未填写）') + '\n'
          + '❌ 反对证据：' + (this.data.evidenceAgainst || '（未填写）') + '\n\n'
          + '🔄 替代视角：' + (this.data.alternative || '（未填写）');
        html = '<label>📝 思维记录总结</label><div class="cbt-summary">' + escapeHtml(summary) + '</div>';
        break;
    }
    body.innerHTML = html;

    // Update step indicators
    var dots = document.querySelectorAll('.cbt-step-dot');
    dots.forEach(function(d, i) {
      d.classList.remove('active', 'done');
      if (i < CbtWizard.step) d.classList.add('done');
      if (i === CbtWizard.step) d.classList.add('active');
    });

    prevBtn.disabled = this.step === 0;
    if (this.step === 3) {
      nextBtn.textContent = '💾 保存记录';
      nextBtn.classList.add('save');
    } else {
      nextBtn.textContent = '下一步 →';
      nextBtn.classList.remove('save');
    }
    if (label) label.textContent = (this.step + 1) + ' / 4';
  },

  submit: function() {
    var self = this;
    fetch('/api/therapy/cbt-record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'situation=' + encodeURIComponent(self.data.situation)
        + '&auto_thought=' + encodeURIComponent(self.data.autoThought)
        + '&evidence_for=' + encodeURIComponent(self.data.evidenceFor)
        + '&evidence_against=' + encodeURIComponent(self.data.evidenceAgainst)
        + '&alternative=' + encodeURIComponent(self.data.alternative)
        + '&reframed=' + encodeURIComponent(self.data.reframed)
    }).then(function(r) { return r.json(); }).then(function(res) {
      if (res.ok) {
        addDebugLog('info', 'CBT记录已保存', 'id=' + res.id, '思维记录已成功保存');
        self.data.reframed = self.data.autoThought + ' → ' + self.data.alternative;
        self.close();
      }
    }).catch(function(e) {
      addDebugLog('error', 'CBT保存失败', e.message);
    });
  }
};

// Expose globally
window.openCbtWizard = function(thought) { CbtWizard.open(thought); };

