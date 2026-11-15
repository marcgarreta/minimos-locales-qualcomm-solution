/* Kangaroo Path — single-page app, no dependencies (the board is offline). */
"use strict";

// ---------------------------------------------------------------- constants
const TOPICS = {
  "Algebra": { es: "Álgebra", short: "Álgebra", ico: "x²" },
  "Arithmetic": { es: "Aritmética", short: "Aritmética", ico: "+−" },
  "Combinatorics": { es: "Combinatoria", short: "Combinatoria", ico: "n!" },
  "Logic": { es: "Lógica", short: "Lógica", ico: "∴" },
  "Number theory": { es: "Teoría de números", short: "Números", ico: "#" },
  "Plane geometry": { es: "Geometría plana", short: "G. plana", ico: "△" },
  "Probability and data": { es: "Probabilidad y datos", short: "Probabilidad", ico: "%" },
  "Solid and spatial geometry": { es: "Geometría espacial", short: "G. espacial", ico: "◇" },
  "Word problems": { es: "Problemas de texto", short: "Problemas", ico: "Aa" },
  "Other": { es: "Otros", short: "Otros", ico: "?" },
};
const SUB = {
  "Equations and unknowns": "Ecuaciones e incógnitas", "Functions and coordinates": "Funciones y coordenadas",
  "Sequences and patterns": "Sucesiones y patrones", "Digits and place value": "Cifras y valor posicional",
  "Fractions, percentages and ratios": "Fracciones, porcentajes y razones", "Operations and calculation": "Operaciones y cálculo",
  "Counting and arrangements": "Conteo y ordenaciones", "Extremal and pigeonhole": "Extremos y palomar",
  "Grids, paths, networks and tilings": "Cuadrículas, caminos y teselas", "Games and strategy": "Juegos y estrategia",
  "Tournaments, rankings and ordering": "Torneos y clasificaciones", "Truth-tellers and liars": "Veraces y mentirosos",
  "Divisibility, multiples and divisors": "Divisibilidad, múltiplos y divisores", "Primes, squares, parity": "Primos, cuadrados y paridad",
  "Unclear": "Sin clasificar", "Angles": "Ángulos", "Area and perimeter": "Área y perímetro", "Circles": "Circunferencias",
  "Triangles and polygons": "Triángulos y polígonos", "Averages and statistics": "Medias y estadística",
  "Graphs, charts and tables": "Gráficos y tablas", "Probability": "Probabilidad",
  "Cubes, dice and polyhedra": "Cubos, dados y poliedros", "Folding, cutting and nets": "Plegado, cortes y desarrollos",
  "Symmetry, rotations and visual puzzles": "Simetría, giros y puzles visuales",
  "Ages, weights and everyday quantities": "Edades, pesos y cantidades", "Calendar and clocks": "Calendario y relojes",
  "Money and prices": "Dinero y precios", "Speed, distance and time": "Velocidad, distancia y tiempo",
};
const ROLE = { refuerzo: "Refuerzo", practica: "Práctica", reto: "Reto", pendiente: "Pendiente" };
const LETTERS = ["A", "B", "C", "D", "E"];
const ICON = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  lock: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 10V8a5 5 0 0110 0v2h1a1 1 0 011 1v9a1 1 0 01-1 1H6a1 1 0 01-1-1v-9a1 1 0 011-1h1zm2 0h6V8a3 3 0 00-6 0v2z"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.8l2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.2l-5.7 3.1 1.2-6.4L2.8 9.5l6.4-.8z"/></svg>',
  bolt: '<svg viewBox="0 0 24 24"><path fill="#f1b82d" d="M13.5 2L4 13.5h6.5L9.5 22 20 9.5h-6.6z"/></svg>',
  flame: '<svg viewBox="0 0 24 24"><path fill="#ff9a3c" d="M12 2s5.5 4.8 5.5 10.6A5.5 5.5 0 0112 18a5.5 5.5 0 01-5.5-5.4c0-2.4 1.2-4 2.4-5.1.1 1.7.8 3 2 3.6C10.7 7.6 12 2 12 2z"/><path fill="#ffd25f" d="M12 22a4 4 0 01-4-4c0-2.3 2-3.6 2.6-5.6.9 1.4 1.4 1.9 2.4 2.3.4-1 .7-1.6.8-2.7C15 13.6 16 15.6 16 18a4 4 0 01-4 4z"/></svg>',
  zoom: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21M10.5 7.5v6M7.5 10.5h6"/></svg>',
  close: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
};
const BRAND = '<svg class="brand-mark" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#fff"/><path d="M7 22l6-6 4 4 8-9" stroke="#008184" stroke-width="3.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="25" cy="11" r="2.6" fill="#e47128"/></svg>';
const BRAND_DARK = BRAND.replace('fill="#fff"', 'fill="#008184"').replace('stroke="#008184"', 'stroke="#fff"');

// ---------------------------------------------------------------- state & utils
const S = { me: null, tax: null, home: null, answers: {}, step: 0, problems: { items: [], offset: 0 }, studentsCache: null };
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = () => $("#app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tName = (t) => (TOPICS[t] || { es: t }).es;
const tShort = (t) => (TOPICS[t] || { short: t }).short;
const tIco = (t) => (TOPICS[t] || { ico: "?" }).ico;
const sub = (s) => SUB[s] || s || "";
const lvl = (l) => `Nivel ${Number(l) + 1}`;
const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)} %`);
const num = (x, d = 1) => (x == null ? "—" : Number(x).toLocaleString("es-ES", { maximumFractionDigits: d, minimumFractionDigits: d }));
const fmtDate = (iso) => (iso ? new Date(iso.length <= 10 ? iso + "T12:00" : iso).toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" }) : "—");
const initials = (n) => n.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || (opts.body ? "POST" : "GET"),
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && !path.endsWith("/login") && path !== "/api/me") {
    // only leave when the server confirms there is no session (a passing error must not log anyone out)
    const me = await fetch("/api/me", { credentials: "same-origin" }).then((r) => r.json()).catch(() => ({ role: "?" }));
    if (!me.role) { S.me = null; go("#/login"); }
  }
  if (!res.ok) throw new Error(data.error || `Error ${res.status}`);
  return data;
}
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 2600);
}
function go(hash) { if (location.hash === hash) render(); else location.hash = hash; }
function loading() { app().innerHTML = '<div class="spin"></div>'; }
function modal(html, onClose) {
  const o = document.createElement("div");
  o.className = "overlay";
  o.innerHTML = `<div class="card modal pop" role="dialog" aria-modal="true"><button class="linkbtn x" aria-label="Cerrar">${ICON.close}</button>${html}</div>`;
  const close = () => { o.remove(); document.removeEventListener("keydown", onKey); onClose && onClose(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  o.addEventListener("click", (e) => { if (e.target === o || e.target.closest(".x")) close(); });
  document.addEventListener("keydown", onKey);
  document.body.appendChild(o);
  return { el: o, close };
}

// ---------------------------------------------------------------- charts
/** Radar ("clock") chart. series: [{values:[0..max], color, fill, dash}] */
function radar(topics, series, size = 340, max = 8) {
  const n = topics.length, c = size / 2, R = size / 2 - 34, padX = 70;
  const pt = (i, v) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
    return [c + Math.cos(a) * R * (v / max), c + Math.sin(a) * R * (v / max)];
  };
  let g = "";
  for (const ring of [2, 4, 6, 8]) {
    g += `<polygon class="ring" points="${topics.map((_, i) => pt(i, ring).join(",")).join(" ")}"/>`;
  }
  topics.forEach((t, i) => {
    const [x, y] = pt(i, max);
    g += `<line class="axis" x1="${c}" y1="${c}" x2="${x}" y2="${y}"/>`;
    const [lx, ly] = pt(i, max + 0.9);
    const anchor = Math.abs(lx - c) < 8 ? "middle" : lx > c ? "start" : "end";
    g += `<text x="${lx}" y="${ly + 4}" text-anchor="${anchor}">${esc(tShort(t))}</text>`;
  });
  for (const ring of [2, 4, 6, 8]) {
    const [x, y] = pt(0, ring);
    g += `<text x="${x + 4}" y="${y + 3}" style="fill:#8c9ba0;font-size:9px">${ring}</text>`;
  }
  for (const s of series) {
    const pts = s.values.map((v, i) => pt(i, Math.max(0.15, v)).join(",")).join(" ");
    g += `<polygon points="${pts}" fill="${s.fill || "none"}" stroke="${s.color}" stroke-width="2.5" ${s.dash ? 'stroke-dasharray="6 5"' : ""} stroke-linejoin="round"/>`;
    if (!s.dash) s.values.forEach((v, i) => { const [x, y] = pt(i, Math.max(0.15, v)); g += `<circle cx="${x}" cy="${y}" r="3.5" fill="${s.color}"/>`; });
  }
  return `<svg class="radar" viewBox="${-padX} -6 ${size + 2 * padX} ${size + 12}" width="100%" style="max-width:${size + 2 * padX}px;display:block;margin:0 auto" role="img" aria-label="Gráfico radar de nivel por tema">${g}</svg>`;
}
function ring(value, total, size = 150) {
  const r = size / 2 - 10, C = 2 * Math.PI * r, f = total ? value / total : 0;
  const col = f >= 0.7 ? "var(--green)" : f >= 0.4 ? "var(--teal)" : "var(--orange)";
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--line)" stroke-width="12"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${col}" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${C * f} ${C}" transform="rotate(-90 ${size / 2} ${size / 2})"/></svg>`;
}
function heatColor(theta) {
  const t = Math.min(1, theta / 8);
  return `background:rgba(0,129,132,${0.1 + t * 0.8});color:${t > 0.45 ? "#fff" : "var(--ink)"}`;
}

