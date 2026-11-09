"""Venue stock ledger (SQLite). Added in this fork.

Stock is one overall figure per product. Bar and Cellar exist only in stocktakes:
on hand is the Bar and Cellar figures from the product's latest stocktake added
together, plus every movement since. Movements are append-only; usage kinds split
sales from wastage, overpour, training, staff drinks and comps.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any

LOCATIONS = ("Bar", "Cellar")
ALL = "All"  # pars and movements apply to overall stock, not a location
USAGE_KINDS = ("sale", "wastage", "overpour", "training", "staff", "comp", "refunded")
REASONS = ("wastage", "overpour", "training", "staff")
LOSS_KINDS = ("wastage", "overpour", "training", "staff", "comp", "refunded")
# A night's trade runs past midnight, so anything before 5am counts towards the evening before.
DAY_START_HOURS = 5
TRADING_DAY = f"date(ts, '-{DAY_START_HOURS} hours')"
CUSTOM = "other:"  # a reason the venue typed in, kept as "other:Breakage"
_q = lambda kinds: ",".join(f"'{k}'" for k in kinds)
LOSS_SQL = f"(m.kind IN ({_q(LOSS_KINDS)}) OR m.kind LIKE '{CUSTOM}%')"
USE_SQL = f"(m.kind IN ({_q(USAGE_KINDS)}) OR m.kind LIKE '{CUSTOM}%')"
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
    _add_column(conn, "recipes", "special", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "recipes", "active", "INTEGER NOT NULL DEFAULT 1")
    _add_column(conn, "events", "category", "TEXT NOT NULL DEFAULT ''")
    # Cost at the time of each movement, so a later price change does not rewrite past GP.
    _add_column(conn, "movements", "cost_per_ml", "REAL")
    _add_column(conn, "count_lines", "counted_by", "TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, "
                 "kind TEXT NOT NULL, ref TEXT NOT NULL, label TEXT NOT NULL, old REAL, new REAL, "
                 "source TEXT NOT NULL DEFAULT '', user TEXT NOT NULL DEFAULT '')")
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


def add_count(conn, location: str, lines: dict[int, float], ts: str = "", label: str = "", user: str = "",
              counted_by: dict[int, str] | None = None) -> int:
    if location not in LOCATIONS:
        raise ValueError("Unknown location")
    cur = conn.execute(
        "INSERT INTO counts (ts, location, label, user) VALUES (?, ?, ?, ?)", (ts or now(), location, label, user)
    )
    cid = cur.lastrowid
    conn.executemany(
        "INSERT INTO count_lines (count_id, product_id, units, counted_by) VALUES (?, ?, ?, ?)",
        [(cid, pid, float(u), (counted_by or {}).get(pid, "")) for pid, u in lines.items()],
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
    if ts:
        when = datetime.fromisoformat(ts)
        if when > datetime.now():
            raise ValueError("The count time is in the future")
        ts = when.isoformat(timespec="seconds")
        last = conn.execute("SELECT MAX(ts) FROM counts").fetchone()[0]
        if last and ts <= last:
            raise ValueError(f"The count time must be after the last stocktake ({last.replace('T', ' ')})")
    ts = ts or now()
    result = {}
    for loc in LOCATIONS:
        lines = {r["product_id"]: r["units"] for r in rows(
            conn, "SELECT product_id, units FROM count_drafts WHERE location = ?", loc)}
        who = {r["product_id"]: r["user"] for r in rows(
            conn, "SELECT product_id, user FROM count_drafts WHERE location = ?", loc)}
        if lines:
            add_count(conn, loc, lines, ts=ts, label=label, user=user, counted_by=who)
        result[loc] = len(lines)
    if not any(result.values()):
        raise ValueError("Nothing counted yet")
    conn.execute("DELETE FROM count_drafts")
    return result


def loss_kind(reason: str) -> str:
    """One of the standard reasons, or the venue's own (\"Breakage\", \"Tasting\") stored as other:Breakage."""
    reason = re.sub(r"\s+", " ", (reason or "").strip())
    if reason.lower() in REASONS:
        return reason.lower()
    if reason.lower().startswith(CUSTOM):
        reason = reason[len(CUSTOM):].strip()
    if not reason or len(reason) > 40:
        raise ValueError("Give a reason of up to 40 characters")
    if reason.lower() in USAGE_KINDS + ("received", "batch_in", "batch_out", "staff drink", "staff drinks"):
        return {"staff drink": "staff", "staff drinks": "staff"}.get(reason.lower(), reason.lower())
    return CUSTOM + reason[0].upper() + reason[1:]


