"""Venue stock ledger (SQLite). Added by the Tranquil Turtle fork.

Stock is one overall figure per product. Bar and Cellar exist only in stocktakes:
on hand is the Bar and Cellar figures from the product's latest stocktake added
together, plus every movement since. Movements are append-only; usage kinds split
sales from wastage, overpour, training, staff drinks and comps.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Any

LOCATIONS = ("Bar", "Cellar")
ALL = "All"  # pars and movements apply to overall stock, not a location
USAGE_KINDS = ("sale", "wastage", "overpour", "training", "staff", "comp", "refunded")
REASONS = ("wastage", "overpour", "training", "staff")
OVERPOUR_RE = re.compile(r"overpour\s*\+?\s*(\d+(?:\.\d+)?)\s*ml", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, variant TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '', subcategory TEXT NOT NULL DEFAULT '',
  unit_label TEXT NOT NULL DEFAULT '', unit_ml REAL NOT NULL, measure TEXT NOT NULL DEFAULT 'ml',
  unit_cost REAL, supplier TEXT NOT NULL DEFAULT '', sell_from TEXT NOT NULL DEFAULT 'Bar',
  is_batch INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(name, variant, unit_ml));
CREATE TABLE IF NOT EXISTS pars (
  product_id INTEGER NOT NULL REFERENCES products(id), location TEXT NOT NULL,
  units REAL NOT NULL, PRIMARY KEY (product_id, location));
CREATE TABLE IF NOT EXISTS counts (
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, location TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '', user TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS count_lines (
  count_id INTEGER NOT NULL REFERENCES counts(id), product_id INTEGER NOT NULL REFERENCES products(id),
  units REAL NOT NULL, PRIMARY KEY (count_id, product_id));
CREATE TABLE IF NOT EXISTS count_drafts (
  location TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id),
  units REAL NOT NULL, user TEXT NOT NULL DEFAULT '', PRIMARY KEY (location, product_id));
CREATE TABLE IF NOT EXISTS imports (
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, source TEXT NOT NULL, filename TEXT NOT NULL DEFAULT '',
  user TEXT NOT NULL DEFAULT '', added INTEGER NOT NULL DEFAULT 0, skipped INTEGER NOT NULL DEFAULT 0,
  undone INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, import_id INTEGER, ts TEXT NOT NULL,
  kind TEXT NOT NULL, item_key TEXT NOT NULL, item_name TEXT NOT NULL, qty REAL NOT NULL,
  net REAL NOT NULL DEFAULT 0, modifiers TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'unmapped');
CREATE TABLE IF NOT EXISTS movements (
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id),
  location TEXT NOT NULL, ml REAL NOT NULL, kind TEXT NOT NULL, event_id INTEGER, ref TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '', user TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS movements_lookup ON movements(product_id, location, ts);
CREATE TABLE IF NOT EXISTS recipes (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, menu_price REAL,
  batch_product_id INTEGER REFERENCES products(id), yield_ml REAL);
CREATE TABLE IF NOT EXISTS recipe_lines (
  recipe_id INTEGER NOT NULL REFERENCES recipes(id), product_id INTEGER NOT NULL REFERENCES products(id),
  ml REAL NOT NULL, PRIMARY KEY (recipe_id, product_id));
CREATE TABLE IF NOT EXISTS mappings (
  item_key TEXT PRIMARY KEY, item_name TEXT NOT NULL, recipe_id INTEGER REFERENCES recipes(id),
  product_id INTEGER REFERENCES products(id), ml REAL);
CREATE TABLE IF NOT EXISTS deliveries (
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, supplier TEXT NOT NULL DEFAULT '', ref TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft', lines TEXT NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS supplier_map (
  supplier TEXT NOT NULL, description TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id),
  units_per_line REAL NOT NULL DEFAULT 1, PRIMARY KEY (supplier, description));
CREATE TABLE IF NOT EXISTS checks (id INTEGER PRIMARY KEY, topic TEXT NOT NULL, detail TEXT NOT NULL,
  resolved INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sell_prices (
  token TEXT PRIMARY KEY, item TEXT NOT NULL, variation TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
  price REAL NOT NULL, product_id INTEGER REFERENCES products(id), ml REAL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(data_dir: str) -> sqlite3.Connection:
    os.makedirs(data_dir, exist_ok=True)
    conn = sqlite3.connect(os.path.join(data_dir, "venue.sqlite"), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.execute("UPDATE OR REPLACE pars SET location = ? WHERE location <> ?", (ALL, ALL))
    _add_column(conn, "recipes", "note", "TEXT NOT NULL DEFAULT ''")
    _add_column(conn, "mappings", "no_stock", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "sell_prices", "recipe_id", "INTEGER REFERENCES recipes(id)")
    return conn


def _add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def rows(conn: sqlite3.Connection, sql: str, *args: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, args)]


def product_label(p: dict[str, Any]) -> str:
    bits = [p["name"]]
    if p.get("variant") and p["variant"].lower() != "original":
        bits.append(p["variant"])
    return " ".join(bits) + f" ({p['unit_label']})"


# ── Stock ────────────────────────────────────────────────────────────────────

def _figures_at(conn, product_id: int, ts: str) -> dict[str, float]:
    """Units last counted at each location, as of a stocktake time."""
    out = {}
    for loc in LOCATIONS:
        row = conn.execute(
            "SELECT l.units FROM count_lines l JOIN counts c ON c.id = l.count_id "
            "WHERE l.product_id = ? AND c.location = ? AND c.ts <= ? ORDER BY c.ts DESC, c.id DESC LIMIT 1",
            (product_id, loc, ts),
        ).fetchone()
        out[loc] = row["units"] if row else 0.0
    return out


def _stocktakes(conn, product_id: int, limit: int) -> list[str]:
    return [r["ts"] for r in rows(
        conn, "SELECT DISTINCT c.ts FROM count_lines l JOIN counts c ON c.id = l.count_id "
              "WHERE l.product_id = ? ORDER BY c.ts DESC LIMIT ?", product_id, limit)]


def on_hand_ml(conn: sqlite3.Connection, product_id: int) -> float:
    taken = _stocktakes(conn, product_id, 1)
    unit_ml = conn.execute("SELECT unit_ml FROM products WHERE id = ?", (product_id,)).fetchone()[0]
    anchor = taken[0] if taken else ""
    base = sum(_figures_at(conn, product_id, anchor).values()) * unit_ml if taken else 0.0
    moved = conn.execute("SELECT COALESCE(SUM(ml), 0) FROM movements WHERE product_id = ? AND ts > ?",
                         (product_id, anchor)).fetchone()[0]
    return base + moved


def stock_lines(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """One line per product: overall stock now, plus where it was at the last stocktake."""
    out = []
    pars = {r["product_id"]: r["units"] for r in rows(conn, "SELECT * FROM pars")}
    for p in rows(conn, "SELECT * FROM products WHERE active = 1 ORDER BY category, subcategory, name, variant"):
        taken = _stocktakes(conn, p["id"], 1)
        units = on_hand_ml(conn, p["id"]) / p["unit_ml"]
        par = pars.get(p["id"])
        cost = p["unit_cost"]
        out.append({
            "product_id": p["id"], "label": product_label(p), "category": p["category"],
            "subcategory": p["subcategory"], "unit_label": p["unit_label"], "units": round(units, 2),
            "counted": _figures_at(conn, p["id"], taken[0]) if taken else {l: 0.0 for l in LOCATIONS},
            "par": par, "unit_cost": cost, "value": round(units * cost, 2) if cost is not None else None,
            "below_par": par is not None and units < par, "negative": units < -0.005,
        })
    return out


def add_count(conn, location: str, lines: dict[int, float], ts: str = "", label: str = "", user: str = "") -> int:
    if location not in LOCATIONS:
        raise ValueError("Unknown location")
    cur = conn.execute(
        "INSERT INTO counts (ts, location, label, user) VALUES (?, ?, ?, ?)", (ts or now(), location, label, user)
    )
    cid = cur.lastrowid
    conn.executemany(
        "INSERT INTO count_lines (count_id, product_id, units) VALUES (?, ?, ?)",
        [(cid, pid, float(u)) for pid, u in lines.items()],
    )
    return cid


def save_draft(conn, location: str, product_id: int, units: float | None, user: str = "") -> None:
    """Hold a figure until the stocktake is finished, so Bar and Cellar can be counted by different people."""
    if location not in LOCATIONS:
        raise ValueError("Unknown location")
    if units is None:
        conn.execute("DELETE FROM count_drafts WHERE location = ? AND product_id = ?", (location, product_id))
        return
    conn.execute("INSERT OR REPLACE INTO count_drafts (location, product_id, units, user) VALUES (?, ?, ?, ?)",
                 (location, product_id, float(units), user))


def one_sided(conn) -> list[str]:
    """Products with a draft at one location only that also hold a figure at the other."""
    out = []
    drafts = rows(conn, "SELECT product_id, GROUP_CONCAT(location) locs FROM count_drafts GROUP BY product_id")
    for d in drafts:
        missing = [l for l in LOCATIONS if l not in d["locs"].split(",")]
        if not missing:
            continue
        taken = _stocktakes(conn, d["product_id"], 1)
        if taken and _figures_at(conn, d["product_id"], taken[0])[missing[0]] > 0:
            p = conn.execute("SELECT * FROM products WHERE id = ?", (d["product_id"],)).fetchone()
            out.append(f"{product_label(dict(p))}: {missing[0]} not counted")
    return out


def finish_stocktake(conn, ts: str = "", label: str = "", user: str = "") -> dict[str, int]:
    """Commit both locations at one moment. That moment becomes the new starting point for
    each counted product; a location left blank for a product keeps its last counted figure."""
    ts = ts or now()
    result = {}
    for loc in LOCATIONS:
        lines = {r["product_id"]: r["units"] for r in rows(
            conn, "SELECT product_id, units FROM count_drafts WHERE location = ?", loc)}
        if lines:
            add_count(conn, loc, lines, ts=ts, label=label, user=user)
        result[loc] = len(lines)
    if not any(result.values()):
        raise ValueError("Nothing counted yet")
    conn.execute("DELETE FROM count_drafts")
    return result


def log_usage(conn, product_id: int, ml: float, reason: str, note: str = "", user: str = "") -> None:
    """Manual wastage/overpour/training/staff drinks entry, for anything not rung through Square."""
    if reason not in REASONS:
        raise ValueError("Reason must be wastage, overpour, training or staff")
    if ml <= 0:
        raise ValueError("Check the amount")
    _move(conn, now(), product_id, -ml, reason, note=note, user=user)


def _move(conn, ts, product_id, ml, kind, event_id=None, ref="", note="", user="") -> None:
    conn.execute(
        "INSERT INTO movements (ts, product_id, location, ml, kind, event_id, ref, note, user) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, product_id, ALL, ml, kind, event_id, ref, note, user),
    )


# ── Sales events → depletion ─────────────────────────────────────────────────

def item_key(name: str, variation: str = "") -> str:
    """Shared by CSV and API so one mapping serves both."""
    clean = lambda s: re.sub(r"\s+", " ", (s or "").strip().lower())
    v = clean(variation)
    return clean(name) + ("|" + v if v and v != "regular" else "")


def serve_lines(conn, mapping: dict[str, Any]) -> list[tuple[int, float]]:
    if mapping.get("recipe_id"):
        return [(r["product_id"], r["ml"]) for r in rows(
            conn, "SELECT product_id, ml FROM recipe_lines WHERE recipe_id = ?", mapping["recipe_id"])]
    if mapping.get("product_id"):
        ml = mapping.get("ml")
        if not ml:
            ml = conn.execute("SELECT unit_ml FROM products WHERE id = ?", (mapping["product_id"],)).fetchone()[0]
        return [(mapping["product_id"], ml)]
    return []


def apply_event(conn, event: dict[str, Any]) -> bool:
    """Write this event's movements once. Stays 'unmapped' until its item has a mapping."""
    mapping = conn.execute("SELECT * FROM mappings WHERE item_key = ?", (event["item_key"],)).fetchone()
    if mapping and mapping["no_stock"]:
        conn.execute("UPDATE events SET status = 'no_stock' WHERE id = ?", (event["id"],))
        return True
    lines = serve_lines(conn, dict(mapping)) if mapping else []
    if not lines:
        return False
    eid, ts, qty = event["id"], event["ts"], abs(event["qty"])
    for product_id, ml in lines:
        total = ml * qty
        if event["kind"] == "refund":
            # The drink was poured: the sale goes away but the stock does not come back.
            _move(conn, ts, product_id, total, "sale", eid, note="refund reverses sale")
            _move(conn, ts, product_id, -total, "refunded", eid)
        else:
            _move(conn, ts, product_id, -total, event["reason"] or "sale", eid)
    match = OVERPOUR_RE.search(event.get("modifiers") or "")
    if match and event["kind"] != "refund":
        main = max(lines, key=lambda x: x[1])[0]
        _move(conn, ts, main, -float(match.group(1)) * qty, "overpour", eid, note=match.group(0))
    conn.execute("UPDATE events SET status = 'applied' WHERE id = ?", (eid,))
    return True


