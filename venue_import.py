"""Importers for the venue ledger: baseline stocktake and Square sales. Added in this fork."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from collections import Counter
from datetime import datetime
from typing import Any

import venue_db as db

# ── This venue's own matching rules ─────────────────────────────────────────
# Product spellings, Square button matches and menu quirks belong to one venue, so they live in
# data/venue-rules.json beside the stock database (never in git). venue-rules.example.json shows
# the shape. With no file, nothing is matched automatically and everything can be matched by hand.

RULES_FILE = "venue-rules.json"
DEFAULT_RULES: dict[str, Any] = {
    "aliases": [], "catalogue_match": {}, "postmix_items": [], "postmix_parts": 6, "dash_ml": 25, "shot_ml": 25,
    "regular_size": {}, "variation_size": {}, "bar_categories": [], "uncategorised_drinks": [],
}
_rules_cache: dict[str, Any] = {}


def rules_path() -> str:
    data = os.environ.get("OSB_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    return os.path.join(data, RULES_FILE)


def rules() -> dict[str, Any]:
    """The venue's rules, reloaded whenever the file changes."""
    path = rules_path()
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return dict(DEFAULT_RULES)
    if _rules_cache.get("key") != (path, stamp):
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        _rules_cache.update(key=(path, stamp), rules={**DEFAULT_RULES, **loaded})
    return _rules_cache["rules"]


def _aliases() -> dict[tuple[str, str], tuple[str, str | None]]:
    return {(a["name"].lower(), (a.get("variant") or "").lower()): (a["to_name"], a.get("to_variant"))
            for a in rules()["aliases"]}


def parse_unit(fmt: str) -> tuple[float, str]:
    m = re.match(r"\s*([\d.]+)\s*(ml|cl|l|kg|g)\b", fmt or "", re.I)
    if not m:
        raise ValueError(f"Cannot read unit size: {fmt!r}")
    v, u = float(m.group(1)), m.group(2).lower()
    factor = {"ml": 1, "cl": 10, "l": 1000, "kg": 1000, "g": 1}[u]
    return v * factor, ("g" if u in ("kg", "g") else "ml")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def _canon(name: str, variant: str) -> tuple[str, str]:
    key = (name.lower(), variant.lower())
    aliases = _aliases()
    hit = aliases.get(key) or aliases.get((name.lower(), ""))
    if hit:
        return hit[0], hit[1] if hit[1] is not None else variant
    return name, variant