def custom_reasons(conn) -> list[str]:
    return [r[0][len(CUSTOM):] for r in conn.execute(
        "SELECT kind FROM movements WHERE kind LIKE ? GROUP BY kind ORDER BY COUNT(*) DESC", (CUSTOM + "%",))]


def log_usage(conn, product_id: int, ml: float, reason: str, note: str = "", user: str = "") -> None:
    """Manual wastage/overpour/training/staff drinks entry, for anything not rung through Square."""
    kind = loss_kind(reason)
    if kind not in REASONS and not kind.startswith(CUSTOM):
        raise ValueError("That reason is for sales, not wastage")
    if ml <= 0:
        raise ValueError("Check the amount")
    _move(conn, now(), product_id, -ml, kind, note=note, user=user)


def _move(conn, ts, product_id, ml, kind, event_id=None, ref="", note="", user="") -> None:
    p = conn.execute("SELECT unit_cost, unit_ml FROM products WHERE id = ?", (product_id,)).fetchone()
    per_ml = p["unit_cost"] / p["unit_ml"] if p and p["unit_cost"] is not None and p["unit_ml"] else None
    conn.execute(
        "INSERT INTO movements (ts, product_id, location, ml, kind, event_id, ref, note, user, cost_per_ml) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, product_id, ALL, ml, kind, event_id, ref, note, user, per_ml),
    )


# ── Sales events > depletion ─────────────────────────────────────────────────

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
    if not mapping and _auto_map(conn, event["item_key"], event["item_name"]):
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


def _auto_map(conn, key: str, name: str) -> bool:
    """A Square item named exactly like an active recipe maps to it, so a new special needs no mapping step."""
    for r in rows(conn, "SELECT id, name FROM recipes WHERE active = 1"):
        if item_key(r["name"]) == key:
            conn.execute("INSERT OR IGNORE INTO mappings (item_key, item_name, recipe_id) VALUES (?, ?, ?)",
                         (key, name, r["id"]))
            return True
    return False


def ingest(conn, events: list[dict[str, Any]], source: str, filename: str = "", user: str = "") -> dict[str, int]:
    """Idempotent: an event key already stored is skipped, so re-importing a file is harmless."""
    cur = conn.execute("INSERT INTO imports (ts, source, filename, user) VALUES (?, ?, ?, ?)",
                        (now(), source, filename, user))
    import_id = cur.lastrowid
    added = skipped = unmapped = 0
    for e in events:
        c = conn.execute(
            "INSERT OR IGNORE INTO events (key, import_id, ts, kind, item_key, item_name, qty, net, modifiers, reason, "
            "category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (e["key"], import_id, e["ts"], e.get("kind", "sale"), e["item_key"], e["item_name"], e["qty"],
             e.get("net", 0), e.get("modifiers", ""), e.get("reason", ""), e.get("category", "")),
        )
        if not c.rowcount:
            skipped += 1
            continue
        added += 1
        stored = dict(conn.execute("SELECT * FROM events WHERE id = ?", (c.lastrowid,)).fetchone())
        if not apply_event(conn, stored):
            unmapped += 1
    conn.execute("UPDATE imports SET added = ?, skipped = ? WHERE id = ?", (added, skipped, import_id))
    span = conn.execute(f"SELECT MIN({TRADING_DAY}), MAX({TRADING_DAY}), COALESCE(SUM(net), 0), "
                        "COALESCE(SUM(CASE WHEN kind = 'sale' AND reason = '' THEN qty "
                        "WHEN kind = 'refund' THEN -qty ELSE 0 END), 0) FROM events WHERE import_id = ?",
                        (import_id,)).fetchone()
    waiting = conn.execute("SELECT COUNT(DISTINCT item_key) FROM events WHERE status = 'unmapped'").fetchone()[0]
    return {"import_id": import_id, "added": added, "skipped": skipped, "unmapped": unmapped,
            "first_day": span[0], "last_day": span[1], "takings": round(span[2], 2), "drinks": span[3],
            "items_waiting": waiting}


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


def delete_mapping(conn, key: str) -> None:
    """Forget a mapping. Sales already applied keep their stock movements; future ones wait again."""
    conn.execute("DELETE FROM mappings WHERE item_key = ?", (key,))


def set_reason(conn, event_id: int, reason: str) -> None:
    """Classify a comp that arrived without a usable reason."""
    reason = loss_kind(reason)
    if reason not in REASONS and not reason.startswith(CUSTOM):
        raise ValueError("Choose wastage, overpour, training, staff or your own reason")
    conn.execute("UPDATE events SET reason = ? WHERE id = ?", (reason, event_id))
    conn.execute("UPDATE movements SET kind = ? WHERE event_id = ? AND kind = 'comp'", (reason, event_id))