def ingest(conn, events: list[dict[str, Any]], source: str, filename: str = "", user: str = "") -> dict[str, int]:
    """Idempotent: an event key already stored is skipped, so re-importing a file is harmless."""
    cur = conn.execute("INSERT INTO imports (ts, source, filename, user) VALUES (?, ?, ?, ?)",
                        (now(), source, filename, user))
    import_id = cur.lastrowid
    added = skipped = unmapped = 0
    for e in events:
        c = conn.execute(
            "INSERT OR IGNORE INTO events (key, import_id, ts, kind, item_key, item_name, qty, net, modifiers, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (e["key"], import_id, e["ts"], e.get("kind", "sale"), e["item_key"], e["item_name"], e["qty"],
             e.get("net", 0), e.get("modifiers", ""), e.get("reason", "")),
        )
        if not c.rowcount:
            skipped += 1
            continue
        added += 1
        stored = dict(conn.execute("SELECT * FROM events WHERE id = ?", (c.lastrowid,)).fetchone())
        if not apply_event(conn, stored):
            unmapped += 1
    conn.execute("UPDATE imports SET added = ?, skipped = ? WHERE id = ?", (added, skipped, import_id))
    return {"import_id": import_id, "added": added, "skipped": skipped, "unmapped": unmapped}


def undo_import(conn, import_id: int) -> int:
    ids = [r["id"] for r in rows(conn, "SELECT id FROM events WHERE import_id = ?", import_id)]
    for eid in ids:
        conn.execute("DELETE FROM movements WHERE event_id = ?", (eid,))
        conn.execute("DELETE FROM events WHERE id = ?", (eid,))
    conn.execute("UPDATE imports SET undone = 1 WHERE id = ?", (import_id,))
    return len(ids)


