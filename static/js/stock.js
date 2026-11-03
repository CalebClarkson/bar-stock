/* Stock screens for the venue fork. Stock is one overall figure; Bar and Cellar are only counted separately. */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const gbp = (v) => (v == null ? "–" : "£" + Number(v).toFixed(2));
const LOCS = ["Bar", "Cellar"];
const RANK = { staff: 1, manager: 2, admin: 3 };
let me = null, data = null, tab = "stock", loc = "Bar";

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.style.display = "none"), 4000);
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

function guard(fn) {
  return async (...a) => { try { await fn(...a); } catch (e) { toast(e.message); } };
}

const TABS = [
  ["stock", "Stock", "staff"], ["count", "Count", "staff"], ["waste", "Wastage", "staff"],
  ["batch", "Batches", "staff"], ["sales", "Square sales", "manager"], ["map", "Mapping", "manager"],
  ["recipes", "Recipes", "manager"], ["prices", "Prices", "manager"], ["deliveries", "Deliveries", "manager"], ["reports", "Reports", "manager"],
  ["people", "People", "admin"],
];

async function boot() {
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
  await reload();
}

async function reload() {
  data = await api("/api/venue/overview");
  renderTabs();
  await render();
}

function renderTabs() {
  const badge = { map: data.unmapped };
  $("tabs").innerHTML = TABS.filter((t) => RANK[me.role] >= RANK[t[2]]).map((t) =>
    `<button data-tab="${t[0]}" class="${t[0] === tab ? "on" : ""}">${t[1]}${badge[t[0]] ? `<span class="badge">${badge[t[0]]}</span>` : ""}</button>`).join("");
}

function segment() {
  return `<div class="seg">${LOCS.map((l) => `<button data-loc="${l}" class="${l === loc ? "on" : ""}">${l}</button>`).join("")}</div>`;
}

function grouped(lines, rowFn) {
  let cat = "", out = "";
  for (const l of lines) {
    if (l.category !== cat) { cat = l.category; out += `<tr class="cat"><td colspan="9">${esc(cat)}</td></tr>`; }
    out += rowFn(l);
  }
  return out;
}

const productOptions = (sel) => `<option value="">Choose…</option>` + data.products.map((p) =>
  `<option value="${p.id}" ${String(sel) === String(p.id) ? "selected" : ""}>${esc(p.label)}</option>`).join("");