def import_baseline(conn, path: str, user: str = "import") -> dict[str, Any]:
    """Load the stocktake as the opening Bar and Cellar counts, taken at one moment."""
    import openpyxl

    if conn.execute("SELECT 1 FROM counts LIMIT 1").fetchone():
        raise ValueError("Stock already has counts; the baseline only loads into an empty database")
    ws = openpyxl.load_workbook(path, data_only=True)["Stocktake"]
    head = [_clean(c.value) for c in ws[4]]
    col = {h: i for i, h in enumerate(head)}
    counted: dict[str, dict[int, float]] = {loc: {} for loc in db.LOCATIONS}
    date_counts: Counter = Counter()
    rowcount = 0
    for r in ws.iter_rows(min_row=5, values_only=True):
        if not r[col["Item Name"]]:
            continue
        rowcount += 1
        location = _clean(r[col["Location"]])
        name, variant = _canon(_clean(r[col["Item Name"]]), _clean(r[col["Variant"]]))
        fmt = _clean(r[col["Unit Size / Format"]])
        unit_ml, measure = parse_unit(fmt)
        conn.execute(
            "INSERT OR IGNORE INTO products (name, variant, category, subcategory, unit_label, unit_ml, measure, unit_cost, supplier) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, variant, _clean(r[col["Category"]]), _clean(r[col["Sub-Category"]]), fmt, unit_ml, measure,
             r[col["Unit Cost (£)"]], _clean(r[col["Supplier"]])),
        )
        pid = conn.execute("SELECT id FROM products WHERE name = ? AND variant = ? AND unit_ml = ?",
                           (name, variant, unit_ml)).fetchone()[0]
        counted[location][pid] = counted[location].get(pid, 0.0) + float(r[col["Units Counted"]] or 0)
        par = r[col["Par Level"]]
        if par is not None:
            conn.execute("INSERT OR REPLACE INTO pars (product_id, location, units) VALUES (?, ?, ?)",
                         (pid, db.ALL, float(par)))
        d = r[col["Date Counted"]]
        if d:
            date_counts[d] += 1
    baseline: datetime = date_counts.most_common(1)[0][0]
    for loc in db.LOCATIONS:
        db.add_count(conn, loc, counted[loc], ts=baseline.replace(hour=23, minute=59).isoformat(timespec="seconds"),
                     label="Baseline stocktake", user=user)
    return {"rows": rowcount, "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "bar_lines": len(counted["Bar"]), "cellar_lines": len(counted["Cellar"])}


def _header(ws) -> dict[str, int] | None:
    for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
        head = [_clean(v) for v in row]
        if "Item Name" in head and "Units Counted" in head:
            return {h: i for i, h in enumerate(head)}
    return None


def read_stocktake(conn, raw: bytes, add_new: bool = False) -> dict[str, Any]:
    """Read a stocktake laid out like the baseline sheet into Bar and Cellar figures.
    A product merged into another counts towards the one it was merged into, and a product
    never counted takes its bottle size from the sheet. Rows that match no product come back
    for entering by hand, or are added as new products with add_new."""
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    except Exception:
        raise ValueError("This is not an Excel .xlsx file")
    ws = next((w for w in wb.worksheets if _header(w)), None)
    if ws is None:
        raise ValueError("No sheet has Item Name and Units Counted columns")
    col = _header(ws)
    products = db.rows(conn, "SELECT id, name, variant, unit_ml, active FROM products")
    exact = {(p["name"].lower(), p["variant"].lower(), p["unit_ml"]): p for p in products}
    by_size: dict[tuple[str, float], list] = {}
    by_variant: dict[tuple[str, str], list] = {}
    for p in products:
        if p["active"]:
            by_size.setdefault((p["name"].lower(), p["unit_ml"]), []).append(p)
            by_variant.setdefault((p["name"].lower(), p["variant"].lower()), []).append(p)
    counted = {r["product_id"] for r in db.rows(conn, "SELECT DISTINCT product_id FROM count_lines")}
    resized: list[str] = []

    def match(name: str, variant: str, unit_ml: float, fmt: str) -> int | None:
        p = exact.get((name.lower(), variant.lower(), unit_ml))
        if p and p["active"]:
            return p["id"]
        named = by_variant.get((name.lower(), variant.lower()), [])
        same = by_size.get((name.lower(), unit_ml), [])
        plain = [q for q in same if not q["variant"]]
        if p:
            pick = named if len(named) == 1 else plain or same
            return pick[0]["id"] if len(pick) == 1 else None
        if len(plain) == 1:  # one product for every label, like the merged Rioja
            return plain[0]["id"]
        if len(named) == 1 and named[0]["id"] not in counted:
            q = named[0]
            conn.execute("UPDATE products SET unit_label = ?, unit_ml = ? WHERE id = ?", (fmt, unit_ml, q["id"]))
            resized.append(f"{q['name']} {q['variant']}: now {fmt}".replace("  ", " "))
            q["unit_ml"] = unit_ml
            exact[(name.lower(), variant.lower(), unit_ml)] = q
            return q["id"]
        return None

    lines: dict[str, dict[int, float]] = {loc: {} for loc in db.LOCATIONS}
    unmatched, added, dates, blank, count = [], [], Counter(), 0, 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        cell = lambda h: r[col[h]] if h in col and col[h] < len(r) else None
        if not _clean(cell("Item Name")) or _clean(cell("Item Name")) == "Item Name":
            continue
        location = _clean(cell("Location")).title()
        raw_name, raw_variant, fmt = _clean(cell("Item Name")), _clean(cell("Variant")), _clean(cell("Unit Size / Format"))
        units = cell("Units Counted")
        row = {"location": location, "name": raw_name, "variant": raw_variant, "unit": fmt, "units": units}
        if units in (None, ""):
            blank += 1
            units = 0
        try:
            units = float(units)
            unit_ml = parse_unit(fmt)[0]
        except ValueError as e:
            unmatched.append({**row, "why": str(e) if "unit" in str(e) else "Units Counted is not a number"})
            continue
        name, variant = _canon(raw_name, raw_variant)
        pid = match(name, variant, unit_ml, fmt)
        if pid is None and add_new and location in db.LOCATIONS:
            cost = cell("Unit Cost (£)")
            cur = conn.execute(
                "INSERT INTO products (name, variant, category, subcategory, unit_label, unit_ml, measure, unit_cost, supplier) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, variant, _clean(cell("Category")), _clean(cell("Sub-Category")), fmt, unit_ml,
                 parse_unit(fmt)[1], cost if isinstance(cost, (int, float)) else None, _clean(cell("Supplier"))))
            pid = cur.lastrowid
            exact[(name.lower(), variant.lower(), unit_ml)] = {"id": pid, "name": name, "variant": variant,
                                                               "unit_ml": unit_ml, "active": 1}
            added.append(f"{name} {variant} ({fmt})".replace("  ", " "))
        if location not in db.LOCATIONS or pid is None:
            unmatched.append({**row, "why": "Location must be Bar or Cellar" if pid else "No matching product"})
            continue
        lines[location][pid] = lines[location].get(pid, 0.0) + units
        count += 1
        if isinstance(cell("Date Counted"), datetime):
            dates[cell("Date Counted").date().isoformat()] += 1
    return {"lines": lines, "matched": count, "blank": blank, "unmatched": unmatched, "added": added, "resized": resized,
            "date": dates.most_common(1)[0][0] if dates else "", "sheet": ws.title}