# ── Recipes and batches ──────────────────────────────────────────────────────

def save_recipe(conn, name: str, lines: list[dict[str, Any]], menu_price=None, batch_yield_ml=None, note: str = "",
                recipe_id: int | None = None, special: bool = False, square_items: list[dict[str, str]] | None = None) -> int:
    """A recipe with batch_yield_ml is a pre-mix: it gets its own stock product. Passing recipe_id edits
    (and can rename) that recipe; otherwise saving an existing name replaces it. square_items are
    Square buttons to point at this recipe; any waiting sales of them apply straight away."""
    name = name.strip()
    lines = [l for l in lines if l.get("product_id") and l.get("ml") not in ("", None)]
    if not name or not lines:
        raise ValueError("A drink needs a name and at least one ingredient")
    if any(float(l["ml"]) <= 0 for l in lines):
        raise ValueError("Each ingredient needs an amount above 0")
    if len({int(l["product_id"]) for l in lines}) != len(lines):
        raise ValueError("An ingredient is listed twice")
    clash = conn.execute("SELECT id FROM recipes WHERE name = ?", (name,)).fetchone()
    if recipe_id:
        existing = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if not existing:
            raise ValueError("That drink no longer exists")
        if clash and clash["id"] != existing["id"]:
            raise ValueError(f"There is already a drink called {name}")
    else:
        existing = conn.execute("SELECT * FROM recipes WHERE name = ?", (name,)).fetchone()
    batch_pid = existing["batch_product_id"] if existing else None
    if batch_yield_ml and not batch_pid:
        cur = conn.execute(
            "INSERT INTO products (name, variant, category, subcategory, unit_label, unit_ml, is_batch) "
            "VALUES (?, 'Batch', 'Batches', 'Pre-mix', '1L batch', 1000, 1)", (name,))
        batch_pid = cur.lastrowid
    elif batch_pid and existing["name"] != name:
        conn.execute("UPDATE products SET name = ? WHERE id = ?", (name, batch_pid))
    if existing:
        rid = existing["id"]
        conn.execute("UPDATE recipes SET name = ?, menu_price = ?, batch_product_id = ?, yield_ml = ?, note = ?, "
                     "special = ? WHERE id = ?",
                     (name, menu_price, batch_pid, batch_yield_ml, note, int(special), rid))
        conn.execute("DELETE FROM recipe_lines WHERE recipe_id = ?", (rid,))
    else:
        rid = conn.execute(
            "INSERT INTO recipes (name, menu_price, batch_product_id, yield_ml, note, special) VALUES (?, ?, ?, ?, ?, ?)",
            (name, menu_price, batch_pid, batch_yield_ml, note, int(special))).lastrowid
    for line in lines:
        conn.execute("INSERT INTO recipe_lines (recipe_id, product_id, ml) VALUES (?, ?, ?)",
                     (rid, int(line["product_id"]), float(line["ml"])))
    refresh_batch_costs(conn)
    for item in square_items or []:
        set_mapping(conn, item["item_key"], item.get("item_name") or item["item_key"], recipe_id=rid)
    for e in rows(conn, "SELECT DISTINCT item_key, item_name FROM events WHERE status = 'unmapped' AND item_key = ?",
                  item_key(name)):
        set_mapping(conn, e["item_key"], e["item_name"], recipe_id=rid)
    return rid


def set_recipe_active(conn, recipe_id: int, active: bool) -> None:
    """Archive a drink that is off the menu, or bring it back. Its past sales are untouched."""
    conn.execute("UPDATE recipes SET active = ? WHERE id = ?", (int(active), recipe_id))


def delete_recipe(conn, recipe_id: int) -> None:
    """Only for a drink nothing points at yet, such as a typo. Anything in use is archived instead."""
    r = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if not r:
        raise ValueError("That drink no longer exists")
    used = (conn.execute("SELECT 1 FROM mappings WHERE recipe_id = ?", (recipe_id,)).fetchone()
            or conn.execute("SELECT 1 FROM sell_prices WHERE recipe_id = ?", (recipe_id,)).fetchone()
            or conn.execute("SELECT 1 FROM recipe_lines WHERE product_id = ?", (r["batch_product_id"],)).fetchone()
            or conn.execute("SELECT 1 FROM movements WHERE product_id = ?", (r["batch_product_id"],)).fetchone())
    if used:
        raise ValueError("This drink is linked to Square items or stock, so archive it instead")
    conn.execute("DELETE FROM recipe_lines WHERE recipe_id = ?", (recipe_id,))
    conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    if r["batch_product_id"]:
        conn.execute("DELETE FROM pars WHERE product_id = ?", (r["batch_product_id"],))
        conn.execute("DELETE FROM count_drafts WHERE product_id = ?", (r["batch_product_id"],))
        if not conn.execute("SELECT 1 FROM count_lines WHERE product_id = ?", (r["batch_product_id"],)).fetchone():
            conn.execute("DELETE FROM products WHERE id = ?", (r["batch_product_id"],))
        else:
            conn.execute("UPDATE products SET active = 0 WHERE id = ?", (r["batch_product_id"],))


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