// ---------------------------------------------------------------- shell
function topbar(links) {
  const me = S.me, cur = location.hash;
  const pills = me.role === "student" && S.home
    ? `<span class="pill" title="Experiencia">${ICON.bolt}${S.home.xp} XP</span><span class="pill hide-sm" title="Semanas seguidas entregando">${ICON.flame}${S.home.streak}</span>`
    : "";
  return `<header class="topbar"><div class="topbar-in">
    <a class="brand" href="${me.role === "student" ? "#/s" : "#/t"}">${BRAND}<span class="hide-sm">${esc(S.tax?.school || "Kangaroo Path")}</span></a>
    <nav class="nav">${links.map(([h, l]) => `<a href="${h}" class="${cur === h ? "on" : ""}">${l}</a>`).join("")}</nav>
    <span class="spacer"></span>${pills}
    <span class="user"><span class="avatar">${esc(initials(me.name))}</span><span class="hide-sm">${esc(me.name)}</span></span>
    <button class="linkbtn" id="logout">Salir</button>
  </div></header>`;
}
function bindShell() {
  const b = $("#logout");
  if (b) b.onclick = async () => { await api("/api/logout", { method: "POST", body: {} }); S.me = null; S.home = null; go("#/login"); };
}
const STUDENT_NAV = [["#/s", "Ruta"], ["#/s/mision", "Misión"], ["#/s/mapa", "Mapa 3D"], ["#/s/progreso", "Progreso"]];
const TEACHER_NAV = [["#/t", "Alumnos"], ["#/t/problemas", "Problemas"], ["#/t/mapa", "Mapa 3D"], ["#/t/estadisticas", "Estadísticas"]];

// ---------------------------------------------------------------- login
function viewLogin() {
  let mode = "student";
  app().innerHTML = `<div class="login-wrap"><div class="card login pop">
    <div class="brand">${BRAND_DARK}<span>${esc(S.tax?.school || "Kangaroo Path")}</span></div>
    <p class="lead">Practica matemáticas, nivel a nivel.</p>
    <div class="seg"><button data-m="student" class="on">Soy alumno</button><button data-m="teacher">Soy profesor</button></div>
    <form id="lf" class="stack" autocomplete="off">
      <div id="fs"><label class="f">Tu código de alumno<input id="code" class="code-input" maxlength="7" placeholder="ABC-123" autofocus></label></div>
      <div id="ft" class="stack hidden">
        <label class="f">Usuario<input id="user" autocomplete="username"></label>
        <label class="f">Contraseña<input id="pass" type="password" autocomplete="current-password"></label>
      </div>
      <div class="err" id="lerr"></div>
      <button class="btn block">Entrar</button>
    </form></div></div>`;
  $$(".seg button").forEach((b) => (b.onclick = () => {
    mode = b.dataset.m;
    $$(".seg button").forEach((x) => x.classList.toggle("on", x === b));
    $("#fs").classList.toggle("hidden", mode !== "student");
    $("#ft").classList.toggle("hidden", mode !== "teacher");
    (mode === "student" ? $("#code") : $("#user")).focus();
  }));
  $("#code").oninput = (e) => {
    let v = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6);
    e.target.value = v.length > 3 ? v.slice(0, 3) + "-" + v.slice(3) : v;
  };
  $("#lf").onsubmit = async (e) => {
    e.preventDefault();
    const body = mode === "student" ? { role: "student", code: $("#code").value } : { role: "teacher", user: $("#user").value.trim(), password: $("#pass").value };
    body.client_time = Date.now();   // fixes the board's clock after a reboot without internet
    try {
      S.me = await api("/api/login", { body });
      go(S.me.role === "student" ? "#/s" : "#/t");
    } catch (err) { $("#lerr").textContent = err.message; }
  };
}

// ---------------------------------------------------------------- student
async function loadHome() { S.home = await api("/api/student/home"); return S.home; }

function standing(t) {
  const d = t.theta - t.class_avg;
  if (Math.abs(d) < 0.15) return '<span class="chip">En la media</span>';
  return d > 0 ? `<span class="chip ahead">▲ Por delante</span>` : `<span class="chip behind">▼ Por detrás</span>`;
}

function unitPath(t, levels = 8) {
  const nodes = [];
  for (let i = 0; i < levels; i++) {
    const wave = Math.round(Math.sin(i * 1.1) * 7);
    let cls = "node", inner = "";
    if (i < t.level) { cls += " done" + (i === levels - 1 ? " gold" : ""); inner = ICON.check; }
    else if (i === t.level) { cls += " cur"; inner = `${i + 1}<span class="bubble">TÚ</span>`; }
    else inner = ICON.lock;
    nodes.push(`<div class="node-wrap" style="transform:translateY(${wave}px)"><div class="${cls}" style="--p:${Math.round(t.progress * 100)}" title="${lvl(i)}">${inner}</div><div class="node-label">${i + 1}</div></div>`);
  }
  const fill = Math.max(0, Math.min(1, (t.theta / levels - 1 / (2 * levels)) / (1 - 1 / levels)));
  const avgLeft = (t.class_avg / levels) * 100;
  return `<div class="path">
      <div class="path-track"><div class="path-fill" style="width:${fill * 100}%"></div></div>
      <div class="path-nodes">${nodes.join("")}</div>
      <div class="avg-mark" style="left:${avgLeft}%" title="Media de tu aula: ${num(t.class_avg + 0.5 > 0 ? t.class_avg : 0)}">Media aula</div>
    </div>`;
}

// ---------------------------------------------------------------- problem pieces (statement, zoom, option tiles)
const lvlQ = (p) => (p.num ? `${lvl(p.level)} · pregunta ${p.num}` : lvl(p.level));

function zoomImage(src, alt = "") {
  const o = document.createElement("div");
  o.className = "zoom";
  o.innerHTML = `<button class="zoom-x" aria-label="Cerrar">${ICON.close}</button>
    <div class="zoom-scroll"><img src="${src}" alt="${esc(alt)}"></div>
    <div class="zoom-hint">Desliza o pellizca para ver los detalles · toca fuera para cerrar</div>`;
  const close = () => { o.remove(); document.removeEventListener("keydown", key); };
  const key = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  o.addEventListener("click", (e) => { if (!e.target.closest("img")) close(); });
  document.addEventListener("keydown", key);
  document.body.appendChild(o);
}
document.addEventListener("click", (e) => {
  const z = e.target.closest("[data-zoom]");
  if (z) { e.preventDefault(); zoomImage(z.dataset.zoom, z.dataset.alt || ""); }
});

/** The statement, once, as text; below it only the figure cut by the team's OCR (tap: the original
    page). Problems without a figure show no picture; uncertain cuts fall back to the page itself. */
