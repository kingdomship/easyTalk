// metaphysics.js — Mental panel logic, star map canvas, API calls, glasses hook
"use strict";

// ── State ──
let metaPanelVisible = false;
let metaActiveTab = "benming";
let fullChartData = null;
let chartETag = null;
let refreshTimer = null;

// ── Panel Toggle ──
function initMetaphysics() {
  const toggleBtn = document.getElementById("metaphysics-toggle");
  const panel = document.getElementById("metaphysics-panel");
  const closeBtn = document.getElementById("metaphysics-close");

  if (!toggleBtn || !panel) return;

  toggleBtn.addEventListener("click", () => {
    metaPanelVisible = !metaPanelVisible;
    panel.classList.toggle("hidden", !metaPanelVisible);
    toggleBtn.classList.toggle("active", metaPanelVisible);
    if (metaPanelVisible) {
      loadFullChart();
      loadBirthInfo();
    }
  });

  closeBtn.addEventListener("click", () => {
    metaPanelVisible = false;
    panel.classList.add("hidden");
    toggleBtn.classList.remove("active");
    stopAutoRefresh();
  });

  document.getElementById("edit-birth-btn")?.addEventListener("click", () => {
    document.getElementById("birth-info-form").classList.toggle("hidden");
  });
  document.getElementById("save-birth-btn")?.addEventListener("click", saveBirthInfo);

  document.querySelectorAll("#timeline-tabs .tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#timeline-tabs .tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      metaActiveTab = tab.dataset.tab;
      renderChartForTab();
      if (metaActiveTab === "liuyue" || metaActiveTab === "liunian") {
        startAutoRefresh();
      } else {
        stopAutoRefresh();
      }
    });
  });

  document.getElementById("trigger-reading-btn")?.addEventListener("click", triggerReading);
  document.getElementById("hehun-btn")?.addEventListener("click", triggerHehun);
}

// ── API calls ──
async function loadFullChart() {
  try {
    const headers = {};
    if (chartETag) headers["If-None-Match"] = chartETag;
    const resp = await fetch("/api/metaphysics/full-chart", { headers });
    if (resp.status === 304) return;
    if (!resp.ok) throw new Error("Failed to load chart");
    fullChartData = await resp.json();
    chartETag = resp.headers.get("ETag") || null;
    localStorage.setItem("metaphysics_chart", JSON.stringify(fullChartData));
    localStorage.setItem("metaphysics_etag", chartETag || "");
    renderChartForTab();
    renderBaziTable();
  } catch (e) {
    console.warn("Metaphysics: failed to load chart", e);
    const cached = localStorage.getItem("metaphysics_chart");
    if (cached) {
      try { fullChartData = JSON.parse(cached); renderBaziTable(); } catch (_) {}
    }
  }
}

async function loadBirthInfo() {
  try {
    const resp = await fetch("/api/metaphysics/birth-info");
    const data = await resp.json();
    const display = document.getElementById("birth-info-display");
    if (data.birth_info) {
      const bi = data.birth_info;
      display.innerHTML = escapeHtml(bi.solar_date + " " + bi.clock_time + " " + (bi.city || "北京") + " · " + bi.gender);
    } else {
      display.innerHTML = '<p class="empty-hint">还没有出生信息，填写后才能查看命盘哦~</p>';
    }
  } catch (e) {
    console.warn("Metaphysics: failed to load birth info", e);
  }
}

async function saveBirthInfo() {
  const info = {
    solar_date: document.getElementById("birth-date").value,
    clock_time: document.getElementById("birth-time").value,
    city: document.getElementById("birth-city").value || "北京",
    gender: document.getElementById("birth-gender").value,
  };
  if (!info.solar_date) { alert("请填写日期"); return; }
  try {
    const resp = await fetch("/api/metaphysics/birth-info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(info),
    });
    if (!resp.ok) throw new Error("Save failed");
    document.getElementById("birth-info-form").classList.add("hidden");
    loadBirthInfo();
    loadFullChart();
  } catch (e) {
    alert("保存失败: " + e.message);
  }
}