def make_batch(conn, recipe_id: int, runs: float, user: str = "", made_ml: float | None = None) -> float:
    """Deduct raw ingredients and add the pre-mix. made_ml records what actually came out when it
    differs from the recipe's yield (dilution, a short bottle). Returns ml made."""
    recipe = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if not recipe or not recipe["batch_product_id"] or runs <= 0:
        raise ValueError("That recipe is not a batch")
    ts, ref = now(), f"batch:{recipe['name']}"
    for r in rows(conn, "SELECT * FROM recipe_lines WHERE recipe_id = ?", recipe_id):
        _move(conn, ts, r["product_id"], -r["ml"] * runs, "batch_out", ref=ref, user=user)
    made = float(made_ml) if made_ml else recipe["yield_ml"] * runs
    if made <= 0:
        raise ValueError("Check the amount made")
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
        if l.get("unit_cost") not in (None, ""):
            set_cost(conn, pid, float(l["unit_cost"]), f"delivery {d['supplier']} {d['ref']}".strip(), user)
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


# ── Products ─────────────────────────────────────────────────────────────────

PRODUCT_FIELDS = ("name", "variant", "category", "subcategory", "supplier")


def set_cost(conn, product_id: int, cost: float | None, source: str = "", user: str = "") -> None:
    """Change what a product costs to buy, keeping a record of the old and new price."""
    p = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    old = p["unit_cost"]
    if (old is None and cost is None) or (old is not None and cost is not None and abs(old - cost) < 0.005):
        return
    conn.execute("UPDATE products SET unit_cost = ? WHERE id = ?", (cost, product_id))
    conn.execute("INSERT INTO price_history (ts, kind, ref, label, old, new, source, user) VALUES (?, 'cost', ?, ?, ?, ?, ?, ?)",
                 (now(), str(product_id), product_label(dict(p)), old, cost, source, user))


def log_sell_price(conn, token: str, label: str, old: float | None, new: float) -> None:
    if old is not None and abs(old - new) < 0.005:
        return
    conn.execute("INSERT INTO price_history (ts, kind, ref, label, old, new, source) VALUES (?, 'sell', ?, ?, ?, ?, ?)",
                 (now(), token, label, old, new, "Square catalogue"))


