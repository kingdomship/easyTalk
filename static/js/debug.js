// @ts-check
// ═══════════════════════════════════════════
// Debug panel (triple-click bottom-left corner)
// ═══════════════════════════════════════════
var debugTrigger = document.getElementById('debug-trigger');
var debugPanel = document.getElementById('debug-panel');
var debugClicks = 0, debugTimer = null;
var ERROR_PATTERNS = {
  'fetch': { cause: '网络请求被阻断或服务器未响应', fix: '检查容器运行状态: docker ps, 检查端口映射' },
  'HTTP 5': { cause: '服务器内部错误', fix: '查看容器日志: docker logs emoji-chat-app-1' },
  'HTTP 4': { cause: '请求参数错误或端点不存在', fix: '检查API路径和请求格式' },
  'timeout': { cause: '请求超时', fix: 'DeepSeek API 响应慢或网络延迟高，考虑降低max_tokens' },
  'rate': { cause: 'API 速率限制', fix: '等待几秒后重试，或检查API配额' },
  'API key': { cause: 'API Key 无效或过期', fix: '检查 ⚙️ 设置中的 API Key 配置' },
  '嗯...': { cause: 'LLM 返回异常或 JSON 解析失败', fix: '检查 DeepSeek 控制台是否有报错，尝试简化 system prompt' },
};

function addDebugLog(level, title, msg, analysis) {
  var now = new Date().toLocaleTimeString();
  var entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = '<span class="log-time">' + now + '</span><span class="log-' + level + '">[' + level.toUpperCase() + '] ' + escapeHtml(title) + ': ' + escapeHtml(msg) + '</span>';
  if (analysis) {
    entry.innerHTML += '<div class="log-analysis">→ ' + escapeHtml(analysis) + '</div>';
  }
  debugPanel.insertBefore(entry, debugPanel.firstChild);
  if (!analysis && level === 'error') {
    for (var pattern in ERROR_PATTERNS) {
      if (msg.toLowerCase().indexOf(pattern.toLowerCase()) !== -1) {
        var info = ERROR_PATTERNS[pattern];
        var analysisEntry = document.createElement('div');
        analysisEntry.className = 'log-analysis';
        analysisEntry.textContent = '→ 原因: ' + info.cause + ' | 建议: ' + info.fix;
        entry.appendChild(analysisEntry);
        break;
      }
    }
  }
}

debugTrigger.addEventListener('click', function() {
  debugClicks++;
  clearTimeout(debugTimer);
  debugTimer = setTimeout(function() { debugClicks = 0; }, 500);
  if (debugClicks >= 3) {
    debugClicks = 0;
    debugPanel.classList.toggle('visible');
  }
});

// Capture global errors and unhandled rejections
window.addEventListener('error', function(e) {
  addDebugLog('error', '全局异常', (e.filename || '') + ':' + (e.lineno || '') + ' ' + (e.message || ''),
    '未捕获的JS错误，检查对应代码行');
});
window.addEventListener('unhandledrejection', function(e) {
  addDebugLog('error', '未处理的Promise拒绝', String(e.reason || ''),
    '异步操作失败未catch，检查fetch/await调用');
});

// Override console.error to capture in debug panel
var _origConsoleError = console.error;
console.error = function() {
  var args = arguments;
  _origConsoleError.apply(console, args);
  var parts = [];
  for (var i = 0; i < args.length; i++) {
    var a = args[i];
    if (typeof a === 'object') {
      try { parts.push(JSON.stringify(a).slice(0, 200)); }
      catch (_) { parts.push(String(a)); }
    } else {
      parts.push(String(a));
    }
  }
  addDebugLog('error', 'Console', parts.join(' '));
};
var _origConsoleWarn = console.warn;
console.warn = function() {
  var args = arguments;
  _origConsoleWarn.apply(console, args);
  var parts = [];
  for (var i = 0; i < args.length; i++) { parts.push(String(args[i])); }
  addDebugLog('warn', 'Console', parts.join(' '));
};

addDebugLog('info', '启动', '页面加载完成', '正常启动，等待用户交互');
