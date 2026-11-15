/* 3D map of a topic. Vertical axis = general difficulty (level + question number, 1..228);
   every problem keeps its place in ONE UMAP shared by all difficulties. Arrows go to similar,
   slightly harder problems (same level first). Tap a problem to zoom into its difficulty and the
   ones just below and above; tap outside to go back to the whole ladder.
   Plain canvas 2D, no libraries (the board is offline). Uses app.js helpers at call time. */
"use strict";

const MAP_SUB_COLORS = ["#6fa8dc", "#a597f5", "#f28fb0", "#9ad17f", "#c9d6ff"];   // never the status colours
const MAP_COL = { solved: "#34e3d4", failed: "#ff8a4c", next: "#ffd166", mission: "#ffd166", plane: "79,179,181" };
const N_ID = 0, N_X = 1, N_Y = 2, N_LV = 3, N_SUB = 4, N_NUM = 5, N_G = 6;

class Map3D {
  constructor(canvas, data, opts = {}) {
    this.c = canvas; this.ctx = canvas.getContext("2d");
    this.data = data; this.opts = opts;
    this.yaw = -0.6; this.pitch = 0.42; this.dist = 6.2; this.zoom = 1;
    this.R = 1.2; this.HT = 2.9;                     // plane half-size, height of the whole ladder
    this.sel = null; this.hover = null; this.unfold = 0; this.t0 = performance.now();
    this.auto = true; this.lastInput = 0;
    this.focus = null; this.f = 0;                  // focused difficulty and the 0..1 blend towards it
    this.total = data.ladder.total;
    this.offsets = Object.fromEntries(Object.entries(data.ladder.offsets).map(([k, v]) => [Number(k), v]));
    this.g = data.nodes.map((n) => n[N_G]);
    this.gs = [...new Set(this.g)].sort((a, b) => a - b);          // difficulties present in this topic
    const N = data.nodes.length;
    this.out = Array.from({ length: N }, () => []);
    this.inn = Array.from({ length: N }, () => []);
    for (const [a, b, s] of data.edges) { this.out[a].push([b, s]); this.inn[b].push([a, s]); }
    const me = data.me || {};
    this.solved = new Set(me.solved || []); this.failed = new Set(me.failed || []);
    this.mission = new Set(me.mission || []);
    this.done = new Set([...this.solved, ...this.failed]);
    this.cls = new Map((data.class || []).map(([i, n, ok]) => [i, { n, ok }]));
    this.tree = this.buildTree();
    this.next = new Set();
    for (const i of this.solved) for (const [j] of this.out[i]) if (!this.done.has(j)) this.next.add(j);
    this.myLevel = me.theta == null ? null : Math.floor(me.theta);
    this.bind(); this.resize();
    this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(canvas.parentElement);
    this.frame = this.frame.bind(this); this.raf = requestAnimationFrame(this.frame);
  }

  /** The student's own tree: each attempted problem hangs from the closest attempted one
      (in the shared UMAP plane) on the nearest lower difficulty. */
  buildTree() {
    const done = [...this.done], links = [], n = this.data.nodes;
    for (const i of done) {
      let best = null, bd = Infinity, bg = -1;
      for (const j of done) {
        if (this.g[j] >= this.g[i]) continue;
        const d = Math.hypot(n[i][N_X] - n[j][N_X], n[i][N_Y] - n[j][N_Y]);
        if (this.g[j] > bg || (this.g[j] === bg && d < bd)) { best = j; bd = d; bg = this.g[j]; }
      }
      if (best != null) links.push([best, i]);
    }
    return links;
  }

  destroy() { cancelAnimationFrame(this.raf); this.ro.disconnect(); window.removeEventListener("keydown", this.onKey); this.dead = true; }