def set_mapping(conn, key: str, name: str, recipe_id=None, product_id=None, ml=None, no_stock: bool = False) -> int:
    """Save a mapping and apply any sales that were waiting for it. no_stock marks items that
    never use stock, such as food or soda from the gun, so they stop waiting for a mapping."""
    conn.execute(
        "INSERT INTO mappings (item_key, item_name, recipe_id, product_id, ml, no_stock) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(item_key) DO UPDATE SET item_name = excluded.item_name, recipe_id = excluded.recipe_id, "
        "product_id = excluded.product_id, ml = excluded.ml, no_stock = excluded.no_stock",
        (key, name, recipe_id, product_id, ml, int(no_stock)),
    )
    applied = 0
    for e in rows(conn, "SELECT * FROM events WHERE item_key = ? AND status = 'unmapped'", key):
        applied += 1 if apply_event(conn, e) else 0
    return applied


def set_reason(conn, event_id: int, reason: str) -> None:
    """Classify a comp that arrived without a usable reason."""
    if reason not in REASONS:
        raise ValueError("Reason must be wastage, overpour, training or staff")
    conn.execute("UPDATE events SET reason = ? WHERE id = ?", (reason, event_id))
    conn.execute("UPDATE movements SET kind = ? WHERE event_id = ? AND kind = 'comp'", (reason, event_id))