function statement(p) {
  const fig = p.figure;
  const text = p.text ? `<p class="stmt-text">${esc(p.text)}</p>` : "";
  if (!fig) return text;
  return `${text}<button type="button" class="stmt-img${p.figure_fallback ? " page" : " fig"}" data-zoom="${p.image || fig}" data-alt="${esc(p.text || "")}" aria-label="Ampliar la figura">
      <img src="${fig}" alt="Figura del problema" loading="lazy"><span class="zoom-badge">${ICON.zoom}</span></button>`;
}

/** The five options as square tiles: the printed option (text or drawing), else the OCR text, else the letter.
    result = {given, answer} colours them after checking. */
function tiles(p, { chosen = null, result = null, interactive = false, small = false } = {}) {
  const tag = interactive ? "button" : "div";
  return `<div class="tiles${small ? " sm" : ""}"${interactive ? ' role="radiogroup" aria-label="Opciones"' : ""}>${LETTERS.map((L) => {
    const img = p.option_images && p.option_images[L], txt = p.options && p.options[L];
    let cls = "tile", mark = "";
    if (result) {
      if (L === result.answer) { cls += " ok"; mark = ICON.check; }
      else if (L === result.given) { cls += " ko"; mark = ICON.x; }
      else cls += " dim";
    } else if (chosen === L) cls += " sel";
    const body = img ? `<img src="${img}" alt="${esc(txt || "Opción " + L)}" loading="lazy">`
      : txt ? `<span class="tile-txt${txt.length > 7 ? " long" : ""}">${esc(txt)}</span>` : `<span class="tile-big">${L}</span>`;
    const attrs = interactive ? ` type="button" data-l="${L}" role="radio" aria-checked="${chosen === L}" aria-label="Opción ${L}${txt ? ": " + esc(txt) : ""}"${result ? " disabled" : ""}` : "";
    return `<${tag} class="${cls}"${attrs}><span class="tile-key">${L}</span>${body}${mark ? `<span class="tile-mark">${mark}</span>` : ""}</${tag}>`;
  }).join("")}</div>`;
}

// ---------------------------------------------------------------- student: mission card, mission, lesson, result
function missionCard(h) {
  const a = h.current;
  if (!a) return `<div class="card card-pad"><h2>Sin misión</h2><p class="muted">Tu profesor te asignará una pronto.</p></div>`;
  const answered = a.items.filter((p) => p.given).length;
  return `<div class="card card-pad mission-hero">
    <div class="row" style="justify-content:space-between"><h2>${esc(a.title)}</h2><span class="chip" style="background:rgba(255,255,255,.18);color:#fff">${a.items.length} problemas</span></div>
    <div class="muted small">Entrega: <b style="color:#fff">${fmtDate(a.due)}</b>${answered ? ` · ${answered} de ${a.items.length} respondidos` : ""}</div>
    <div class="mini-list">${a.items.slice(0, 5).map((p, i) => `<div class="mini-item"><span class="dot">${p.given ? (p.correct ? "✓" : "✗") : i + 1}</span><span style="flex:1">${esc(tName(p.topic))} · ${lvl(p.level)}</span><span class="role ${p.role}">${ROLE[p.role] || ""}</span></div>`).join("")}
    ${a.items.length > 5 ? `<div class="small muted">+ ${a.items.length - 5} más</div>` : ""}</div>
    <div class="stack" style="gap:10px"><a class="btn orange block" href="#/s/entregar">${answered ? "Seguir respondiendo" : "Responder misión"}</a><a class="btn ghost block" href="#/s/mision">Ver problemas</a></div>
  </div>`;
}

async function viewMission() {
  loading();
  const h = await loadHome();
  const a = h.current;
  app().innerHTML = topbar(STUDENT_NAV) + `<main class="page">
    ${!a ? '<div class="card empty">No tienes ninguna misión abierta.</div>' : `
    <div class="page-head"><div><h1>${esc(a.title)}</h1><div class="muted">Resuélvelos en papel y vuelve con tus respuestas · Entrega ${fmtDate(a.due)}</div></div>
      <span class="spacer"></span><a class="btn orange" href="#/s/entregar">Responder</a></div>
    <div class="problem-list">${a.items.map((p, i) => `<article class="card problem-card">
        <div class="num">${p.given ? (p.correct ? ICON.check : ICON.x) : i + 1}</div>
        <div class="stack" style="gap:12px">
          <div class="row"><span class="role ${p.role}">${ROLE[p.role] || ""}</span><span class="chip teal">${esc(tName(p.topic))}</span><span class="chip">${lvlQ(p)}</span>
            ${p.because ? `<span class="small muted">Para preparar un problema que fallaste</span>` : ""}${p.role === "pendiente" ? `<span class="small muted">Lo saltaste la última vez</span>` : ""}</div>
          ${statement(p)}
          ${tiles(p, { small: true, result: p.given ? { given: p.given, answer: p.answer } : null })}
        </div></article>`).join("")}</div>`}
  </main>`;
  bindShell();
}