  resize() {
    const r = this.c.parentElement.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    this.w = r.width; this.h = r.height;
    this.c.width = Math.round(r.width * dpr); this.c.height = Math.round(r.height * dpr);
    this.c.style.width = r.width + "px"; this.c.style.height = r.height + "px";
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // ---- vertical placement: whole ladder vs the three focused difficulties
  zAll(g) { return ((g - 0.5) / this.total - 0.5) * this.HT * this.unfold; }
  slices() {
    if (this.focus == null) return null;
    const k = this.gs.indexOf(this.focus);
    return [this.gs[k - 1], this.focus, this.gs[k + 1]];
  }
  zFocus(g) {
    const s = this.slices(), gap = 1.0;
    const k = s.indexOf(g);
    if (k >= 0 && g != null) return (k - 1) * gap + 0.3;          // a little up: the legend sits at the bottom
    return g < this.focus ? -2.2 : 2.2;                         // everything else slides away
  }
  zOf(g) { return this.f > 0.001 && this.focus != null ? this.zAll(g) * (1 - this.f) + this.zFocus(g) * this.f : this.zAll(g); }
  visible(i) {
    if (this.focus == null) return 1;
    return this.slices().includes(this.g[i]) ? 1 : 1 - this.f;
  }

  project(x, y, z) {
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
    const x1 = x * cy - y * sy, y1 = x * sy + y * cy;
    const cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    const depth = y1 * cp - z * sp, up = y1 * sp + z * cp;
    const zoom = this.zoom * (1 + 0.18 * this.f);
    const d = this.dist + depth, f = Math.min(this.w * 0.95, this.h * 1.1) * 0.98 * zoom / d;
    return [this.w / 2 + x1 * f, this.h / 2 + 8 - up * f, f, d];
  }

  bind() {
    const ptrs = new Map(); let start = null, pinch = null, moved = 0;
    const touch = () => { this.auto = false; this.lastInput = performance.now(); };
    this.onKey = (e) => { if (e.key === "Escape") this.setFocus(null); };
    window.addEventListener("keydown", this.onKey);
    this.c.addEventListener("pointerdown", (e) => {
      this.c.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, [e.clientX, e.clientY]);
      start = [e.clientX, e.clientY, this.yaw, this.pitch]; moved = 0; touch();
      if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; pinch = [Math.hypot(a[0] - b[0], a[1] - b[1]), this.zoom]; }
    });
    this.c.addEventListener("pointermove", (e) => {
      const rect = this.c.getBoundingClientRect();
      if (!ptrs.has(e.pointerId)) {
        const x = e.clientX - rect.left, y = e.clientY - rect.top;
        this.hover = this.pick(x, y);
        this.hoverBand = this.hover != null ? this.bandOf(this.g[this.hover]) : this.pickPlane(x, y);
        this.c.style.cursor = this.hover != null ? "pointer" : "grab";
        return;
      }
      ptrs.set(e.pointerId, [e.clientX, e.clientY]); touch();
      if (ptrs.size === 2 && pinch) {
        const [a, b] = [...ptrs.values()];
        this.zoom = Math.max(0.6, Math.min(3.5, pinch[1] * Math.hypot(a[0] - b[0], a[1] - b[1]) / pinch[0]));
        moved = 99; return;
      }
      const dx = e.clientX - start[0], dy = e.clientY - start[1]; moved = Math.max(moved, Math.abs(dx) + Math.abs(dy));
      this.yaw = start[2] + dx * 0.008;
      this.pitch = Math.max(0.05, Math.min(1.35, start[3] + dy * 0.006));
    });
    this.c.addEventListener("pointerup", (e) => {
      const rect = this.c.getBoundingClientRect();
      if (ptrs.size === 1 && moved < 6) {
        const i = this.pick(e.clientX - rect.left, e.clientY - rect.top);
        if (i == null) this.setFocus(null); else this.select(i);       // outside: back to the whole ladder
      }
      ptrs.delete(e.pointerId); if (ptrs.size < 2) pinch = null;
    });
    this.c.addEventListener("pointercancel", (e) => ptrs.delete(e.pointerId));
    this.c.addEventListener("pointerleave", () => { this.hover = null; this.hoverBand = null; });
    this.c.addEventListener("wheel", (e) => { e.preventDefault(); touch(); this.zoom = Math.max(0.6, Math.min(3.5, this.zoom * Math.exp(-e.deltaY * 0.0012))); }, { passive: false });
  }

  select(i) {
    this.sel = i;
    if (i != null) this.setFocus(this.g[i], true);
    this.opts.onSelect && this.opts.onSelect(i);
  }

  setFocus(g, keepSel) {
    if (g == null) {
      this.focusTarget = 0;
      if (!keepSel && this.sel != null) { this.sel = null; this.opts.onSelect && this.opts.onSelect(null); }
    } else {
      if (this.focus != null && this.focus !== g && this.f > 0.5) this.f = 0.5;   // glide to the new difficulty
      this.focus = g; this.focusTarget = 1;
    }
    this.opts.onFocus && this.opts.onFocus(g == null ? null : g);
  }

  /** Move the focus one difficulty down (-1) or up (+1). */
  step(dir) {
    const k = this.gs.indexOf(this.focus);
    const g = this.gs[k + dir];
    if (g == null) return;
    this.sel = null; this.opts.onSelect && this.opts.onSelect(null);
    this.setFocus(g);
  }

  /** What "a level" is under the mouse: a whole level of the ladder ("L3"), or one of the three
      difficulties when zoomed in ("G61"). */
  bandOf(g) { return this.focus != null && this.f > 0.5 ? "G" + g : "L" + this.levelOf(g); }
  inBand(i, band) {
    if (band == null) return true;
    return band[0] === "G" ? this.g[i] === Number(band.slice(1)) : this.levelOf(this.g[i]) === Number(band.slice(1));
  }

  /** The plane whose outline is closest to the mouse (within 14 px), or whose label is under it. */
  pickPlane(x, y) {
    let best = null, bd = 14;
    for (const pl of this.planesDrawn || []) {
      if (pl.alpha < 0.4) continue;
      const [lx, ly] = pl.labelAt;
      if (x >= lx - 4 && x <= lx + 90 && y >= ly - 14 && y <= ly + 4) return pl.band;
      for (let k = 0; k < 4; k++) {
        const a = pl.pts[k], b = pl.pts[(k + 1) % 4];
        const dx = b[0] - a[0], dy = b[1] - a[1], len = dx * dx + dy * dy || 1;
        const u = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / len));
        const d = Math.hypot(x - (a[0] + u * dx), y - (a[1] + u * dy));
        if (d < bd) { bd = d; best = pl.band; }
      }
    }
    return best;
  }

  pick(x, y) {
    let best = null, bd = 16;
    for (const [i, sx, sy, a] of this.proj || []) { if (a < 0.3) continue; const d = Math.hypot(sx - x, sy - y); if (d < bd) { bd = d; best = i; } }
    return best;
  }

  arrow(a, b, color, width, dash, t, alpha = 1) {
    if (alpha < 0.02) return;
    const ctx = this.ctx;
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2 - Math.abs(b[0] - a[0]) * 0.08;   // a gentle arc
    ctx.globalAlpha = alpha; ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash || []);
    if (dash) ctx.lineDashOffset = -t * 18;
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.quadraticCurveTo(mx, my, b[0], b[1]); ctx.stroke(); ctx.setLineDash([]);
    const u = 0.86, px = (1 - u) * (1 - u) * a[0] + 2 * (1 - u) * u * mx + u * u * b[0], py = (1 - u) * (1 - u) * a[1] + 2 * (1 - u) * u * my + u * u * b[1];
    const ang = Math.atan2(b[1] - py, b[0] - px), s = 3 + width * 1.6;
    ctx.fillStyle = color; ctx.beginPath();
    ctx.moveTo(px + Math.cos(ang) * s, py + Math.sin(ang) * s);
    ctx.lineTo(px + Math.cos(ang + 2.5) * s, py + Math.sin(ang + 2.5) * s);
    ctx.lineTo(px + Math.cos(ang - 2.5) * s, py + Math.sin(ang - 2.5) * s); ctx.fill();
    ctx.globalAlpha = 1;
  }

  plane(z, fill, stroke, width, label, labelColor, alpha, band) {
    if (alpha < 0.02) return;
    const ctx = this.ctx, P = 1.45 * this.R, lit = band != null && band === this.hoverBand;
    const pts = [[-P, -P], [P, -P], [P, P], [-P, P]].map(([x, y]) => this.project(x, y, z));
    ctx.globalAlpha = alpha; ctx.fillStyle = lit ? "rgba(52,227,212,.16)" : fill;
    ctx.strokeStyle = lit ? "rgba(255,255,255,.9)" : stroke; ctx.lineWidth = lit ? 2 : width;
    ctx.beginPath(); pts.forEach((p, k) => (k ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath(); ctx.fill(); ctx.stroke();
    const lab = pts.reduce((a, b) => (b[0] < a[0] ? b : a)), at = [Math.max(6, lab[0] + 6), lab[1] - 4];
    if (label) {
      ctx.fillStyle = lit ? "#fff" : labelColor; ctx.font = `${lit ? 800 : 600} ${lit ? 12 : 11}px system-ui, sans-serif`; ctx.textAlign = "left";
      ctx.fillText(lit && band[0] === "L" ? `${label} · ${this.countBand(band)} problemas` : label, at[0], at[1]);
    }
    ctx.globalAlpha = 1;
    if (band != null) this.planesDrawn.push({ band, pts, labelAt: at, alpha });
  }

  countBand(band) {
    this._counts = this._counts || {};
    if (!(band in this._counts)) this._counts[band] = this.g.filter((_, i) => this.inBand(i, band)).length;
    return this._counts[band];
  }

  /** Colour of a problem, the same in the whole ladder, the zoom and the footprints:
      student status (solved / failed / suggested), class accuracy for the teacher, else subtopic. */
  style(i, t) {
    let col = MAP_SUB_COLORS[this.data.nodes[i][N_SUB] % MAP_SUB_COLORS.length], alpha = 0.75, r = 1, glow = null, status = false;
    if (this.cls.size) {
      const s = this.cls.get(i);
      if (s) {
        col = s.ok / s.n >= 0.6 ? "#7fd39a" : s.ok / s.n >= 0.3 ? "#e9b866" : "#ff8a4c";
        alpha = 0.95; r = 1 + Math.min(2, Math.sqrt(s.n) * 0.45); glow = col; status = true;
      } else alpha = 0.35;
    }
    if (this.done.size || this.mission.size) {
      if (this.solved.has(i)) { col = MAP_COL.solved; r = 1.6; glow = col; status = true; }
      else if (this.failed.has(i)) { col = MAP_COL.failed; r = 1.5; glow = col; status = true; }
      else if (this.next.has(i)) { col = MAP_COL.next; r = 1.25 + 0.2 * Math.sin(t * 3 + i); status = true; }
      else alpha = 0.45;
    }
    return { col, alpha, r, glow, status };
  }

  levelOf(g) {
    let lv = 0;
    for (const [l, off] of Object.entries(this.offsets)) if (g > off) lv = Number(l);
    return lv;
  }

  frame(now) {
    if (this.dead) return;
    const t = (now - this.t0) / 1000, ctx = this.ctx;
    this.unfold = 1 - Math.pow(1 - Math.min(1, t / 1.4), 3);
    const target = this.focusTarget || 0;
    this.f += (target - this.f) * 0.12;
    if (target === 0 && this.f < 0.002) { this.f = 0; this.focus = null; }
    if (!this.auto && now - this.lastInput > 9000) this.auto = true;
    if (this.auto) this.yaw += 0.0018 * (1 - 0.7 * this.f);
    const g = ctx.createRadialGradient(this.w / 2, this.h * 0.35, 10, this.w / 2, this.h / 2, Math.max(this.w, this.h));
    g.addColorStop(0, "#123a42"); g.addColorStop(1, "#06161b");
    ctx.fillStyle = g; ctx.fillRect(0, 0, this.w, this.h);
    const F = this.f, n = this.data.nodes;
    this.planesDrawn = [];
    const band = this.hoverBand;

    // whole ladder: one plane where each level starts
    for (const [lvS, off] of Object.entries(this.offsets)) {
      const lv = Number(lvS), mine = this.myLevel === lv;
      this.plane(this.zAll(off + 0.5), `rgba(${MAP_COL.plane},${mine ? 0.12 : 0.045})`,
        mine ? "rgba(52,227,212,.75)" : `rgba(${MAP_COL.plane},.22)`, mine ? 1.6 : 1,
        mine ? `N${lv + 1} · tú` : `N${lv + 1}`, mine ? "#34e3d4" : "rgba(200,230,232,.7)", 1 - F, "L" + lv);
    }
    // focus: the three difficulties
    const sl = this.slices();
    if (sl && F > 0.02) {
      sl.forEach((gg, k) => {
        if (gg == null) return;
        const lv = this.levelOf(gg), q = gg - this.offsets[lv];
        const mid = k === 1;
        this.plane(this.zFocus(gg) * F + this.zAll(gg) * (1 - F), `rgba(${MAP_COL.plane},${mid ? 0.14 : 0.07})`,
          mid ? "rgba(255,255,255,.7)" : `rgba(${MAP_COL.plane},.5)`, mid ? 1.6 : 1,
          `Nivel ${lv + 1} · pregunta ${q}  (dificultad ${gg})${mid ? "" : k === 0 ? "  ▼ más fácil" : "  ▲ más difícil"}`,
          mid ? "#fff" : "rgba(210,235,237,.85)", F, "G" + gg);
        // footprint: every problem of the topic, in its own colour, faintly on each plane
        const z = this.zFocus(gg) * F + this.zAll(gg) * (1 - F);
        n.forEach((nd, i) => {
          if (this.g[i] === gg) return;                      // the real ones are drawn later, full size
          const st = this.style(i, 0);
          const p = this.project(nd[N_X] * this.R, nd[N_Y] * this.R, z);
          ctx.globalAlpha = F * (st.status ? 0.55 : 0.28); ctx.fillStyle = st.col;
          ctx.beginPath(); ctx.arc(p[0], p[1], st.status ? 2.4 : 1.7, 0, 6.283); ctx.fill();
        });
        ctx.globalAlpha = 1;
      });
    }

    // project nodes
    const pr = n.map((nd, i) => this.project(nd[N_X] * this.R, nd[N_Y] * this.R, this.zOf(this.g[i])));
    const vis = n.map((_, i) => this.visible(i));
    this.proj = pr.map((p, i) => [i, p[0], p[1], vis[i]]);

    // all arrows, faint (fade out in focus)
    if (F < 0.98) {
      ctx.globalAlpha = 1 - F; ctx.strokeStyle = "rgba(170,215,220,.07)"; ctx.lineWidth = 1; ctx.beginPath();
      for (const [a, b] of this.data.edges) { ctx.moveTo(pr[a][0], pr[a][1]); ctx.lineTo(pr[b][0], pr[b][1]); }
      ctx.stroke(); ctx.globalAlpha = 1;
    }
    // in focus: how problems move from one difficulty to the next (closest on the shared map)
    if (sl && F > 0.02) {
      const at = (gg) => n.map((_, i) => i).filter((i) => this.g[i] === gg);
      for (const [lo, hi] of [[sl[0], sl[1]], [sl[1], sl[2]]]) {
        if (lo == null || hi == null) continue;
        const up = at(hi);
        for (const i of at(lo)) {
          const near = up.map((j) => [j, Math.hypot(n[i][N_X] - n[j][N_X], n[i][N_Y] - n[j][N_Y])]).sort((a, b) => a[1] - b[1]).slice(0, 2);
          for (const [j] of near) this.arrow(pr[i], pr[j], "rgba(190,235,240,.55)", 1.3, null, t, F);
        }
      }
    }

    // the student's tree, and where to go next
    for (const [a, b] of this.tree) this.arrow(pr[a], pr[b], this.solved.has(b) ? "rgba(52,227,212,.9)" : "rgba(255,138,76,.85)", 2, null, t, Math.min(vis[a], vis[b]));
    for (const i of this.solved) for (const [j] of this.out[i]) if (this.next.has(j)) this.arrow(pr[i], pr[j], "rgba(255,209,102,.7)", 1.4, [5, 5], t, Math.min(vis[i], vis[j]));

    // selection: its arrows up (harder) and down (easier)
    if (this.sel != null) {
      for (const [j] of this.out[this.sel]) this.arrow(pr[this.sel], pr[j], "rgba(255,255,255,.95)", 2.2, [6, 4], t, Math.max(0.35, vis[j]));
      for (const [j] of this.inn[this.sel]) this.arrow(pr[j], pr[this.sel], "rgba(255,255,255,.5)", 1.4, null, t, Math.max(0.35, vis[j]));
    }

    // nodes, far to near
    const order = pr.map((p, i) => i).sort((a, b) => pr[b][3] - pr[a][3]);
    for (const i of order) {
      if (vis[i] < 0.02 && i !== this.sel) continue;
      const [x, y, f] = pr[i];
      const st = this.style(i, t);
      let r = Math.max(1.6, f * 0.022) * (1 + 0.9 * F * vis[i]) * st.r, col = st.col, glow = st.glow;
      let alpha = (st.status ? 1 : st.alpha + (1 - st.alpha) * 0.8 * F) * vis[i];
      if (band != null) {                       // a level under the mouse: light its points, dim the rest
        if (this.inBand(i, band)) { alpha = Math.max(alpha, 0.95 * vis[i]); r *= 1.45; glow = glow || col; }
        else alpha *= 0.18;
      }
      if (glow) { ctx.globalAlpha = 0.22 * alpha; ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(x, y, r * 2.6, 0, 6.283); ctx.fill(); }
      ctx.globalAlpha = alpha; ctx.fillStyle = col; ctx.beginPath(); ctx.arc(x, y, r, 0, 6.283); ctx.fill();
      ctx.globalAlpha = 1;
      if (this.mission.has(i) && vis[i] > 0.3) { ctx.strokeStyle = MAP_COL.mission; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, r + 3, 0, 6.283); ctx.stroke(); }
      if (i === this.sel || i === this.hover) {
        ctx.strokeStyle = "#fff"; ctx.lineWidth = i === this.sel ? 2.4 : 1.4;
        ctx.beginPath(); ctx.arc(x, y, r + (i === this.sel ? 5 + Math.sin(t * 4) : 4), 0, 6.283); ctx.stroke();
      }
    }
    this.raf = requestAnimationFrame(this.frame);
  }
}