# ── Recipes and batches ──────────────────────────────────────────────────────

def save_recipe(conn, name: str, lines: list[dict[str, Any]], menu_price=None, batch_yield_ml=None, note: str = "") -> int:
    """A recipe with batch_yield_ml is a pre-mix: it gets its own stock product."""
    name = name.strip()
    if not name or not lines:
        raise ValueError("A recipe needs a name and at least one ingredient")
    existing = conn.execute("SELECT * FROM recipes WHERE name = ?", (name,)).fetchone()
    batch_pid = existing["batch_product_id"] if existing else None
    if batch_yield_ml and not batch_pid:
        cur = conn.execute(
            "INSERT INTO products (name, variant, category, subcategory, unit_label, unit_ml, is_batch) "
            "VALUES (?, 'Batch', 'Batches', 'Pre-mix', '1L batch', 1000, 1)", (name,))
        batch_pid = cur.lastrowid
    if existing:
        rid = existing["id"]
        conn.execute("UPDATE recipes SET menu_price = ?, batch_product_id = ?, yield_ml = ?, note = ? WHERE id = ?",
                     (menu_price, batch_pid, batch_yield_ml, note, rid))
        conn.execute("DELETE FROM recipe_lines WHERE recipe_id = ?", (rid,))
    else:
        rid = conn.execute(
            "INSERT INTO recipes (name, menu_price, batch_product_id, yield_ml, note) VALUES (?, ?, ?, ?, ?)",
            (name, menu_price, batch_pid, batch_yield_ml, note)).lastrowid
    for line in lines:
        conn.execute("INSERT INTO recipe_lines (recipe_id, product_id, ml) VALUES (?, ?, ?)",
                     (rid, int(line["product_id"]), float(line["ml"])))
    refresh_batch_costs(conn)
    return rid


