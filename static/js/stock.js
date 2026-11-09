/* Bar Stock screens. The front page only shows figures and tables, plus one button to upload the
   night's Square sales. Everything that changes setup (drinks, specials, products, mappings) lives in
   Settings mode, which managers switch into from the header. */
"use strict";

// ── Helpers ──────────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// Line icons (24px grid, drawn with the current text colour).
const ICONS = {
  upload: "M12 15V4M7 9l5-5 5 5M5 20h14",
  count: "M9 3h6v3H9zM8 4.5H6a1 1 0 0 0-1 1V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V5.5a1 1 0 0 0-1-1h-2M9 14l2 2 4-4",
  waste: "M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11zM9.5 15a2.5 2.5 0 0 0 2.5 2.5",
  batch: "M9 3h6M10 3v6.5L5.2 18A2 2 0 0 0 7 21h10a2 2 0 0 0 1.8-3L14 9.5V3M7.5 15h9",
  settings: "M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1M15 4v4M9 10v4M17 16v4",
  done: "M5 12.5l4.5 4.5L19 7",
  out: "M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4M10 8l-4 4 4 4M6 12h10",
  back: "M15 5l-7 7 7 7",
  up: "M7 14l5-5 5 5", down: "M7 10l5 5 5-5",
  takings: "M16 7.5A4 4 0 0 0 9 10v9M6.5 14H14M6.5 19H17",
  drinks: "M6 3h12l-1.2 8.5a4.8 4.8 0 0 1-9.6 0zM12 16v5M8 21h8M6.6 7.5h10.8",
  gp: "M18.5 5.5l-13 13M7.5 9.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM16.5 18.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  loss: "M12 4l9 16H3zM12 10v4M12 17.2v.1",
  stock: "M3.5 7.5L12 3.5l8.5 4v9L12 20.5l-8.5-4zM3.5 7.5L12 11.5l8.5-4M12 11.5v9",
  order: "M3 4h2.5l2.2 11h10.6l2-7.5H6.4M9 20.2v.1M17 20.2v.1",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  truck: "M3 6h11v10H3zM14 9.5h4l3 3V16h-7M7 19.5a1.6 1.6 0 1 0 0-.1M17 19.5a1.6 1.6 0 1 0 0-.1",
  tag: "M3.5 12.5V4h8.5l8.5 8.5-8 8zM8 8.2v.1",
  image: "M4 5h16v14H4zM4 15.5l4.5-4.5 5 5M13.5 14l2.5-2.5 4 4M15.5 8.7v.1",
  palette: "M12 3a9 9 0 1 0 0 18c.9 0 1.5-.7 1.5-1.5 0-.4-.2-.8-.4-1.1-.3-.3-.4-.6-.4-1 0-.8.7-1.4 1.5-1.4H16a5 5 0 0 0 5-5c0-4.4-4-8-9-8zM7.5 11.5v.1M10.5 7.5v.1M15 7.5v.1",
  reset: "M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4",
  people: "M15.5 19v-1a4 4 0 0 0-4-4h-5a4 4 0 0 0-4 4v1M9 10.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM21.5 19v-1a4 4 0 0 0-3-3.9M15 3.6a3.5 3.5 0 0 1 0 6.8",
  plus: "M12 5v14M5 12h14", download: "M12 4v11M7 10l5 5 5-5M5 20h14", chart: "M4 20h16M7 16v-5M12 16V7M17 16v-8",
};
const icon = (name, size = 18) => `<svg class="i" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICONS[name]}"/></svg>`;

const RANK = { staff: 1, manager: 2, admin: 3 };
const LOCS = ["Bar", "Cellar"];
const isMgr = () => RANK[me?.role] >= 2;
const isAdmin = () => RANK[me?.role] >= 3;

const GBP = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
const GBP0 = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const gbp = (v) => (v == null || isNaN(v) ? "-" : GBP.format(v));
const gbpShort = (v) => (v == null ? "-" : Math.abs(v) >= 1000 ? GBP0.format(v) : GBP.format(v));
/** Up to `dp` decimals, without trailing zeros: 11 not 11.0, 4.2 not 4.20. */
const num = (v, dp = 1) => {
  if (v == null || isNaN(v)) return "-";
  const s = Number(v).toLocaleString("en-GB", { maximumFractionDigits: dp });
  return /^-0(\.0*)?$/.test(s) ? "0" : s; // never show "-0"
};
const pct = (v) => (v == null ? "-" : `${num(v, 0)}%`);

/** A liquid amount as people say it: 11 L, 4.2 L, 175 ml (or kg/g for things sold by weight). */
function vol(ml, measure = "ml") {
  if (ml == null || isNaN(ml)) return "-";
  const g = measure === "g", a = Math.abs(ml);
  if (a >= 1000) return `${num(ml / 1000, a >= 20000 ? 0 : 1)} ${g ? "kg" : "L"}`;
  return `${num(ml, 0)} ${g ? "g" : "ml"}`;
}

/** "70cl bottle" gives bottles, "50L keg" kegs, "1L batch" batches. */
function unitWord(label, n) {
  let w = String(label || "").trim().split(/\s+/).pop().toLowerCase();
  if (!w || /^\d/.test(w)) w = "unit";
  if (Math.abs(n) === 1) return w;
  return /(x|ch|sh|s)$/.test(w) ? w + "es" : w + "s";
}
const units = (n, label) => (n == null ? "-" : `${num(n, 1)} ${unitWord(label, n)}`);

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function day(iso) {
  if (!iso) return "-";
  const d = new Date(iso.slice(0, 10) + "T12:00:00");
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}
const when = (ts) => (ts ? `${day(ts)}, ${ts.slice(11, 16)}` : "never");
const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
/** Trading day now: before 5am still counts as last night. */
const tradingToday = () => isoDay(new Date(Date.now() - 5 * 3600e3));
const addDays = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return isoDay(d); };

/** Same rule as the server's item_key, so a Square button can be linked before it has sold. */
function itemKey(name, variation = "") {
  const clean = (s) => String(s || "").trim().toLowerCase().replace(/\s+/g, " ");
  const v = clean(variation);
  return clean(name) + (v && v !== "regular" ? "|" + v : "");
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.style.display = "none"), 4500);
}

async function api(path, opts = {}) {
  if (opts.json !== undefined) {
    opts = { ...opts, method: opts.method || "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opts.json) };
  }
  const r = await fetch(path, opts);
  if (r.status === 401 && !path.includes("/auth/")) { boot(); throw new Error("Please sign in"); }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `Request failed (${r.status})`);
  return body;
}

const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message); } };

// ── State ────────────────────────────────────────────────────────────────────

let me = null;            // signed-in user
let base = null;          // /overview: stock lines and the product list
let mode = "view";        // "view" (figures only) or "settings"
let task = null;          // "count" | "waste" | "batch": a job opened from the front page
let report = "overview";  // tab on the front page
let setTab = "drinks";    // section in Settings
let period = { kind: "last", from: "", to: "" };
let lastResult = null;    // message from the last upload
let draft = null;         // drink being edited
let prodDraft = null;     // product being edited
let editKey = null;       // Square item being re-linked
let loc = "Bar", countAt = "", sheet = null, sheetFile = null;
let cache = {};           // per-render fetches, cleared on reload

const productById = new Map();
const productByLabel = new Map();
const targetByLabel = new Map();
const squareByLabel = new Map();

// ── Sortable, searchable tables ──────────────────────────────────────────────
// cols: { k, label, n (numeric), f(row) gives html, v(row) gives the value for sorting and CSV }

const TB = {};
function tbl(id, cols, rows, o = {}) {
  const old = TB[id] || {};
  TB[id] = { cols, rows, o, sort: old.sort ?? o.sort ?? null, q: old.q ?? "", all: false };
  const tools = o.search || o.csv ? `<div class="tools">
    ${o.search ? `<input data-tsearch="${id}" placeholder="${esc(o.search)}" value="${esc(TB[id].q)}" aria-label="Search">` : ""}
    <span class="sp"></span>${o.csv ? `<button class="btn ghost small" data-tcsv="${id}">Download CSV</button>` : ""}</div>` : "";
  return `${tools}<div class="scroll" id="tb-${id}">${tblBody(id)}</div>`;
}

const cellVal = (c, r) => (c.v ? c.v(r) : r[c.k]);
function tblRows(id) {
  const t = TB[id];
  let rows = t.rows;
  if (t.q) {
    const q = t.q.toLowerCase();
    rows = rows.filter((r) => t.cols.some((c) => String(cellVal(c, r) ?? "").toLowerCase().includes(q)) ||
      (t.o.extra && String(t.o.extra(r)).toLowerCase().includes(q)));
  }
  if (t.sort) {
    const [k, dir] = t.sort, c = t.cols.find((x) => x.k === k);
    if (c) rows = [...rows].sort((a, b) => {
      const x = cellVal(c, a), y = cellVal(c, b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * dir;
    });
  }
  return rows;
}

function tblBody(id) {
  const t = TB[id], rows = tblRows(id);
  const limit = t.o.limit && !t.all ? t.o.limit : Infinity;
  const head = t.cols.map((c) => {
    const s = t.sort && t.sort[0] === c.k ? icon(t.sort[1] > 0 ? "up" : "down", 13) : "";
    return `<th class="${c.n ? "n" : ""}" ${c.nosort ? "" : `data-sort="${id}:${c.k}"`}>${esc(c.label)}${s}</th>`;
  }).join("");
  const body = rows.slice(0, limit).map((r) => `<tr${t.o.rowAttr ? " " + t.o.rowAttr(r) : ""}>${t.cols.map((c) =>
    `<td class="${c.n ? "n" : ""}">${c.f ? c.f(r) : plain(cellVal(c, r))}</td>`).join("")}</tr>`).join("");
  const more = rows.length > limit ? `<tr><td colspan="${t.cols.length}" class="empty"><button class="link" data-tall="${id}">Show all ${rows.length}</button></td></tr>` : "";
  const foot = t.o.foot ? `<tfoot>${t.o.foot(rows)}</tfoot>` : "";
  return `<table><thead><tr>${head}</tr></thead><tbody>${body || `<tr><td colspan="${t.cols.length}" class="empty">${esc(t.o.empty || "Nothing to show.")}</td></tr>`}${more}</tbody>${foot}</table>`;
}

const plain = (v) => (typeof v === "number" ? num(v, 2) : typeof v === "object" && v !== null ? "" : esc(v ?? ""));
const redrawTable = (id) => { const el = $(`tb-${id}`); if (el) el.innerHTML = tblBody(id); };

function downloadCsv(id) {
  const t = TB[id], rows = tblRows(id);
  const cell = (v) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const text = [t.cols.map((c) => cell(c.label)).join(","), ...rows.map((r) => t.cols.map((c) => cell(cellVal(c, r))).join(","))].join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  a.download = `${id}-${tradingToday()}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ── Boot and data ────────────────────────────────────────────────────────────

let brand = { name: "", color: "", logo: false, v: 0 };
async function loadBranding() {
  try { brand = await api("/api/venue/branding"); } catch { /* keep the defaults */ }
  applyBranding();
}

const rgbOf = (hex) => { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const hexOf = (rgb) => "#" + rgb.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
function luminance(hex) {
  const [r, g, b] = rgbOf(hex).map((v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const contrast = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
/** Step a colour towards black or white until it stands out from the surface by at least 3:1. */
function legibleOn(hex, surface) {
  // Change lightness only, keeping hue and saturation, so gold stays gold rather than turning olive.
  let [h, sat, l] = toHsl(rgbOf(hex)), out = hex;
  const step = luminance(surface) > 0.5 ? -0.03 : 0.03;
  for (let i = 0; i < 30 && contrast(out, surface) < 3; i++) { l = Math.min(1, Math.max(0, l + step)); out = hexOf(fromHsl(h, sat, l)); }
  return out;
}
function toHsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
  if (!d) return [0, 0, l];
  const s = d / (1 - Math.abs(2 * l - 1));
  const h = mx === r ? ((g - b) / d + 6) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, s, l];
}
function fromHsl(h, s, l) {
  const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}

/** Dark or light text, whichever reads better on the brand colour. */
function inkFor(hex) {
  const n = parseInt(hex.slice(1), 16), r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return 0.299 * r + 0.587 * g + 0.114 * b > 165 ? "#14181f" : "#ffffff";
}

function applyBranding() {
  const root = document.documentElement.style;
  const c = brand.color || "#1f6b5c";
  if (brand.color) { root.setProperty("--brand", c); root.setProperty("--brand-ink", inkFor(c)); }
  else { root.removeProperty("--brand"); root.removeProperty("--brand-ink"); }
  // Pale brand colours (gold, yellow) are fine on buttons but vanish as thin bars or link text on white.
  root.setProperty("--chart-light", legibleOn(c, "#ffffff"));
  root.setProperty("--chart-dark", legibleOn(c, "#181c22"));
  const html = document.documentElement;
  for (const k of ["theme", "header", "banner", "font", "size", "corners", "density"]) if (brand[k]) html.dataset[k] = brand[k];
  const name = brand.name || "Bar Stock";
  document.title = brand.name ? `${brand.name} · Stock` : "Bar Stock";
  const logo = brand.logo ? `/api/venue/branding/logo?v=${encodeURIComponent(brand.v)}` : "";
  $("brand").innerHTML = `${logo ? `<img src="${logo}" alt="">` : `<span class="mark">${esc(name[0].toUpperCase())}</span>`}
    <span class="nm">${logo ? "<small>Stock</small>" : `${esc(name)}${brand.name ? "<small>Stock</small>" : ""}`}</span>`;
  $("loginLogo").innerHTML = logo ? `<img src="${logo}" alt="${esc(name)}">` : "";
  $("favicon").href = logo || "data:,";
}

async function boot() {
  await loadBranding();
  const st = await api("/api/auth/status");
  me = st.user;
  $("app").classList.toggle("hidden", !me);
  $("login").classList.toggle("hidden", !!me);
  if (!me) {
    $("firstAdmin").classList.toggle("hidden", !st.needs_first_admin);
    $("loginForm").classList.toggle("hidden", st.needs_first_admin);
    $("loginTitle").textContent = st.needs_first_admin ? "Set up" : "Sign in";
    $("loginUser").innerHTML = st.users_public.map((u) => `<option value="${esc(u.id)}">${esc(u.name)}</option>`).join("");
    return;
  }
  $("who").textContent = `${me.name} · ${me.role}`;
  $("settingsBtn").classList.toggle("hidden", !isAdmin());
  await reload();
}

async function reload() {
  cache = {};
  base = await api("/api/venue/overview");
  productById.clear(); productByLabel.clear();
  const seen = new Set();
  for (const p of base.products) {
    const label = seen.has(p.label) ? `${p.label} #${p.id}` : p.label;
    seen.add(p.label);
    p.pick = label;
    productById.set(p.id, p);
    productByLabel.set(label, p);
  }
  $("productList").innerHTML = base.products.map((p) => `<option value="${esc(p.pick)}"></option>`).join("");
  const cats = [...new Set(base.products.map((p) => p.category).filter(Boolean))].sort();
  const subs = [...new Set(base.products.map((p) => p.subcategory).filter(Boolean))].sort();
  $("catList").innerHTML = cats.map((c) => `<option value="${esc(c)}"></option>`).join("");
  $("subcatList").innerHTML = subs.map((c) => `<option value="${esc(c)}"></option>`).join("");
  await render();
}