const VIEWS = {
  stock() {
    const lines = data.stock;
    const value = lines.reduce((s, l) => s + (l.value || 0), 0);
    const low = lines.filter((l) => l.below_par).length;
    const neg = lines.filter((l) => l.negative);
    return `<section>
      <p class="hint">${lines.length} products · costed value ${gbp(value)} · ${low} below par${neg.length ? ` · <span class="neg">${neg.length} below zero: recount</span>` : ""}. In stock is the overall figure after sales. Bar and Cellar are from the last count.</p>
      <input id="filter" placeholder="Search stock…" aria-label="Search">
      <div class="scroll"><table><thead><tr><th>Product</th><th class="n">In stock</th><th class="n">Bar count</th><th class="n">Cellar count</th><th class="n">Par</th><th class="n">Cost</th><th class="n">Value</th></tr></thead>
      <tbody id="stockBody">${grouped(lines, (l) => `<tr data-q="${esc(l.label.toLowerCase())}"><td>${esc(l.label)}</td>
        <td class="n ${l.negative ? "neg" : l.below_par ? "low" : ""}">${l.units}</td>
        <td class="n">${l.counted.Bar}</td><td class="n">${l.counted.Cellar}</td>
        <td class="n">${RANK[me.role] >= 2 ? `<input data-par="${l.product_id}" value="${l.par ?? ""}" inputmode="decimal" aria-label="Par">` : l.par ?? "–"}</td>
        <td class="n">${RANK[me.role] >= 2 ? `<input data-cost="${l.product_id}" value="${l.unit_cost ?? ""}" inputmode="decimal" aria-label="Unit cost">` : gbp(l.unit_cost)}</td>
        <td class="n">${gbp(l.value)}</td></tr>`)}</tbody></table></div></section>`;
  },
  async count() {
    const { drafts } = await api("/api/venue/count");
    const mine = Object.fromEntries(drafts.filter((d) => d.location === loc).map((d) => [d.product_id, d.units]));
    const done = LOCS.map((l) => `${l}: ${drafts.filter((d) => d.location === l).length}`).join(" · ");
    return `<section>${segment()}<h2>Count the ${loc}</h2>
      <p class="hint">Enter units on the shelf, using tenths for open bottles (0.7). Each figure saves as you go, so two people can count Bar and Cellar at once. Stock only changes when you finish. Counted so far: ${done}.</p>
      <div class="scroll"><table><thead><tr><th>Product</th><th class="n">Last count</th><th class="n">Counted</th></tr></thead><tbody>
      ${grouped(data.stock, (l) => `<tr><td>${esc(l.label)}</td><td class="n">${l.counted[loc]}</td><td class="n"><input data-count="${l.product_id}" value="${mine[l.product_id] ?? ""}" inputmode="decimal" aria-label="Counted"></td></tr>`)}
      </tbody></table></div><div class="row"><button class="act" id="saveCount">Finish stocktake</button></div></section>`;
  },
  waste() {
    return `<section><h2>Log wastage, overpour, training or staff drinks</h2><p class="hint">For anything not rung through Square. Comps from Square come in with the sales import.</p>
      <div class="row"><label>Product<select id="wP">${productOptions()}</select></label>
      <label>Reason<select id="wR"><option value="wastage">Wastage</option><option value="overpour">Overpour</option><option value="training">Training</option><option value="staff">Staff drinks</option></select></label>
      <label>Amount (ml)<input id="wM" inputmode="decimal"></label></div>
      <div class="row"><label>Note<input id="wN"></label><button class="act" id="wGo">Log it</button></div></section>`;
  },
  async batch() {
    const { recipes } = await api("/api/venue/recipes");
    const batches = recipes.filter((r) => r.batch_product_id);
    return `<section><h2>Make a batch</h2><p class="hint">Takes the raw ingredients out of stock and adds the pre-mix.</p>
      ${batches.length ? `<div class="row"><label>Batch<select id="bR">${batches.map((r) => `<option value="${r.id}">${esc(r.name)} (${r.yield_ml}ml)</option>`).join("")}</select></label>
      <label>How many runs<input id="bN" value="1" inputmode="decimal"></label><button class="act" id="bGo">Made it</button></div>` : `<p>No batch recipes yet. A manager can add one under Recipes.</p>`}</section>`;
  },
  async sales() {
    const { imports } = await api("/api/venue/imports");
    return `<section><h2>Import the day's Square sales</h2>
      <p class="hint">Square Dashboard → Reports → Item sales → Export → <strong>Item sales detail CSV</strong>. Importing the same file twice is safe.</p>
      <div class="row"><label>CSV file<input id="csv" type="file" accept=".csv,text/csv"></label>
      <label>Trading date (summary exports only)<input id="csvDate" type="date"></label><button class="act" id="csvGo">Import</button></div>
      ${data.square_api ? `<div class="row"><button class="alt" id="syncGo">Sync from Square now</button></div>` : ""}</section>
      <section><h2>Recent imports</h2><div class="scroll"><table><thead><tr><th>When</th><th>File</th><th class="n">Added</th><th class="n">Skipped</th><th></th></tr></thead><tbody>
      ${imports.map((i) => `<tr><td>${esc(i.ts.replace("T", " "))}</td><td>${esc(i.filename || i.source)}</td><td class="n">${i.added}</td><td class="n">${i.skipped}</td>
      <td>${i.undone ? "Undone" : `<button class="alt" data-undo="${i.id}">Undo</button>`}</td></tr>`).join("") || `<tr><td colspan="5">Nothing imported yet.</td></tr>`}</tbody></table></div></section>`;
  },
  async map() {
    const m = await api("/api/venue/mappings");
    const { recipes } = await api("/api/venue/recipes");
    const target = `<option value="">Choose…</option><optgroup label="Recipes">${recipes.map((r) => `<option value="r${r.id}">${esc(r.name)}</option>`).join("")}</optgroup>
      <optgroup label="Products">${data.products.map((p) => `<option value="p${p.id}">${esc(p.label)}</option>`).join("")}</optgroup>`;
    return `<section><h2>Items waiting to be mapped (${m.unmapped.length})</h2>
      <p class="hint">Point each Square item at a recipe, or at a product with the amount per serve. Leave ml blank for a whole bottle or can. Use No stock for anything that uses no bar stock, such as food. Waiting sales apply as soon as you save.</p>
      <div class="scroll"><table><thead><tr><th>Square item</th><th class="n">Sold</th><th>Takes stock from</th><th>ml per serve</th><th></th></tr></thead><tbody>
      ${m.unmapped.map((u, i) => `<tr><td>${esc(u.item_name)}</td><td class="n">${u.qty}</td><td><select data-mt="${i}" style="min-width:190px">${target}</select></td>
      <td><input data-mm="${i}" inputmode="decimal"></td><td><button class="alt" data-map="${i}">Save</button> <button class="alt" data-nostock="${i}">No stock</button></td></tr>`).join("") || `<tr><td colspan="5">All sold items are mapped.</td></tr>`}</tbody></table></div></section>
      <section><h2>Mapped (${m.mapped.length})</h2><div class="scroll"><table><tbody>${m.mapped.map((x) => `<tr><td>${esc(x.item_name)}</td><td>${x.no_stock ? "No stock used" : esc(x.recipe || (data.products.find((p) => p.id === x.product_id) || {}).label)}</td><td class="n">${x.ml ? Math.round(x.ml * 10) / 10 + "ml" : ""}</td></tr>`).join("")}</tbody></table></div></section>
      <script type="application/json" id="mapData">${esc(JSON.stringify(m.unmapped))}</script>`;
  },
  async recipes() {
    const { recipes } = await api("/api/venue/recipes");
    return `<section><h2>Recipes</h2><div class="scroll"><table><thead><tr><th>Recipe</th><th>Ingredients</th><th class="n">Cost</th><th class="n">Price</th></tr></thead><tbody>
      ${recipes.map((r) => `<tr><td>${esc(r.name)}${r.batch_product_id ? ` <em>(batch, ${r.yield_ml}ml)</em>` : ""}</td><td>${r.lines.map((l) => `${l.ml}ml ${esc(l.label)}`).join(", ")}${r.note ? `<br><span class="hint">${esc(r.note)}</span>` : ""}</td><td class="n">${gbp(r.cost)}</td><td class="n">${gbp(r.menu_price)}</td></tr>`).join("") || `<tr><td colspan="4">No recipes yet.</td></tr>`}</tbody></table></div></section>
      <section><h2>Add or update a recipe</h2><p class="hint">Saving an existing name replaces it. Past sales keep the amounts used at the time. To use a pre-mix in a cocktail, add the batch first, then choose it as an ingredient.</p>
      <div class="row"><label>Name<input id="rName"></label><label>Menu price £<input id="rPrice" inputmode="decimal"></label><label>Batch yield ml (pre-mix only)<input id="rYield" inputmode="decimal"></label></div>
      <div id="rLines">${recipeLine()}${recipeLine()}</div><div class="row"><button class="alt" id="rAdd">Add ingredient</button><button class="act" id="rSave">Save recipe</button></div></section>`;
  },
  async prices() {
    const { prices } = await api("/api/venue/prices");
    const open = prices.filter((p) => !p.product);
    let cat = "";
    const rowsHtml = prices.filter((p) => p.product).map((p) => {
      const head = p.category !== cat ? `<tr class="cat"><td colspan="6">${esc((cat = p.category))}</td></tr>` : "";
      return `${head}<tr data-q="${esc((p.item + " " + p.product).toLowerCase())}"><td>${esc(p.item)}</td><td>${esc(p.variation)}</td><td class="n">${gbp(p.price)}</td><td class="n">${gbp(p.cost)}</td><td class="n">${p.gp_pct == null ? "–" : p.gp_pct + "%"}</td><td>${esc(p.product)}</td></tr>`;
    }).join("");
    return `<section><h2>Selling prices</h2><p class="hint">From the Square catalogue, including VAT. These are not cost prices. Cost and GP show once a product has a cost, and GP is worked out after 20% VAT.</p>
      <div class="row"><label>New Square catalogue CSV<input id="catFile" type="file" accept=".csv,text/csv"></label><button class="alt" id="catGo">Update prices</button></div>
      <input id="filter" placeholder="Search prices…" aria-label="Search">
      <div class="scroll"><table><thead><tr><th>Square item</th><th>Serve</th><th class="n">Sell</th><th class="n">Cost</th><th class="n">GP</th><th>Comes off</th></tr></thead><tbody id="stockBody">${rowsHtml || `<tr><td colspan="6">No prices yet.</td></tr>`}</tbody></table></div></section>
      <section><h2>Not matched to a stock product (${open.length})</h2><p class="hint">These have no recipe or stock link yet, so they cannot come off stock. Match any single product here; leave ml blank if the serve size is unknown.</p>
      <div class="scroll"><table><tbody>${open.map((p) => `<tr><td>${esc(p.item)} ${esc(p.variation)}</td><td class="n">${gbp(p.price)}</td><td><select data-pp="${esc(p.token)}" style="min-width:170px">${productOptions(p.product_id)}</select></td><td><input data-pm="${esc(p.token)}" inputmode="decimal" aria-label="ml"></td><td><button class="alt" data-pmatch="${esc(p.token)}">Save</button></td></tr>`).join("")}</tbody></table></div></section>`;
  },
  async deliveries() {
    const { deliveries } = await api("/api/venue/deliveries");
    const opts = (sel) => productOptions(sel);
    return `${deliveries.filter((d) => d.status === "draft").map((d) => `<section data-del="${d.id}"><h2>Review: ${esc(d.supplier)} ${esc(d.ref)}</h2><p class="hint">Stock only changes when you approve. Match each line; matches are remembered for next time.</p>
      <div class="scroll"><table><thead><tr><th>Invoice line</th><th>Product</th><th class="n">Units</th><th class="n">Unit cost</th></tr></thead><tbody>
      ${d.lines.map((l, i) => `<tr data-line="${i}"><td>${esc(l.description)}</td><td><select class="dP" style="min-width:190px">${opts(l.product_id)}</select></td><td><input class="dU" value="${l.units ?? ""}"></td><td><input class="dC" value="${l.unit_cost ?? ""}"></td></tr>`).join("")}</tbody></table></div>
      <div class="row"><button class="act" data-approve="${d.id}">Approve into stock</button></div></section>`).join("")}
      <section><h2>New delivery</h2><p class="hint">Paste the invoice text, or use a photo if an AI key is set in venue.env. Either way you review it before stock changes.</p>
      <label>Invoice text<textarea id="dText" rows="5"></textarea></label><div class="row"><button class="act" id="dParse">Read text</button></div>
      <div class="row"><label>Invoice photo<input id="dImg" type="file" accept="image/*"></label><button class="alt" id="dPhoto">Read photo</button></div>
      <div class="row"><label>Supplier (manual entry)<input id="dSup"></label><label>Reference<input id="dRef"></label><label>Lines<input id="dN" value="3" inputmode="numeric"></label><button class="alt" id="dBlank">Start blank</button></div></section>
      <section><h2>Approved</h2><div class="scroll"><table><tbody>${deliveries.filter((d) => d.status !== "draft").map((d) => `<tr><td>${esc(d.ts.slice(0, 10))}</td><td>${esc(d.supplier)} ${esc(d.ref)}</td><td class="n">${d.lines.length} lines</td></tr>`).join("") || `<tr><td>None yet.</td></tr>`}</tbody></table></div></section>`;
  },
  async reports() {
    const to = new Date().toISOString().slice(0, 10);
    const from = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
    const f = VIEWS.reports.from || from, t = VIEWS.reports.to || to;
    const u = await api(`/api/venue/reports/usage?from=${f}&to=${t}`);
    const v = await api("/api/venue/reports/variance");
    const { comps } = await api("/api/venue/comps");
    const kinds = ["sale", "wastage", "overpour", "training", "staff", "comp", "refunded"];
    return `<section><h2>Usage</h2><div class="row"><label>From<input id="rpF" type="date" value="${f}"></label><label>To<input id="rpT" type="date" value="${t}"></label><button class="alt" id="rpGo">Show</button></div>
      <div class="scroll"><table><thead><tr><th>Product</th>${kinds.map((k) => `<th class="n">${k}</th>`).join("")}<th class="n">Cost</th></tr></thead><tbody>
      ${u.lines.map((l) => `<tr><td>${esc(l.label)}</td>${kinds.map((k) => `<td class="n">${l[k] || ""}</td>`).join("")}<td class="n">${gbp(l.cost)}</td></tr>`).join("") || `<tr><td colspan="9">No usage in this period.</td></tr>`}
      <tr class="cat"><td>Total ml</td>${kinds.map((k) => `<td class="n">${u.totals_ml[k] || ""}</td>`).join("")}<td></td></tr></tbody></table></div></section>
      ${comps.length ? `<section><h2>Comps with no reason (${comps.length})</h2><p class="hint">Square's export did not say why. Classify them here.</p><div class="scroll"><table><tbody>${comps.map((c) => `<tr><td>${esc(c.ts.replace("T", " "))}</td><td>${esc(c.item_name)}</td><td class="n">${c.qty}</td><td><select data-comp="${c.id}" style="min-width:120px"><option value="">Reason…</option><option>wastage</option><option>overpour</option><option>training</option><option value="staff">staff drinks</option></select></td></tr>`).join("")}</tbody></table></div></section>` : ""}
      <section><h2>Variance between the last two stocktakes</h2><p class="hint">Opening + received − all logged usage = expected. Bar and Cellar counts are added together; counted minus expected is stock nobody can account for.</p>
      <div class="scroll"><table><thead><tr><th>Product</th><th class="n">Opening</th><th class="n">Expected</th><th class="n">Bar</th><th class="n">Cellar</th><th class="n">Counted</th><th class="n">Variance</th><th class="n">£</th></tr></thead><tbody>
      ${v.lines.map((r) => `<tr><td>${esc(r.label)}</td><td class="n">${r.opening_units}</td><td class="n">${r.expected_units}</td><td class="n">${r.closing_bar}</td><td class="n">${r.closing_cellar}</td><td class="n">${r.closing_units}</td><td class="n ${Math.abs(r.variance_units) > 0.05 ? "low" : ""}">${r.variance_units}</td><td class="n">${gbp(r.variance_value)}</td></tr>`).join("") || `<tr><td colspan="8">Needs a second stocktake.</td></tr>`}</tbody></table></div></section>`;
  },
  async people() {
    const { users } = await api("/api/people");
    return `<section><h2>People</h2><div class="scroll"><table><tbody>${users.map((u) => `<tr><td>${esc(u.name)}</td><td>${esc(u.login)}</td><td>${esc(u.role)}</td><td>${u.active ? "" : "Inactive"}</td><td><button class="alt" data-resetpin="${esc(u.id)}">Reset PIN</button></td></tr>`).join("")}</tbody></table></div>
      <h3>Add someone</h3><div class="row"><label>Name<input id="pName"></label><label>Role<select id="pRole"><option>staff</option><option>manager</option><option>admin</option></select></label><label>6-digit PIN<input id="pPin" inputmode="numeric" maxlength="6"></label><button class="act" id="pGo">Add</button></div></section>`;
  },
};

const recipeLine = () => `<div class="row rl"><label>Ingredient<select class="rP">${productOptions()}</select></label><label style="flex:0 1 110px">ml<input class="rM" inputmode="decimal"></label></div>`;

async function render() {
  const v = $("view");
  v.innerHTML = await VIEWS[tab]();
}

async function saveCost(input) {
  await api(`/api/venue/products/${input.dataset.cost}`, { method: "PATCH", json: { unit_cost: input.value } });
  toast("Cost saved");
}

const CLICK = {
  saveCount: async () => {
    const { one_sided: partial } = await api("/api/venue/count");
    const warn = partial.length ? `\n\nCounted in one place only (the other keeps its last figure):\n${partial.slice(0, 15).join("\n")}` : "";
    if (!confirm(`Finish this stocktake and update stock?${warn}`)) return;
    await api("/api/venue/count/finish", { json: {} });
    toast("Stocktake saved");
    await reload();
  },
  wGo: async () => {
    await api("/api/venue/usage", { json: { product_id: $("wP").value, ml: $("wM").value, reason: $("wR").value, note: $("wN").value } });
    toast("Logged");
    await reload();
  },
  bGo: async () => {
    const r = await api("/api/venue/batches", { json: { recipe_id: $("bR").value, runs: $("bN").value } });
    toast(`${r.made_ml}ml added to stock`);
    await reload();
  },
  csvGo: async () => {
    const f = $("csv").files[0];
    if (!f) throw new Error("Choose a file first");
    const fd = new FormData();
    fd.append("file", f);
    fd.append("sale_date", $("csvDate").value);
    const r = await api("/api/venue/import/square", { method: "POST", body: fd });
    toast(`${r.added} lines added, ${r.skipped} already imported, ${r.unmapped} need mapping`);
    await reload();
  },
  syncGo: async () => {
    const r = await api("/api/venue/square/sync", { method: "POST" });
    toast(`${r.added} new lines from Square`);
    await reload();
  },
  rAdd: async () => $("rLines").insertAdjacentHTML("beforeend", recipeLine()),
  rSave: async () => {
    const lines = [...document.querySelectorAll(".rl")].map((r) => ({ product_id: r.querySelector(".rP").value, ml: r.querySelector(".rM").value })).filter((l) => l.product_id && l.ml);
    await api("/api/venue/recipes", { json: { name: $("rName").value, menu_price: $("rPrice").value, yield_ml: $("rYield").value, lines } });
    toast("Recipe saved");
    await reload();
  },
  dParse: async () => {
    await api("/api/venue/deliveries/parse", { json: { text: $("dText").value } });
    await reload();
  },
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
    const lines = Array.from({ length: n }, () => ({ description: "", units: "" }));
    await api("/api/venue/deliveries", { json: { supplier: $("dSup").value, ref: $("dRef").value, lines } });
    await reload();
  },
  catGo: async () => {
    const f = $("catFile").files[0];
    if (!f) throw new Error("Choose a file first");
    const fd = new FormData();
    fd.append("file", f);
    const r = await api("/api/venue/prices/catalogue", { method: "POST", body: fd });
    toast(`${r.prices} prices loaded, ${r.matched} matched to stock`);
    await render();
  },
  rpGo: async () => {
    VIEWS.reports.from = $("rpF").value;
    VIEWS.reports.to = $("rpT").value;
    await render();
  },
  pGo: async () => {
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
    await boot();
  },
};

document.addEventListener("click", guard(async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.tab) { tab = b.dataset.tab; renderTabs(); return render(); }
  if (b.dataset.loc) { loc = b.dataset.loc; return render(); }
  if (b.dataset.resetpin) {
    const pin = prompt("New 6-digit PIN");
    if (!pin) return;
    await api(`/api/people/${b.dataset.resetpin}/reset-pin`, { json: { pin } });
    toast("PIN changed");
    return;
  }
  if (b.dataset.undo) {
    if (!confirm("Remove this import and put its stock back?")) return;
    await api(`/api/venue/imports/${b.dataset.undo}/undo`, { method: "POST" });
    return reload();
  }
  if (b.dataset.pmatch) {
    const t = b.dataset.pmatch;
    await api(`/api/venue/prices/${t}`, { json: { product_id: document.querySelector(`[data-pp="${t}"]`).value, ml: document.querySelector(`[data-pm="${t}"]`).value } });
    toast("Matched");
    return render();
  }
  if (b.dataset.nostock !== undefined) {
    const items = JSON.parse(new DOMParser().parseFromString($("mapData").textContent, "text/html").body.textContent);
    const item = items[b.dataset.nostock];
    await api("/api/venue/mappings", { json: { item_key: item.item_key, item_name: item.item_name, no_stock: true } });
    toast("Marked as no stock");
    return reload();
  }
  if (b.dataset.map !== undefined) {
    const i = b.dataset.map;
    const items = JSON.parse(new DOMParser().parseFromString($("mapData").textContent, "text/html").body.textContent);
    const t = document.querySelector(`[data-mt="${i}"]`).value;
    if (!t) throw new Error("Choose what it takes stock from");
    const json = { item_key: items[i].item_key, item_name: items[i].item_name, ml: document.querySelector(`[data-mm="${i}"]`).value };
    json[t[0] === "r" ? "recipe_id" : "product_id"] = t.slice(1);
    const r = await api("/api/venue/mappings", { json });
    toast(`Mapped, ${r.applied} sales applied`);
    return reload();
  }
  if (b.dataset.approve) {
    const sec = b.closest("[data-del]");
    const d = (await api("/api/venue/deliveries")).deliveries.find((x) => String(x.id) === b.dataset.approve);
    const lines = d.lines.map((l, i) => {
      const r = sec.querySelector(`[data-line="${i}"]`);
      return { ...l, product_id: r.querySelector(".dP").value, units: r.querySelector(".dU").value, unit_cost: r.querySelector(".dC").value || null };
    });
    await api("/api/venue/deliveries", { json: { id: d.id, supplier: d.supplier, ref: d.ref, lines } });
    await api(`/api/venue/deliveries/${d.id}/approve`, { method: "POST" });
    toast("Delivery added to stock");
    return reload();
  }
  if (b.id && CLICK[b.id]) await CLICK[b.id]();
}));

document.addEventListener("change", guard(async (e) => {
  const el = e.target;
  if (el.dataset.cost) return saveCost(el);
  if (el.dataset.par) {
    await api(`/api/venue/products/${el.dataset.par}`, { method: "PATCH", json: { par: el.value } });
    return toast("Par saved");
  }
  if (el.dataset.count) {
    return api("/api/venue/count/draft", { json: { location: loc, product_id: el.dataset.count, units: el.value } });
  }
  if (el.dataset.comp && el.value) {
    await api(`/api/venue/comps/${el.dataset.comp}`, { json: { reason: el.value } });
    return render();
  }
}));

document.addEventListener("input", (e) => {
  if (e.target.id !== "filter") return;
  const q = e.target.value.toLowerCase();
  document.querySelectorAll("#stockBody tr").forEach((r) => {
    r.classList.toggle("hidden", !!q && !(r.dataset.q || "").includes(q));
  });
});

guard(boot)();