def refresh_batch_costs(conn) -> None:
    """Keep each pre-mix's cost in step with its ingredients. A batch can be an ingredient of a batch."""
    batches = rows(conn, "SELECT * FROM recipes WHERE batch_product_id IS NOT NULL AND yield_ml > 0")
    for _ in batches:
        for r in batches:
            cost = recipe_cost(conn, r["id"])
            conn.execute("UPDATE products SET unit_cost = ? WHERE id = ?",
                         (None if cost is None else cost / r["yield_ml"] * 1000, r["batch_product_id"]))


def recipe_cost(conn, recipe_id: int) -> float | None:
    """Cost of one recipe run; None while any ingredient has no cost yet."""
    total = 0.0
    for r in rows(conn, "SELECT l.ml, p.unit_cost, p.unit_ml FROM recipe_lines l JOIN products p "
                        "ON p.id = l.product_id WHERE l.recipe_id = ?", recipe_id):
        if r["unit_cost"] is None:
            return None
        total += r["ml"] * r["unit_cost"] / r["unit_ml"]
    return total


def make_batch(conn, recipe_id: int, runs: float, user: str = "") -> float:
    """Deduct raw ingredients and add the pre-mix. Returns ml made."""
    recipe = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if not recipe or not recipe["batch_product_id"] or runs <= 0:
        raise ValueError("That recipe is not a batch")
    ts, ref = now(), f"batch:{recipe['name']}"
    for r in rows(conn, "SELECT * FROM recipe_lines WHERE recipe_id = ?", recipe_id):
        _move(conn, ts, r["product_id"], -r["ml"] * runs, "batch_out", ref=ref, user=user)
    made = recipe["yield_ml"] * runs
    _move(conn, ts, recipe["batch_product_id"], made, "batch_in", ref=ref, user=user)
    return made