async function viewAnswer() {
  loading();
  const h = await loadHome();
  const a = h.current;
  if (!a) return go("#/s");
  const st = S.lesson && S.lesson.aid === a.id ? S.lesson
    : (S.lesson = { aid: a.id, idx: null, chosen: null, skipped: new Set(), results: {} });
  st.explained = st.explained || new Set();
  for (const p of a.items) if (p.given && !st.results[p.id]) st.results[p.id] = { given: p.given, answer: p.answer, correct: p.correct };
  const pending = (i) => !st.results[a.items[i].id] && !st.skipped.has(a.items[i].id);
  const nextIdx = (from) => {
    for (let k = 1; k <= a.items.length; k++) { const i = (from + k) % a.items.length; if (pending(i)) return i; }
    return null;
  };
  if (st.idx == null || !a.items[st.idx] || (!pending(st.idx) && !st.results[a.items[st.idx].id])) st.idx = nextIdx(-1);
  const xpFor = (p, ok) => 2 + (ok ? 10 : 0) + (ok && p.role === "reto" ? 5 : 0);

  const finish = () => {
    st.idx = null;
    const answered = Object.keys(st.results).length, good = Object.values(st.results).filter((r) => r.correct).length;
    const skipped = a.items.filter((p) => st.skipped.has(p.id));
    app().innerHTML = `<div class="lesson"><div class="lesson-top"><a class="linkbtn" href="#/s" aria-label="Salir">${ICON.close}</a>
        <div class="bar"><i style="width:100%"></i></div><b class="small">${a.items.length}/${a.items.length}</b></div>
      <div class="lesson-body lesson-end pop">
        <div class="score-ring">${ring(good, Math.max(answered, 1))}<b>${good}/${answered}</b></div>
        <h1>${answered ? (skipped.length ? "Casi lista" : "¡Misión completada!") : "No has respondido ninguno"}</h1>
        <p class="muted">${skipped.length ? `Has saltado ${skipped.length} problema${skipped.length > 1 ? "s" : ""}. Si entregas así, volverá${skipped.length > 1 ? "n" : ""} en tu próxima misión.` : "Entrega para ver cómo cambia tu nivel y tu próxima misión."}</p>
        ${skipped.length ? `<div class="skipped-list">${skipped.map((p) => `<span class="chip">${esc(tName(p.topic))} · ${lvl(p.level)}</span>`).join("")}</div>` : ""}
      </div>
      <div class="lesson-foot"><div class="lesson-foot-in">
        ${skipped.length ? `<button class="btn ghost" id="back">Volver a los saltados</button>` : "<span></span>"}
        <button class="btn green" id="send" ${answered ? "" : "disabled"}>Entregar misión</button>
      </div></div></div>`;
    const back = $("#back");
    if (back) back.onclick = () => { st.skipped.clear(); st.idx = nextIdx(-1); draw(); };
    $("#send").onclick = async (e) => {
      e.target.disabled = true;
      try {
        const r = await api("/api/student/submit", { body: { assignment_id: a.id, answers: {} } });
        S.lesson = null; S.home = null;
        go(`#/s/resultado/${r.id}`);
      } catch (err) { toast(err.message); e.target.disabled = false; }
    };
  };

  const draw = () => {
    if (st.idx == null) return finish();
    const p = a.items[st.idx], res = st.results[p.id];
    const done = Object.keys(st.results).length + st.skipped.size;
    app().innerHTML = `<div class="lesson">
      <div class="lesson-top"><a class="linkbtn" href="#/s" aria-label="Salir">${ICON.close}</a>
        <div class="bar" role="progressbar" aria-valuenow="${done}" aria-valuemin="0" aria-valuemax="${a.items.length}"><i style="width:${(done / a.items.length) * 100}%"></i></div>
        <b class="small">${st.idx + 1}/${a.items.length}</b></div>
      <div class="lesson-body">
        <div class="row"><span class="role ${p.role}">${ROLE[p.role] || ""}</span><span class="chip teal">${esc(tName(p.topic))}</span><span class="chip">${lvlQ(p)}</span></div>
        <h1>¿Qué respuesta te salió?</h1>
        ${statement(p)}
        ${tiles(p, { interactive: true, chosen: st.chosen, result: res })}
      </div>
      <div class="lesson-foot ${res ? (res.correct ? "is-ok" : "is-ko") : ""}"><div class="lesson-foot-in">
        ${res ? `<div class="verdict"><span class="verdict-ico">${res.correct ? ICON.check : ICON.x}</span>
              <div><b>${res.correct ? "¡Correcto!" : "No es correcta"}</b>
              <span>${res.correct ? `+${xpFor(p, true)} XP` : `La respuesta era la ${res.answer}${p.options && p.options[res.answer] ? ` · ${esc(p.options[res.answer])}` : ""}`}</span>
              ${res.correct ? "" : st.explained.has(p.id)
                ? '<em class="expl-sent">✓ Explicación enviada: la revisamos en segundo plano</em>'
                : '<button class="linkbtn expl-link" id="explain">✎ Explicar cómo lo hice <small>(opcional)</small></button>'}</div></div>
              <button class="btn ${res.correct ? "green" : "red"}" id="go">Continuar</button>`
          : `<button class="btn ghost" id="skip">Saltar</button>
             <button class="btn" id="check" ${st.chosen ? "" : "disabled"}>Comprobar</button>`}
      </div></div></div>`;
    $$(".tile[data-l]").forEach((b) => (b.onclick = () => { if (!res) { st.chosen = b.dataset.l; draw(); } }));
    const check = $("#check"), skip = $("#skip"), go_ = $("#go");
    if (check) check.onclick = async () => {
      check.disabled = true;
      try {
        const r = await api("/api/student/check", { body: { assignment_id: a.id, problem_id: p.id, answer: st.chosen } });
        st.results[p.id] = r; st.chosen = null; draw();
        if (!r.correct) { const t = $(".tile.ko"); if (t) t.classList.add("shake"); }
      } catch (e) { toast(e.message); check.disabled = false; }
    };
    if (skip) skip.onclick = () => { st.skipped.add(p.id); st.chosen = null; st.idx = nextIdx(st.idx); draw(); };
    if (go_) { go_.onclick = () => { st.idx = nextIdx(st.idx); draw(); }; go_.focus(); }
    const explain = $("#explain");
    if (explain) explain.onclick = () => explainModal(a.id, p, () => { st.explained.add(p.id); draw(); });
  };

  // keyboard: A-E or 1-5 choose, Enter checks / continues, S skips
  S.lessonKey = (e) => {
    if (e.target.closest && e.target.closest("input,textarea") || document.querySelector(".zoom")) return;
    const k = e.key.toUpperCase();
    const L = LETTERS.includes(k) ? k : "12345".includes(k) && k.length === 1 ? LETTERS[Number(k) - 1] : null;
    if (L && $(`.tile[data-l="${L}"]:not([disabled])`)) { $(`.tile[data-l="${L}"]`).click(); return; }
    if (e.key === "Enter") { const b = $("#go") || $("#check:not([disabled])") || $("#send:not([disabled])"); if (b) { e.preventDefault(); b.click(); } }
    if (k === "S" && $("#skip")) $("#skip").click();
  };
  draw();
}

// ---- optional "how did you solve it?" on a wrong answer. The board's LLM checks the NUMBERS in the background
// (calculation slips only: a surprising digit = probably a wrong result; it can't judge the reasoning).
const explUrl = (aid) => `/api/student/assignments/${aid}/explanations`;
const EXPL_HELP = "Revisaremos los números que escribas (no el razonamiento). Tarda un poco: se hace en segundo plano.";
const EXPL_PH = "Por ejemplo: 3 cajas de 4 son 3 x 4 = 12, menos 2 son 10…";

function explainModal(aid, p, onSent) {
  const m = modal(`<h2>¿Cómo lo resolviste?</h2>
    <p class="small muted" style="margin-top:-4px">Escribe tus pasos y tus cuentas. ${EXPL_HELP}</p>
    <textarea id="expl-ta" maxlength="2000" placeholder="${EXPL_PH}"></textarea>
    <div class="row" style="margin-top:10px;justify-content:flex-end"><button class="btn ghost sm" id="expl-no">Ahora no</button><button class="btn sm" id="expl-go">Revisar mis cálculos</button></div>`);
  const ta = $("#expl-ta", m.el); ta.focus();
  $("#expl-no", m.el).onclick = () => m.close();
  $("#expl-go", m.el).onclick = async (e) => {
    if (!ta.value.trim()) return toast("Escribe cómo lo resolviste");
    e.target.disabled = true;
    try {
      await api(explUrl(aid), { body: { problem_id: p.id, text: ta.value.trim() } });
      m.close(); toast("Enviada. Verás la revisión en la corrección de la misión."); onSent();
    } catch (err) { toast(err.message); e.target.disabled = false; }
  };
}

function markNumbers(text, numbers) {
  let out = "", at = 0;
  for (const n of numbers) {
    out += esc(text.slice(at, n.start));
    out += `<span class="${n.flag ? "num-bad" : "num-ok"}" title="${n.flag ? "Revisa este cálculo" : "Parece correcto"}">${esc(text.slice(n.start, n.end))}</span>`;
    at = n.end;
  }
  return out + esc(text.slice(at));
}

function explBlock(p, ex) {
  const pid = esc(p.id);
  if (!ex) return `<div class="expl" data-pid="${pid}">
      <button class="linkbtn small expl-open">✎ Explicar cómo lo hice <span class="muted">(opcional)</span></button></div>`;
  const head = '<div class="small muted" style="margin-bottom:6px">Tu explicación</div>';
  if (ex.status === "pending") return `<div class="expl" data-pid="${pid}">${head}<div class="expl-text">${esc(ex.text)}</div>
      <div class="row small muted expl-wait"><span class="spin sm"></span>Revisando tus cálculos en segundo plano… puedes seguir navegando.</div></div>`;
  if (ex.status === "done") {
    const res = ex.result, bad = res.flagged;
    return `<div class="expl" data-pid="${pid}">${head}<div class="expl-text">${markNumbers(ex.text, res.numbers)}</div>
      <div class="expl-msg ${bad ? "bad" : "ok"}">${bad
        ? `Revisa ${bad === 1 ? "el número marcado" : `los ${bad} números marcados`} en rojo: puede que haya un error de cálculo.`
        : res.numbers.length ? "No vemos errores en tus cuentas. Si fallaste, revisa el razonamiento o el planteamiento."
          : "No hay números que revisar. Solo comprobamos cálculos, no el razonamiento."}</div>
      <button class="linkbtn small expl-open">Editar explicación</button></div>`;
  }
  const msg = ex.status === "off" ? "La revisión automática no está disponible en esta placa." : esc((ex.result || {}).error || "No se pudo analizar.");
  return `<div class="expl" data-pid="${pid}">${head}<div class="expl-text">${esc(ex.text)}</div>
    <div class="expl-msg">${msg}</div>${ex.status === "error" ? '<button class="linkbtn small expl-retry">Reintentar</button>' : ""}</div>`;
}