/** Fetch once per render cycle. */
async function get(path) {
  if (!(path in cache)) cache[path] = await api(path);
  return cache[path];
}

async function loadTargets() {
  const { recipes } = await get("/api/venue/recipes");
  targetByLabel.clear();
  for (const r of recipes.filter((x) => x.active)) targetByLabel.set(`Drink: ${r.name}`, { recipe_id: r.id });
  for (const p of base.products) targetByLabel.set(p.pick, { product_id: p.id });
  $("targetList").innerHTML = [...targetByLabel.keys()].map((k) => `<option value="${esc(k)}"></option>`).join("");
  return recipes;
}

function periodRange() {
  const t = tradingToday();
  if (period.kind === "7") return { from: addDays(t, -6), to: t };
  if (period.kind === "30") return { from: addDays(t, -29), to: t };
  if (period.kind === "custom" && period.from && period.to) return { from: period.from, to: period.to };
  return { from: "", to: "" }; // last night with sales
}

async function render() {
  $("modeTag").classList.toggle("hidden", mode !== "settings");
  $("settingsBtn").innerHTML = mode === "settings" ? `${icon("done", 16)} Done` : `${icon("settings", 16)} Settings`;
  const html = task ? await TASKS[task]() : mode === "settings" ? await settingsView() : await frontView();
  // Redrawing replaces every input, so put focus back where it was (e.g. after tabbing between ingredients).
  const a = document.activeElement, sel = a && a !== document.body ? focusKey(a) : null;
  const caret = a && "selectionStart" in a ? (() => { try { return a.selectionStart; } catch { return null; } })() : null;
  $("view").innerHTML = html;
  if (sel) {
    const el = document.querySelector(sel);
    if (el) { el.focus(); if (caret != null) try { el.setSelectionRange(caret, caret); } catch { /* not a text field */ } }
  }
}

function focusKey(el) {
  if (el.id) return `#${CSS.escape(el.id)}`;
  for (const { name, value } of el.attributes) if (name.startsWith("data-")) return `[${name}="${CSS.escape(value)}"]`;
  return null;
}

// ── Front page ───────────────────────────────────────────────────────────────

function uploadCard(k) {
  const res = lastResult ? `<div class="result ${lastResult.warn ? "warn" : ""}">${lastResult.html}</div>` : "";
  return `<div class="hero" id="drop">
    <div class="txt"><h2>End of the night? Upload the sales.</h2>
      <p>In Square: Reports &gt; Item sales &gt; Export &gt; <b>Item sales detail</b>. Then press the button or drop the file here. Uploading the same file twice is safe.</p>
      <div class="last">Last upload: ${esc(when(k.last_import))}</div>
      <div id="needDate" class="row hidden"><label style="max-width:240px">This is a summary export. Which night is it for?<input type="date" id="csvDate"></label><button class="btn ghost small" id="csvRetry">Upload</button></div>
      ${res}</div>
    <button class="btn big" id="uploadBtn">${icon("upload", 20)} Upload Square sales</button></div>
    ${quickActions()}`;
}

const canDo = (job) => isAdmin() || !!(me?.stock_jobs || {})[job];

function quickActions() {
  const jobs = [["count", "count", "Stocktake"], ["waste", "waste", "Log wastage or staff drink"], ["batch", "batch", "Make a batch"]]
    .filter(([j]) => canDo(j));
  return jobs.length ? `<div class="quick">${jobs.map(([j, ic, l]) => `<button class="btn ghost" data-task="${j}"><span class="ico">${icon(ic, 16)}</span>${l}</button>`).join("")}</div>` : `<div class="quick"></div>`;
}

function periodBar(d) {
  const label = d.from === d.to ? day(d.from) : `${day(d.from)} to ${day(d.to)}`;
  const chips = [["last", "Last night"], ["7", "7 days"], ["30", "30 days"], ["custom", "Custom"]]
    .map(([k, l]) => `<button class="chip ${period.kind === k ? "on" : ""}" data-period="${k}">${l}</button>`).join("");
  const custom = period.kind === "custom" ? `<input type="date" id="pFrom" value="${esc(d.from)}" style="width:auto;min-height:32px">
    <input type="date" id="pTo" value="${esc(d.to)}" style="width:auto;min-height:32px"><button class="btn small" id="pGo">Show</button>` : "";
  return `<div class="bar"><span class="label">${esc(label)}${d.nights > 1 ? ` <span class="hint">· ${d.nights} trading nights</span>` : ""}</span><div class="chips">${chips}</div>${custom}</div>`;
}

function change(now, prev) {
  if (!prev) return "";
  const p = (now - prev) / prev * 100;
  return `<span class="${p >= 0 ? "up" : "down"}">${p >= 0 ? "+" : "-"}${num(Math.abs(p), 0)}%</span> vs previous`;
}

function kpi(label, value, sub = "", ic = "chart", trend = null) {
  return `<div class="kpi"><div class="kl"><span class="kic">${icon(ic, 16)}</span>${label}</div><div class="kv">${value}</div>
    <div class="kd">${sub || "&nbsp;"}</div>${trend || ""}</div>`;
}