# ── Deliveries ───────────────────────────────────────────────────────────────

def approve_delivery(conn, delivery_id: int, user: str = "") -> int:
    """Only approval changes stock. Lines: product_id, units, unit_cost, description."""
    d = conn.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,)).fetchone()
    if not d or d["status"] != "draft":
        raise ValueError("Delivery is not awaiting approval")
    lines = json.loads(d["lines"])
    missing = [l.get("description", "?") for l in lines if not l.get("product_id")]
    if missing:
        raise ValueError("Match every line to a product first: " + ", ".join(missing))
    for l in lines:
        pid, units = int(l["product_id"]), float(l["units"])
        unit_ml = conn.execute("SELECT unit_ml FROM products WHERE id = ?", (pid,)).fetchone()[0]
        _move(conn, d["ts"], pid, units * unit_ml, "received",
              ref=f"{d['supplier']} {d['ref']}".strip(), user=user)
        if l.get("unit_cost") is not None:
            conn.execute("UPDATE products SET unit_cost = ? WHERE id = ?", (float(l["unit_cost"]), pid))
        if l.get("description") and d["supplier"]:
            conn.execute(
                "INSERT OR REPLACE INTO supplier_map (supplier, description, product_id, units_per_line) "
                "VALUES (?, ?, ?, ?)",
                (d["supplier"], l["description"].lower(), pid, float(l.get("units_per_line") or 1)))
    conn.execute("UPDATE deliveries SET status = 'approved' WHERE id = ?", (delivery_id,))
    refresh_batch_costs(conn)
    return len(lines)


def merge_products(conn, source_id: int, target_id: int) -> None:
    """Fold one product into another. Units count one-for-one, so a merged 50cl bottle counts as
    one target bottle. The source is hidden, not deleted, and its history moves across."""
    src = conn.execute("SELECT * FROM products WHERE id = ?", (source_id,)).fetchone()
    for line in rows(conn, "SELECT * FROM count_lines WHERE product_id = ?", source_id):
        conn.execute("INSERT INTO count_lines (count_id, product_id, units) VALUES (?, ?, ?) "
                     "ON CONFLICT(count_id, product_id) DO UPDATE SET units = units + excluded.units",
                     (line["count_id"], target_id, line["units"]))
    conn.execute("DELETE FROM count_lines WHERE product_id = ?", (source_id,))
    conn.execute("UPDATE OR IGNORE pars SET product_id = ? WHERE product_id = ?", (target_id, source_id))
    conn.execute("DELETE FROM pars WHERE product_id = ?", (source_id,))
    for table in ("movements", "mappings", "sell_prices", "supplier_map", "recipe_lines"):
        conn.execute(f"UPDATE OR IGNORE {table} SET product_id = ? WHERE product_id = ?", (target_id, source_id))
    conn.execute("DELETE FROM recipe_lines WHERE product_id = ?", (source_id,))
    conn.execute("UPDATE products SET unit_cost = COALESCE(unit_cost, ?) WHERE id = ?", (src["unit_cost"], target_id))
    conn.execute("UPDATE products SET active = 0 WHERE id = ?", (source_id,))
    for d in rows(conn, "SELECT id, lines FROM deliveries"):
        lines = json.loads(d["lines"])
        for line in lines:
            if line.get("product_id") == source_id:
                line["product_id"] = target_id
        conn.execute("UPDATE deliveries SET lines = ? WHERE id = ?", (json.dumps(lines), d["id"]))


# ── Selling prices ───────────────────────────────────────────────────────────

VAT_RATE = 0.20