function bindExplanations(aid, items, ex) {
  const hash = location.hash;
  const find = (pid) => $$(".expl").find((el) => el.dataset.pid === pid);
  const redraw = (pid) => {
    const el = find(pid);
    if (el) el.outerHTML = explBlock(items.find((p) => p.id === pid), ex[pid]);
    bindOne(pid);
  };
  const send = async (pid, text, btn) => {
    if (btn) btn.disabled = true;
    try { Object.assign(ex, await api(explUrl(aid), { body: { problem_id: pid, text } })); redraw(pid); poll(); }
    catch (e) { toast(e.message); if (btn) btn.disabled = false; }
  };
  const bindOne = (pid) => {
    const el = find(pid);
    if (!el) return;
    const open = $(".expl-open", el), retry = $(".expl-retry", el);
    if (retry) retry.onclick = () => send(pid, ex[pid].text, retry);
    if (open) open.onclick = () => {
      el.innerHTML = `<label class="f small">¿Cómo lo resolviste? Escribe tus pasos y tus cuentas.
          <textarea maxlength="2000" placeholder="${EXPL_PH}">${esc((ex[pid] || {}).text || "")}</textarea></label>
        <div class="small muted">${EXPL_HELP}</div>
        <div class="row" style="margin-top:8px"><button class="btn sm expl-send">Revisar mis cálculos</button><button class="btn sm ghost expl-cancel">Cancelar</button></div>`;
      const ta = $("textarea", el); ta.focus();
      $(".expl-cancel", el).onclick = () => redraw(pid);
      $(".expl-send", el).onclick = (e) => { if (ta.value.trim()) send(pid, ta.value.trim(), e.target); else toast("Escribe cómo lo resolviste"); };
    };
  };
  let timer = null;
  const poll = () => {
    clearTimeout(timer);
    if (!Object.values(ex).some((e) => e.status === "pending")) return;
    timer = setTimeout(async () => {
      if (location.hash !== hash) return;
      try {
        const fresh = await api(explUrl(aid));
        for (const [pid, e] of Object.entries(fresh)) {
          const was = ex[pid] && ex[pid].status; ex[pid] = e;
          const el = find(pid);
          if (was !== e.status && !(el && $("textarea", el))) redraw(pid);
        }
      } catch (e) { /* keep polling */ }
      poll();
    }, 3000);
  };
  items.forEach((p) => bindOne(p.id));
  poll();
}

async function viewResult(id) {
  loading();
  const [r, h, ex] = await Promise.all([api(`/api/student/results/${id}`), loadHome(),
    api(explUrl(id)).catch(() => ({}))]);
  const res = r.result;
  const wrong = r.items.filter((p) => p.given && !p.correct);
  const skippedN = (res.skipped || []).length;
  const pct = res.total ? res.correct / res.total : 0;
  app().innerHTML = topbar(STUDENT_NAV) + `<main class="page">
    <div class="grid-main">
      <div class="stack">
        <section class="card result-hero pop">
          <div class="score-ring">${ring(res.correct, res.total)}<b>${res.correct}/${res.total}</b></div>
          <h1>${res.total && res.correct === res.total ? "¡Perfecto!" : pct >= 0.6 ? "¡Buen trabajo!" : "Sigue practicando"}</h1>
          <p class="muted">${esc(r.title)} · entregada ${fmtDate(r.submitted_at)}${skippedN ? ` · ${skippedN} saltado${skippedN > 1 ? "s" : ""}` : ""}</p>
          <span class="xp-gain">${ICON.bolt.replace("<svg", '<svg width="20" height="20"')} +${res.xp} XP</span>
        </section>
        ${wrong.length ? `<section class="card card-pad"><h2>Antes de volver a intentarlo</h2>
          <p class="muted small" style="margin-top:-6px">Problemas parecidos y un poco más sencillos para preparar los que fallaste. Ya están en tu próxima misión.</p>
          ${wrong.map((p) => `<div class="prereq"><div class="row"><b>${esc(tName(p.topic))} · ${lvlQ(p)}</b><span class="chip red">Marcaste ${p.given} · era ${p.answer}</span></div>
            <div class="prereq-items">${(r.prereq_problems[p.id] || []).map((q) => `<button type="button" class="thumb" data-zoom="${q.image || ""}" data-alt="${esc(q.text || "")}">${q.figure ? `<img src="${q.figure}" alt="">` : ""}<span><b>${lvlQ(q)}</b> · ${esc(sub(q.subtopic))}</span></button>`).join("") || '<span class="small muted">No hay problemas más sencillos de este tipo.</span>'}</div></div>`).join("")}
          </section>` : ""}
        <section class="card card-pad"><h2>Corrección</h2>
          ${r.items.map((p, i) => { const sk = !p.given; return `<div class="answer-row">
            <span class="tick ${sk ? "skip" : p.correct ? "ok" : "ko"}">${sk ? "–" : p.correct ? ICON.check : ICON.x}</span>
            <div><b>${i + 1}. ${esc(tName(p.topic))}</b> <span class="muted small">${lvlQ(p)} · ${esc(sub(p.subtopic))}</span></div>
            <span class="mono small">${sk ? "saltado" : p.given + (p.correct ? "" : ` → ${p.answer}`)}</span></div>
            ${!sk && !p.correct ? explBlock(p, ex[p.id]) : ""}`; }).join("")}
        </section>
      </div>
      <aside class="stack">
        <div class="card card-pad"><h2>Cómo has cambiado</h2>
          ${res.changes.map((c) => { const up = c.after >= c.before; return `<div style="margin-bottom:12px"><div class="row" style="justify-content:space-between"><b class="small">${esc(tName(c.topic))}</b>
            <span class="small ${up ? "delta-up" : "delta-down"}">${up ? "▲" : "▼"} ${lvl(Math.floor(c.after))}</span></div>
            <div class="lvbar" style="margin-top:6px"><i style="width:${(c.after / 8) * 100}%;background:${up ? "var(--teal)" : "var(--orange)"}"></i><em style="left:${(c.before / 8) * 100}%;background:var(--muted)" title="antes"></em></div></div>`; }).join("")}
        </div>
        ${h.current ? missionCard(h) : ""}
      </aside>
    </div></main>`;
  bindShell();
  bindExplanations(r.id, wrong, ex);
}

async function viewStudentPath() {
  loading();
  const h = await loadHome();
  const done = h.topics.reduce((s, t) => s + t.level, 0), total = h.topics.length * 8;
  app().innerHTML = topbar(STUDENT_NAV) + `<main class="page">
    <div class="page-head"><div><h1>Hola, ${esc(h.name.split(" ")[0])}</h1><div class="muted">${esc(h.classroom)} · ${done} de ${total} niveles superados</div></div></div>
    <div class="grid-main">
      <div class="stack">${h.topics.map((t) => `<section class="card unit">
          <div class="unit-head"><div class="topic-ico">${esc(tIco(t.topic))}</div>
            <div style="flex:1"><h3>${esc(tName(t.topic))}</h3><div class="sub">${lvl(t.level)} · ${Math.round(t.progress * 100)} % completado</div></div>
            ${standing(t)}</div>
          ${unitPath(t)}
        </section>`).join("")}</div>
      <aside class="stack">${missionCard(h)}
        <div class="card card-pad"><h2>Tu reloj de temas</h2>
          ${radar(h.topics.map((t) => t.topic), [
            { values: h.topics.map((t) => t.class_avg), color: "#e47128", dash: true },
            { values: h.topics.map((t) => t.theta), color: "#008184", fill: "rgba(0,129,132,.18)" }], 300)}
          <div class="legend" style="justify-content:center;margin-top:6px"><span><i style="background:#008184"></i>Tú</span><span><i style="background:#e47128"></i>Media del aula</span></div>
        </div>
        ${h.last_result_id ? `<a class="btn ghost block" href="#/s/resultado/${h.last_result_id}">Ver último resultado</a>` : ""}
      </aside>
    </div></main>`;
  bindShell();
}