/** A small trend line under a figure: muted line, current point in the brand colour. */
function sparkline(values) {
  if (!values || values.length < 2) return "";
  const w = 120, h = 28, max = Math.max(...values), min = Math.min(...values), span = max - min || 1;
  const pts = values.map((v, i) => [i / (values.length - 1) * (w - 6) + 3, h - 3 - (v - min) / span * (h - 6)]);
  const [lx, ly] = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true"><polyline points="${pts.map((p) => p.join(",")).join(" ")}" fill="none" stroke="var(--muted)" stroke-opacity=".55" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${lx}" cy="${ly}" r="4" fill="var(--chart)" stroke="var(--card)" stroke-width="2"/></svg>`;
}

function alerts(k) {
  const out = [];
  if (k.waiting) out.push(`<div class="alert"><b>${k.waiting} Square item${k.waiting > 1 ? "s" : ""} not linked to stock yet.</b>
    Their sales are kept and come off stock once linked.${isAdmin() ? `<button class="btn small" data-goset="square">Link them</button>` : " An admin can link them in Settings."}</div>`);
  if (k.negative) out.push(`<div class="alert"><b>${k.negative} product${k.negative > 1 ? "s are" : " is"} below zero.</b> A recount or a missing delivery usually explains it.
    <button class="btn small ghost" data-report="stock">See stock</button></div>`);
  if (isAdmin() && k.comps) out.push(`<div class="alert"><b>${k.comps} comp${k.comps > 1 ? "s" : ""} with no reason.</b> Say whether each was wastage, overpour, training or a staff drink.
    <button class="btn small ghost" data-report="losses">Sort them</button></div>`);
  return out.join("");
}

const REPORTS = [
  ["overview", "Overview", 1], ["sold", "Drinks sold", 2], ["used", "Stock used", 2], ["stock", "Stock levels", 1],
  ["reorder", "To order", 1], ["losses", "Losses", 2], ["variance", "Stocktake check", 2], ["gp", "Prices & GP", 2],
];

async function frontView() {
  const r = periodRange();
  const d = await get(`/api/venue/dashboard?from=${r.from}&to=${r.to}`);
  const k = d.kpis;
  const tiles = isMgr() ? [
    kpi("Takings", gbpShort(k.takings), change(k.takings, k.prev_takings), "takings", sparkline(d.by_day.map((x) => x.takings))),
    kpi("Drinks sold", num(k.drinks, 0), change(k.drinks, k.prev_drinks), "drinks", sparkline(d.by_day.map((x) => x.drinks))),
    kpi("Gross profit", pct(k.gp_pct), k.gp_cover_pct != null && k.gp_cover_pct < 95 ? `on the ${k.gp_cover_pct}% of takings with costs` : "after VAT", "gp"),
    kpi("Losses", gbpShort(k.losses), "wastage, comps, staff, overpour", "loss"),
    kpi("Stock value", gbpShort(k.stock_value), `last count ${esc(k.last_count ? day(k.last_count) : "never")}`, "stock"),
    kpi("To order", num(k.reorder, 0), `${k.below_par} below par`, "order"),
  ] : [
    kpi("Drinks sold", num(k.drinks, 0), change(k.drinks, k.prev_drinks), "drinks"),
    kpi("To order", num(k.reorder, 0), `${k.below_par} below par`, "order"),
    kpi("Last stocktake", esc(k.last_count ? day(k.last_count) : "never"), "", "count"),
  ];
  const tabs = REPORTS.filter((t) => RANK[me.role] >= t[2]).map(([key, label]) =>
    `<button data-report="${key}" class="${report === key ? "on" : ""}">${label}${key === "losses" && k.comps ? `<span class="n">${k.comps}</span>` : ""}</button>`).join("");
  if (!REPORTS.some((t) => t[0] === report && RANK[me.role] >= t[2])) report = "overview";
  return `${uploadCard(k)}${alerts(k)}${periodBar(d)}<div class="kpis">${tiles.join("")}</div>
    <nav class="tabs">${tabs}</nav>${await REPORT_VIEWS[report](d)}`;
}

// Column sets reused by the overview and the full tabs.
const COLS = {
  sold: [
    { k: "item", label: "Square item", f: (r) => `${esc(r.item)}${r.waiting ? ` <span class="pill warn">not linked</span>` : ""}${r.no_stock ? ` <span class="pill">no stock</span>` : ""}<span class="sub">${esc(r.category)}</span>`, v: (r) => r.item },
    { k: "qty", label: "Sold", n: true, f: (r) => num(r.qty, 0) + (r.comped ? `<span class="sub">+${num(r.comped, 0)} comped</span>` : "") },
    { k: "takings", label: "Takings", n: true, f: (r) => gbp(r.takings) },
    { k: "avg", label: "Avg price", n: true, v: (r) => (r.qty ? r.takings / r.qty : null), f: (r) => gbp(r.qty ? r.takings / r.qty : null) },
    { k: "cost", label: "Cost", n: true, f: (r) => gbp(r.cost) },
    { k: "gp_pct", label: "GP", n: true, f: (r) => gpCell(r.gp_pct) },
  ],
  used: [
    { k: "label", label: "Product", f: (r) => `${esc(r.label)}<span class="sub">${esc(r.category)}</span>` },
    { k: "sold_ml", label: "Sold", n: true, f: (r) => `${vol(r.sold_ml, r.measure)}<span class="sub">${units(r.sold_ml / r.unit_ml, r.unit_label)}</span>` },
    { k: "lost_ml", label: "Lost", n: true, f: (r) => (r.lost_ml ? `<span class="low">${vol(r.lost_ml, r.measure)}</span>` : "-") },
    { k: "sold_cost", label: "Cost of sales", n: true, f: (r) => gbp(r.sold_cost) },
    { k: "lost_cost", label: "Cost of losses", n: true, f: (r) => (r.lost_cost ? gbp(r.lost_cost) : "-") },
    { k: "in_stock", label: "In stock", n: true, f: (r) => units(r.in_stock, r.unit_label) },
  ],
  reorder: [
    { k: "label", label: "Product", f: (r) => `${esc(r.label)}<span class="sub">${esc(r.category)}</span>` },
    { k: "units", label: "In stock", n: true, f: (r) => `<span class="${r.units < 0 ? "neg" : "low"}">${units(r.units, r.unit_label)}</span>` },
    { k: "par", label: "Par", n: true, f: (r) => (r.par == null ? "-" : num(r.par, 1)) },
    { k: "per_night", label: "Used per night", n: true, f: (r) => (r.per_night ? units(r.per_night, r.unit_label) : "-") },
    { k: "nights_left", label: "Lasts", n: true, f: (r) => (r.nights_left == null ? "-" : r.nights_left < 1 ? `<span class="neg">under a night</span>` : `${num(r.nights_left, 1)} nights`) },
    { k: "order", label: "Order", n: true, f: (r) => (r.order ? `<b>${units(r.order, r.unit_label)}</b>` : "-") },
  ],
};

function gpCell(v) {
  if (v == null) return `<span class="hint">no cost</span>`;
  return `<span class="${v < 60 ? "neg" : v < 70 ? "low" : ""}">${pct(v)}</span>`;
}

// ── Charts ───────────────────────────────────────────────────────────────────
// One series each, in the brand colour (darkened if too pale to see). No legend: the card title says
// what is plotted. Every bar has a hover tooltip, and each chart has its numbers as a table underneath.

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v)), n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}
const axisMoney = (v) => (v >= 10000 ? `£${num(v / 1000, 0)}K` : `£${num(v, 0)}`);

/** Vertical columns along time, e.g. takings per hour or per night. */
function columnChart(points, { label, value, tip, axis = axisMoney }) {
  if (!points.length) return `<p class="empty">Nothing to chart yet.</p>`;
  const max = niceMax(Math.max(...points.map(value)));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => `<div class="cc-tick" style="bottom:${f * 100}%"><span>${axis(max * f)}</span></div>`).join("");
  const peak = points.reduce((a, b) => (value(b) > value(a) ? b : a));
  const cols = points.map((p) => {
    const h = value(p) / max * 100;
    return `<div class="cc-col" data-tip="${esc(tip(p))}" tabindex="0"><div class="cc-bar" style="height:${h}%">${p === peak ? `<span class="cc-peak">${esc(axis(value(p)))}</span>` : ""}</div><span class="cc-x">${esc(label(p))}</span></div>`;
  }).join("");
  return `<div class="cc"><div class="cc-plot">${ticks}<div class="cc-cols">${cols}</div></div></div>`;
}

/** Horizontal bars for comparing parts, value at each bar's tip. */
function barList(rows, { label, value, show, tip, limit = 8 }) {
  if (!rows.length) return `<p class="empty">Nothing to chart yet.</p>`;
  let list = [...rows].sort((a, b) => value(b) - value(a));
  if (list.length > limit) {
    const rest = list.slice(limit - 1);
    list = [...list.slice(0, limit - 1), { _other: true, _n: rest.length, _v: rest.reduce((s, r) => s + value(r), 0) }];
  }
  const v = (r) => (r._other ? r._v : value(r));
  const max = Math.max(...list.map(v)) || 1;
  return `<div class="hb">${list.map((r) => `<div class="hb-row" data-tip="${esc(r._other ? `${r._n} more: ${show(r._v)}` : tip(r))}" tabindex="0">
    <span class="hb-l">${esc(r._other ? `Other (${r._n})` : label(r))}</span>
    <span class="hb-track"><span class="hb-bar" style="width:${Math.max(v(r) / max * 100, 0.5)}%"></span></span>
    <span class="hb-v">${esc(show(v(r)))}</span></div>`).join("")}</div>`;
}

const asTable = (html) => `<details class="astable"><summary>Show as a table</summary>${html}</details>`;
/** Square sends categories in capitals; "SPARKLING & CHAMPAGNE" reads better as "Sparkling & champagne". */
const titleCase = (t) => { const x = String(t || "").toLowerCase(); return x.charAt(0).toUpperCase() + x.slice(1); };
const hourLabel = (h) => `${h % 12 || 12}${h < 12 ? "am" : "pm"}`;

const LOSS_NAMES = { wastage: "Wastage", overpour: "Overpour", training: "Training", staff: "Staff drinks", comp: "Comps (no reason)", refunded: "Refunded after pouring" };
const lossName = (k) => (String(k).startsWith("other:") ? k.slice(6) : LOSS_NAMES[k] || k);

const REPORT_VIEWS = {
  async overview(d) {
    if (!isMgr()) return REPORT_VIEWS.reorder(d);
    const card = (title, key, body, cls = "") => `<div class="card ${cls}"><h2>${title}${key ? `<button class="link more" data-report="${key}">See all</button>` : ""}</h2>${body}</div>`;
    const multi = d.by_day.length > 1;
    const time = multi
      ? columnChart(d.by_day, { label: (p) => day(p.day).slice(0, 6), value: (p) => p.takings, tip: (p) => `${day(p.day)}: ${gbp(p.takings)} from ${num(p.drinks, 0)} drinks` })
      : columnChart(d.by_hour, { label: (p) => hourLabel(p.hour), value: (p) => p.takings, tip: (p) => `${hourLabel(p.hour)} to ${hourLabel((p.hour + 1) % 24)}: ${gbp(p.takings)} from ${num(p.drinks, 0)} drinks` });
    const timeTable = multi ? tbl("ovDays", [
      { k: "day", label: "Night", f: (r) => esc(day(r.day)) }, { k: "drinks", label: "Drinks", n: true, f: (r) => num(r.drinks, 0) },
      { k: "takings", label: "Takings", n: true, f: (r) => gbp(r.takings) }, { k: "cost", label: "Cost of sales", n: true, f: (r) => gbp(r.cost) },
    ], d.by_day) : tbl("ovHours", [
      { k: "hour", label: "Hour", f: (r) => esc(hourLabel(r.hour)) }, { k: "drinks", label: "Drinks", n: true, f: (r) => num(r.drinks, 0) },
      { k: "takings", label: "Takings", n: true, f: (r) => gbp(r.takings) }], d.by_hour);
    const catChart = barList(d.categories, { label: (r) => titleCase(r.category), value: (r) => r.takings, show: gbpShort,
      tip: (r) => `${titleCase(r.category)}: ${gbp(r.takings)} from ${num(r.qty, 0)} sold${r.gp_pct != null ? `, GP ${pct(r.gp_pct)}` : ""}` });
    const cats = tbl("ovCats", [
      { k: "category", label: "Square category", f: (r) => esc(titleCase(r.category)) },
      { k: "qty", label: "Sold", n: true, f: (r) => num(r.qty, 0) },
      { k: "takings", label: "Takings", n: true, f: (r) => gbp(r.takings) },
      { k: "gp_pct", label: "GP", n: true, f: (r) => gpCell(r.gp_pct) },
    ], d.categories);
    const lossChart = d.losses.length ? barList(d.losses, { label: (r) => lossName(r.reason), value: (r) => r.cost, show: gbpShort,
      tip: (r) => `${lossName(r.reason)}: ${gbp(r.cost)} over ${r.entries} entr${r.entries === 1 ? "y" : "ies"}` }) : `<p class="empty">No losses logged. Nice.</p>`;
    const top = tbl("ovSold", COLS.sold.filter((c) => ["item", "qty", "takings", "gp_pct"].includes(c.k)), d.items, { limit: 8, empty: "No sales in this period." });
    const low = tbl("ovReorder", COLS.reorder.filter((c) => ["label", "units", "nights_left", "order"].includes(c.k)), d.reorder, { limit: 8, empty: "Nothing running low." });
    return `${card(multi ? `${icon("chart")} Takings by night` : `${icon("chart")} Takings through the night`, "", time + asTable(timeTable), "wide")}
      <div class="grid2">${card(`${icon("tag")} Takings by category`, "", catChart + asTable(cats))}
      ${card(`${icon("loss")} Losses`, "losses", lossChart)}
      ${card(`${icon("drinks")} Best sellers`, "sold", top)}${card(`${icon("order")} Running low`, "reorder", low)}
      ${d.price_changes.length ? card(`${icon("tag")} Price changes (${d.price_changes.length})`, "", priceChanges("ovPrices", d.price_changes, { limit: 6 })) : ""}
      ${card(`${icon("stock")} Not moving (no use in 4 weeks)`, "", tbl("ovIdle", [
        { k: "label", label: "Product" }, { k: "units", label: "In stock", n: true, f: (r) => units(r.units, r.unit_label) },
        { k: "value", label: "Tied up", n: true, f: (r) => gbp(r.value) }], d.idle, { limit: 6, empty: "Everything is moving." }))}</div>`;
  },
  async sold(d) {
    return `<div class="card"><h2>Drinks sold</h2><p class="hint">Per Square button. Takings include VAT; GP is after 20% VAT and needs cost prices on every ingredient.</p>
      ${tbl("sold", COLS.sold, d.items, { search: "Search drinks…", csv: true, sort: ["takings", -1], empty: "No sales in this period." })}</div>`;
  },
  async used(d) {
    return `<div class="card"><h2>Stock used</h2><p class="hint">What came off stock, by product. Lost covers wastage, comps, staff drinks, training and overpours.</p>
      ${tbl("used", COLS.used, d.usage, { search: "Search products…", csv: true, empty: "No stock used in this period." })}</div>`;
  },
  async stock() {
    const lines = base.stock;
    const cols = [
      { k: "label", label: "Product", f: (r) => `${esc(r.label)}<span class="sub">${esc(r.category)}${r.subcategory ? " · " + esc(r.subcategory) : ""}</span>` },
      { k: "units", label: "In stock", n: true, f: (r) => `<span class="${r.negative ? "neg" : r.below_par ? "low" : ""}">${units(r.units, r.unit_label)}</span>` },
      { k: "status", label: "", nosort: true, f: (r) => (r.negative ? `<span class="pill bad">below zero</span>` : r.below_par ? `<span class="pill warn">below par</span>` : "") },
      { k: "bar", label: "Bar count", n: true, v: (r) => r.counted.Bar, f: (r) => num(r.counted.Bar, 2) },
      { k: "cellar", label: "Cellar count", n: true, v: (r) => r.counted.Cellar, f: (r) => num(r.counted.Cellar, 2) },
      { k: "par", label: "Par", n: true, f: (r) => (r.par == null ? "-" : num(r.par, 1)) },
    ];
    if (isMgr()) cols.push({ k: "value", label: "Value", n: true, f: (r) => gbp(r.value) });
    const value = lines.reduce((s, l) => s + (l.value || 0), 0);
    return `<div class="card"><h2>Stock levels</h2><p class="hint">${lines.length} products${isMgr() ? ` · ${gbp(value)} at cost` : ""}. In stock is the overall figure after sales; Bar and Cellar are from the last stocktake.</p>
      ${tbl("stock", cols, lines, { search: "Search stock…", csv: true, extra: (r) => r.category + " " + r.subcategory })}</div>`;
  },
  async reorder(d) {
    return `<div class="card"><h2>To order</h2><p class="hint">Below par, or likely to run out within three nights at the last four weeks' pace. Order brings it back up to par.</p>
      ${tbl("reorder", COLS.reorder, d.reorder, { search: "Search…", csv: true, empty: "Nothing running low." })}</div>`;
  },
  async losses(d) {
    const { comps } = await get("/api/venue/comps");
    const sortComps = comps.length && isAdmin() ? `<div class="card"><h2>Comps that need a reason (${comps.length})</h2><p class="hint">Square's export did not say why these were given away.</p>
      ${tbl("comps", [
        { k: "ts", label: "When", f: (r) => esc(when(r.ts)) }, { k: "item_name", label: "Item" }, { k: "qty", label: "Qty", n: true },
        { k: "why", label: "Reason", nosort: true, f: (r) => `<select data-comp="${r.id}"><option value="">Choose…</option><option value="wastage">Wastage</option><option value="overpour">Overpour</option><option value="training">Training</option><option value="staff">Staff drink</option>${base.reasons.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join("")}</select>` },
      ], comps)}</div>` : "";
    return `${sortComps}<div class="grid2"><div class="card"><h2>By reason</h2>${tbl("lossR", [
        { k: "reason", label: "Reason", f: (r) => esc(lossName(r.reason)) },
        { k: "entries", label: "Times", n: true }, { k: "ml", label: "Amount", n: true, f: (r) => vol(r.ml) },
        { k: "cost", label: "Cost", n: true, f: (r) => gbp(r.cost) }], d.losses, { empty: "No losses logged." })}</div>
      <div class="card"><h2>By product</h2>${tbl("lossP", [
        { k: "label", label: "Product" }, { k: "lost_ml", label: "Lost", n: true, f: (r) => vol(r.lost_ml, r.measure) },
        { k: "lost_cost", label: "Cost", n: true, f: (r) => gbp(r.lost_cost) }], d.usage.filter((u) => u.lost_ml > 0), { sort: ["lost_cost", -1], limit: 10, empty: "No losses logged." })}</div></div>
      <div class="card"><h2>Every entry</h2>${tbl("lossAll", [
        { k: "ts", label: "When", f: (r) => esc(when(r.ts)) }, { k: "reason", label: "Reason", f: (r) => esc(lossName(r.reason)) },
        { k: "label", label: "Product" }, { k: "ml", label: "Amount", n: true, f: (r) => vol(r.ml, r.measure) },
        { k: "cost", label: "Cost", n: true, f: (r) => gbp(r.cost) }, { k: "note", label: "Note", f: (r) => esc([r.note, r.user].filter(Boolean).join(" · ")) },
      ], d.loss_lines, { search: "Search…", csv: true, limit: 25, empty: "No losses logged." })}</div>`;
  },
  async variance() {
    const { lines } = await get("/api/venue/reports/variance");
    return `<div class="card"><h2>Stocktake check</h2><p class="hint">Between each product's last two stocktakes: what should be there (opening + deliveries − everything sold or logged) against what was counted. A minus is stock nobody can account for.</p>
      ${tbl("variance", [
        { k: "label", label: "Product" },
        { k: "opening_units", label: "Opening", n: true, f: (r) => num(r.opening_units, 2) },
        { k: "expected_units", label: "Expected", n: true, f: (r) => num(r.expected_units, 2) },
        { k: "closing_units", label: "Counted", n: true, f: (r) => `${num(r.closing_units, 2)}<span class="sub">bar ${num(r.closing_bar, 2)} · cellar ${num(r.closing_cellar, 2)}</span>` },
        { k: "variance_units", label: "Difference", n: true, f: (r) => `<span class="${r.variance_units < -0.05 ? "neg" : r.variance_units > 0.05 ? "low" : ""}">${r.variance_units > 0 ? "+" : ""}${num(r.variance_units, 2)}</span><span class="sub">${vol(r.variance_ml)}</span>` },
        { k: "variance_value", label: "£", n: true, f: (r) => gbp(r.variance_value) },
      ], lines, { search: "Search…", csv: true, sort: ["variance_value", 1], empty: "Needs two stocktakes first." })}</div>`;
  },
  async gp() {
    const { prices } = await get("/api/venue/prices");
    const linked = prices.filter((p) => p.product);
    return `<div class="card"><h2>Prices & GP</h2><p class="hint">Square selling prices (with VAT) against what each serve costs. Low GP is highlighted; a manager can fix costs and links in Settings.</p>
      ${tbl("gp", [
        { k: "item", label: "Square item", f: (r) => `${esc(r.item)}${r.variation ? ` <span class="hint">${esc(r.variation)}</span>` : ""}<span class="sub">${esc(r.category)}</span>` },
        { k: "price", label: "Sells at", n: true, f: (r) => gbp(r.price) },
        { k: "cost", label: "Costs", n: true, f: (r) => gbp(r.cost) },
        { k: "gp_pct", label: "GP", n: true, f: (r) => gpCell(r.gp_pct) },
        { k: "product", label: "Comes off", f: (r) => `${esc(r.product)}${r.ml ? ` <span class="hint">${vol(r.ml)}</span>` : ""}` },
      ], linked, { search: "Search…", csv: true, sort: ["gp_pct", 1], empty: "An admin can upload the Square catalogue in Settings &gt; Prices." })}</div>`;
  },
};

// ── Jobs opened from the front page ──────────────────────────────────────────

const backBtn = `<button class="btn ghost small back" id="back">${icon("back", 16)} Back</button>`;

const TASKS = {
  async count() {
    const { drafts } = await api("/api/venue/count");
    const mine = Object.fromEntries(drafts.filter((d) => d.location === loc).map((d) => [d.product_id, d.units]));
    const done = LOCS.map((l) => `${l} ${drafts.filter((d) => d.location === l).length}/${base.stock.length}`).join(" · ");
    let cat = "", rowsHtml = "";
    for (const l of base.stock) {
      if (l.category !== cat) { cat = l.category; rowsHtml += `<tr class="cat" data-cat><td colspan="3">${esc(cat)}</td></tr>`; }
      rowsHtml += `<tr data-q="${esc((l.label + " " + l.category).toLowerCase())}"><td>${esc(l.label)}</td><td class="n">${num(l.counted[loc], 2)}</td>
        <td class="n"><input class="num" data-count="${l.product_id}" value="${mine[l.product_id] ?? ""}" inputmode="decimal" aria-label="Counted"></td></tr>`;
    }
    const excel = isAdmin() ? `<div class="card"><h2>Or fill it in from an Excel stocktake</h2><p class="hint">Replaces anything typed so far. Stock only changes when you press Finish.</p>
      <div class="row"><label>Stocktake .xlsx<input id="countFile" type="file" accept=".xlsx"></label><button class="btn ghost" id="countXls">Fill in the count</button></div>
      ${sheet ? `<p>${sheet.matched} rows filled in from sheet ${esc(sheet.sheet)}${sheet.blank ? `, ${sheet.blank} blank counts read as 0` : ""}.</p>
      ${sheet.added.length ? `<p>Added as new products: ${sheet.added.map(esc).join(", ")}.</p>` : ""}
      ${sheet.resized.length ? `<p>Bottle size taken from the sheet: ${sheet.resized.map(esc).join(", ")}.</p>` : ""}
      ${sheet.unmatched.length ? `<h3>Enter these by hand (${sheet.unmatched.length})</h3><div class="scroll"><table><thead><tr><th>Location</th><th>Item</th><th>Unit</th><th class="n">Units</th><th>Why</th></tr></thead><tbody>
      ${sheet.unmatched.map((u) => `<tr><td>${esc(u.location)}</td><td>${esc(u.name)}${u.variant ? `, ${esc(u.variant)}` : ""}</td><td>${esc(u.unit)}</td><td class="n">${esc(u.units)}</td><td>${esc(u.why)}</td></tr>`).join("")}</tbody></table></div>
      ${sheet.unmatched.some((u) => u.why === "No matching product") ? `<p class="hint">Check none of these is a product you already have under another name. Otherwise add them all as new products.</p><div class="row"><button class="btn ghost" id="countNew">Add as new products</button></div>` : ""}` : ""}` : ""}</div>` : "";
    return `${backBtn}<div class="card"><h2>Stocktake</h2>
      <p class="hint">Count what is on the shelf, using tenths for open bottles (0.7). Each figure saves as you type, so Bar and Cellar can be counted by two people at once. Counted so far: ${done}.</p>
      <div class="seg">${LOCS.map((l) => `<button data-loc="${l}" class="${l === loc ? "on" : ""}">${l}</button>`).join("")}</div>
      <div class="tools"><input id="countFilter" placeholder="Find a product…" aria-label="Find"></div>
      <div class="scroll"><table><thead><tr><th>Product</th><th class="n">Last count</th><th class="n">Now</th></tr></thead><tbody id="countBody">${rowsHtml}</tbody></table></div>
      <div class="foot"><label style="max-width:260px">Counted at (leave blank for now)<input id="countAt" type="datetime-local" value="${esc(countAt)}"></label><span class="sp"></span><button class="btn" id="saveCount">Finish stocktake</button></div></div>${excel}`;
  },
  async waste() {
    const reasons = [["wastage", "Wastage"], ["overpour", "Overpour"], ["training", "Training"], ["staff", "Staff drink"],
      ...base.reasons.map((r) => [r, r])];
    const unitP = productByLabel.get(waste.product || "");
    const word = unitP ? unitWord(unitP.unit_label, 2) : "bottles";
    return `${backBtn}<div class="card" style="max-width:860px"><h2>Log wastage, overpour, training or a staff drink</h2>
      <p class="hint">For anything not rung through Square. Comps on Square come in with the sales upload.</p>
      <h3>Why?</h3>
      <div class="chips">${reasons.map(([k, l]) => `<button class="chip ${waste.reason === k ? "on" : ""}" data-wr="${esc(k)}">${esc(l)}</button>`).join("")}
        <button class="chip ${waste.reason === "__other" ? "on" : ""}" data-wr="__other">+ Other reason…</button></div>
      ${waste.reason === "__other" ? `<div class="row"><label style="max-width:360px">Your reason (it is remembered for next time)<input id="wOther" value="${esc(waste.other)}" maxlength="40" placeholder="e.g. Breakage, Tasting, Event"></label></div>` : ""}
      <h3>What?</h3>
      <div class="row"><label>Product<input id="wP" list="productList" value="${esc(waste.product)}" placeholder="Start typing a product…" autocomplete="off"></label></div>
      <h3>How much?</h3>
      <div class="seg">${[["ml", "Millilitres"], ["units", word[0].toUpperCase() + word.slice(1)]].map(([k, l]) =>
        `<button data-wunit="${k}" class="${waste.unit === k ? "on" : ""}">${esc(l)}</button>`).join("")}</div>
      <div class="row"><label style="flex:0 1 180px">${waste.unit === "ml" ? "Amount (ml)" : `Number of ${esc(word)}`}<input id="wM" inputmode="decimal" value="${esc(waste.amount)}"></label>
        <div class="chips">${waste.unit === "ml" ? [25, 50, 125, 175, 250, 568].map((m) => `<button class="chip" data-wml="${m}">${m === 568 ? "pint" : m + " ml"}</button>`).join("")
          : [0.5, 1, 2, 6].map((m) => `<button class="chip" data-wml="${m}">${m}</button>`).join("")}</div></div>
      <div class="row"><label>Note (optional)<input id="wN" value="${esc(waste.note)}" placeholder="e.g. dropped bottle, out of date"></label></div>
      <div class="foot"><span class="sp"></span><button class="btn" id="wGo">Log it</button></div></div>`;
  },
  async batch() {
    const { recipes } = await get("/api/venue/recipes");
    const batches = recipes.filter((r) => r.batch_product_id && r.active);
    const r = batches.find((x) => String(x.id) === String(batchState.id)) || batches[0];
    const runs = Number(batchState.runs) || 0;
    const manage = isAdmin() ? `<div class="row"><button class="btn ghost small" data-newbatch>+ New batch recipe</button>
      ${r ? `<button class="btn ghost small" data-editbatch="${r.id}">Change this recipe</button>` : ""}</div>` : "";
    if (!r) return `${backBtn}<div class="card" style="max-width:860px"><h2>Make a batch</h2><p>No batch recipes yet.${isAdmin() ? "" : " An admin can add one."}</p>${manage}</div>`;
    const made = batchState.made !== "" ? Number(batchState.made) : r.yield_ml * runs;
    return `${backBtn}<div class="card" style="max-width:860px"><h2>Make a batch</h2>
      <p class="hint">Record a batch once it is made: its ingredients come off stock and the batch goes into stock, ready to sell.</p>
      <div class="row"><label>Which batch?<select id="bR">${batches.map((x) => `<option value="${x.id}" ${x.id === r.id ? "selected" : ""}>${esc(x.name)} (one batch makes ${vol(x.yield_ml)})</option>`).join("")}</select></label>
        <label style="flex:0 1 160px">How many batches<input id="bN" value="${esc(batchState.runs)}" inputmode="decimal"></label>
        <label style="flex:0 1 220px">Amount actually made (ml)<input id="bMade" value="${esc(batchState.made)}" inputmode="decimal" placeholder="${num(r.yield_ml * runs, 0)} as per recipe"></label></div>
      <h3>This will take off stock</h3>
      <div class="scroll"><table><thead><tr><th>Ingredient</th><th class="n">Amount</th></tr></thead><tbody>
        ${r.lines.map((l) => `<tr><td>${esc(l.label)}</td><td class="n">${vol(l.ml * runs)}</td></tr>`).join("")}
        <tr class="cat"><td>Adds to stock: ${esc(r.name)}</td><td class="n">${vol(made)}</td></tr></tbody></table></div>
      ${r.note ? `<p class="hint" style="margin-top:10px">Method: ${esc(r.note)}</p>` : ""}
      <div class="foot">${manage}<span class="sp"></span><button class="btn" id="bGo">Record ${runs === 1 ? "batch" : `${num(runs, 1)} batches`}</button></div></div>`;
  },
};

let waste = { reason: "wastage", other: "", product: "", unit: "ml", amount: "", note: "" };
let batchState = { id: null, runs: "1", made: "" };

// ── Settings mode ────────────────────────────────────────────────────────────

const SECTIONS = [
  ["drinks", "Drinks & specials", "drinks"], ["square", "Square buttons", "link"], ["products", "Products", "stock"],
  ["deliveries", "Deliveries", "truck"], ["prices", "Prices", "tag"], ["imports", "Sales uploads", "upload"],
  ["branding", "Look & feel", "palette"], ["people", "People", "people"],
];

async function settingsView() {
  const side = SECTIONS.map(([k, l, ic]) =>
    `<button data-set="${k}" class="${setTab === k ? "on" : ""}">${icon(ic, 17)}<span>${l}</span>${k === "square" && base.unmapped ? `<span class="n">${base.unmapped}</span>` : ""}</button>`).join("");
  return `<div class="settings"><nav class="side">${side}</nav><div>${await SETTINGS[setTab]()}</div></div>`;
}

/** Square's catalogue price wins, so a price change in Square flows through; the typed price is the fallback. */
const sellPrice = (r) => r.square_price ?? r.menu_price ?? null;
const drinkGp = (r) => { const p = sellPrice(r); return r.cost != null && p ? (p / 1.2 - r.cost) / (p / 1.2) * 100 : null; };

const KINDS = [["drink", "Drink"], ["special", "Special"], ["batch", "Batch (pre-mix)"]];
const kindOf = (r) => (r.batch_product_id ? "batch" : r.special ? "special" : "drink");
let drinkFilter = "active";

function recipeCost(lines) {
  let total = 0;
  const missing = [];
  for (const l of lines) {
    const p = productById.get(Number(l.product_id));
    if (!p || !l.ml) continue;
    if (p.unit_cost == null) { missing.push(p.label); continue; }
    total += Number(l.ml) * p.unit_cost / p.unit_ml;
  }
  return { total, missing };
}

function priceChanges(id, rows, o = {}) {
  return tbl(id, [
    { k: "ts", label: "When", f: (r) => esc(day(r.ts)) },
    { k: "kind", label: "", f: (r) => (r.kind === "cost" ? `<span class="pill">we pay</span>` : `<span class="pill brand">we charge</span>`) },
    { k: "label", label: "Item" },
    { k: "old", label: "Was", n: true, f: (r) => gbp(r.old) },
    { k: "new", label: "Now", n: true, f: (r) => `<b>${gbp(r.new)}</b>` },
    { k: "change", label: "Change", n: true, v: (r) => (r.old ? (r.new - r.old) / r.old * 100 : null), f: (r) => {
      if (!r.old || r.new == null) return "";
      const c = (r.new - r.old) / r.old * 100, bad = r.kind === "cost" ? c > 0 : c < 0;
      return `<span class="${bad ? "down" : "up"}">${c > 0 ? "+" : ""}${num(c, 1)}%</span>`;
    } },
    { k: "source", label: "From", f: (r) => esc([r.source, r.user].filter(Boolean).join(" · ")) },
  ], rows, { search: o.search, csv: o.csv, limit: o.limit, empty: "No price changes yet." });
}

const STYLE_DEFAULT = { theme: "light", header: "light", banner: "brand", font: "modern", size: "m", corners: "soft", density: "comfy" };
const FONT_STACKS = {
  modern: { body: "'Segoe UI',system-ui,sans-serif", head: "'Segoe UI',system-ui,sans-serif" },
  elegant: { body: "'Segoe UI',system-ui,sans-serif", head: "Cambria,'Times New Roman',serif" },
  classic: { body: "Cambria,'Times New Roman',serif", head: "Cambria,'Times New Roman',serif" },
  times: { body: "'Times New Roman',Times,serif", head: "'Times New Roman',Times,serif" },
  soft: { body: "Calibri,Carlito,sans-serif", head: "Calibri,Carlito,sans-serif" },
};
const FONTS = [
  ["modern", "Modern", "Clean and plain"],
  ["elegant", "Elegant", "Serif headings, clear figures. Recommended"],
  ["classic", "Classic", "Serif throughout"],
  ["times", "Times New Roman", "Traditional; small text is harder to read"],
  ["soft", "Soft", "Rounded and friendly"],
];
// Ready-made looks. A colour of null keeps the venue's own (or its logo's).
const LOOKS = [
  { id: "classic", name: "Classic", note: "Light and clear", s: { theme: "light", header: "light", banner: "brand", font: "modern", corners: "soft", density: "comfy", color: "#1f6b5c" } },
  { id: "gold", name: "Black & gold", note: "Elegant, made for a gold logo", s: { theme: "light", header: "dark", banner: "dark", font: "elegant", corners: "soft", density: "comfy", color: "logo:#c9a227" } },
  { id: "midnight", name: "Midnight", note: "Dark all over, your colour", s: { theme: "dark", header: "dark", banner: "dark", font: "elegant", corners: "soft", density: "comfy", color: null } },
  { id: "fresh", name: "Fresh", note: "Bright, airy and rounded", s: { theme: "light", header: "light", banner: "plain", font: "modern", corners: "round", density: "comfy", color: "#1d4ed8" } },
  { id: "bold", name: "Bold", note: "Your colour across the top", s: { theme: "light", header: "brand", banner: "brand", font: "modern", corners: "sharp", density: "comfy", color: null } },
  { id: "compact", name: "Office", note: "Compact, more on screen", s: { theme: "light", header: "light", banner: "plain", font: "soft", corners: "sharp", density: "compact", color: "#334155" } },
];
function lookStyle(l) {
  const st = { ...l.s };
  if (st.color === null) st.color = brand.color || brand.logo_color || "#1f6b5c";
  else if (String(st.color).startsWith("logo:")) st.color = brand.logo_color || st.color.slice(5);
  return st;
}
/** A thumbnail of the app in a given look: header, banner and two figure tiles. */
function miniPreview(st) {
  const dark = st.theme === "dark", bg = dark ? "#0f1216" : "#eef0f3", card = dark ? "#1d2229" : "#fff";
  const head = st.header === "dark" ? "#0e1013" : st.header === "brand" ? st.color : card;
  const ban = st.banner === "dark" ? "#1b1f25" : st.banner === "plain" ? card : st.color;
  const r = st.corners === "sharp" ? 2 : st.corners === "round" ? 9 : 5;
  return `<span class="mini" style="background:${bg};border-radius:${r + 3}px"><span style="background:${head};height:12px;display:block"></span>
    <span style="display:block;margin:6px;height:20px;border-radius:${r}px;background:${ban};position:relative"><span style="position:absolute;right:5px;top:6px;width:18px;height:8px;border-radius:${Math.min(r, 3)}px;background:${st.banner === "brand" ? "#fff" : st.color}"></span></span>
    <span style="display:flex;gap:5px;margin:0 6px 6px"><span style="flex:1;height:18px;border-radius:${r}px;background:${card};border-left:3px solid ${st.color}"></span><span style="flex:1;height:18px;border-radius:${r}px;background:${card};border-left:3px solid ${st.color}"></span></span></span>`;
}

const SWATCHES = ["#c9a227", "#1f6b5c", "#0f766e", "#1d4ed8", "#4338ca", "#7c3aed", "#be185d", "#b91c1c", "#c2410c", "#a16207", "#334155"];

const SETTINGS = {
  async branding() {
    const color = brand.color || "#1f6b5c";
    const logo = brand.logo ? `/api/venue/branding/logo?v=${encodeURIComponent(brand.v)}` : "";
    const looks = LOOKS.map((l) => {
      const st = lookStyle(l);
      const on = Object.entries(st).every(([k, v]) => (k === "color" ? (brand.color || "#1f6b5c") === v : (brand[k] || STYLE_DEFAULT[k]) === v));
      return `<button class="look ${on ? "on" : ""}" data-look="${l.id}">${miniPreview(st)}<span class="look-name">${esc(l.name)}</span><span class="hint" style="margin:0">${esc(l.note)}</span></button>`;
    }).join("");
    const seg = (key, opts) => `<div class="seg">${opts.map(([v, l]) => `<button data-style="${key}:${v}" class="${(brand[key] || STYLE_DEFAULT[key]) === v ? "on" : ""}">${l}</button>`).join("")}</div>`;
    const row = (label, hint, control) => `<div class="tune"><div><b>${label}</b>${hint ? `<span class="hint" style="margin:0">${hint}</span>` : ""}</div><div>${control}</div></div>`;
    const fonts = FONTS.map(([k, name, note]) => `<button class="fontcard ${(brand.font || "modern") === k ? "on" : ""}" data-style="font:${k}">
      <span class="fc-sample" style="font-family:${FONT_STACKS[k].head}">Aa</span><span class="fc-name" style="font-family:${FONT_STACKS[k].body}">${name}</span>
      <span class="hint" style="margin:0;font-family:${FONT_STACKS[k].body}">${note}</span></button>`).join("");
    const swatches = [...(brand.logo_color ? [[brand.logo_color, "From your logo"]] : []), ...SWATCHES.map((c) => [c, c])];
    return `<div class="card" style="max-width:980px"><h2>${icon("palette")} Look & feel</h2>
      <p class="hint">Pick a ready-made look, then change anything you like underneath. Changes show straight away, for everyone using this computer's Bar Stock.</p>
      <h3>Ready-made looks</h3><div class="looks">${looks}</div>
      <h3 style="margin-top:26px">Fine-tune</h3>
      ${row("Mode", "Dark is easier on the eyes in a dim bar", seg("theme", [["light", "Light"], ["dark", "Dark"], ["auto", "Match this device"]]))}
      ${row("Main colour", "Buttons, charts and highlights", `<div class="swatches">${swatches.map(([c, l]) => `<button data-swatch="${c}" class="${c === color ? "on" : ""}" style="background:${c}" title="${esc(l)}" aria-label="${esc(l)}"></button>`).join("")}
        <input type="color" id="bColor" value="${esc(color)}" aria-label="Any colour" title="Any colour"></div>`)}
      ${row("Font", "", `<div class="fonts">${fonts}</div>`)}
      ${row("Text size", "", seg("size", [["s", "Smaller"], ["m", "Normal"], ["l", "Larger"]]))}
      ${row("Corners", "", seg("corners", [["sharp", "Square"], ["soft", "Soft"], ["round", "Round"]]))}
      ${row("Spacing", "Compact fits more on screen", seg("density", [["compact", "Compact"], ["comfy", "Roomy"]]))}
      ${row("Header", "The bar along the top", seg("header", [["light", "Light"], ["dark", "Dark"], ["brand", "Main colour"]]))}
      ${row("Upload banner", "The big box on the front page", seg("banner", [["brand", "Main colour"], ["dark", "Dark"], ["plain", "Plain"]]))}
      <div class="foot"><span class="sp"></span><button class="btn ghost" id="styleReset">${icon("reset", 16)} Back to the original look</button></div></div>

      <div class="card" style="max-width:980px"><h2>${icon("image")} Logo & name</h2>
      <p class="hint">Saved on this computer, in the app's data folder with the stock records, so they are never part of the code on GitHub, survive updates, and are included in backups.</p>
      <h3>Venue name</h3>
      <div class="row"><label style="max-width:420px">Shown in the header and browser tab<input id="bName" value="${esc(brand.name)}" maxlength="60" placeholder="Your venue name"></label><button class="btn ghost" id="bNameGo">Save name</button></div>
      <h3>Logo</h3>
      <div class="preview">${logo ? `<img src="${logo}" alt="Current logo">` : `<span class="hint" style="margin:0">No logo yet.</span>`}</div>
      <div class="row"><label style="max-width:420px">PNG, JPG or WebP, under 2 MB. Spare space around it is trimmed for you.<input id="bLogo" type="file" accept="image/png,image/jpeg,image/webp"></label>
        ${logo ? `<button class="btn danger" id="bLogoDel">Remove logo</button>` : ""}</div></div>`;
  },


  async drinks() {
    const recipes = await loadTargets();
    if (draft) return drinkEditor(recipes);
    const counts = { active: 0, special: 0, batch: 0, archived: 0 };
    for (const r of recipes) {
      if (!r.active) counts.archived++;
      else { counts.active++; if (r.special) counts.special++; if (r.batch_product_id) counts.batch++; }
    }
    const shown = recipes.filter((r) => drinkFilter === "archived" ? !r.active : r.active &&
      (drinkFilter === "active" || (drinkFilter === "special" ? r.special : r.batch_product_id)));
    const filters = [["active", "On the menu"], ["special", "Specials"], ["batch", "Batches"], ["archived", "Archived"]]
      .map(([k, l]) => `<button class="chip ${drinkFilter === k ? "on" : ""}" data-dfilter="${k}">${l} ${counts[k]}</button>`).join("");
    return `<div class="card"><h2>Drinks & specials</h2>
      <p class="hint">A drink is a recipe: what goes in it and how much. Link it to its Square button and every sale takes those ingredients off stock. Give it the same name as the Square button and it links itself.</p>
      <div class="row"><button class="btn" data-newdrink="drink">+ New drink</button><button class="btn ghost" data-newdrink="special">+ New special</button><button class="btn ghost" data-newdrink="batch">+ New batch</button></div>
      <div class="chips" style="margin:12px 0">${filters}</div>
      ${tbl("drinks", [
        { k: "name", label: "Name", f: (r) => `<button class="link" data-editdrink="${r.id}">${esc(r.name)}</button> ${r.special ? `<span class="pill brand">special</span>` : ""}${r.batch_product_id ? `<span class="pill">batch · ${vol(r.yield_ml)}</span>` : ""}<span class="sub">${r.lines.map((l) => `${num(l.ml, 1)}ml ${esc(l.label)}`).join(", ")}</span>` },
        { k: "cost", label: "Cost", n: true, f: (r) => gbp(r.cost) },
        { k: "price", label: "Price", n: true, v: sellPrice, f: (r) => (r.batch_product_id ? "" : `${gbp(sellPrice(r))}${r.square_price != null ? `<span class="sub">from Square</span>` : ""}`) },
        { k: "gp", label: "GP", n: true, v: drinkGp, f: (r) => (r.batch_product_id ? "" : gpCell(drinkGp(r))) },
        { k: "sq", label: "Square buttons", n: true, v: (r) => r.square_items.length, f: (r) => (r.square_items.length ? num(r.square_items.length, 0) : r.batch_product_id ? "" : `<span class="hint" title="Links itself to a Square button with exactly this name">by name</span>`) },
        { k: "act", label: "", nosort: true, f: (r) => `<button class="btn ghost small" data-editdrink="${r.id}">Edit</button>` },
      ], shown, { search: "Search drinks or ingredients…", extra: (r) => r.lines.map((l) => l.label).join(" "), empty: "None here yet." })}</div>`;
  },

  async square() {
    const m = await get("/api/venue/mappings");
    await loadTargets();
    const pickerRow = (item, i, current = "") => `<input list="targetList" data-mt="${i}" value="${esc(current)}" placeholder="Drink or product…" autocomplete="off" class="pick">`;
    window._unmapped = m.unmapped;
    window._mapped = m.mapped;
    const waiting = m.unmapped.length ? `<div class="card"><h2>Waiting to be linked (${m.unmapped.length})</h2>
      <p class="hint">Square sold these but the app does not know what stock they use. Pick a drink (recipe) or a single product. For a product, give the serve size, or leave it blank for a whole bottle or can. Waiting sales come off stock as soon as you save.</p>
      <div class="scroll"><table><thead><tr><th>Square item</th><th class="n">Sold</th><th>Takes stock from</th><th>ml per serve</th><th></th></tr></thead><tbody>
      ${m.unmapped.map((u, i) => `<tr><td>${esc(u.item_name)}</td><td class="n">${num(u.qty, 0)}</td><td>${pickerRow(u, i)}</td>
        <td><input class="num" data-mm="${i}" inputmode="decimal" placeholder="whole"></td>
        <td><div class="acts"><button class="btn small" data-map="${i}">Save</button> <button class="btn ghost small" data-newfrom="${i}">New drink</button> <button class="btn ghost small" data-nostock="${i}" title="Food, soda gun and anything else that uses no bar stock">No stock</button></div></td></tr>`).join("")}
      </tbody></table></div></div>` : `<div class="card"><h2>Square buttons</h2><p class="hint">Every Square item that has sold is linked to stock. New ones show up here after an upload.</p></div>`;
    const targetName = (x) => x.no_stock ? `<span class="hint">uses no stock</span>` : x.recipe ? `Drink: ${esc(x.recipe)}` : esc((productById.get(x.product_id) || {}).label || "?");
    const linked = tbl("mapped", [
      { k: "item_name", label: "Square item" },
      { k: "target", label: "Takes stock from", v: (x) => (x.no_stock ? "no stock" : x.recipe || (productById.get(x.product_id) || {}).label), f: (x) => x.item_key === editKey
        ? `<input list="targetList" id="reTarget" value="${esc(x.recipe ? "Drink: " + x.recipe : (productById.get(x.product_id) || {}).pick || "")}" class="pick" autocomplete="off">` : targetName(x) },
      { k: "ml", label: "Per serve", n: true, f: (x) => x.item_key === editKey ? `<input class="num" id="reMl" value="${x.ml ?? ""}" inputmode="decimal" placeholder="whole">` : x.ml ? vol(x.ml) : "" },
      { k: "qty", label: "Sold to date", n: true, f: (x) => num(x.qty || 0, 0) },
      { k: "act", label: "", nosort: true, f: (x) => x.item_key === editKey
        ? `<span class="acts"><button class="btn small" data-relink="${esc(x.item_key)}">Save</button> <button class="btn ghost small" data-recancel>Cancel</button></span>`
        : `<span class="acts"><button class="btn ghost small" data-reedit="${esc(x.item_key)}">Change</button> <button class="btn danger small" data-unlink="${esc(x.item_key)}">Unlink</button></span>` },
    ], m.mapped, { search: "Search Square items…", csv: true, empty: "Nothing linked yet." });
    return `${waiting}<div class="card"><h2>Linked (${m.mapped.length})</h2><p class="hint">Changing a link affects sales from now on. Past sales keep what they took off stock.</p>${linked}</div>`;
  },

  async products() {
    const { products } = await get("/api/venue/products/all");
    if (prodDraft) return productEditor();
    const showArchived = SETTINGS.products.archived;
    const list = products.filter((p) => (showArchived ? !p.active : p.active));
    return `<div class="card"><h2>Products</h2><p class="hint">Everything you stock and count. Set the cost per bottle, keg or can for GP, and a par (the level you want to keep) for the order list.</p>
      <div class="row"><button class="btn" id="newProduct">+ New product</button><span style="flex:1"></span>
      <label class="check"><input type="checkbox" id="showArchived" ${showArchived ? "checked" : ""}> Show archived (${products.filter((p) => !p.active).length})</label></div>
      ${tbl("products", [
        { k: "label", label: "Product", f: (p) => `<button class="link" data-editprod="${p.id}">${esc(p.label)}</button>${p.is_batch ? ` <span class="pill">batch</span>` : ""}<span class="sub">${esc(p.category)}${p.subcategory ? " · " + esc(p.subcategory) : ""}</span>` },
        { k: "unit_cost", label: "Cost each", n: true, f: (p) => p.is_batch ? `${gbp(p.unit_cost)}<span class="sub">from recipe</span>` : `<input class="num" data-cost="${p.id}" value="${p.unit_cost ?? ""}" inputmode="decimal" aria-label="Cost">` },
        { k: "par", label: "Par", n: true, f: (p) => `<input class="num" data-par="${p.id}" value="${p.par ?? ""}" inputmode="decimal" aria-label="Par">` },
        { k: "supplier", label: "Supplier" },
        { k: "in_recipes", label: "In drinks", n: true, f: (p) => (p.in_recipes ? num(p.in_recipes, 0) : "") },
        { k: "act", label: "", nosort: true, f: (p) => `<button class="btn ghost small" data-editprod="${p.id}">Edit</button>` },
      ], list, { search: "Search products…", csv: true, extra: (p) => p.category + " " + p.subcategory })}</div>`;
  },

  async deliveries() {
    const { deliveries } = await get("/api/venue/deliveries");
    const drafts = deliveries.filter((d) => d.status === "draft").map((d) => `<div class="card" data-del="${d.id}"><h2>Check delivery: ${esc(d.supplier || "no supplier")} ${esc(d.ref)}</h2>
      <p class="hint">Stock only changes when you approve. Match each line to a product; matches are remembered for this supplier.</p>
      <div class="scroll"><table><thead><tr><th>Invoice line</th><th>Product</th><th class="n">Units</th><th class="n">Cost each</th></tr></thead><tbody>
      ${d.lines.map((l, i) => `<tr data-line="${i}"><td><input class="dD" value="${esc(l.description)}"></td><td><input class="dP pick" list="productList" value="${esc((productById.get(Number(l.product_id)) || {}).pick || "")}" autocomplete="off"></td>
        <td class="n"><input class="num dU" value="${l.units ?? ""}" inputmode="decimal"></td><td class="n"><input class="num dC" value="${l.unit_cost ?? ""}" inputmode="decimal"></td></tr>`).join("")}</tbody></table></div>
      <div class="foot"><button class="btn ghost small" data-addline="${d.id}">+ Line</button><span class="sp"></span><button class="btn ghost" data-savedel="${d.id}">Save for later</button><button class="btn" data-approve="${d.id}">Approve into stock</button></div></div>`).join("");
    return `${drafts}<div class="card"><h2>New delivery</h2><p class="hint">Start a blank one, paste the invoice text, or use a photo if an AI key is set in venue.env. You always check it before stock changes.</p>
      <div class="row"><label>Supplier<input id="dSup"></label><label>Invoice ref<input id="dRef"></label><label style="flex:0 1 100px">Lines<input id="dN" value="5" inputmode="numeric"></label><button class="btn" id="dBlank">Start</button></div>
      <h3>From the invoice</h3><label>Invoice text<textarea id="dText" rows="4"></textarea></label><div class="row"><button class="btn ghost" id="dParse">Read text</button>
      <label>Or a photo<input id="dImg" type="file" accept="image/*"></label><button class="btn ghost" id="dPhoto">Read photo</button></div></div>
      <div class="card"><h2>Approved</h2>${tbl("delDone", [
        { k: "ts", label: "Date", f: (d) => esc(day(d.ts)) }, { k: "supplier", label: "Supplier" }, { k: "ref", label: "Ref" },
        { k: "lines", label: "Lines", n: true, v: (d) => d.lines.length },
        { k: "units", label: "Units", n: true, v: (d) => d.lines.reduce((s, l) => s + Number(l.units || 0), 0) },
        { k: "value", label: "Value", n: true, v: (d) => d.lines.reduce((s, l) => s + Number(l.units || 0) * Number(l.unit_cost || 0), 0), f: (d) => gbp(d.lines.reduce((s, l) => s + Number(l.units || 0) * Number(l.unit_cost || 0), 0)) },
      ], deliveries.filter((d) => d.status !== "draft"), { empty: "None yet." })}</div>`;
  },

  async prices() {
    const { prices } = await get("/api/venue/prices");
    const open = prices.filter((p) => !p.product);
    return `<div class="card"><h2>Selling prices</h2><p class="hint">From the Square catalogue export (Items &gt; Export library), with VAT. Re-upload whenever prices change; links you made by hand are kept. ${prices.length} prices loaded.</p>
      <div class="row"><label>Square catalogue CSV<input id="catFile" type="file" accept=".csv,text/csv"></label><button class="btn" id="catGo">Update prices</button></div>
      <p class="hint">What you pay changes in two ways: approving a delivery with a new cost, or typing a new cost in Products. Past sales keep the cost they had at the time, so old GP figures do not shift.</p></div>
      <div class="card"><h2>Price changes</h2>${priceChanges("priceHist", (await get("/api/venue/prices/history")).changes, { search: "Search…", csv: true, limit: 20 })}</div>
      <div class="card"><h2>Prices not linked to stock (${open.length})</h2><p class="hint">Link a single product and serve size so GP can be worked out. Drinks with recipes get their GP from Drinks & specials.</p>
      ${tbl("pricesOpen", [
        { k: "item", label: "Square item", f: (p) => `${esc(p.item)} <span class="hint">${esc(p.variation)}</span><span class="sub">${esc(p.category)}</span>` },
        { k: "price", label: "Price", n: true, f: (p) => gbp(p.price) },
        { k: "pick", label: "Product", nosort: true, f: (p) => `<input list="productList" data-pp="${esc(p.token)}" autocomplete="off" class="pick">` },
        { k: "ml", label: "ml", nosort: true, f: (p) => `<input class="num" data-pm="${esc(p.token)}" inputmode="decimal">` },
        { k: "act", label: "", nosort: true, f: (p) => `<button class="btn small" data-pmatch="${esc(p.token)}">Save</button>` },
      ], open, { search: "Search…", limit: 30, empty: "Every price is linked." })}</div>`;
  },

  async imports() {
    const { imports } = await get("/api/venue/imports");
    return `<div class="card"><h2>Sales uploads</h2><p class="hint">Undo removes an upload and puts its stock back, for example if the wrong night was uploaded.</p>
      ${base.square_api ? `<div class="row"><button class="btn ghost" id="syncGo">Sync from Square now</button></div>` : ""}
      ${tbl("imports", [
        { k: "ts", label: "Uploaded", f: (i) => esc(when(i.ts)) }, { k: "filename", label: "File", f: (i) => esc(i.filename || i.source) },
        { k: "user", label: "By" }, { k: "added", label: "New lines", n: true }, { k: "skipped", label: "Already in", n: true },
        { k: "act", label: "", nosort: true, f: (i) => (i.undone ? `<span class="pill">undone</span>` : `<button class="btn danger small" data-undo="${i.id}">Undo</button>`) },
      ], imports, { empty: "Nothing uploaded yet." })}</div>`;
  },

  async people() {
    const { users } = await api("/api/people");
    const job = (u, j, label) => u.role === "admin" ? "" : `<label class="check"><input type="checkbox" data-job="${esc(u.id)}:${j}" ${u.stock_jobs?.[j] ? "checked" : ""}> ${label}</label>`;
    return `<div class="card"><h2>${icon("people")} People</h2>
      <p class="hint"><b>Admin</b> changes everything. <b>Manager</b> sees every figure, including takings and GP. <b>Staff</b> see stock figures only.
      Everyone signed in can upload the night's Square sales. Tick the jobs below to let someone also do stocktakes, log wastage or record batches.</p>
      <div class="scroll"><table><thead><tr><th>Name</th><th>Role</th><th>Can also</th><th></th></tr></thead><tbody>
      ${users.map((u) => `<tr class="${u.active ? "" : "muted-row"}"><td><b>${esc(u.name)}</b><span class="sub">login: ${esc(u.login)}${u.active ? "" : " · switched off"}</span></td>
        <td><select data-role="${esc(u.id)}" style="max-width:150px">${["staff", "manager", "admin"].map((r) => `<option ${u.role === r ? "selected" : ""}>${r}</option>`).join("")}</select></td>
        <td>${u.role === "admin" ? `<span class="hint" style="margin:0">everything</span>` : `<div class="jobs">${job(u, "count", "Stocktakes")}${job(u, "waste", "Wastage")}${job(u, "batch", "Batches")}</div>`}</td>
        <td><div class="acts"><button class="btn ghost small" data-resetpin="${esc(u.id)}" data-name="${esc(u.name)}">Change PIN</button>
          ${u.id === me.id ? "" : `<button class="btn ghost small" data-active="${esc(u.id)}:${u.active ? 0 : 1}">${u.active ? "Switch off" : "Switch on"}</button>
          <button class="btn danger small" data-deluser="${esc(u.id)}" data-name="${esc(u.name)}">Remove</button>`}</div></td></tr>`).join("")}
      </tbody></table></div>
      <p class="hint" style="margin-top:12px">PINs are stored scrambled (hashed), so nobody can look one up, not even an admin. If someone forgets theirs, use Change PIN and tell them the new one.</p>
      <h3>Add someone</h3><div class="row"><label>Name<input id="pName"></label><label style="flex:0 1 160px">Role<select id="pRole"><option>staff</option><option>manager</option><option>admin</option></select></label>
      <label style="flex:0 1 160px">6-digit PIN<input id="pPin" inputmode="numeric" maxlength="6" autocomplete="off"></label><button class="btn" id="personGo">${icon("plus", 16)} Add</button></div></div>`;
  },
};

// ── Drink editor ─────────────────────────────────────────────────────────────

const ML_CHIPS = [25, 50, 125, 175, 250];

function newDraft(kind, name = "", square = []) {
  return { id: null, kind, name, price: "", yield: kind === "batch" ? "1000" : "", note: "", lines: [{ product_id: "", ml: "" }, { product_id: "", ml: "" }], square, original: [] };
}

function draftFrom(r) {
  return {
    id: r.id, kind: kindOf(r), name: r.name, price: r.menu_price ?? "", squarePrice: r.square_price, yield: r.yield_ml ?? "", note: r.note || "", active: r.active,
    lines: r.lines.map((l) => ({ product_id: l.product_id, ml: l.ml })), square: r.square_items.map((s) => ({ ...s })), original: r.square_items.map((s) => s.item_key),
  };
}

async function squareChoices() {
  const m = await get("/api/venue/mappings");
  const { prices } = await get("/api/venue/prices");
  squareByLabel.clear();
  for (const u of m.unmapped) squareByLabel.set(`${u.item_name} (waiting)`, { item_key: u.item_key, item_name: u.item_name });
  for (const p of prices) {
    const name = p.item + (p.variation && p.variation.toLowerCase() !== "regular" ? ` - ${p.variation}` : "");
    const key = itemKey(p.item, p.variation);
    if (![...squareByLabel.values()].some((x) => x.item_key === key)) squareByLabel.set(name, { item_key: key, item_name: name });
  }
  for (const x of m.mapped) if (![...squareByLabel.values()].some((y) => y.item_key === x.item_key)) squareByLabel.set(x.item_name, { item_key: x.item_key, item_name: x.item_name });
  $("squareList").innerHTML = [...squareByLabel.keys()].map((k) => `<option value="${esc(k)}"></option>`).join("");
  return m;
}

async function drinkEditor() {
  const m = await squareChoices();
  const d = draft, batch = d.kind === "batch";
  const { total, missing } = recipeCost(d.lines);
  const price = d.squarePrice ?? (d.price === "" ? null : Number(d.price));
  const exVat = price / 1.2;
  const gp = !batch && price && !missing.length && total ? (exVat - total) / exVat * 100 : null;
  const elsewhere = (key) => { const x = m.mapped.find((y) => y.item_key === key && y.recipe_id !== d.id); return x ? ` <span class="hint">(moves from ${esc(x.recipe || "a product")})</span>` : ""; };
  const lines = d.lines.map((l, i) => {
    const p = productById.get(Number(l.product_id));
    return `<div class="line"><input list="productList" data-lp="${i}" value="${esc(p ? p.pick : "")}" placeholder="Ingredient…" autocomplete="off" aria-label="Ingredient">
      <input data-lm="${i}" value="${esc(l.ml)}" inputmode="decimal" placeholder="ml" aria-label="ml">
      <div class="ml-chips">${ML_CHIPS.map((c) => `<button data-chip="${i}:${c}">${c}</button>`).join("")}</div>
      <button class="x" data-rmline="${i}" aria-label="Remove">×</button></div>`;
  }).join("");
  return `${`<button class="btn ghost small back" id="closeDrink">${icon("back", 16)} All drinks</button>`}<div class="card">
    <h2>${d.id ? `Edit ${esc(d.name)}` : `New ${KINDS.find((k) => k[0] === d.kind)[1].toLowerCase()}`}${d.id && !d.active ? ` <span class="pill">archived</span>` : ""}</h2>
    <div class="seg">${KINDS.map(([k, l]) => `<button data-kind="${k}" class="${d.kind === k ? "on" : ""}" ${d.id && (k === "batch") !== batch ? "disabled" : ""}>${l}</button>`).join("")}</div>
    <p class="hint">${batch ? "A batch is made ahead (such as a pre-mix). Making one takes these ingredients off stock and adds the batch as its own product, which drinks can then use." : d.kind === "special" ? "Specials show up under their own filter, so they are easy to archive when they come off." : "Each sale of this drink takes these amounts off stock."}</p>
    <div class="row"><label>Name<input data-df="name" value="${esc(d.name)}" placeholder="${batch ? "e.g. Margarita Mix" : "e.g. Espresso Martini"}"></label>
      ${batch ? `<label style="flex:0 1 200px">One batch makes (ml)<input data-df="yield" value="${esc(d.yield)}" inputmode="decimal"></label>`
        : d.squarePrice != null ? `<label style="flex:0 1 240px">Price (from the Square catalogue)<input value="${gbp(d.squarePrice)}" disabled></label>`
        : `<label style="flex:0 1 220px">Menu price £ (with VAT)<input data-df="price" value="${esc(d.price)}" inputmode="decimal" placeholder="until Square has it"></label>`}</div>
    <h3>${batch ? "Ingredients for one batch" : "Ingredients per drink"}</h3>
    <div class="lines">${lines}</div><button class="btn ghost small" id="addLine">+ Add ingredient</button>
    <div class="summary"><div>Cost${batch ? " per batch" : ""}<b>${missing.length ? "-" : gbp(total)}</b></div>
      ${batch ? `<div>Cost per litre<b>${missing.length || !d.yield ? "-" : gbp(total / Number(d.yield) * 1000)}</b></div>` : `<div>Sells for${d.squarePrice != null ? " (Square)" : ""}<b>${price ? gbp(price) : "-"}</b></div><div>Gross profit<b>${gp == null ? "-" : pct(gp)}</b></div>`}
      ${missing.length ? `<div style="flex-basis:100%">No cost price yet for ${missing.map(esc).join(", ")}. Add it under Products to see GP.</div>` : ""}</div>
    <div class="row"><label>Method / notes (optional)<input data-df="note" value="${esc(d.note)}" placeholder="e.g. shake, double strain, top with prosecco"></label></div>
    ${batch ? "" : `<h3>Square buttons that sell it</h3><p class="hint">Sales of these buttons take this drink's ingredients off stock. A button with exactly the same name as the drink links itself, so a new special needs nothing here.</p>
      <div class="tags">${d.square.map((s, i) => `<span class="tag">${esc(s.item_name)}${elsewhere(s.item_key)}<button data-rmsq="${i}" aria-label="Remove">×</button></span>`).join("") || `<span class="hint">None yet.</span>`}</div>
      <div class="row"><label>Add a Square button<input id="sqAdd" list="squareList" placeholder="Type to search, or type a new button's exact name" autocomplete="off"></label><button class="btn ghost" id="sqAddGo">Add</button></div>`}
    <div class="foot">${d.id ? `<button class="btn ghost" id="dupDrink">Duplicate</button><button class="btn ghost" id="archDrink">${d.active ? "Archive" : "Put back on the menu"}</button><button class="btn danger" id="delDrink">Delete</button>` : ""}
      <span class="sp"></span><button class="btn ghost" id="closeDrink2">Cancel</button><button class="btn" id="saveDrink">Save</button></div></div>`;
}

async function saveDrink() {
  const d = draft;
  const lines = d.lines.filter((l) => l.product_id || l.ml);
  if (lines.some((l) => !l.product_id)) throw new Error("Pick each ingredient from the list");
  if (lines.some((l) => !(Number(l.ml) > 0))) throw new Error("Give an amount for each ingredient");
  const batch = d.kind === "batch";
  const r = await api("/api/venue/recipes", { json: {
    id: d.id, name: d.name, lines, note: d.note, special: d.kind === "special",
    menu_price: batch ? null : d.price || null, yield_ml: batch ? d.yield || null : null, square_items: batch ? [] : d.square,
  } });
  const keep = new Set(d.square.map((s) => s.item_key));
  for (const key of d.original) if (!keep.has(key)) await api("/api/venue/mappings/delete", { json: { item_key: key } });
  toast(`${d.name} saved`);
  draft = null;
  return r;
}

// ── Product editor ───────────────────────────────────────────────────────────

function productEditor() {
  const p = prodDraft;
  const f = (k, label, extra = "") => `<label>${label}<input data-pf="${k}" value="${esc(p[k] ?? "")}" ${extra}></label>`;
  return `<button class="btn ghost small back" id="closeProd">${icon("back", 16)} All products</button><div class="card">
    <h2>${p.id ? `Edit ${esc(p.name)}` : "New product"}${p.id && !p.active ? ` <span class="pill">archived</span>` : ""}</h2>
    <div class="row">${f("name", "Name", 'placeholder="e.g. House Vodka"')}${f("variant", "Variant (optional)", 'placeholder="e.g. Citron"')}</div>
    <div class="row">${f("unit_label", "Size", 'placeholder="70cl bottle, 50L keg, 330ml can"')}${f("unit_cost", "Cost each £ (ex VAT)", 'inputmode="decimal"')}${f("par", "Par (units to keep)", 'inputmode="decimal"')}</div>
    <div class="row">${f("category", "Category", 'list="catList"')}${f("subcategory", "Type", 'list="subcatList"')}${f("supplier", "Supplier")}</div>
    ${p.id ? `<p class="hint">The size cannot change once a product has been counted or sold, because its stock is held in that size. For a new size, add a new product and archive this one.</p>` : ""}
    <div class="foot">${p.id ? `<button class="btn ghost" id="archProd">${p.active ? "Archive" : "Restore"}</button>` : ""}<span class="sp"></span>
      <button class="btn ghost" id="closeProd2">Cancel</button><button class="btn" id="saveProd">Save</button></div></div>`;
}

// ── Uploading the night's sales ──────────────────────────────────────────────

let pendingFile = null;
async function uploadSales(file, saleDate = "") {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("sale_date", saleDate);
  $("uploadBtn").disabled = true;
  $("uploadBtn").textContent = "Uploading…";
  try {
    const r = await api("/api/venue/import/square", { method: "POST", body: fd });
    pendingFile = null;
    const span = r.first_day ? (r.first_day === r.last_day ? day(r.first_day) : `${day(r.first_day)} to ${day(r.last_day)}`) : "";
    const parts = [`${span ? span + ": " : ""}${num(r.drinks, 0)} drinks${isMgr() ? `, ${gbp(r.takings)}` : ""}`];
    if (r.skipped) parts.push(`${r.skipped} lines were already uploaded and skipped`);
    if (r.unmapped) parts.push(`${r.unmapped} sales are waiting for their Square item to be linked`);
    if (!r.added && r.skipped) parts[0] = "This file was already uploaded, so nothing changed";
    lastResult = { html: esc(parts.join(". ")) + ".", warn: !!r.unmapped || !r.added };
    if (r.first_day) period = r.first_day === r.last_day ? { kind: "last" } : { kind: "custom", from: r.first_day, to: r.last_day };
    report = "overview";
    await reload();
  } catch (e) {
    if (/summary export/i.test(e.message)) {
      pendingFile = file;
      $("needDate").classList.remove("hidden");
      $("csvDate").value = addDays(tradingToday(), -0);
      $("csvDate").focus();
    } else {
      lastResult = { html: esc(e.message), warn: true };
      await render();
    }
  } finally {
    if ($("uploadBtn")) { $("uploadBtn").disabled = false; $("uploadBtn").innerHTML = `${icon("upload", 20)} Upload Square sales`; }
  }
}

// ── Events ───────────────────────────────────────────────────────────────────

const CLICK = {
  settingsBtn: async () => { mode = mode === "settings" ? "view" : "settings"; task = null; draft = null; prodDraft = null; await reload(); },
  back: async () => { task = null; await reload(); },
  uploadBtn: async () => $("csvPick").click(),
  csvRetry: async () => {
    if (!pendingFile) throw new Error("Choose the file again");
    if (!$("csvDate").value) throw new Error("Choose the night");
    await uploadSales(pendingFile, $("csvDate").value);
  },
  pGo: async () => {
    period = { kind: "custom", from: $("pFrom").value, to: $("pTo").value };
    cache = {};
    await render();
  },
  saveCount: async () => {
    const { one_sided: partial } = await api("/api/venue/count");
    const warn = partial.length ? `\n\nCounted in one place only (the other keeps its last figure):\n${partial.slice(0, 15).join("\n")}` : "";
    const ts = $("countAt").value;
    if (!confirm(`Finish this stocktake${ts ? ` as counted at ${ts.replace("T", " ")}` : ""} and update stock?${warn}`)) return;
    await api("/api/venue/count/finish", { json: { ts } });
    countAt = ""; sheet = null; task = null;
    toast("Stocktake saved");
    await reload();
  },
  countXls: async () => {
    const f = $("countFile").files[0];
    if (!f) throw new Error("Choose a file first");
    const { drafts } = await api("/api/venue/count");
    if (drafts.length && !confirm("This replaces the figures already typed into the count. Carry on?")) return;
    sheetFile = f;
    await uploadCount(false);
  },
  countNew: async () => {
    if (!sheetFile) throw new Error("Choose the file again");
    if (!confirm("Add every unmatched row as a new product and fill in its count? This replaces the figures typed into the count.")) return;
    await uploadCount(true);
    await reload();
  },
  wGo: async () => {
    const p = productByLabel.get(waste.product);
    if (!p) throw new Error("Pick the product from the list");
    const reason = waste.reason === "__other" ? waste.other.trim() : waste.reason;
    if (!reason) throw new Error("Type the reason");
    const amount = Number(waste.amount);
    if (!(amount > 0)) throw new Error("Give the amount");
    const ml = waste.unit === "ml" ? amount : amount * p.unit_ml;
    await api("/api/venue/usage", { json: { product_id: p.id, ml, reason, note: waste.note } });
    toast(`Logged ${vol(ml, p.measure)} of ${p.label}`);
    waste = { ...waste, product: "", amount: "", note: "", other: "", reason: waste.reason === "__other" ? reason : waste.reason };
    task = null;
    await reload();
  },
  bGo: async () => {
    const r = await api("/api/venue/batches", { json: { recipe_id: $("bR").value, runs: batchState.runs, made_ml: batchState.made } });
    toast(`${vol(r.made_ml)} added to stock`);
    batchState = { id: batchState.id, runs: "1", made: "" };
    task = null;
    await reload();
  },
  syncGo: async () => {
    const r = await api("/api/venue/square/sync", { method: "POST" });
    toast(`${r.added} new lines from Square`);
    await reload();
  },
  // Drinks
  addLine: async () => { draft.lines.push({ product_id: "", ml: "" }); await render(); },
  closeDrink: async () => { draft = null; await render(); },
  closeDrink2: async () => { draft = null; await render(); },
  saveDrink: async () => { await saveDrink(); await reload(); },
  dupDrink: async () => {
    draft = { ...draft, id: null, name: `${draft.name} (copy)`, active: 1, square: [], original: [], lines: draft.lines.map((l) => ({ ...l })) };
    await render();
  },
  archDrink: async () => {
    await api(`/api/venue/recipes/${draft.id}/active`, { json: { active: !draft.active } });
    toast(draft.active ? `${draft.name} archived. Its Square buttons still take stock until unlinked.` : `${draft.name} is back on the menu`);
    draft = null;
    await reload();
  },
  delDrink: async () => {
    if (!confirm(`Delete ${draft.name} for good?`)) return;
    await api(`/api/venue/recipes/${draft.id}`, { method: "DELETE" });
    toast("Deleted");
    draft = null;
    await reload();
  },
  sqAddGo: async () => {
    const text = $("sqAdd").value.trim();
    if (!text) return;
    const hit = squareByLabel.get(text) || { item_key: itemKey(text), item_name: text };
    if (!draft.square.some((s) => s.item_key === hit.item_key)) draft.square.push(hit);
    await render();
  },
  // Branding
  bNameGo: async () => {
    await api("/api/venue/branding", { json: { name: $("bName").value } });
    await loadBranding();
    toast("Name saved");
    await render();
  },
  bLogoDel: async () => {
    if (!confirm("Remove the logo?")) return;
    await api("/api/venue/branding", { json: { remove_logo: true } });
    await loadBranding();
    await render();
  },
  styleReset: async () => {
    if (!confirm("Go back to the original look? Your logo and name stay.")) return;
    await api("/api/venue/branding", { json: { reset_style: true } });
    const html = document.documentElement;
    Object.assign(html.dataset, STYLE_DEFAULT);
    await loadBranding();
    await render();
  },
  // Products
  newProduct: async () => { prodDraft = { active: 1 }; await render(); },
  closeProd: async () => { prodDraft = null; await render(); },
  closeProd2: async () => { prodDraft = null; await render(); },
  saveProd: async () => {
    const p = prodDraft, body = {};
    for (const k of ["name", "variant", "unit_label", "unit_cost", "par", "category", "subcategory", "supplier"]) body[k] = p[k] ?? "";
    if (p.id) await api(`/api/venue/products/${p.id}`, { method: "PATCH", json: body });
    else await api("/api/venue/products", { json: body });
    toast(`${p.name} saved`);
    prodDraft = null;
    await reload();
  },
  archProd: async () => {
    await api(`/api/venue/products/${prodDraft.id}`, { method: "PATCH", json: { active: !prodDraft.active } });
    toast(prodDraft.active ? "Archived. It no longer shows in stock or counts." : "Restored");
    prodDraft = null;
    await reload();
  },
  // Deliveries
  dParse: async () => { await api("/api/venue/deliveries/parse", { json: { text: $("dText").value } }); await reload(); },
  dPhoto: async () => {
    const f = $("dImg").files[0];
    if (!f) throw new Error("Choose a photo first");
    const fd = new FormData();
    fd.append("image", f);
    await api("/api/venue/deliveries/parse", { method: "POST", body: fd });
    await reload();
  },
  dBlank: async () => {
    const n = Math.max(1, Math.min(60, parseInt($("dN").value, 10) || 1));
    await api("/api/venue/deliveries", { json: { supplier: $("dSup").value, ref: $("dRef").value, lines: Array.from({ length: n }, () => ({ description: "", units: "" })) } });
    await reload();
  },
  catGo: async () => {
    const f = $("catFile").files[0];
    if (!f) throw new Error("Choose a file first");
    const fd = new FormData();
    fd.append("file", f);
    const r = await api("/api/venue/prices/catalogue", { method: "POST", body: fd });
    toast(`${r.prices} prices loaded, ${r.matched} matched to stock`);
    await reload();
  },
  personGo: async () => {
    await api("/api/people", { json: { name: $("pName").value, role: $("pRole").value, pin: $("pPin").value } });
    toast("Added");
    await render();
  },
  faGo: async () => {
    await api("/api/people", { json: { name: $("faName").value, pin: $("faPin").value, setup_token: $("faToken").value } });
    await boot();
  },
  loginGo: async () => {
    await api("/api/auth/login", { json: { user_id: $("loginUser").value, pin: $("loginPin").value } });
    $("loginPin").value = "";
    await boot();
  },
  logout: async () => {
    await api("/api/auth/logout", { method: "POST" });
    mode = "view"; task = null; draft = null; prodDraft = null; lastResult = null;
    await boot();
  },
};

/** Crop the empty margin around a logo (transparent or a plain background), shrink it to a sensible
    size, and read its main colour and how light it is, so the header can be styled to suit. */
async function prepareLogo(file) {
  const bmp = await createImageBitmap(file);
  const scale = Math.min(1, 1200 / Math.max(bmp.width, bmp.height));
  const W = Math.round(bmp.width * scale), H = Math.round(bmp.height * scale);
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const x = c.getContext("2d");
  x.drawImage(bmp, 0, 0, W, H);
  const { data } = x.getImageData(0, 0, W, H);
  const bg = [data[0], data[1], data[2], data[3]], clear = bg[3] < 16;
  const isBg = (i) => (clear ? data[i + 3] < 16 : Math.abs(data[i] - bg[0]) + Math.abs(data[i + 1] - bg[1]) + Math.abs(data[i + 2] - bg[2]) < 48);
  let x0 = W, y0 = H, x1 = -1, y1 = -1, lumSum = 0, count = 0;
  const buckets = {};
  for (let y = 0; y < H; y++) for (let xx = 0; xx < W; xx++) {
    const i = (y * W + xx) * 4;
    if (isBg(i)) continue;
    if (xx < x0) x0 = xx; if (xx > x1) x1 = xx; if (y < y0) y0 = y; if (y > y1) y1 = y;
    if (data[i + 3] < 128) continue;
    const r = data[i] / 255, g = data[i + 1] / 255, b = data[i + 2] / 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, sat = mx === mn ? 0 : (mx - mn) / (1 - Math.abs(2 * l - 1));
    lumSum += l; count++;
    if (sat < 0.3 || l < 0.2 || l > 0.8) continue;
    const wt = sat * (1 - Math.abs(l - 0.5) * 2); // favour the solid mid-tone over highlights and shadows
    const h = mx === r ? ((g - b) / (mx - mn) + 6) % 6 : mx === g ? (b - r) / (mx - mn) + 2 : (r - g) / (mx - mn) + 4;
    const k = Math.floor(h * 4);
    const bk = (buckets[k] ||= { w: 0, r: 0, g: 0, b: 0 });
    bk.w += wt; bk.r += data[i] * wt; bk.g += data[i + 1] * wt; bk.b += data[i + 2] * wt;
  }
  if (x1 < 0) throw new Error("That image looks empty");
  const pad = Math.round(Math.max(x1 - x0, y1 - y0) * 0.04);
  x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad); x1 = Math.min(W - 1, x1 + pad); y1 = Math.min(H - 1, y1 + pad);
  const out = document.createElement("canvas");
  out.width = x1 - x0 + 1; out.height = y1 - y0 + 1;
  out.getContext("2d").drawImage(c, x0, y0, out.width, out.height, 0, 0, out.width, out.height);
  const blob = await new Promise((res) => out.toBlob(res, "image/png"));
  const top = Object.values(buckets).sort((a, b) => b.w - a.w)[0];
  const color = top ? hexOf([top.r / top.w, top.g / top.w, top.b / top.w]) : null;
  const bgLum = clear ? null : (bg[0] * 0.299 + bg[1] * 0.587 + bg[2] * 0.114) / 255;
  // A light logo (white lettering) or a logo on a dark square needs a dark header to be seen.
  const dark = clear ? count && lumSum / count > 0.55 : bgLum < 0.35;
  return { blob, color, dark, trimmed: out.width < W || out.height < H };
}

async function setColour(color) { await saveStyle({ color }); }

/** Show the change at once, then save it. */
async function saveStyle(change) {
  Object.assign(brand, change);
  applyBranding();
  await render();
  await api("/api/venue/branding", { json: change });
}

async function uploadCount(addNew) {
  const fd = new FormData();
  fd.append("file", sheetFile);
  if (addNew) fd.append("add_new", "1");
  sheet = await api("/api/venue/count/upload", { method: "POST", body: fd });
  countAt = sheet.date ? `${sheet.date}T23:59` : "";
  toast(`${sheet.matched} rows filled in, ${sheet.unmatched.length} to enter by hand`);
  await render();
}

function deliveryLines(sec) {
  return [...sec.querySelectorAll("[data-line]")].map((r) => {
    const p = productByLabel.get(r.querySelector(".dP").value);
    return { description: r.querySelector(".dD").value, product_id: p ? p.id : null, units: r.querySelector(".dU").value, unit_cost: r.querySelector(".dC").value || null };
  });
}

async function saveDelivery(id, extra = 0) {
  const sec = document.querySelector(`[data-del="${id}"]`);
  const d = (await api("/api/venue/deliveries")).deliveries.find((x) => String(x.id) === String(id));
  const lines = deliveryLines(sec);
  for (let i = 0; i < extra; i++) lines.push({ description: "", units: "" });
  await api("/api/venue/deliveries", { json: { id: d.id, supplier: d.supplier, ref: d.ref, lines } });
  return lines;
}

document.addEventListener("click", guard(async (e) => {
  const b = e.target.closest("button, th[data-sort]");
  if (!b) return;
  const ds = b.dataset;
  if (ds.sort) {
    const [id, k] = ds.sort.split(":"), t = TB[id], c = t.cols.find((x) => x.k === k);
    t.sort = t.sort && t.sort[0] === k ? [k, -t.sort[1]] : [k, c.n ? -1 : 1];
    return redrawTable(id);
  }
  if (ds.tall) { TB[ds.tall].all = true; return redrawTable(ds.tall); }
  if (ds.tcsv) return downloadCsv(ds.tcsv);
  if (ds.report) { report = ds.report; task = null; return render(); }
  if (ds.period) { period = { kind: ds.period, from: period.from, to: period.to }; cache = {}; return render(); }
  if (ds.task) { task = ds.task; return render(); }
  if (ds.goset) { mode = "settings"; setTab = ds.goset; task = null; return reload(); }
  if (ds.set) { setTab = ds.set; draft = null; prodDraft = null; editKey = null; cache = {}; return render(); }
  if (ds.loc) { loc = ds.loc; return render(); }
  if (ds.wr) { waste.reason = ds.wr; return render(); }
  if (ds.wunit) { waste.unit = ds.wunit; waste.amount = ""; return render(); }
  if (ds.wml) { waste.amount = ds.wml; $("wM").value = ds.wml; return; }
  if (ds.newbatch !== undefined) { mode = "settings"; setTab = "drinks"; task = null; draft = newDraft("batch"); return reload(); }
  if (ds.editbatch) {
    const { recipes } = await get("/api/venue/recipes");
    mode = "settings"; setTab = "drinks"; task = null;
    draft = draftFrom(recipes.find((x) => String(x.id) === ds.editbatch));
    return render();
  }
  if (ds.swatch !== undefined) return setColour(ds.swatch);
  if (ds.style) { const [k, v] = ds.style.split(":"); return saveStyle({ [k]: v }); }
  if (ds.look) return saveStyle(lookStyle(LOOKS.find((l) => l.id === ds.look)));
  // Drinks
  if (ds.dfilter) { drinkFilter = ds.dfilter; return render(); }
  if (ds.newdrink) { draft = newDraft(ds.newdrink); return render(); }
  if (ds.editdrink) {
    const { recipes } = await get("/api/venue/recipes");
    draft = draftFrom(recipes.find((r) => String(r.id) === ds.editdrink));
    return render();
  }
  if (ds.kind && draft) { draft.kind = ds.kind; if (ds.kind === "batch" && !draft.yield) draft.yield = "1000"; return render(); }
  if (ds.rmline !== undefined) { draft.lines.splice(Number(ds.rmline), 1); if (!draft.lines.length) draft.lines.push({ product_id: "", ml: "" }); return render(); }
  if (ds.chip) { const [i, ml] = ds.chip.split(":"); draft.lines[i].ml = ml; return render(); }
  if (ds.rmsq !== undefined) { draft.square.splice(Number(ds.rmsq), 1); return render(); }
  // Square buttons
  if (ds.map !== undefined || ds.nostock !== undefined || ds.newfrom !== undefined) {
    const i = ds.map ?? ds.nostock ?? ds.newfrom, item = window._unmapped[i];
    if (ds.newfrom !== undefined) {
      setTab = "drinks";
      draft = newDraft("drink", item.item_name.replace(/ - Regular$/i, ""), [{ item_key: item.item_key, item_name: item.item_name }]);
      return render();
    }
    const json = { item_key: item.item_key, item_name: item.item_name };
    if (ds.nostock !== undefined) json.no_stock = true;
    else {
      const t = targetByLabel.get(document.querySelector(`[data-mt="${i}"]`).value);
      if (!t) throw new Error("Pick a drink or product from the list");
      Object.assign(json, t, { ml: t.product_id ? document.querySelector(`[data-mm="${i}"]`).value : null });
    }
    const r = await api("/api/venue/mappings", { json });
    toast(json.no_stock ? "Marked as using no stock" : `Linked. ${r.applied} sales came off stock`);
    return reload();
  }
  if (ds.reedit) { editKey = ds.reedit; return render(); }
  if (ds.recancel !== undefined) { editKey = null; return render(); }
  if (ds.relink) {
    const x = window._mapped.find((y) => y.item_key === ds.relink);
    const t = targetByLabel.get($("reTarget").value);
    if (!t) throw new Error("Pick a drink or product from the list");
    await api("/api/venue/mappings", { json: { item_key: x.item_key, item_name: x.item_name, ...t, ml: t.product_id ? $("reMl").value : null } });
    editKey = null;
    toast("Link changed for future sales");
    return reload();
  }
  if (ds.unlink) {
    if (!confirm("Unlink this Square item? Past sales stay as they are; new sales wait until it is linked again.")) return;
    await api("/api/venue/mappings/delete", { json: { item_key: ds.unlink } });
    return reload();
  }
  // Products
  if (ds.editprod) {
    const { products } = await get("/api/venue/products/all");
    prodDraft = { ...products.find((p) => String(p.id) === ds.editprod) };
    return render();
  }
  // Deliveries
  if (ds.addline) { await saveDelivery(ds.addline, 1); return reload(); }
  if (ds.savedel) { await saveDelivery(ds.savedel); toast("Saved"); return reload(); }
  if (ds.approve) {
    const lines = await saveDelivery(ds.approve);
    if (lines.some((l) => !l.product_id)) throw new Error("Pick a product from the list for every line");
    await api(`/api/venue/deliveries/${ds.approve}/approve`, { method: "POST" });
    toast("Delivery added to stock");
    return reload();
  }
  if (ds.pmatch) {
    const t = ds.pmatch, p = productByLabel.get(document.querySelector(`[data-pp="${t}"]`).value);
    if (!p) throw new Error("Pick a product from the list");
    await api(`/api/venue/prices/${t}`, { json: { product_id: p.id, ml: document.querySelector(`[data-pm="${t}"]`).value } });
    toast("Linked");
    return reload();
  }
  if (ds.undo) {
    if (!confirm("Remove this upload and put its stock back?")) return;
    const r = await api(`/api/venue/imports/${ds.undo}/undo`, { method: "POST" });
    toast(`Undone: ${r.removed} lines removed`);
    return reload();
  }
  if (ds.resetpin) {
    const pin = prompt(`New 6-digit PIN for ${ds.name}`);
    if (!pin) return;
    await api(`/api/people/${ds.resetpin}/reset-pin`, { json: { pin } });
    return toast(`PIN changed for ${ds.name}`);
  }
  if (ds.active) {
    const [id, on] = ds.active.split(":");
    await api(`/api/people/${id}`, { method: "PATCH", json: { active: on === "1" } });
    toast(on === "1" ? "Switched on" : "Switched off. They can no longer sign in.");
    return render();
  }
  if (ds.deluser) {
    if (!confirm(`Remove ${ds.name}? Their past entries stay in the records.`)) return;
    await api(`/api/people/${ds.deluser}`, { method: "DELETE" });
    toast("Removed");
    return render();
  }
  if (b.id && CLICK[b.id]) await CLICK[b.id]();
}));

document.addEventListener("change", guard(async (e) => {
  const el = e.target, ds = el.dataset;
  if (el.id === "csvPick" && el.files[0]) { const f = el.files[0]; el.value = ""; return uploadSales(f); }
  if (el.id === "bLogo" && el.files[0]) {
    const logo = await prepareLogo(el.files[0]);
    const fd = new FormData();
    fd.append("file", logo.blob, "logo.png");
    await api("/api/venue/branding/logo", { method: "POST", body: fd });
    const style = logo.dark ? { header: "dark", banner: "dark" } : {};
    if (logo.color) style.logo_color = logo.color;
    if (logo.color && !brand.color) style.color = logo.color;
    await api("/api/venue/branding", { json: style });
    await loadBranding();
    toast(`Logo saved${logo.trimmed ? ", spare space trimmed" : ""}${style.color ? ", colour taken from it" : ""}${logo.dark ? ", dark header to suit it" : ""}. Change any of it below.`);
    return render();
  }
  if (el.id === "bColor") return setColour(el.value);
  if (ds.role) {
    await api(`/api/people/${ds.role}`, { method: "PATCH", json: { role: el.value } });
    toast("Role changed");
    return render();
  }
  if (ds.job) {
    const [id, j] = ds.job.split(":");
    await api(`/api/people/${id}`, { method: "PATCH", json: { stock_jobs: { [j]: el.checked } } });
    return toast("Saved");
  }
  if (el.id === "showArchived") { SETTINGS.products.archived = el.checked; return render(); }
  if (ds.cost) {
    await api(`/api/venue/products/${ds.cost}`, { method: "PATCH", json: { unit_cost: el.value } });
    const p = productById.get(Number(ds.cost));
    if (p) p.unit_cost = el.value === "" ? null : Number(el.value);
    return toast("Cost saved");
  }
  if (ds.par) {
    await api(`/api/venue/products/${ds.par}`, { method: "PATCH", json: { par: el.value } });
    return toast("Par saved");
  }
  if (ds.count) return api("/api/venue/count/draft", { json: { location: loc, product_id: ds.count, units: el.value } });
  if (ds.comp && el.value) {
    await api(`/api/venue/comps/${ds.comp}`, { json: { reason: el.value } });
    toast("Saved");
    cache = {};
    return render();
  }
  if (ds.lp !== undefined && draft) {
    const p = productByLabel.get(el.value);
    draft.lines[ds.lp].product_id = p ? p.id : "";
    if (!p && el.value) toast("Pick the ingredient from the list");
    return render();
  }
  if (ds.lm !== undefined && draft) { draft.lines[ds.lm].ml = el.value; return render(); }
  if (el.id === "wP") { waste.product = el.value; return render(); }
  if (el.id === "bR") { batchState = { id: el.value, runs: batchState.runs, made: "" }; return render(); }
  if (el.id === "bN") { batchState.runs = el.value; return render(); }
  if (el.id === "bMade") { batchState.made = el.value; return render(); }
  if (ds.df === "price" && draft) { draft.price = el.value; return render(); }
  if (ds.df === "yield" && draft) { draft.yield = el.value; return render(); }
}));

document.addEventListener("input", (e) => {
  const el = e.target, ds = el.dataset;
  if (ds.tsearch) { TB[ds.tsearch].q = el.value; TB[ds.tsearch].all = false; return redrawTable(ds.tsearch); }
  if (ds.df && draft) { draft[ds.df] = el.value; return; }
  if (ds.pf && prodDraft) { prodDraft[ds.pf] = el.value; return; }
  const wmap = { wOther: "other", wP: "product", wM: "amount", wN: "note" };
  if (wmap[el.id]) { waste[wmap[el.id]] = el.value; return; }
  if (el.id === "bColor") { document.documentElement.style.setProperty("--brand", el.value); return; }
  if (el.id === "countFilter") {
    const q = el.value.toLowerCase();
    document.querySelectorAll("#countBody tr").forEach((r) => {
      if (r.hasAttribute("data-cat")) r.classList.toggle("hidden", !!q);
      else r.classList.toggle("hidden", !!q && !(r.dataset.q || "").includes(q));
    });
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (e.target.id === "loginPin") guard(CLICK.loginGo)();
  if (e.target.id === "sqAdd") guard(CLICK.sqAddGo)();
});

// Hover (or tap / tab to) a bar to see its figures.
function showTip(el, x, y) {
  const t = $("tip");
  t.textContent = el.dataset.tip;
  t.style.display = "block";
  const r = t.getBoundingClientRect();
  t.style.left = `${Math.min(Math.max(8, x - r.width / 2), innerWidth - r.width - 8)}px`;
  t.style.top = `${Math.max(8, y - r.height - 12)}px`;
}
document.addEventListener("mousemove", (e) => {
  const el = e.target.closest && e.target.closest("[data-tip]");
  if (el) showTip(el, e.clientX, e.clientY); else $("tip").style.display = "none";
});
document.addEventListener("focusin", (e) => {
  const el = e.target.closest && e.target.closest("[data-tip]");
  if (!el) return;
  const r = el.getBoundingClientRect();
  showTip(el, r.left + r.width / 2, r.top);
});
document.addEventListener("focusout", () => { $("tip").style.display = "none"; });

// Drag a CSV onto the upload card.
document.addEventListener("dragover", (e) => {
  const z = e.target.closest && e.target.closest("#drop");
  if (!z) return;
  e.preventDefault();
  z.classList.add("drag");
});
document.addEventListener("dragleave", (e) => { const z = e.target.closest && e.target.closest("#drop"); if (z) z.classList.remove("drag"); });
document.addEventListener("drop", guard(async (e) => {
  const z = e.target.closest && e.target.closest("#drop");
  if (!z) return;
  e.preventDefault();
  z.classList.remove("drag");
  const f = e.dataTransfer.files[0];
  if (f) await uploadSales(f);
}));

guard(boot)();