// ---------------------------------------------------------------- view
const nodeLabel = (nd) => `N${nd[N_LV] + 1} · P${nd[N_NUM] ?? "?"}`;

async function viewMap() {
  const student = S.me.role === "student";
  const topics = S.tax.topics;
  if (!S.mapTopic || !topics.includes(S.mapTopic)) S.mapTopic = topics[0];
  if (S.map3d) { S.map3d.destroy(); S.map3d = null; }
  app().innerHTML = topbar(student ? STUDENT_NAV : TEACHER_NAV) + `<main class="page">
    <div class="page-head"><div><h1>Mapa 3D</h1><div class="muted">Altura = dificultad (nivel y número de pregunta). Problemas parecidos quedan cerca a cualquier altura.</div></div></div>
    <div class="map-topics">${topics.map((t) => `<button class="chip-btn ${t === S.mapTopic ? "on" : ""}" data-t="${esc(t)}"><span class="mono">${esc(tIco(t))}</span>${esc(tName(t))}</button>`).join("")}</div>
    <div class="map-grid">
      <div class="map-stage"><canvas id="map" aria-label="Mapa 3D de problemas por dificultad"></canvas>
        <div class="map-hint" id="hint">Arrastra para girar · rueda o pellizco para acercar · toca un punto para ver su dificultad</div>
        <div class="map-steps hidden" id="steps"><button id="down" title="Más fácil">▼</button><span id="stepLabel"></span><button id="up" title="Más difícil">▲</button><button id="all" title="Ver todo">✕</button></div>
        <div class="map-legend" id="legend"></div></div>
      <aside class="card card-pad map-side" id="side"><div class="spin"></div></aside>
    </div></main>`;
  bindShell();
  $$(".chip-btn").forEach((b) => (b.onclick = () => { S.mapTopic = b.dataset.t; viewMap(); }));
  const data = await api(`/api/map?topic=${encodeURIComponent(S.mapTopic)}`);
  if (!$("#map")) return;
  const legend = student
    ? `<span><i style="background:${MAP_COL.solved}"></i>Acertado</span><span><i style="background:${MAP_COL.failed}"></i>Fallado</span>
       <span><i style="background:${MAP_COL.next}"></i>Siguiente sugerido</span><span><i class="ring"></i>En tu misión</span>`
    : `<span><i style="background:#7fd39a"></i>≥60 % aciertos</span><span><i style="background:#e9b866"></i>30–60 %</span><span><i style="background:#ff8a4c"></i>&lt;30 %</span><span class="muted">tamaño = intentos</span>`;
  $("#legend").innerHTML = legend + `<span class="subs">${data.subtopics.map((s, i) => `<span><i style="background:${MAP_SUB_COLORS[i % MAP_SUB_COLORS.length]}"></i>${esc(sub(s))}</span>`).join("")}</span>`;

  const summary = () => {
    const me = data.me;
    if (!me) {
      const tried = (data.class || []).length;
      return `<h2>${esc(tName(S.mapTopic))}</h2><p class="muted small">${data.nodes.length} problemas · ${tried} intentados por la clase</p>
        <p class="small">Toca un problema para ampliar su dificultad, ver su enunciado y a qué problemas lleva. Toca fuera para volver.</p>`;
    }
    return `<h2>${esc(tName(S.mapTopic))}</h2>
      <div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr));margin:10px 0">
        <div class="card kpi"><span>Acertados</span><b>${me.solved.length}</b></div>
        <div class="card kpi"><span>Fallados</span><b>${me.failed.length}</b></div>
        <div class="card kpi"><span>Tu nivel</span><b>${me.theta == null ? "—" : Math.floor(me.theta) + 1}</b></div></div>
      <p class="small muted">Turquesa: tu camino. Amarillo: problemas parecidos y un poco más difíciles (del mismo nivel) a los que puedes ir.</p>
      ${S.map3d && S.map3d.next.size ? `<button class="btn sm block" id="gonext">Ver un siguiente sugerido</button>` : ""}`;
  };
  const side = $("#side");
  const showSummary = () => { side.innerHTML = summary(); const g = $("#gonext"); if (g) g.onclick = () => S.map3d.select([...S.map3d.next][0]); };
  const showFocus = (gg) => {
    const m = S.map3d, at = data.nodes.map((nd, i) => i).filter((i) => m.g[i] === gg);
    const lv = m.levelOf(gg);
    side.innerHTML = `<div class="row"><button class="linkbtn small" id="back">← Todo el mapa</button></div>
      <h2 style="margin-top:6px">Nivel ${lv + 1} · pregunta ${gg - m.offsets[lv]}</h2><p class="muted small">Dificultad general ${gg} de ${m.total} · ${at.length} problema${at.length === 1 ? "" : "s"}</p>
      <div class="map-links">${at.map((i) => `<button class="map-link" data-i="${i}"><span>${esc(sub(data.subtopics[data.nodes[i][N_SUB]]))}</span><b>${m.solved.has(i) ? "✓" : m.failed.has(i) ? "✗" : m.next.has(i) ? "★" : ""}</b><em>${esc(data.nodes[i][N_ID].split("_")[1] || "")}</em></button>`).join("")}</div>`;
    $("#back").onclick = () => m.setFocus(null);
    $$(".map-link", side).forEach((b) => (b.onclick = () => m.select(Number(b.dataset.i))));
  };
  const showNode = async (i) => {
    const m = S.map3d;
    if (i == null) return m.focus != null && m.focusTarget ? showFocus(m.focus) : showSummary();
    const nd = data.nodes[i];
    side.innerHTML = '<div class="spin"></div>';
    const p = await api(student ? `/api/student/problem/${encodeURIComponent(nd[N_ID])}` : `/api/problems/${encodeURIComponent(nd[N_ID])}`);
    if (m.sel !== i) return;
    const status = student ? (m.solved.has(i) ? '<span class="chip ahead">Acertado</span>' : m.failed.has(i) ? '<span class="chip behind">Fallado</span>'
      : m.next.has(i) ? '<span class="chip gold">Siguiente sugerido</span>' : "") + (m.mission.has(i) ? '<span class="chip teal">En tu misión</span>' : "") : "";
    const cs = m.cls.get(i);
    const list = (arr, title) => arr.length ? `<h3 style="margin:14px 0 6px">${title}</h3><div class="map-links">${arr.sort((a, b) => b[1] - a[1]).map(([j, s]) => {
      const st = m.solved.has(j) ? "✓" : m.failed.has(j) ? "✗" : m.next.has(j) ? "★" : "";
      return `<button class="map-link" data-i="${j}"><span>${nodeLabel(data.nodes[j])} · ${esc(sub(data.subtopics[data.nodes[j][N_SUB]]))}</span><b>${st}</b><em>${Math.round(s * 100)}%</em></button>`; }).join("")}</div>` : "";
    side.innerHTML = `<div class="row"><button class="linkbtn small" id="back">← Todo el mapa</button></div>
      <div class="row" style="margin:6px 0 10px">${status}<span class="chip">${lvl(p.level)} · pregunta ${p.num ?? "?"}</span><span class="chip teal">${esc(sub(p.subtopic))}</span></div>
      <div class="map-problem">
        ${statement(p)}
        ${tiles(p, { small: true, result: !student ? { answer: p.answer, given: null } : null })}
      </div>
      ${!student && cs ? `<div class="small muted" style="margin-top:8px">${cs.ok}/${cs.n} aciertos en clase</div>` : ""}
      ${list(m.out[i], "Después: parecidos y un poco más difíciles")}${list(m.inn[i], "Antes: parecidos y un poco más fáciles")}`;
    $("#back").onclick = () => m.setFocus(null);
    $$(".map-link", side).forEach((b) => (b.onclick = () => m.select(Number(b.dataset.i))));
  };
  const steps = $("#steps"), hint = $("#hint");
  const onFocus = (gg) => {
    steps.classList.toggle("hidden", gg == null); hint.classList.toggle("hidden", gg != null);
    if (gg == null) { if (S.map3d && S.map3d.sel == null) showSummary(); return; }
    const m = S.map3d, lv = m.levelOf(gg), k = m.gs.indexOf(gg);
    $("#stepLabel").textContent = `N${lv + 1} · P${gg - m.offsets[lv]}`;
    $("#down").disabled = k <= 0; $("#up").disabled = k >= m.gs.length - 1;
    if (m.sel == null) showFocus(gg);
  };
  S.map3d = new Map3D($("#map"), data, { onSelect: showNode, onFocus });
  $("#down").onclick = () => S.map3d.step(-1);
  $("#up").onclick = () => S.map3d.step(+1);
  $("#all").onclick = () => S.map3d.setFocus(null);
  showSummary();
}