async function viewProgress() {
  loading();
  const h = await loadHome();
  const done = h.assignments.filter((a) => a.status === "done");
  app().innerHTML = topbar(STUDENT_NAV) + `<main class="page">
    <div class="page-head"><h1>Tu progreso</h1></div>
    <div class="kpis">
      <div class="card kpi"><span>XP</span><b>${h.xp}</b></div>
      <div class="card kpi"><span>Racha (semanas)</span><b>${h.streak}</b></div>
      <div class="card kpi"><span>Problemas</span><b>${h.answered}</b></div>
      <div class="card kpi"><span>Aciertos</span><b>${h.answered ? pct(h.correct / h.answered) : "—"}</b></div>
    </div>
    <div class="two">
      <div class="card card-pad"><h2>Reloj de temas</h2>
        ${radar(h.topics.map((t) => t.topic), [
          { values: h.topics.map((t) => t.class_avg), color: "#e47128", dash: true },
          { values: h.topics.map((t) => t.theta), color: "#008184", fill: "rgba(0,129,132,.18)" }], 380)}
        <div class="legend" style="justify-content:center"><span><i style="background:#008184"></i>Tú</span><span><i style="background:#e47128"></i>Media del aula</span></div>
      </div>
      <div class="card card-pad"><h2>Por tema</h2>
        ${h.topics.map((t) => `<div style="margin-bottom:14px"><div class="row" style="justify-content:space-between"><b class="small">${esc(tName(t.topic))}</b><span class="row small">${lvl(t.level)} ${standing(t)}</span></div>
          <div class="lvbar" style="margin-top:6px"><i style="width:${(t.theta / 8) * 100}%"></i><em style="left:${(t.class_avg / 8) * 100}%" title="Media del aula"></em></div>
          <div class="small muted" style="margin-top:4px">${t.answered} resueltos · aciertos ${pct(t.accuracy)}</div></div>`).join("")}
      </div>
    </div>
    <div class="card card-pad" style="margin-top:20px"><h2>Misiones entregadas</h2>
      ${done.length ? `<div class="table-wrap"><table><thead><tr><th>Misión</th><th>Entregada</th><th>Aciertos</th><th>XP</th></tr></thead><tbody>
        ${done.map((a) => `<tr class="click" data-id="${a.id}"><td>${esc(a.title)}</td><td>${fmtDate(a.submitted_at)}</td><td>${a.result.correct}/${a.result.total}</td><td>+${a.result.xp}</td></tr>`).join("")}
      </tbody></table></div>` : '<div class="empty">Aún no has entregado ninguna misión.</div>'}
    </div></main>`;
  $$("tr.click").forEach((tr) => (tr.onclick = () => go(`#/s/resultado/${tr.dataset.id}`)));
  bindShell();
}

// ---------------------------------------------------------------- teacher: students
function levelCells(topics) {
  return topics.map((t) => `<td style="padding:6px 4px"><span class="heat" style="${heatColor(t.theta)}" title="${esc(tName(t.topic))}: ${lvl(t.level)}">${t.level + 1}</span></td>`).join("");
}

async function viewTeacherStudents() {
  loading();
  const list = await api("/api/students");
  const topics = S.tax.topics;
  app().innerHTML = topbar(TEACHER_NAV) + `<main class="page">
    <div class="page-head"><div><h1>Alumnos</h1><div class="muted">${list.length} alumnos · cada alumno entra con su código</div></div>
      <span class="spacer"></span><button class="btn" id="add">Añadir alumno</button></div>
    <div class="card">${list.length ? `<div class="table-wrap"><table>
      <thead><tr><th>Alumno</th><th>Código</th><th>Aula</th><th>XP</th><th>Aciertos</th>${topics.map((t) => `<th style="padding:10px 4px;text-transform:none;font-family:var(--mono)" title="${esc(tName(t))}">${esc(tIco(t))}</th>`).join("")}</tr></thead>
      <tbody>${list.map((s) => `<tr class="click" data-id="${s.id}"><td><div class="row" style="flex-wrap:nowrap"><span class="avatar" style="background:var(--teal-50)">${esc(initials(s.name))}</span><b>${esc(s.name)}</b></div></td>
        <td class="mono">${s.id}</td><td>${esc(s.classroom)}</td><td>${s.xp}</td><td>${s.answered ? pct(s.correct / s.answered) : "—"}</td>${levelCells(s.topics)}</tr>`).join("")}</tbody>
    </table></div>` : '<div class="empty">Todavía no hay alumnos. Añade el primero.</div>'}</div>
  </main>`;
  bindShell();
  $("#add").onclick = addStudentModal;
  $$("tr.click").forEach((tr) => (tr.onclick = () => studentModal(tr.dataset.id)));
}

function addStudentModal() {
  const rooms = [...new Set((S.studentsCache || []).map((s) => s.classroom))];
  const m = modal(`<h2>Nuevo alumno</h2><form id="sf" class="stack" style="margin-top:14px">
    <div class="form-grid">
      <label class="f">Nombre<input id="sn" required placeholder="Nombre y apellido"></label>
      <label class="f">Aula<input id="sc" value="${esc(rooms[0] || "Aula 1")}" list="rooms"><datalist id="rooms">${rooms.map((r) => `<option value="${esc(r)}">`).join("")}</datalist></label>
      <label class="f">Nivel inicial<select id="sl">${[...Array(8)].map((_, i) => `<option value="${i}">${lvl(i)}</option>`).join("")}</select></label>
    </div><div class="err" id="serr"></div>
    <div class="row" style="justify-content:flex-end"><button class="btn">Crear alumno</button></div></form>`, () => { if (location.hash === "#/t") render(); });
  $("#sn").focus();
  $("#sf").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const s = await api("/api/students", { body: { name: $("#sn").value, classroom: $("#sc").value, start_level: $("#sl").value } });
      $(".modal", m.el).innerHTML = `<button class="linkbtn x" aria-label="Cerrar">${ICON.close}</button><h2>Alumno creado</h2>
        <div class="credential pop"><div class="muted small">Código de acceso de ${esc(s.name)}</div><div class="code">${s.id}</div></div>
        <p class="muted small">Dáselo al alumno: entra en la web y escribe este código. Ya tiene una primera misión de ${8} problemas.</p>
        <div class="row" style="justify-content:flex-end"><button class="btn ghost" id="again">Añadir otro</button><button class="btn" id="ok">Hecho</button></div>`;
      $("#ok").onclick = m.close;
      $("#again").onclick = () => { m.el.remove(); addStudentModal(); };
    } catch (err) { $("#serr").textContent = err.message; }
  };
}

async function studentModal(id) {
  const s = await api(`/api/students/${id}`);
  const m = modal(`<div class="row"><span class="avatar" style="width:44px;height:44px;background:var(--teal);color:#fff">${esc(initials(s.name))}</span>
      <div><h2>${esc(s.name)}</h2><div class="muted small">${esc(s.classroom)} · código <b class="mono">${s.id}</b> · empezó en ${lvl(s.start_level)}</div></div></div>
    <div class="kpis" style="margin-top:16px"><div class="card kpi"><span>XP</span><b>${s.xp}</b></div><div class="card kpi"><span>Racha</span><b>${s.streak}</b></div>
      <div class="card kpi"><span>Resueltos</span><b>${s.answered}</b></div><div class="card kpi"><span>Aciertos</span><b>${s.answered ? pct(s.correct / s.answered) : "—"}</b></div></div>
    <div class="two"><div>${radar(s.topics.map((t) => t.topic), [
        { values: s.topics.map((t) => t.class_avg), color: "#e47128", dash: true },
        { values: s.topics.map((t) => t.theta), color: "#008184", fill: "rgba(0,129,132,.18)" }], 320)}
      <div class="legend" style="justify-content:center"><span><i style="background:#008184"></i>Alumno</span><span><i style="background:#e47128"></i>Media del aula</span></div></div>
      <div>${s.topics.map((t) => `<div style="margin-bottom:10px"><div class="row small" style="justify-content:space-between"><b>${esc(tName(t.topic))}</b><span>${lvl(t.level)} · ${pct(t.accuracy)}</span></div>
        <div class="lvbar" style="margin-top:4px"><i style="width:${(t.theta / 8) * 100}%"></i><em style="left:${(t.class_avg / 8) * 100}%"></em></div></div>`).join("")}</div></div>
    <h3 style="margin:16px 0 6px">Misiones</h3>
    <div class="table-wrap"><table><thead><tr><th>Misión</th><th>Creada</th><th>Entrega</th><th>Estado</th><th>Aciertos</th></tr></thead><tbody>
      ${s.assignments.map((a) => `<tr><td>${esc(a.title)}</td><td>${fmtDate(a.created_at)}</td><td>${fmtDate(a.due)}</td>
        <td>${a.status === "done" ? '<span class="chip ahead">Entregada</span>' : '<span class="chip teal">Pendiente</span>'}</td><td>${a.result ? `${a.result.correct}/${a.result.total}` : "—"}</td></tr>`).join("")}
    </tbody></table></div>
    <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn red sm" id="del">Eliminar alumno</button></div>`);
  $("#del").onclick = async () => {
    if (!confirm(`¿Eliminar a ${s.name} y todos sus datos?`)) return;
    await api(`/api/students/${id}`, { method: "DELETE" });
    m.close(); toast("Alumno eliminado"); render();
  };
}