# ── Square catalogue (selling prices) ───────────────────────────────────────

_SERVE_ML = {"half pint": 284, "pint": 568, "small": 125, "medium": 175, "large": 250}


def _serve_ml(item: str, variation: str, unit_ml: float) -> float | None:
    r = rules()
    v = variation.lower().strip()
    diluted, parts = set(r["postmix_items"]), r["postmix_parts"]
    if item.startswith("dash "):
        return r["dash_ml"] / parts if item in diluted else r["dash_ml"]
    if item in diluted:
        return next((ml / parts for word, ml in _SERVE_ML.items() if v.startswith(word)), None)
    if item.startswith("water"):
        return unit_ml  # Small and Large here are bottle sizes, not wine glasses
    if v.startswith("bottle"):
        return unit_ml
    m = re.search(r"(\d+)\s*ml", v)
    if m:
        return float(m.group(1))
    for word, ml in _SERVE_ML.items():
        if v.startswith(word):
            return ml
    if v in ("regular", ""):
        return r["regular_size"].get(item, unit_ml)
    return r["variation_size"].get(v)


def import_catalogue(conn, text: str) -> dict[str, int]:
    """Load selling prices from a Square catalogue export. Never touches cost prices or stock.
    Re-importing refreshes prices and keeps any match made by hand."""
    seen = matched = 0
    live = set()
    venue = rules()
    match = {k: tuple(v) for k, v in venue["catalogue_match"].items()}
    skip = db.ignore_matcher(conn)
    extra, cats = set(venue["uncategorised_drinks"]), tuple(c.upper() for c in venue["bar_categories"])
    for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=_dialect_delimiter(text)):
        category = (r.get("Categories") or "").strip()
        name = (r.get("Item Name") or "").strip()
        lowered = name.lower()
        hit = match.get(db.item_key(name, r.get("Variation Name") or "")) or match.get(lowered)
        # With no bar categories set, every priced item is kept; a venue can narrow it to its drinks.
        wanted = hit or lowered in extra or not cats or category.upper().startswith(cats)
        try:
            price = float(r.get("Price") or "")
        except ValueError:
            continue
        if r.get("Archived") == "Y" or not wanted or skip(name) or skip(r.get("Variation Name") or ""):
            continue
        variation = (r.get("Variation Name") or "").strip()
        product_id, ml = None, None
        if hit:
            row = conn.execute("SELECT id, unit_ml FROM products WHERE name = ? AND variant = ? AND unit_ml = ?", hit).fetchone()
            if row:
                product_id, ml = row["id"], _serve_ml(lowered, variation, row["unit_ml"])
                matched += 1
        seen += 1
        live.add(r["Token"])
        before = conn.execute("SELECT price FROM sell_prices WHERE token = ?", (r["Token"],)).fetchone()
        if before:  # a first load is not a change
            db.log_sell_price(conn, r["Token"], name + (f" - {variation}" if variation and variation.lower() != "regular" else ""),
                              before["price"], price)
        conn.execute(
            "INSERT INTO sell_prices (token, item, variation, category, price, product_id, ml) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(token) DO UPDATE SET item = excluded.item, variation = excluded.variation, "
            "category = excluded.category, price = excluded.price, "
            "product_id = COALESCE(sell_prices.product_id, excluded.product_id), ml = COALESCE(sell_prices.ml, excluded.ml)",
            (r["Token"], name, variation, category, price, product_id, ml))
    gone = [t["token"] for t in db.rows(conn, "SELECT token FROM sell_prices") if t["token"] not in live]
    conn.executemany("DELETE FROM sell_prices WHERE token = ?", [(t,) for t in gone])
    return {"prices": seen, "matched": matched, "removed": len(gone)}