async function triggerReading() {
  const outputDiv = document.getElementById("reading-output");
  outputDiv.textContent = "解读中...";
  try {
    const resp = await fetch("/api/metaphysics/reading", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: "bazi",
        scope: metaActiveTab === "benming" ? "general" : metaActiveTab,
      }),
    });
    const data = await resp.json();
    outputDiv.textContent = data.reading_text || "解读失败";
  } catch (e) {
    outputDiv.textContent = "解读请求失败: " + e.message;
  }
}

async function triggerHehun() {
  const other = {
    solar_date: document.getElementById("hehun-date").value,
    clock_time: document.getElementById("hehun-time").value || "12:00",
    city: document.getElementById("hehun-city").value || "北京",
    gender: document.getElementById("hehun-gender").value,
  };
  if (!other.solar_date) { alert("请填写对方日期"); return; }
  const outputDiv = document.getElementById("hehun-output");
  outputDiv.textContent = "合盘计算中...";
  try {
    const resp = await fetch("/api/metaphysics/hehun", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ other_birth: other }),
    });
    const data = await resp.json();
    const hepan = data.hepan || {};
    const si = hepan.star_interactions || {};
    const ds = hepan.daxian_sync || {};
    outputDiv.innerHTML = escapeHtml(
      "综合评分: " + (data.compatibility_score || "?") + "/100\n" +
      "纳音关系: " + (data.nayan_relation || "—") + "\n" +
      "干支合: " + (data.ganzhi_he ? data.ganzhi_he.join(", ") : "—") + "\n" +
      "十神互补: " + (data.shishen_complement || "—") + "\n" +
      "五行互补: " + (data.wuxing_balance || "—") + "\n" +
      "---\n" +
      "星曜互动: " + (si.total || "?") + " (" + (si.positive || 0) + "正/" + (si.negative || 0) + "负)\n" +
      "大限同步: " + (ds.sync_level || "—")
    ).replace(/\n/g, "<br>");
  } catch (e) {
    outputDiv.textContent = "合盘请求失败: " + e.message;
  }
}

// ── Rendering ──
function renderBaziTable() {
  const c = fullChartData?.chart || fullChartData;
  if (!c?.bazi?.static?.four_pillars) return;
  const fp = c.bazi.static.four_pillars;
  const tg = c.bazi.static.ten_gods_gan || {};
  ["year", "month", "day", "time"].forEach((k, i) => {
    const ganCell = document.querySelector("#bazi-gan-row td:nth-child(" + (i+1) + ")");
    const zhiCell = document.querySelector("#bazi-zhi-row td:nth-child(" + (i+1) + ")");
    const tgCell = document.querySelector("#bazi-tengod-row td:nth-child(" + (i+1) + ")");
    if (fp[k]) {
      if (ganCell) ganCell.textContent = fp[k].gan || "?";
      if (zhiCell) zhiCell.textContent = fp[k].zhi || "?";
      if (tgCell) tgCell.textContent = tg[k] || "?";
    }
  });
}