// ---------------------------------------------------------------- teacher: problems
function topicOptions(sel, withAll = "Todos los temas") {
  return `<option value="">${withAll}</option>` + Object.keys(S.tax.taxonomy).map((t) => `<option value="${esc(t)}" ${t === sel ? "selected" : ""}>${esc(tName(t))}</option>`).join("");
}
function levelOptions(sel, first = "Todos los niveles") {
  return `<option value="">${first}</option>` + [...Array(8)].map((_, i) => `<option value="${i}" ${String(sel) === String(i) ? "selected" : ""}>${lvl(i)}</option>`).join("");
}
function pcard(p) {
  return `<article class="card pcard" data-id="${esc(p.id)}">
    ${p.figure ? `<div class="pcard-img"><img src="${p.figure}" alt="" loading="lazy"></div>` : ""}
    <div class="row"><span class="chip teal">${esc(tName(p.topic))}</span><span class="chip">${lvlQ(p)}</span>${p.source === "profe" ? '<span class="chip gold">Tuyo</span>' : ""}</div>
    <div class="txt">${esc(p.text) || "<i>Solo imagen</i>"}</div>
    <div class="row small muted" style="justify-content:space-between"><span class="mono">${esc(p.id)}</span><span>Respuesta <b>${p.answer}</b></span></div></article>`;
}

async function viewTeacherProblems() {
  const f = (S.pf = S.pf || { topic: "", level: "", q: "" });
  loading();
  const data = await api(`/api/problems?topic=${encodeURIComponent(f.topic)}&level=${f.level}&q=${encodeURIComponent(f.q)}&limit=40`);
  S.problems = { items: data.items, total: data.total };
  const maxC = Math.max(1, ...Object.values(data.counts).flat());
  app().innerHTML = topbar(TEACHER_NAV) + `<main class="page">
    <div class="page-head"><div><h1>Problemas</h1><div class="muted">${data.total} en la selección</div></div><span class="spacer"></span><button class="btn" id="newp">Nuevo problema</button></div>
    <details class="card card-pad" style="margin-bottom:16px"><summary style="cursor:pointer;font-weight:700">Banco por tema y nivel</summary>
      <div class="coverage" style="margin-top:12px"><div class="h t">Tema</div>${[...Array(8)].map((_, i) => `<div class="h">${i + 1}</div>`).join("")}
      ${Object.keys(S.tax.taxonomy).map((t) => `<div class="t">${esc(tName(t))}</div>${(data.counts[t] || Array(8).fill(0)).map((c) => `<div style="${heatColor((c / maxC) * 8)}">${c}</div>`).join("")}`).join("")}</div>
    </details>
    <div class="filters">
      <select id="ft">${topicOptions(f.topic)}</select><select id="fl">${levelOptions(f.level)}</select>
      <input id="fq" placeholder="Buscar en el enunciado o id" value="${esc(f.q)}"><button class="btn ghost" id="fgo">Filtrar</button>
    </div>
    <div class="pgrid" id="grid">${data.items.map(pcard).join("") || '<div class="empty">Sin resultados</div>'}</div>
    ${data.total > data.items.length ? '<div class="row" style="justify-content:center;margin-top:18px"><button class="btn ghost" id="more">Cargar más</button></div>' : ""}
  </main>`;
  bindShell();
  const apply = () => { S.pf = { topic: $("#ft").value, level: $("#fl").value, q: $("#fq").value.trim() }; viewTeacherProblems(); };
  $("#ft").onchange = apply; $("#fl").onchange = apply; $("#fgo").onclick = apply;
  $("#fq").onkeydown = (e) => { if (e.key === "Enter") apply(); };
  $("#newp").onclick = newProblemModal;
  const bindCards = () => $$(".pcard").forEach((c) => (c.onclick = () => problemModal(c.dataset.id)));
  bindCards();
  const more = $("#more");
  if (more) more.onclick = async () => {
    const d = await api(`/api/problems?topic=${encodeURIComponent(f.topic)}&level=${f.level}&q=${encodeURIComponent(f.q)}&limit=40&offset=${S.problems.items.length}`);
    S.problems.items.push(...d.items);
    $("#grid").insertAdjacentHTML("beforeend", d.items.map(pcard).join(""));
    bindCards();
    if (S.problems.items.length >= d.total) more.remove();
  };
}

async function problemModal(id) {
  const [p, sim] = await Promise.all([api(`/api/problems/${encodeURIComponent(id)}`), api(`/api/problems/${encodeURIComponent(id)}/similar`)]);
  const m = modal(`<div class="row"><h2 class="mono">${esc(p.id)}</h2><span class="chip teal">${esc(tName(p.topic))}</span><span class="chip">${esc(sub(p.subtopic))}</span><span class="chip">${lvlQ(p)}</span></div>
    <div class="stack" style="margin-top:14px">
      ${statement(p)}
      ${tiles(p, { small: true, result: { answer: p.answer, given: null } })}
      ${p.auto_topic ? `<div class="auto-box">Clasificación automática: <b>${esc(tName(p.auto_topic))}</b> (${pct(p.auto_confidence)})</div>` : ""}
      <h3>Problemas parecidos (Qwen3-Embedding)</h3>
      <div class="pgrid">${sim.map((q) => `<article class="card pcard" data-id="${esc(q.id)}">${q.figure ? `<div class="pcard-img"><img src="${q.figure}" alt="" loading="lazy"></div>` : ""}
        <div class="row"><span class="chip teal">${esc(tName(q.topic))}</span><span class="chip">${lvlQ(q)}</span><span class="chip gold">${num(q.score, 2)}</span></div>
        <div class="txt">${esc(q.text)}</div></article>`).join("")}</div>
    </div>`);
  $$(".pcard[data-id]", m.el).forEach((c) => (c.onclick = () => { m.el.remove(); problemModal(c.dataset.id); }));
}

function newProblemModal() {
  let image = null, timer = null;
  const m = modal(`<h2>Nuevo problema</h2>
    <form id="pf" class="stack" style="margin-top:14px">
      <div class="two">
        <div class="stack">
          <label class="f">Enunciado<textarea id="pt" placeholder="Escribe o pega el enunciado"></textarea></label>
          <div class="auto-box" id="auto"><span class="muted">Escribe el enunciado y lo clasifico automáticamente.</span></div>
        </div>
        <div class="stack">
          <label class="drop" id="drop" tabindex="0"><input type="file" id="pi" accept="image/png,image/jpeg,image/webp" hidden>
            <span id="dropTxt">Añadir foto del problema</span><span class="small muted">PNG o JPG · leo las opciones A–E</span></label>
          <div class="small muted" id="ocr"></div>
        </div>
      </div>
      <div><div class="f" style="margin-bottom:6px">Opciones y respuesta correcta</div>
        <div class="opts">${LETTERS.map((l) => `<div class="opt"><label class="lt"><input type="radio" name="ans" value="${l}"> ${l}</label><input id="o${l}" placeholder="Opción ${l}"></div>`).join("")}</div></div>
      <div class="form-grid">
        <label class="f">Tema<select id="ptopic">${topicOptions("", "Automático")}</select></label>
        <label class="f">Subtema<select id="psub"><option value="">Automático</option></select></label>
        <label class="f">Nivel<select id="plevel">${levelOptions("", "Automático")}</select></label>
      </div>
      <div class="err" id="perr"></div>
      <div class="row" style="justify-content:flex-end"><button type="button" class="btn ghost" id="pcancel">Cancelar</button><button class="btn">Guardar problema</button></div>
    </form>`);
  const fillSubs = () => {
    const t = $("#ptopic").value;
    $("#psub").innerHTML = '<option value="">Automático</option>' + (t ? S.tax.taxonomy[t].map((s) => `<option value="${esc(s)}">${esc(sub(s))}</option>`).join("") : "");
  };
  let asked = 0;
  const classify = async () => {
    const pt = $("#pt");
    const text = pt ? pt.value.trim() : "";
    if (!text) return;
    const mine = ++asked;
    let r;
    try { r = await api("/api/classify", { body: { text, topic: $("#ptopic").value } }); }
    catch (e) { return; }                                    // the form still works without the suggestion
    const box = $("#auto");
    if (!box || mine !== asked) return;                      // form closed, or a newer text was sent meanwhile
    box.innerHTML = `<div>Clasificación automática</div><div><b>${esc(tName(r.topic))}</b> › ${esc(sub(r.subtopic))} · <b>${lvl(r.level)}</b></div>
      <div class="small muted">Confianza ${pct(r.confidence)} · según los ${r.neighbors.length ? 15 : 0} problemas más parecidos del banco</div>`;
  };
  $("#pt").oninput = () => { clearTimeout(timer); timer = setTimeout(classify, 450); };
  $("#ptopic").onchange = () => { fillSubs(); classify(); };
  $("#pcancel").onclick = m.close;
  $("#pi").onchange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const rd = new FileReader();
    rd.onload = async () => {
      image = rd.result;
      $("#drop").innerHTML = `<img src="${image}" alt="Vista previa">`;
      $("#ocr").textContent = "Leyendo opciones de la foto…";
      try {
        const r = await api("/api/extract-options", { body: { image } });
        if (!r.available) { $("#ocr").textContent = "Lector de opciones no disponible en este equipo: escríbelas a mano."; return; }
        const n = Object.keys(r.options).length;
        LETTERS.forEach((l) => { if (r.options[l] && !$("#o" + l).value) $("#o" + l).value = r.options[l]; });
        $("#ocr").innerHTML = n === 5 ? `<span style="color:var(--green);font-weight:700">✓ 5 opciones leídas de la foto</span>`
          : `${n} de 5 opciones leídas${r.problems ? " · " + esc(Object.entries(r.problems).map(([k, v]) => `${k}: ${v}`).join(", ")) : ""}`;
      } catch (err) { $("#ocr").textContent = err.message; }
    };
    rd.readAsDataURL(file);
  };
  $("#pf").onsubmit = async (e) => {
    e.preventDefault();
    const answer = ($("input[name=ans]:checked") || {}).value;
    const options = {}; LETTERS.forEach((l) => { if ($("#o" + l).value.trim()) options[l] = $("#o" + l).value.trim(); });
    try {
      const p = await api("/api/problems", { body: { text: $("#pt").value, image, answer, options, topic: $("#ptopic").value, subtopic: $("#psub").value, level: $("#plevel").value } });
      m.close(); toast(`Guardado como ${tName(p.topic)} · ${lvl(p.level)}`);
      S.pf = { topic: "", level: "", q: "" };
      await viewTeacherProblems(); problemModal(p.id);
    } catch (err) { $("#perr").textContent = err.message; }
  };
}