def save_product(conn, b: dict[str, Any], product_id: int | None = None, user: str = "") -> int:
    """Add or edit a product. unit_label is read for the size (\"70cl bottle\"). A product that has
    been counted or moved keeps its size, since changing it would rewrite the stock it holds."""
    import venue_import

    name = (b.get("name") if "name" in b else None)
    if product_id is None and not (name or "").strip():
        raise ValueError("A product needs a name")
    fields: dict[str, Any] = {k: str(b[k]).strip() for k in PRODUCT_FIELDS if k in b}
    if "name" in fields and not fields["name"]:
        raise ValueError("A product needs a name")
    if b.get("unit_label"):
        unit_ml, measure = venue_import.parse_unit(b["unit_label"])
        if product_id is not None:
            old = conn.execute("SELECT unit_ml FROM products WHERE id = ?", (product_id,)).fetchone()
            used = (conn.execute("SELECT 1 FROM count_lines WHERE product_id = ?", (product_id,)).fetchone()
                    or conn.execute("SELECT 1 FROM movements WHERE product_id = ?", (product_id,)).fetchone())
            if used and abs(old["unit_ml"] - unit_ml) > 0.001:
                raise ValueError("This product already has stock history, so its size cannot change. "
                                 "Add the new size as its own product and archive this one")
        fields.update(unit_label=b["unit_label"].strip(), unit_ml=unit_ml, measure=measure)
    new_cost = None if b.get("unit_cost") in ("", None) else float(b["unit_cost"])
    if new_cost is not None and new_cost < 0:
        raise ValueError("A cost cannot be below zero")
    if "active" in b:
        fields["active"] = int(bool(b["active"]))
    is_new = product_id is None
    if is_new:
        if "unit_ml" not in fields:
            raise ValueError("Give the size, such as 70cl bottle or 50L keg")
        cols = ", ".join(fields)
        product_id = conn.execute(f"INSERT INTO products ({cols}) VALUES ({', '.join('?' * len(fields))})",
                                  tuple(fields.values())).lastrowid
    elif fields:
        conn.execute(f"UPDATE products SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                     (*fields.values(), product_id))
    if "unit_cost" in b:
        set_cost(conn, product_id, new_cost, "new product" if is_new else "edited", user)
    if "par" in b:
        conn.execute("DELETE FROM pars WHERE product_id = ?", (product_id,))
        if b["par"] not in ("", None):
            conn.execute("INSERT INTO pars (product_id, location, units) VALUES (?, ?, ?)",
                         (product_id, ALL, float(b["par"])))
    refresh_batch_costs(conn)
    return product_id


# ── Dashboard ────────────────────────────────────────────────────────────────

def _bounds(start: str, end: str) -> tuple[str, str]:
    """Trading days start..end inclusive, as timestamps from 5am to 5am."""
    lo = datetime.fromisoformat(start).replace(hour=DAY_START_HOURS)
    hi = datetime.fromisoformat(end).replace(hour=DAY_START_HOURS) + timedelta(days=1)
    return lo.isoformat(timespec="seconds"), hi.isoformat(timespec="seconds")


def last_trading_day(conn) -> str | None:
    return conn.execute(f"SELECT MAX({TRADING_DAY}) FROM events").fetchone()[0]


_SOLD = "CASE WHEN e.kind = 'sale' AND e.reason = '' THEN e.qty WHEN e.kind = 'refund' THEN -e.qty ELSE 0 END"
_PER_ML = "COALESCE(m.cost_per_ml, p.unit_cost / p.unit_ml)"
_COST = f"-m.ml * {_PER_ML}"


def _gp(takings_inc_vat: float, cost: float) -> float | None:
    ex = takings_inc_vat / (1 + VAT_RATE)
    return round((ex - cost) / ex * 100, 1) if ex > 0 else None


def _takings(conn, lo: str, hi: str) -> tuple[float, float]:
    r = conn.execute(f"SELECT COALESCE(SUM(e.net), 0), COALESCE(SUM({_SOLD}), 0) FROM events e "
                     "WHERE e.ts >= ? AND e.ts < ?", (lo, hi)).fetchone()
    return round(r[0], 2), r[1]


def dashboard(conn, start: str, end: str) -> dict[str, Any]:
    """Everything the manager's front page shows for trading days start..end."""
    lo, hi = _bounds(start, end)
    days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1
    plo, phi = _bounds((datetime.fromisoformat(start) - timedelta(days=days)).date().isoformat(),
                       (datetime.fromisoformat(start) - timedelta(days=1)).date().isoformat())

    cost_by_item = {r["item_key"]: r for r in rows(
        conn, f"SELECT e.item_key, SUM({_COST}) cost, SUM({_PER_ML} IS NULL) uncosted FROM movements m "
              "JOIN events e ON e.id = m.event_id JOIN products p ON p.id = m.product_id "
              "WHERE e.ts >= ? AND e.ts < ? AND m.kind = 'sale' GROUP BY e.item_key", lo, hi)}
    items = []
    for r in rows(conn, f"SELECT e.item_key, MAX(e.item_name) item, MAX(e.category) category, SUM({_SOLD}) qty, "
                        "SUM(CASE WHEN e.kind = 'sale' AND e.reason <> '' THEN e.qty ELSE 0 END) comped, "
                        "COALESCE(SUM(e.net), 0) takings, SUM(e.status = 'unmapped') waiting, "
                        "MAX(e.status = 'no_stock') no_stock FROM events e WHERE e.ts >= ? AND e.ts < ? "
                        "GROUP BY e.item_key", lo, hi):
        c = cost_by_item.get(r["item_key"])
        cost = round(c["cost"], 2) if c and c["cost"] is not None and not c["uncosted"] else None
        ex_vat = r["takings"] / (1 + VAT_RATE)
        items.append({**r, "takings": round(r["takings"], 2), "cost": cost,
                      "gp_pct": round((ex_vat - cost) / ex_vat * 100, 1) if cost is not None and ex_vat > 0 else None})
    items.sort(key=lambda x: (-x["takings"], -x["qty"]))

    usage: dict[int, dict[str, Any]] = {}
    for r in rows(conn, f"SELECT m.product_id, m.kind, SUM(m.ml) ml, SUM({_COST}) cost, "
                        f"SUM({_PER_ML} IS NULL) uncosted FROM movements m "
                        f"JOIN products p ON p.id = m.product_id WHERE m.ts >= ? AND m.ts < ? AND {USE_SQL} "
                        "GROUP BY m.product_id, m.kind", lo, hi):
        u = usage.setdefault(r["product_id"], {"product_id": r["product_id"], "sold_ml": 0.0, "lost_ml": 0.0,
                                               "sold_cost": 0.0, "lost_cost": 0.0, "uncosted": 0})
        u["uncosted"] += r["uncosted"]
        side = "sold" if r["kind"] == "sale" else "lost"
        u[f"{side}_ml"] += -r["ml"]
        u[f"{side}_cost"] += r["cost"] or 0.0

    products = {p["id"]: p for p in rows(conn, "SELECT * FROM products")}
    stock = {s["product_id"]: s for s in stock_lines(conn)}
    nights = conn.execute(f"SELECT COUNT(DISTINCT {TRADING_DAY}) FROM events WHERE ts >= ? AND ts < ?",
                          (lo, hi)).fetchone()[0]
    usage_lines = []
    for pid, u in usage.items():
        p = products[pid]
        usage_lines.append({
            **u, "label": product_label(p), "category": p["category"], "unit_ml": p["unit_ml"],
            "measure": p["measure"], "unit_label": p["unit_label"],
            "sold_ml": round(u["sold_ml"], 1), "lost_ml": round(u["lost_ml"], 1),
            "sold_cost": None if u["uncosted"] else round(u["sold_cost"], 2),
            "lost_cost": None if u["uncosted"] else round(u["lost_cost"], 2),
            "in_stock": stock[pid]["units"] if pid in stock else None,
        })
    usage_lines.sort(key=lambda x: -(x["sold_cost"] or 0) - x["sold_ml"] / 1e6)

    losses = rows(conn, f"SELECT m.kind reason, COUNT(*) entries, SUM(-m.ml) ml, SUM({_COST}) cost FROM movements m "
                        f"JOIN products p ON p.id = m.product_id WHERE m.ts >= ? AND m.ts < ? AND {LOSS_SQL} "
                        "GROUP BY m.kind ORDER BY cost DESC", lo, hi)
    for l in losses:
        l["cost"] = round(l["cost"] or 0, 2)
    loss_lines = rows(conn, f"SELECT m.ts, m.kind reason, -m.ml ml, {_COST} cost, m.note, m.user, p.name, p.variant, "
                            "p.unit_label, p.measure FROM movements m JOIN products p ON p.id = m.product_id "
                            f"WHERE m.ts >= ? AND m.ts < ? AND {LOSS_SQL} ORDER BY m.ts DESC LIMIT 300", lo, hi)
    for l in loss_lines:
        l["label"] = product_label(l)
        l["cost"] = None if l["cost"] is None else round(l["cost"], 2)

    by_day = rows(conn, f"SELECT {TRADING_DAY.replace('ts', 'e.ts')} day, SUM({_SOLD}) drinks, "
                        "COALESCE(SUM(e.net), 0) takings FROM events e WHERE e.ts >= ? AND e.ts < ? "
                        "GROUP BY day ORDER BY day", lo, hi)
    day_cost = {r["day"]: r["cost"] for r in rows(
        conn, f"SELECT {TRADING_DAY.replace('ts', 'm.ts')} day, SUM({_COST}) cost FROM movements m "
              "JOIN products p ON p.id = m.product_id WHERE m.ts >= ? AND m.ts < ? AND m.kind = 'sale' GROUP BY day",
              lo, hi)}
    for d in by_day:
        d["takings"] = round(d["takings"], 2)
        d["cost"] = round(day_cost.get(d["day"]) or 0, 2)

    # Hour by hour through the night, in trading order (5am first, so 1am sorts after 11pm).
    by_hour = rows(conn, f"SELECT CAST(strftime('%H', e.ts) AS INTEGER) hour, SUM({_SOLD}) drinks, "
                         "COALESCE(SUM(e.net), 0) takings FROM events e WHERE e.ts >= ? AND e.ts < ? GROUP BY hour", lo, hi)
    by_hour.sort(key=lambda h: (h["hour"] - DAY_START_HOURS) % 24)
    for h in by_hour:
        h["takings"] = round(h["takings"], 2)

    by_category: dict[str, dict[str, Any]] = {}
    for i in items:
        c = by_category.setdefault(i["category"] or "Uncategorised", {"category": i["category"] or "Uncategorised",
                                                                      "qty": 0, "takings": 0.0, "_costed": 0.0,
                                                                      "_cost": 0.0})
        c["qty"] += i["qty"]
        c["takings"] = round(c["takings"] + i["takings"], 2)
        if i["cost"] is not None:
            c["_costed"] += i["takings"]
            c["_cost"] += i["cost"]
    categories = sorted(by_category.values(), key=lambda x: -x["takings"])
    for c in categories:
        c["gp_pct"] = _gp(c.pop("_costed"), c.pop("_cost"))

    # Reorder: average use per trading night over the last four weeks, against what is on hand now.
    rlo = (datetime.now() - timedelta(days=28)).isoformat(timespec="seconds")
    recent_nights = conn.execute(f"SELECT COUNT(DISTINCT {TRADING_DAY}) FROM events WHERE ts >= ?",
                                 (rlo,)).fetchone()[0] or 0
    recent_use = {r["product_id"]: -r["ml"] for r in rows(
        conn, f"SELECT m.product_id, SUM(m.ml) ml FROM movements m WHERE m.ts >= ? AND {USE_SQL} "
              "GROUP BY m.product_id", rlo)}
    reorder, idle = [], []
    for pid, s in stock.items():
        p = products[pid]
        per_night = recent_use.get(pid, 0) / p["unit_ml"] / recent_nights if recent_nights else 0
        left = s["units"] / per_night if per_night > 0 else None
        line = {"product_id": pid, "label": s["label"], "category": s["category"], "units": s["units"],
                "unit_label": p["unit_label"], "par": s["par"], "per_night": round(per_night, 2),
                "nights_left": None if left is None else round(max(left, 0), 1), "value": s["value"]}
        if s["below_par"] or (left is not None and left < 3):
            line["order"] = max(0, math.ceil((s["par"] or 0) - s["units"])) if s["par"] is not None else None
            reorder.append(line)
        if s["units"] > 0 and pid not in recent_use and not p["is_batch"]:
            idle.append(line)
    reorder.sort(key=lambda x: (x["nights_left"] if x["nights_left"] is not None else 999, x["label"]))
    idle.sort(key=lambda x: -(x["value"] or 0))

    takings, drinks = _takings(conn, lo, hi)
    prev_takings, prev_drinks = _takings(conn, plo, phi)
    cost_of_sales = round(sum(u["sold_cost"] or 0 for u in usage_lines), 2)
    costed = [i for i in items if i["cost"] is not None]
    costed_takings = sum(i["takings"] for i in costed)
    last_import = conn.execute("SELECT ts FROM imports WHERE undone = 0 ORDER BY id DESC LIMIT 1").fetchone()
    last_count = conn.execute("SELECT MAX(ts) FROM counts").fetchone()[0]
    return {
        "from": start, "to": end, "nights": nights,
        "kpis": {
            "takings": takings, "prev_takings": prev_takings, "drinks": drinks, "prev_drinks": prev_drinks,
            "cost_of_sales": cost_of_sales,
            "gp_pct": _gp(costed_takings, sum(i["cost"] for i in costed)),
            "gp_cover_pct": round(costed_takings / takings * 100) if takings > 0 else None,
            "losses": round(sum(l["cost"] for l in losses), 2),
            "stock_value": round(sum(s["value"] or 0 for s in stock.values()), 2),
            "below_par": sum(1 for s in stock.values() if s["below_par"]),
            "negative": sum(1 for s in stock.values() if s["negative"]),
            "reorder": len(reorder),
            "waiting": conn.execute("SELECT COUNT(DISTINCT item_key) FROM events WHERE status = 'unmapped'").fetchone()[0],
            "comps": conn.execute("SELECT COUNT(*) FROM events WHERE reason = 'comp'").fetchone()[0],
            "last_import": last_import[0] if last_import else None, "last_count": last_count,
        },
        "items": items, "usage": usage_lines, "losses": losses, "loss_lines": loss_lines, "by_day": by_day, "by_hour": by_hour,
        "categories": categories, "reorder": reorder, "idle": idle[:40],
        "price_changes": rows(conn, "SELECT * FROM price_history WHERE ts >= ? AND ts < ? ORDER BY ts DESC", lo, hi),
    }


# ── Counts sent from a phone ─────────────────────────────────────────────────

MAX_UNITS = 100000


def _units(v: Any) -> float:
    u = float(v)
    if not 0 <= u <= MAX_UNITS:
        raise ValueError("A count in the phone file is out of range")
    return u


def phone_count(conn, data: dict[str, Any], add_new: bool = False, user: str = "") -> dict[str, Any]:
    """Fill the open stocktake from a phone count file. Only what was counted on the phone is filled in, so
    two phones (say Bar and Cellar) can each send their part. New items are listed, and only become
    products when add_new is set, so nobody creates a duplicate by accident."""
    import venue_import

    if not isinstance(data, dict) or data.get("kind") != "bar-stock-count":
        raise ValueError("That is not a count file from the phone page")
    who = str(data.get("by") or "").strip()[:40]
    who = f"{who} (phone)" if who else (user or "phone")
    active = {r["id"]: r for r in rows(conn, "SELECT * FROM products WHERE active = 1")}
    filled, skipped = {loc: 0 for loc in LOCATIONS}, []
    counts = data.get("counts") or {}
    for loc in LOCATIONS:
        for line in counts.get(loc) or []:
            pid, units = int(line[0]), _units(line[1])
            if pid not in active:
                skipped.append(str(line[2] if len(line) > 2 else pid)[:80])
                continue
            save_draft(conn, loc, pid, units, who)
            filled[loc] += 1
    new, added = [], []
    for item in data.get("new") or []:
        loc = item.get("loc")
        name = re.sub(r"\s+", " ", str(item.get("name") or "")).strip()[:80]
        size = str(item.get("size") or "").strip()[:40]
        if loc not in LOCATIONS or not name:
            continue
        units = _units(item.get("units") or 0)
        try:
            unit_ml, _ = venue_import.parse_unit(size)
        except ValueError:
            new.append({"loc": loc, "name": name, "size": size, "units": units, "why": "Size not understood, e.g. 70cl bottle"})
            continue
        same = next((p for p in active.values() if p["unit_ml"] == unit_ml and name.lower() in
                     (p["name"].lower(), f"{p['name']} {p['variant']}".strip().lower(), product_label(p).lower())), None)
        if same:
            save_draft(conn, loc, same["id"], units, who)
            filled[loc] += 1
            continue
        if not add_new:
            new.append({"loc": loc, "name": name, "size": size, "units": units, "why": "Not a product yet"})
            continue
        pid = save_product(conn, {"name": name, "unit_label": size, "category": str(item.get("category") or "")[:40]},
                           user=user)
        active[pid] = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        save_draft(conn, loc, pid, units, who)
        filled[loc] += 1
        added.append(f"{name} ({size})")
    return {"filled": filled, "skipped": skipped, "new": new, "added": added, "by": who}


# ── Stocktake history and undo ───────────────────────────────────────────────

def stocktakes(conn, limit: int = 30) -> list[dict[str, Any]]:
    """Each finished stocktake: when, who pressed Finish, who counted, and how many items per place."""
    out = []
    for r in rows(conn, "SELECT ts, MAX(user) finished_by, MAX(label) label FROM counts GROUP BY ts ORDER BY ts DESC LIMIT ?",
                  limit):
        lines = rows(conn, "SELECT c.location, COUNT(*) n FROM count_lines l JOIN counts c ON c.id = l.count_id "
                           "WHERE c.ts = ? GROUP BY c.location", r["ts"])
        counters = [x["counted_by"] for x in rows(
            conn, "SELECT l.counted_by, COUNT(*) n FROM count_lines l JOIN counts c ON c.id = l.count_id "
                  "WHERE c.ts = ? AND l.counted_by <> '' GROUP BY l.counted_by ORDER BY n DESC", r["ts"])]
        out.append({**r, "counted_by": counters, **{loc: 0 for loc in LOCATIONS},
                    **{x["location"]: x["n"] for x in lines}})
    return out


def undo_stocktake(conn, ts: str) -> dict[str, int]:
    """Take the latest stocktake back out. Stock returns to the stocktake before it plus every sale,
    delivery and wastage since, and the counted figures go back into the open count, so one wrong
    number can be fixed and the stocktake finished again (or the open count cleared)."""
    latest = conn.execute("SELECT MAX(ts) FROM counts").fetchone()[0]
    if not latest or ts != latest:
        raise ValueError("Only the most recent stocktake can be undone")
    if conn.execute("SELECT 1 FROM count_drafts LIMIT 1").fetchone():
        raise ValueError("There is already an open count. Finish or clear it first")
    reopened = {loc: 0 for loc in LOCATIONS}
    for c in rows(conn, "SELECT * FROM counts WHERE ts = ?", ts):
        for l in rows(conn, "SELECT * FROM count_lines WHERE count_id = ?", c["id"]):
            save_draft(conn, c["location"], l["product_id"], l["units"], l["counted_by"] or c["user"])
            reopened[c["location"]] += 1
        conn.execute("DELETE FROM count_lines WHERE count_id = ?", (c["id"],))
        conn.execute("DELETE FROM counts WHERE id = ?", (c["id"],))
    return reopened


def clear_drafts(conn) -> int:
    return conn.execute("DELETE FROM count_drafts").rowcount

