/** Memory constellation — Obsidian-style interactive graph view.
 *
 * Force-directed graph with zoom/pan/drag. Stars are memory nodes;
 * connections are semantic links. Physics simulation runs continuously
 * for a living, breathing feel.
 */

const Constellation = (() => {
  let canvas = null;
  let ctx = null;
  let animId = 0;
  let data = null;

  // Viewport state (zoom/pan)
  let viewX = 0, viewY = 0;   // pan offset in screen pixels
  let zoom = 1;                // zoom level (1 = default)
  let targetZoom = 1;
  let targetViewX = 0, targetViewY = 0;

  // Node store (with physics state)
  /** @type {GraphNode[]} */
  let nodes = [];
  /** @type {GraphEdge[]} */
  let edges = [];
  let core = null;
  let galaxies = [];

  // Interaction
  let hoveredId = null;
  let selectedId = null;
  let dragNode = null;         // node being dragged
  let dragBg = false;          // panning background
  let dragStartX = 0, dragStartY = 0;
  let dragNodeOrigX = 0, dragNodeOrigY = 0;
  let pointerDownX = 0, pointerDownY = 0;
  let pointerMoved = false;
  const DRAG_THRESHOLD_MOUSE = 4;   // mouse is precise
  const DRAG_THRESHOLD_TOUCH = 12;  // finger jitter on capacitive screens

  // Inertia / momentum for panning
  let panVelX = 0, panVelY = 0;
  let viewVX = 0, viewVY = 0;
  let lastPanTime = 0;

  // Long-press on touch devices
  let longPressTimer = null;
  let longPressFired = false;  // prevent tap from also firing after long-press
  const LONG_PRESS_MS = 600;

  // Pinch zoom midpoint tracking
  let pinchMidX = 0, pinchMidY = 0;

  // Canvas dimensions
  let W = 800, H = 600;
  let CX = 400, CY = 300;

  // Physics config — tuned for calm, grounded feel (not bouncy)
  const REPULSION = 1000;       // lower push = nodes stay closer, less chaotic
  const SPRING_LEN = 130;       // slightly looser rest distance
  const SPRING_K = 0.015;       // weaker springs = less oscillation
  const DAMPING = 0.78;         // more friction = faster settling
  const CENTER_GRAVITY = 0.005; // stronger center pull = tighter cluster
  const MIN_VEL = 0.08;         // stop sooner = less micro-jitter

  let time = 0;

  // ── Data model ────────────────────────────────────────────

  /**
   * @typedef {{ id: number, tag: string, summary: string, importance: number,
   *             x: number, y: number, vx: number, vy: number,
   *             size: number, color: string, galaxy: string,
   *             isCore: boolean, coreType: ('user'|'ai'|null) }} GraphNode
   * @typedef {{ from: number, to: number, weight: number }} GraphEdge
   */

  // ── Init ─────────────────────────────────────────────────

  function init(apiData) {
    data = apiData;
    core = apiData.core;
    galaxies = apiData.galaxies || [];

    nodes = [];
    edges = [];

    // Build nodes from galaxy stars
    for (const g of galaxies) {
      for (const s of g.stars) {
        nodes.push({
          id: s.id,
          tag: s.tag,
          summary: s.summary,
          importance: s.importance || 0.3,
          x: s.x || (Math.random() - 0.5) * 200,
          y: s.y || (Math.random() - 0.5) * 200,
          vx: 0, vy: 0,
          size: s.size || 4,
          color: g.color,
          galaxy: g.topic,
          isCore: false,
          coreType: null,
        });
      }
    }

    // Build edges from connections
    for (const c of (apiData.connections || [])) {
      const fromNode = nodes.find(n => n.id === c.from_id);
      const toNode = nodes.find(n => n.id === c.to_id);
      if (fromNode && toNode) {
        edges.push({ from: c.from_id, to: c.to_id, weight: c.weight || 0.5 });
      }
    }

    // Add core nodes (User + AI) at center
    nodes.push({
      id: -1, tag: core.user.label, summary: '',
      importance: 1.0, x: -28, y: 0, vx: 0, vy: 0,
      size: 9, color: '#ffd700', galaxy: 'core',
      isCore: true, coreType: 'user',
    });
    nodes.push({
      id: -2, tag: core.ai.label, summary: '',
      importance: 1.0, x: 28, y: 0, vx: 0, vy: 0,
      size: 9, color: '#a78bfa', galaxy: 'core',
      isCore: true, coreType: 'ai',
    });

    // Connect core nodes together
    edges.push({ from: -1, to: -2 });

    // Connect stars with high importance to nearest core
    for (const n of nodes) {
      if (n.isCore) continue;
      const distU = Math.hypot(n.x + 28, n.y);
      const distA = Math.hypot(n.x - 28, n.y);
      if (Math.min(distU, distA) < 160 && n.importance > 0.4) {
        edges.push({ from: -1, to: n.id });
      }
    }

    hoveredId = null;
    selectedId = null;
    dragNode = null;
    time = 0;

    // Reset viewport
    viewX = 0; viewY = 0; zoom = 1;
    targetZoom = 1; targetViewX = 0; targetViewY = 0;

    _resize();
    // tick() is started by attach(), not here — avoids double animation loop
  }

  // ── Physics ───────────────────────────────────────────────

  function stepPhysics() {
    // Repulsion between all node pairs (n^2, but N is small)
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.hypot(dx, dy) || 1;
        const minDist = (a.size + b.size) * 2;
        if (dist < minDist) dist = minDist;
        const force = REPULSION / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx -= fx; a.vy -= fy;
        b.vx += fx; b.vy += fy;
      }
    }

    // Spring force along edges
    for (const e of edges) {
      const a = nodes.find(n => n.id === e.from);
      const b = nodes.find(n => n.id === e.to);
      if (!a || !b) continue;
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      const dist = Math.hypot(dx, dy) || 1;
      const weightFactor = 1 - (e.weight || 0.5) * 0.5;  // stronger edges → shorter spring
      const targetLen = SPRING_LEN * weightFactor * (1 + (2 - a.importance - b.importance) * 0.5);
      const displacement = dist - targetLen;
      const force = SPRING_K * displacement;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
    }

    // Center gravity (weak pull toward origin)
    for (const n of nodes) {
      if (n.isCore) continue;
      n.vx -= n.x * CENTER_GRAVITY;
      n.vy -= n.y * CENTER_GRAVITY;
    }

    // Integrate + damping
    for (const n of nodes) {
      if (n === dragNode) { n.vx = 0; n.vy = 0; continue; }
      n.vx *= DAMPING;
      n.vy *= DAMPING;
      if (Math.abs(n.vx) < MIN_VEL) n.vx = 0;
      if (Math.abs(n.vy) < MIN_VEL) n.vy = 0;
      n.x += n.vx;
      n.y += n.vy;
    }

    // Keep core nodes near center with slight dynamics
    const userCore = nodes.find(n => n.id === -1);
    const aiCore = nodes.find(n => n.id === -2);
    if (userCore) {
      userCore.x += (-28 - userCore.x) * 0.15;
      userCore.y += (0 - userCore.y) * 0.15;
      userCore.vx = 0; userCore.vy = 0;
    }
    if (aiCore) {
      aiCore.x += (28 - aiCore.x) * 0.15;
      aiCore.y += (0 - aiCore.y) * 0.15;
      aiCore.vx = 0; aiCore.vy = 0;
    }
  }

  // ── Animation ────────────────────────────────────────────

  function tick() {
    time += 0.016;
    stepPhysics();

    // Apply pan inertia (decay per frame, stops when dragging)
    if (!dragBg && (Math.abs(viewVX) > 0.05 || Math.abs(viewVY) > 0.05)) {
      targetViewX += viewVX;
      targetViewY += viewVY;
      viewVX *= 0.85;  // faster decay for snappier stop
      viewVY *= 0.85;
      if (Math.abs(viewVX) < 0.05) viewVX = 0;
      if (Math.abs(viewVY) < 0.05) viewVY = 0;
    }

    // Smooth zoom/pan — responsive but not floaty
    zoom += (targetZoom - zoom) * 0.14;
    viewX += (targetViewX - viewX) * 0.14;
    viewY += (targetViewY - viewY) * 0.14;

    draw(time);
    animId = requestAnimationFrame(tick);
  }

  function stop() {
    if (animId) { cancelAnimationFrame(animId); animId = 0; }
  }

  // ── Draw ─────────────────────────────────────────────────

  function draw(t) {
    if (!ctx || !core) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    // Background
    ctx.fillStyle = "#07070f";
    ctx.fillRect(0, 0, W, H);

    // Background stars
    drawBgStars(t);

    // Apply viewport transform
    ctx.save();
    ctx.translate(CX + viewX, CY + viewY);
    ctx.scale(zoom, zoom);

    // Draw edges
    const nodeMap = {};
    for (const n of nodes) nodeMap[n.id] = n;

    for (const e of edges) {
      const a = nodeMap[e.from];
      const b = nodeMap[e.to];
      if (!a || !b) continue;

      const isHovered = hoveredId === e.from || hoveredId === e.to;
      const alpha = isHovered ? 0.5 : (selectedId && selectedId !== e.from && selectedId !== e.to ? 0.03 : 0.12);
      const baseWidth = 0.5 + (e.weight || 0.5) * 4;
      const width = isHovered ? baseWidth * 2 : baseWidth;

      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = `rgba(200,200,255,${alpha})`;
      ctx.lineWidth = width;
      ctx.stroke();
    }

    // Draw nodes
    for (const n of nodes) {
      const sx = n.x, sy = n.y;
      const pulse = n.isCore ? (1 + Math.sin(t * 1.5 + n.id) * 0.06) : 1;
      const r = n.size * pulse;
      const isHovered = hoveredId === n.id;
      const isSelected = selectedId === n.id;
      const focusId = hoveredId || selectedId;
      const isDimmed = focusId && !isHovered && !isSelected &&
        !edges.some(e => (e.from === focusId && e.to === n.id) || (e.to === focusId && e.from === n.id));

      if (isDimmed) {
        ctx.globalAlpha = 0.2;
      }

      // Glow
      if (r > 2) {
        const glow = ctx.createRadialGradient(sx, sy, 0, sx, sy, r * 3);
        glow.addColorStop(0, n.color + (isHovered ? "88" : "44"));
        glow.addColorStop(1, "transparent");
        ctx.beginPath();
        ctx.arc(sx, sy, r * 3, 0, Math.PI * 2);
        ctx.fillStyle = glow;
        ctx.fill();
      }

      // Node body
      ctx.beginPath();
      if (n.isCore) {
        // Diamond shape for core nodes
        ctx.moveTo(sx, sy - r * 1.2);
        ctx.lineTo(sx + r * 1.2, sy);
        ctx.lineTo(sx, sy + r * 1.2);
        ctx.lineTo(sx - r * 1.2, sy);
        ctx.closePath();
      } else {
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
      }
      ctx.fillStyle = isHovered ? n.color : n.color + "dd";
      ctx.fill();

      if (isSelected) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Brightness spike for important nodes
      if (n.importance > 0.5 && !n.isCore) {
        const spikeAlpha = 0.15 + Math.sin(t * 3 + n.id) * 0.1;
        ctx.beginPath();
        ctx.arc(sx, sy, r * 2, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${spikeAlpha})`;
        ctx.fill();
      }

      // Label
      if (zoom > 0.5 || n.isCore) {
        ctx.fillStyle = n.color + "cc";
        ctx.font = `${Math.max(9, 11 / zoom)}px monospace`;
        ctx.textAlign = "center";
        ctx.fillText(n.tag, sx, sy + r + 13 / zoom);
      }

      ctx.globalAlpha = 1;
    }

    ctx.restore();
  }

  function drawBgStars(t) {
    for (let i = 0; i < 80; i++) {
      const x = (Math.sin(i * 127.1 + t * 0.02) * 0.5 + 0.5) * W;
      const y = (Math.cos(i * 311.7 + t * 0.015) * 0.5 + 0.5) * H;
      const alpha = 0.1 + Math.sin(t * 0.5 + i) * 0.06;
      ctx.fillStyle = `rgba(200,200,255,${alpha})`;
      ctx.fillRect(x, y, 1, 1);
    }
  }

  // ── Interaction ──────────────────────────────────────────

  function screenToWorld(sx, sy) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (sx - rect.left - CX - viewX) / zoom,
      y: (sy - rect.top - CY - viewY) / zoom,
    };
  }

  function findNodeAt(wx, wy) {
    const threshold = 14;
    let closest = null;
    let closestDist = threshold;
    for (const n of nodes) {
      const dx = n.x - wx;
      const dy = n.y - wy;
      const dist = Math.hypot(dx, dy);
      if (dist < closestDist) {
        closestDist = dist;
        closest = n;
      }
    }
    return closest;
  }

  // ── Attach / Detach ──────────────────────────────────────

  function _resize() {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentNode.getBoundingClientRect();
    W = rect.width;
    H = rect.height;
    CX = W / 2;
    CY = H / 2;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
  }

  let resizeTimer = 0;
  function onResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(_resize, 150);
  }

  function attach(parentEl) {
    if (canvas) detach();
    canvas = document.createElement("canvas");
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.display = "block";
    canvas.style.cursor = "grab";
    ctx = canvas.getContext("2d");

    // Mouse events
    canvas.addEventListener("mousedown", (e) => {
      pointerDownX = e.clientX;
      pointerDownY = e.clientY;
      pointerMoved = false;
      const { x, y } = screenToWorld(e.clientX, e.clientY);
      const node = findNodeAt(x, y);
      if (node) {
        dragNode = node;
        dragNodeOrigX = node.x;
        dragNodeOrigY = node.y;
        canvas.style.cursor = "grabbing";
        // Selection + callback deferred to mouseup (click vs drag check)
      } else {
        dragBg = true;
        dragStartX = e.clientX - targetViewX;
        dragStartY = e.clientY - targetViewY;
        canvas.style.cursor = "grabbing";
      }
    });

    canvas.addEventListener("mousemove", (e) => {
      // Check if pointer has moved beyond click threshold
      const dx = e.clientX - pointerDownX;
      const dy = e.clientY - pointerDownY;
      if (Math.abs(dx) > DRAG_THRESHOLD_MOUSE || Math.abs(dy) > DRAG_THRESHOLD_MOUSE) {
        pointerMoved = true;
      }
      if (dragNode) {
        const { x, y } = screenToWorld(e.clientX, e.clientY);
        dragNode.x = x;
        dragNode.y = y;
        // Track pan velocity for inertia
        if (lastPanTime > 0) {
          const dt = (performance.now() - lastPanTime) * 0.06; // scale to ~frame units
          panVelX = (x - dragNodeOrigX) / Math.max(dt, 1);
          panVelY = (y - dragNodeOrigY) / Math.max(dt, 1);
        }
        dragNodeOrigX = x; dragNodeOrigY = y;
        lastPanTime = performance.now();
        return;
      }
      if (dragBg) {
        // Track pan velocity for inertia
        const prevX = targetViewX, prevY = targetViewY;
        targetViewX = e.clientX - dragStartX;
        targetViewY = e.clientY - dragStartY;
        viewX = targetViewX;
        viewY = targetViewY;
        panVelX = targetViewX - prevX;
        panVelY = targetViewY - prevY;
        lastPanTime = performance.now();
        return;
      }
      const { x, y } = screenToWorld(e.clientX, e.clientY);
      const node = findNodeAt(x, y);
      hoveredId = node ? node.id : null;
      canvas.style.cursor = node ? "pointer" : "grab";
    });

    canvas.addEventListener("mouseup", (e) => {
      if (dragNode && !pointerMoved) {
        // Click on node — select and show bubble
        selectedId = dragNode.id;
        if (window._onConstellationStarClick && !dragNode.isCore) {
          window._onConstellationStarClick({
            id: dragNode.id, tag: dragNode.tag, summary: dragNode.summary,
            importance: dragNode.importance, color: dragNode.color,
            galaxy: dragNode.galaxy,
            galaxyName: (galaxies.find(g => g.topic === dragNode.galaxy) || {}).label || dragNode.galaxy,
          });
        }
      }
      if (!dragNode && !dragBg && !pointerMoved) {
        // Click on blank — deselect and close bubble
        selectedId = null;
        if (window._onConstellationStarClick) {
          window._onConstellationStarClick(null);
        }
      }
      // Apply pan inertia on release
      if (dragBg && (Math.abs(panVelX) > 0.5 || Math.abs(panVelY) > 0.5)) {
        viewVX = panVelX;
        viewVY = panVelY;
      }
      dragNode = null;
      dragBg = false;
      canvas.style.cursor = hoveredId ? "pointer" : "grab";
    });

    canvas.addEventListener("mouseleave", () => {
      hoveredId = null;
      dragNode = null;
      dragBg = false;
      canvas.style.cursor = "grab";
    });

    // Zoom with scroll wheel (zoom toward cursor, Obsidian-style)
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      const newZoom = Math.max(0.2, Math.min(3.0, targetZoom * delta));
      // Keep the world point under the cursor fixed
      targetViewX = mouseX - CX - (mouseX - CX - viewX) * (newZoom / zoom);
      targetViewY = mouseY - CY - (mouseY - CY - viewY) * (newZoom / zoom);
      targetZoom = newZoom;
    }, { passive: false });

    // Touch support
    let touchDist0 = 0;
    canvas.addEventListener("touchstart", (e) => {
      // Clear any stale long-press state
      if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
      longPressFired = false;

      if (e.touches.length === 1) {
        pointerDownX = e.touches[0].clientX;
        pointerDownY = e.touches[0].clientY;
        pointerMoved = false;
        const { x, y } = screenToWorld(e.touches[0].clientX, e.touches[0].clientY);
        const node = findNodeAt(x, y);
        if (node) {
          dragNode = node;
          dragNodeOrigX = node.x;
          dragNodeOrigY = node.y;
          // Start long-press timer for touch devices
          longPressTimer = setTimeout(() => {
            if (dragNode && !pointerMoved && !longPressFired) {
              longPressFired = true;
              longPressTimer = null;
              selectedId = dragNode.id;
              if (window._onConstellationStarClick && !dragNode.isCore) {
                window._onConstellationStarClick({
                  id: dragNode.id, tag: dragNode.tag, summary: dragNode.summary,
                  importance: dragNode.importance, color: dragNode.color,
                  galaxy: dragNode.galaxy,
                  galaxyName: (galaxies.find(g => g.topic === dragNode.galaxy) || {}).label || dragNode.galaxy,
                });
              }
            }
          }, LONG_PRESS_MS);
        } else {
          dragBg = true;
          dragStartX = e.touches[0].clientX - targetViewX;
          dragStartY = e.touches[0].clientY - targetViewY;
        }
      } else if (e.touches.length === 2) {
        dragBg = false;
        dragNode = null;
        if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        touchDist0 = Math.hypot(dx, dy);
        // Track pinch midpoint for anchor-fixed zoom
        const rect = canvas.getBoundingClientRect();
        pinchMidX = (e.touches[0].clientX + e.touches[1].clientX) / 2 - rect.left;
        pinchMidY = (e.touches[0].clientY + e.touches[1].clientY) / 2 - rect.top;
      }
    }, { passive: false });

    canvas.addEventListener("touchmove", (e) => {
      e.preventDefault();
      if (e.touches.length === 1) {
        const dx = e.touches[0].clientX - pointerDownX;
        const dy = e.touches[0].clientY - pointerDownY;
        if (Math.abs(dx) > DRAG_THRESHOLD_TOUCH || Math.abs(dy) > DRAG_THRESHOLD_TOUCH) {
          pointerMoved = true;
        }
        // Clear long-press timer if user is dragging
        if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
      }
      if (e.touches.length === 1 && dragNode) {
        const { x, y } = screenToWorld(e.touches[0].clientX, e.touches[0].clientY);
        dragNode.x = x;
        dragNode.y = y;
        dragNodeOrigX = x; dragNodeOrigY = y;
      } else if (e.touches.length === 1 && dragBg) {
        const prevX = targetViewX, prevY = targetViewY;
        targetViewX = e.touches[0].clientX - dragStartX;
        targetViewY = e.touches[0].clientY - dragStartY;
        viewX = targetViewX; viewY = targetViewY;
        panVelX = targetViewX - prevX;
        panVelY = targetViewY - prevY;
      } else if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const newDist = Math.hypot(dx, dy);
        if (touchDist0 > 0 && newDist > 0) {
          const rect = canvas.getBoundingClientRect();
          const newMidX = (e.touches[0].clientX + e.touches[1].clientX) / 2 - rect.left;
          const newMidY = (e.touches[0].clientY + e.touches[1].clientY) / 2 - rect.top;
          const scale = newDist / touchDist0;
          const newZoom = Math.max(0.2, Math.min(3.0, targetZoom * scale));
          // Keep the world point under the pinch midpoint fixed
          targetViewX = newMidX - CX - (pinchMidX - CX - viewX) * (newZoom / zoom);
          targetViewY = newMidY - CY - (pinchMidY - CY - viewY) * (newZoom / zoom);
          targetZoom = newZoom;
          pinchMidX = newMidX;
          pinchMidY = newMidY;
          touchDist0 = newDist;
        }
      }
    }, { passive: false });

    function onTouchEnd() {
      // Clear long-press timer if it hasn't fired yet
      if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }

      if (dragNode && !pointerMoved && !longPressFired) {
        // Tap on node — select and show bubble
        selectedId = dragNode.id;
        if (window._onConstellationStarClick && !dragNode.isCore) {
          window._onConstellationStarClick({
            id: dragNode.id, tag: dragNode.tag, summary: dragNode.summary,
            importance: dragNode.importance, color: dragNode.color,
            galaxy: dragNode.galaxy,
            galaxyName: (galaxies.find(g => g.topic === dragNode.galaxy) || {}).label || dragNode.galaxy,
          });
        }
      }
      if (!dragNode && !dragBg && !pointerMoved && !longPressFired) {
        // Tap on blank — deselect and close bubble
        selectedId = null;
        if (window._onConstellationStarClick) {
          window._onConstellationStarClick(null);
        }
      }
      // Apply pan inertia on release
      if (dragBg && (Math.abs(panVelX) > 0.5 || Math.abs(panVelY) > 0.5)) {
        viewVX = panVelX;
        viewVY = panVelY;
      }
      dragNode = null;
      dragBg = false;
      touchDist0 = 0;
    }
    canvas.addEventListener("touchend", onTouchEnd);
    canvas.addEventListener("touchcancel", onTouchEnd);

    // Double-click to reset view
    canvas.addEventListener("dblclick", () => {
      targetZoom = 1;
      targetViewX = 0;
      targetViewY = 0;
      selectedId = null;
    });

    parentEl.appendChild(canvas);
    window.addEventListener("resize", onResize);
    _resize();
    tick();
  }

  function detach() {
    stop();
    window.removeEventListener("resize", onResize);
    if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
    canvas = null;
    ctx = null;
    core = null;
    nodes = [];
    edges = [];
    hoveredId = null;
    selectedId = null;
    dragNode = null;
  }

  function clearSelection() {
    selectedId = null;
  }

  return { init, attach, detach, stop, clearSelection };
})();