function renderChartForTab() {
  if (!fullChartData) return;
  const canvas = document.getElementById("ziwei-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const c = fullChartData.chart || fullChartData;
  drawZiweiStarMap(ctx, c.ziwei, metaActiveTab);
}

function drawZiweiStarMap(ctx, ziweiData, tab) {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  ctx.clearRect(0, 0, w, h);

  const palaces = ziweiData?.static?.palaces;
  if (!palaces || palaces.length !== 12) {
    ctx.fillStyle = "#666";
    ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("请先填写出生信息", w/2, h/2);
    return;
  }

  const cols = 4, rows = 3;
  const cellW = w / cols;
  const cellH = h / rows;
  const cx = cellW / 2;
  const cy = cellH / 2;

  for (let i = 0; i < 12; i++) {
    const p = palaces[i];
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = col * cellW;
    const y = row * cellH;

    ctx.fillStyle = "rgba(255,255,255,0.03)";
    ctx.fillRect(x, y, cellW, cellH);
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.strokeRect(x, y, cellW, cellH);

    ctx.fillStyle = "#888";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(p.name, x + cx, y + 14);

    ctx.fillStyle = "#bbb";
    ctx.font = "bold 11px sans-serif";
    ctx.fillText((p.gan || "?") + (p.zhi || "?"), x + cx, y + 30);

    ctx.fillStyle = "#ddd";
    ctx.font = "9px sans-serif";
    const stars = (p.stars || []).filter(function(s) { return s; }).slice(0, 3);
    stars.forEach(function(s, si) {
      const short = s.replace(/\[.*\]/, "").charAt(0);
      if (s.indexOf("[禄]") >= 0) ctx.fillStyle = "#4caf50";
      else if (s.indexOf("[权]") >= 0) ctx.fillStyle = "#ff9800";
      else if (s.indexOf("[科]") >= 0) ctx.fillStyle = "#2196f3";
      else if (s.indexOf("[忌]") >= 0) ctx.fillStyle = "#f44336";
      else ctx.fillStyle = "#ddd";
      ctx.fillText(short, x + cx - 10 + si * 16, y + 48);
    });

    const sihua = ziweiData?.static?.sihua;
    if (sihua) {
      const dotColors = { "禄": "#4caf50", "权": "#ff9800", "科": "#2196f3", "忌": "#f44336" };
      var di = 0;
      Object.keys(sihua).forEach(function(hua) {
        const info = sihua[hua];
        if (info?.palace_idx === i || info?.palace === p.name) {
          ctx.fillStyle = dotColors[hua] || "#fff";
          ctx.beginPath();
          ctx.arc(x + cellW - 10 - di * 10, y + 10, 3, 0, Math.PI * 2);
          ctx.fill();
          di++;
        }
      });
    }
  }
}

// ── Auto refresh ──
function startAutoRefresh() {
  stopAutoRefresh();
  refreshTimer = setInterval(function() {
    loadFullChart();
  }, 5 * 60 * 1000);
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

// ── Pixel Glasses Hook ──
function drawRoundGlasses(ctx, ox, faceOy, faceCS) {
  const leftEyeX = ox + 20 * faceCS;
  const rightEyeX = ox + 43 * faceCS;
  const eyeY = faceOy + 20 * faceCS;
  const radius = 5 * faceCS;

  ctx.strokeStyle = "#222";
  ctx.lineWidth = Math.max(1, 2 * faceCS);

  ctx.beginPath();
  ctx.arc(leftEyeX, eyeY, radius, 0, Math.PI * 2);
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(rightEyeX, eyeY, radius, 0, Math.PI * 2);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(leftEyeX + radius, eyeY);
  ctx.lineTo(rightEyeX - radius, eyeY);
  ctx.stroke();
}

function setGlassesActive(active) {
  if (!window.faceOverlayHooks) window.faceOverlayHooks = [];
  if (active) {
    if (window.faceOverlayHooks.indexOf(drawRoundGlasses) < 0) {
      window.faceOverlayHooks.push(drawRoundGlasses);
    }
  } else {
    window.faceOverlayHooks = window.faceOverlayHooks.filter(function(fn) { return fn !== drawRoundGlasses; });
  }
}

// ── Mode management ──
function setMetaphysicsMode(mode) {
  localStorage.setItem("metaphysics_mode", mode);
  const toggleBtn = document.getElementById("metaphysics-toggle");
  if (toggleBtn) {
    toggleBtn.classList.toggle("active", mode !== "off");
  }
  if (typeof setGlassesActive === "function") {
    setGlassesActive(mode !== "off");
  }
}

// ── Initialize ──
document.addEventListener("DOMContentLoaded", function() {
  initMetaphysics();
  const cached = localStorage.getItem("metaphysics_chart");
  const etag = localStorage.getItem("metaphysics_etag");
  if (cached) {
    try { fullChartData = JSON.parse(cached); chartETag = etag || null; } catch (_) {}
  }
});