# ── Square CSV ───────────────────────────────────────────────────────────────

def _money(text: str) -> float:
    s = (text or "").replace("£", "").replace("$", "").replace(",", "").strip()
    neg = s.startswith("(") or s.startswith("-")
    s = s.strip("()-")
    try:
        return -float(s) if neg else float(s)
    except ValueError:
        return 0.0


def decode_export(raw: bytes) -> str:
    """Square's Excel-style exports are UTF-16 with tabs; its other exports are UTF-8 with commas."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def _dialect_delimiter(text: str) -> str:
    head = text.split("\n", 1)[0]
    return "\t" if head.count("\t") > head.count(",") else ","


def _parse_ts(date: str, time: str) -> str:
    date, time = (date or "").strip(), (time or "").strip() or "00:00:00"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(f"{date} {time}", fmt).isoformat(timespec="seconds")
        except ValueError:
            continue
    raise ValueError(f"Cannot read date {date!r}")


def _find_reason(text: str) -> str:
    low = (text or "").lower()
    for reason in db.REASONS:
        if reason in low:
            return reason
    return ""


def parse_square_csv(text: str, sale_date: str = "") -> list[dict[str, Any]]:
    """Square Dashboard export > events. Reads the per-transaction Item Sales detail export,
    and the summary export (which needs sale_date, and has no per-line comps)."""
    text = text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text), delimiter=_dialect_delimiter(text))
    fields = {(f or "").strip().lower(): f for f in reader.fieldnames or []}

    def col(row, *names):
        for n in names:
            if n in fields:
                return (row.get(fields[n]) or "").strip()
        return ""

    if "item" not in fields and "item name" not in fields:
        raise ValueError("This does not look like a Square item sales export (no Item column)")
    detail = "transaction id" in fields
    if not detail and not sale_date:
        raise ValueError("This is a summary export: choose the trading date it covers")
    seen: Counter = Counter()
    events = []
    for row in reader:
        name = col(row, "item", "item name")
        if not name:
            continue
        variation = col(row, "price point name", "item variation", "variation")
        key_item = db.item_key(name, variation)
        label = name + (f" - {variation}" if variation and variation.lower() != "regular" else "")
        if detail:
            qty = float(col(row, "qty", "quantity") or 0)
            # Current exports call the pre-discount figure Product Sales; Gross Sales there is after discounts.
            gross = _money(col(row, "product sales", "gross sales"))
            net = _money(col(row, "net sales"))
            discounts = _money(col(row, "discounts"))
            is_refund = "refund" in col(row, "event type").lower() or qty < 0 or gross < 0
            base = "|".join((col(row, "transaction id"), key_item, col(row, "modifiers applied"), str(is_refund)))
            seen[base] += 1
            comped = not is_refund and gross > 0 and abs(net) < 0.005 and abs(discounts) > 0
            hint = " ".join((col(row, "discount name", "discounts name", "comp reason", "reason"), col(row, "notes"), col(row, "details")))
            events.append({
                "key": "csv:" + hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()[:32],
                "ts": _parse_ts(col(row, "date"), col(row, "time")), "kind": "refund" if is_refund else "sale",
                "item_key": key_item, "item_name": label, "qty": abs(qty), "net": net,
                "modifiers": col(row, "modifiers applied"), "category": col(row, "category"),
                "reason": (_find_reason(hint) or "comp") if comped else "",
            })
        else:
            sold = float(col(row, "items sold", "qty", "quantity") or 0)
            refunded = float(col(row, "items refunded") or 0)
            ts = f"{sale_date}T12:00:00"
            if sold:
                events.append({"key": f"sum:{sale_date}:{key_item}", "ts": ts, "kind": "sale", "item_key": key_item,
                               "item_name": label, "qty": sold, "net": _money(col(row, "net sales")),
                               "category": col(row, "category")})
            if refunded:
                events.append({"key": f"sumr:{sale_date}:{key_item}", "ts": ts, "kind": "refund", "item_key": key_item,
                               "item_name": label, "qty": refunded})
    return events