// ---------------------------------------------------------------- teacher: statistics
async function viewTeacherStats() {
  loading();
  const room = S.room || "";
  const st = await api(`/api/stats?classroom=${encodeURIComponent(room)}`);
  const T = st.topics;
  app().innerHTML = topbar(TEACHER_NAV) + `<main class="page">
    <div class="page-head"><div><h1>Estadísticas</h1><div class="muted">Embeddings: ${esc(st.embedder)} · clasificador: ${esc(st.classifier)} · lector de opciones: ${st.options_reader ? "sí" : "no"}</div></div><span class="spacer"></span>
      <select id="room" style="width:auto"><option value="">Todas las aulas</option>${st.classrooms.map((r) => `<option ${r === room ? "selected" : ""}>${esc(r)}</option>`).join("")}</select></div>
    <div class="kpis">
      <div class="card kpi"><span>Alumnos</span><b>${st.students.length}</b></div>
      <div class="card kpi"><span>Respuestas</span><b>${st.answered}</b></div>
      <div class="card kpi"><span>Aciertos</span><b>${pct(st.accuracy)}</b></div>
      <div class="card kpi"><span>Banco</span><b>${st.bank}</b></div>
    </div>
    ${!st.students.length ? '<div class="card empty">Añade alumnos para ver estadísticas.</div>' : `
    <div class="two">
      <div class="card card-pad"><h2>Nivel medio del aula</h2>
        ${radar(T.map((t) => t.topic), [
          { values: T.map((t) => t.max), color: "#4fb3b5", dash: true },
          { values: T.map((t) => t.avg_theta), color: "#008184", fill: "rgba(0,129,132,.18)" },
          { values: T.map((t) => t.min), color: "#e47128", dash: true }], 380)}
        <div class="legend" style="justify-content:center"><span><i style="background:#008184"></i>Media</span><span><i style="background:#4fb3b5"></i>Mejor</span><span><i style="background:#e47128"></i>Más bajo</span></div>
      </div>
      <div class="card card-pad"><h2>Por tema</h2>
        <div class="table-wrap"><table><thead><tr><th>Tema</th><th style="width:40%">Nivel medio</th><th>Aciertos</th><th>Resp.</th></tr></thead><tbody>
        ${T.map((t) => `<tr><td><b>${esc(tName(t.topic))}</b></td><td><div class="lvbar"><i style="width:${(t.avg_theta / 8) * 100}%"></i></div><div class="small muted" style="margin-top:3px">${lvl(Math.floor(t.avg_theta))} · ${num(t.avg_theta)}</div></td>
          <td>${pct(t.accuracy)}</td><td>${t.answered}</td></tr>`).join("")}</tbody></table></div>
      </div>
    </div>
    <div class="card card-pad" style="margin-top:20px"><h2>Mapa de niveles</h2>
      <div class="table-wrap"><table><thead><tr><th>Alumno</th><th>Aula</th>${T.map((t) => `<th style="padding:10px 4px" title="${esc(tName(t.topic))}">${esc(tShort(t.topic))}</th>`).join("")}<th>XP</th></tr></thead>
      <tbody>${st.students.map((s) => `<tr class="click" data-id="${s.id}"><td><b>${esc(s.name)}</b></td><td>${esc(s.classroom)}</td>${levelCells(s.topics)}<td>${s.xp}</td></tr>`).join("")}</tbody></table></div>
    </div>
    ${st.hardest.length ? `<div class="card card-pad" style="margin-top:20px"><h2>Problemas con más fallos</h2>
      <div class="table-wrap"><table><thead><tr><th>Problema</th><th>Tema</th><th>Nivel</th><th>Fallos</th></tr></thead><tbody>
      ${st.hardest.map((h) => `<tr class="click prob" data-id="${esc(h.id)}"><td class="mono">${esc(h.id)}</td><td>${esc(tName(h.topic))}</td><td>${lvl(h.level)}</td><td>${h.wrong}/${h.n}</td></tr>`).join("")}</tbody></table></div></div>` : ""}`}
  </main>`;
  bindShell();
  $("#room").onchange = (e) => { S.room = e.target.value; viewTeacherStats(); };
  $$("tr.click").forEach((tr) => (tr.onclick = () => (tr.classList.contains("prob") ? problemModal(tr.dataset.id) : studentModal(tr.dataset.id))));
}

// ---------------------------------------------------------------- router
async function render() {
  const hash = location.hash || "#/";
  $$(".overlay").forEach((o) => o.remove());
  if (S.map3d && !hash.includes("/mapa")) { S.map3d.destroy(); S.map3d = null; }
  try {
    if (!S.tax) S.tax = await api("/api/taxonomy");
    if (!S.me) { const me = await api("/api/me"); S.me = me.role ? me : null; }
    if (!S.me || hash === "#/login") return viewLogin();
    if (S.me.role === "student") {
      if (hash.startsWith("#/s/mision")) return viewMission();
      if (hash.startsWith("#/s/entregar")) return viewAnswer();
      if (hash.startsWith("#/s/progreso")) return viewProgress();
      if (hash.startsWith("#/s/mapa")) return viewMap();
      const m = hash.match(/^#\/s\/resultado\/(\d+)/);
      if (m) return viewResult(m[1]);
      if (hash !== "#/s") return go("#/s");
      return viewStudentPath();
    }
    if (hash.startsWith("#/t/problemas")) return viewTeacherProblems();
    if (hash.startsWith("#/t/estadisticas")) return viewTeacherStats();
    if (hash.startsWith("#/t/mapa")) return viewMap();
    if (hash !== "#/t") return go("#/t");
    const r = await viewTeacherStudents();
    api("/api/students").then((l) => (S.studentsCache = l));
    return r;
  } catch (e) {
    console.error(e);
    app().innerHTML = `<div class="page"><div class="card empty">${esc(e.message)}<br><br><a class="btn sm" href="#/login">Volver</a></div></div>`;
  }
}
window.addEventListener("hashchange", render);
document.addEventListener("keydown", (e) => { if (location.hash.startsWith("#/s/entregar") && S.lessonKey) S.lessonKey(e); });
render();