def price_lines(conn) -> list[dict[str, Any]]:
    """Square selling prices (VAT inclusive). Margin needs a stock match, a serve size and a cost."""
    out = []
    for r in rows(conn, "SELECT s.*, p.name, p.variant, p.unit_label, p.unit_ml, p.unit_cost, c.name recipe "
                        "FROM sell_prices s LEFT JOIN products p ON p.id = s.product_id "
                        "LEFT JOIN recipes c ON c.id = s.recipe_id ORDER BY s.category, s.item, s.price"):
        cost = None
        if r["recipe_id"]:
            cost = recipe_cost(conn, r["recipe_id"])
        elif r["unit_cost"] is not None and r["ml"]:
            cost = r["unit_cost"] / r["unit_ml"] * r["ml"]
        net = r["price"] / (1 + VAT_RATE)
        target = f"Recipe: {r['recipe']}" if r["recipe_id"] else product_label(r) if r["product_id"] else None
        out.append({
            "token": r["token"], "item": r["item"], "variation": r["variation"], "category": r["category"],
            "price": r["price"], "product_id": r["product_id"], "ml": r["ml"], "product": target,
            "cost": round(cost, 2) if cost is not None else None,
            "gp_pct": round((net - cost) / net * 100, 1) if cost is not None and net > 0 else None,
        })
    return out


# ── Reports ──────────────────────────────────────────────────────────────────

def usage_report(conn, start: str, end: str) -> dict[str, Any]:
    """Usage in ml and £ per product, split by kind."""
    out: dict[int, dict[str, Any]] = {}
    for r in rows(
        conn,
        "SELECT m.kind, m.product_id, SUM(m.ml) ml, p.name, p.variant, p.unit_label, p.unit_ml, p.unit_cost "
        "FROM movements m JOIN products p ON p.id = m.product_id WHERE m.ts >= ? AND m.ts < ? AND m.kind IN "
        f"({','.join('?' * len(USAGE_KINDS))}) GROUP BY m.kind, m.product_id",
        start, end, *USAGE_KINDS,
    ):
        row = out.setdefault(r["product_id"], {
            "label": product_label(r), **{k: 0.0 for k in USAGE_KINDS}, "cost": 0.0})
        used = -r["ml"]
        row[r["kind"]] = round(used, 1)
        if r["unit_cost"] is not None:
            row["cost"] = round(row["cost"] + used * r["unit_cost"] / r["unit_ml"], 2)
    lines = sorted(out.values(), key=lambda x: x["label"])
    totals = {k: round(sum(l[k] for l in lines), 1) for k in USAGE_KINDS}
    return {"lines": lines, "totals_ml": totals}


def variance_report(conn) -> list[dict[str, Any]]:
    """Between each product's last two stocktakes (Bar + Cellar added together):
    opening + movements in − usage = expected; counted − expected = variance."""
    out = []
    for p in rows(conn, "SELECT * FROM products WHERE active = 1 ORDER BY category, name"):
        taken = _stocktakes(conn, p["id"], 2)
        if len(taken) < 2:
            continue
        closing_ts, opening_ts = taken
        opening = _figures_at(conn, p["id"], opening_ts)
        closing = _figures_at(conn, p["id"], closing_ts)
        moves = {r["kind"]: r["ml"] for r in rows(
            conn, "SELECT kind, SUM(ml) ml FROM movements WHERE product_id = ? AND ts > ? AND ts <= ? GROUP BY kind",
            p["id"], opening_ts, closing_ts)}
        expected = sum(opening.values()) * p["unit_ml"] + sum(moves.values())
        total = sum(closing.values())
        diff_ml = total * p["unit_ml"] - expected
        out.append({
            "label": product_label(p), "opening_units": round(sum(opening.values()), 2), "closing_bar": closing["Bar"],
            "closing_cellar": closing["Cellar"], "closing_units": round(total, 2),
            "expected_units": round(expected / p["unit_ml"], 2), "moves_ml": {k: round(v, 1) for k, v in moves.items()},
            "variance_ml": round(diff_ml, 1), "variance_units": round(diff_ml / p["unit_ml"], 2),
            "variance_value": round(diff_ml / p["unit_ml"] * p["unit_cost"], 2) if p["unit_cost"] is not None else None,
        })
    return out
