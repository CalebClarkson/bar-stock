"""Importers for the venue ledger: baseline stocktake and Square sales. Added by the Tranquil Turtle fork."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from datetime import datetime
from typing import Any

import venue_db as db

# (name, variant) spellings in the stocktake → the one product they mean.
ALIASES = {
    ("ciroq vodka", ""): ("Cîroc Vodka", None),
    ("fevertree tonic water", "soda"): ("Fever-Tree", "Soda Water"),
    ("fevertree tonic water", ""): ("Fever-Tree Tonic Water", None),
    ("jameson irish whiskey", ""): ("Jameson Whiskey", None),
    ("vueve clicquot", "brut champagne"): ("Brut Champagne", "Veuve Clicquot"),
    ("whitley neill gin", "rhubarb & ginger alcohol-free spirit"): ("Whitley Neill Gin", "Rhubarb & Ginger 0.0%"),
    ("bumbu rum", "cream liquor"): ("Bumbu Rum", "Cream Liqueur"),
    ("absolut vodka", "original 70cl"): ("Absolut Vodka", "Original"),
    ("old mout cider", "mango & passionfuit"): ("Old Mout Cider", "Mango & Passionfruit"),
    ("asahi", "0"): ("Asahi", "0.0%"),
    ("guinness", "0"): ("Guinness", "0.0%"),
    ("fever-tree", "premium ginger beer"): ("Fever-Tree", "Ginger Beer"),
    # Syrups added from the cocktail specs, by their bottle names on later stocktakes.
    ("le syrup de monin", "vanille de madagascar"): ("Vanilla Syrup", "Original"),
    ("le syrup de monin", "watermelon"): ("Watermelon Syrup", "Original"),
    ("1883 maison routin", "blueberry syrup"): ("Blueberry Syrup", "Original"),
    ("1883 maison routin", "iced tea peach syrup"): ("Peach Tea Syrup", "Original"),
    ("bristol syrup co", "simple sugar"): ("Gomme Syrup", "Original"),
}


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
    hit = ALIASES.get(key) or ALIASES.get((name.lower(), ""))
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

# Square item → stock product, checked by hand. Similar names that are different products
# stay out on purpose (Hennessy VS is not VSOP; menu wines from another producer are not the
# wine in stock). Unlisted items import unmatched and can be matched on the Prices screen.
CATALOGUE_MATCH = {
    "asahi 0%": ("Asahi", "0.0%", 330), "asahi super dry": ("Asahi", "Original", 330),
    "budweiser": ("Budweiser", "Original", 300), "corona extra": ("Corona Extra", "Original", 330),
    "london pride": ("London Pride", "Original", 330), "aspall suffolk cider": ("Aspall", "Original", 330),
    "guinness": ("Guinness", "Original", 558), "guinness 0%": ("Guinness", "0.0%", 538),
    "cherries berries old mout 0%": ("Old Mout Cider", "Berries & Cherries Alcohol Free 0%", 500),
    "old mout berries & cherries": ("Old Mout Cider", "Berries & Cherries", 500),
    "old mout mango & passionfruit": ("Old Mout Cider", "Mango & Passionfruit", 500),
    # House vodka is sold as 42 Below and poured from Absolut for now. Moretti is replaced by Cruzcampo.
    # Square's Hennessy VS is the same stock as the VSOP in the stocktake.
    "42 below vodka": ("Absolut Vodka", "Original", 700), "birra moretti": ("Cruzcampo", "Original", 50000),
    "cruzcampo": ("Cruzcampo", "Original", 50000), "hennessy vs": ("Hennessy Cognac", "VSOP", 700),
    "roku": ("Roku Gin", "Original", 700),
    # Wines are bought on price each week, so Square's labels are matched by grape.
    "arte noble merlot": ("Merlot", "Art Series", 750), "kleindal chenin blanc": ("Chenin Blanc", "Flock Together", 750),
    "domaine foncastel picpoul de pinet": ("Picpoul de Pinet", "Les Roches Saintes", 750),
    "piedra negra alta malbec": ("Malbec", "Trivento Tribu", 750), "woolloomooloo shiraz": ("Shiraz", "Healy & Gray", 750),
    "sensorial rioja crianza": ("Rioja", "", 750), "san giorgio pinot grigio": ("Pinot Grigio", "Art Series", 750),
    "san giorgio pinot rose": ("Pinot Grigio Rose", "", 750), "chardonnay": ("Chardonnay", "El Dueto", 750),
    "wildwood zinfandel rose": ("Zinfandel Rose", "Healy & Gray", 750),
    "whispering angel": ("Zinfandel Rose", "Healy & Gray", 750), "belaire": ("Luc Belaire", "Rose Sparkling Wine", 750),
    # Held at 0 until stocked.
    "bumbu xo": ("Bumbu Rum", "XO", 700), "glenfiddich 15yr": ("Glenfiddich Whisky", "15 Year", 700),
    "nikka from thé barrel": ("Nikka Whisky", "From The Barrel", 500), "oxford rye": ("Oxford Rye Whiskey", "Original", 700),
    "pernod": ("Pernod", "Original", 700), "whitley neil pink grapefruit": ("Whitley Neill Gin", "Pink Grapefruit", 700),
    "desperados": ("Desperados", "Original", 330), "ft ginger beer": ("Fever-Tree", "Ginger Beer", 200),
    "ft mediterranean tonic": ("Fever-Tree Tonic Water", "Mediterranean", 200),
    "tinamou pinot noir": ("Pinot Noir", "Tinamou", 750),
    "barossa valley estate cabernet sauv": ("Cabernet Sauvignon", "Barossa Valley Estate", 750),
    "british brut": ("British Brut", "Original", 750), "vueve cliquot rose": ("Veuve Clicquot Rose", "Original", 750),
    "mozart dark chocolate": ("Mozart Dark Chocolate", "Original", 500), "hooch": ("Hooch", "Original", 330),
    "san pellegrino blood orange": ("San Pellegrino", "Blood Orange", 330), "large water still": ("Large Water", "Still", 750),
    "botter prosecco": ("Botter Prosecco", "Original", 750), "botter prosecco rose (bottle only)": ("Botter Prosecco", "Rose", 750),
    "rosé prosecco": ("Botter Prosecco", "Rose", 750), "don julio": ("Don Julio Tequila", "1942", 700),
    "amstel": ("Amstel", "Original", 50000), "beavertown neck oil": ("Neck Oil", "Original", 30000),
    "coke": ("Coca-Cola", "Original", 7000), "diet coke": ("Coca-Cola", "Diet", 7000),
    "lemonade": ("Lemonade", "Original", 7000), "dash coke": ("Coca-Cola", "Original", 7000),
    "dash diet coke": ("Coca-Cola", "Diet", 7000), "dash lemonade": ("Lemonade", "Original", 7000),
    "apple juice": ("Sun Pride Juice", "Apple", 1000), "orange juice": ("Sun Pride Juice", "Orange", 1000),
    "cranberry juice": ("Sun Pride Juice", "Cranberry", 1000), "pineapple juice": ("Sun Pride Juice", "Pineapple", 1000),
    "dash apple juice": ("Sun Pride Juice", "Apple", 1000), "dash orange juice": ("Sun Pride Juice", "Orange", 1000),
    "dash cranberry juice": ("Sun Pride Juice", "Cranberry", 1000), "dash pineapple juice": ("Sun Pride Juice", "Pineapple", 1000),
    "dash blackcurrant cordial": ("Cordial", "Blackcurrant", 1000), "dash lime cordial": ("Cordial", "Lime", 1000),
    "water sparkling|small": ("Small Water", "Sparkling", 330), "water sparkling|large": ("Large Water", "Sparkling", 750),
    "water still": ("Small Water", "Still", 330), "appletiser": ("Appletiser Sparkling Juice", "Original", 275),
    "ft elderflower tonic": ("Fever-Tree Tonic Water", "Elderflower", 200),
    "ft ginger ale": ("Fever-Tree", "Premium Ginger Ale", 200),
    "ft indian tonic": ("Fever-Tree Tonic Water", "Indian", 200),
    "ft refreshingly light tonic": ("Fever-Tree Tonic Water", "Refreshingly Light", 200),
    "fruit shoot apple&blackcurrant": ("Fruit Shoot", "Apple & Blackcurrant", 200),
    "fruit shoot orange": ("Fruit Shoot", "Orange", 200),
    "j20 apple&raspberry": ("J2O", "Apple & Raspberry", 275),
    "j20 orange&passionfruit": ("J2O", "Orange & Passion Fruit", 275),
    "redbull": ("RedBull", "Original", 250), "magnum": ("Magnum Tonic Wine", "Original", 200),
    "hennessy xo": ("Hennessy Cognac", "XO", 700), "bombay sapphire": ("Bombay Sapphire Gin", "Original", 700),
    "hendricks": ("Hendricks Gin", "Original", 700), "casamigos reposado": ("Casamigos Tequila", "Reposado", 700),
    "don julio 1942": ("Don Julio Tequila", "1942", 700), "grey goose": ("Grey Goose Vodka", "Original", 700),
    "glenfiddich 12yr": ("Glenfiddich Whisky", "12 Year", 700), "haig club": ("Haig Club Whiskey", "Original", 700),
    "courvoisier vs": ("Courvoisier Cognac", "VS", 700), "martell vs": ("Martell Cognac", "VS", 700),
    "bathtub gin": ("Bathtub Gin", "Original", 700), "beefeater pink": ("Beefeater Gin", "Pink Strawberry", 700),
    "tanqueray flor de sevilla": ("Tanqueray Gin", "Sevilla", 700), "tanqueray no10": ("Tanqueray Gin", "No. 10", 700),
    "whitley neill rhubarb & ginger": ("Whitley Neill Gin", "Rhubarb & Ginger", 700),
    "amaretto disaronno": ("Disaronno Liqueur", "Original", 700), "antica classic sambuca": ("Sambuca", "Original", 700),
    "aperol": ("Aperol Aperitif", "Original", 700), "archers": ("Archers Liqueur", "Original", 700),
    "baileys (always 50ml)": ("Bailey's Liqueur", "Original", 700), "chambord": ("Chambord Raspberry Liqueur", "Original", 700),
    "jagermeister": ("Jagermeister", "Original", 700), "kahlua": ("Kahlua", "Original", 700),
    "malibu": ("Malibu", "Original", 700), "pimms": ("Pimm's Liqueur", "Original", 700),
    "southern comfort": ("Southern Comfort Whiskey", "Original", 700),
    "bacardi carta blanca": ("Bacardi Rum", "Carta Blanca", 700), "bacardi spiced": ("Bacardi Rum", "Spiced", 700),
    "bumbu": ("Bumbu Rum", "Original", 700), "bumbu cream": ("Bumbu Rum", "Cream Liqueur", 700),
    "captain morgan's spiced": ("Captain Morgan Rum", "Spiced Gold", 700),
    "havana 7yr": ("Havana Club Rum", "Anejo 7 Year Old", 700), "kraken black spiced": ("The Kraken Black Rum", "Spiced", 700),
    "wray & nephew": ("Wray & Nephew's Rum", "Original", 700), "tequila rose": ("Tequila Rose", "Original", 700),
    "buen amigo tequila": ("Buen Amigo Tequila", "Original", 700), "ciroq": ("Cîroc Vodka", "Original", 700),
    "ciroq mango": ("Cîroc Vodka", "Mango", 700), "ciroq pineapple": ("Cîroc Vodka", "Pineapple", 700),
    "ciroq red berry": ("Cîroc Vodka", "Red Berry", 700), "jack daniels": ("Jack Daniels Whiskey", "Old No.7 Tennessee", 700),
    "jameson": ("Jameson Whiskey", "Original", 700), "buffalo trace": ("Buffalo Trace Whiskey", "Original", 700),
    "seedlip grove 42": ("Seedlip Distilled Non-Alcoholic Spirit", "Grove 42 (Citrus)", 700),
    "te aka sauvignon blanc": ("Sauvignon Blanc", "Te Aka", 750), "moët & chandon": ("Moet et Chandon", "Brut Champagne NV", 750),
    "vueve cliquot brut": ("Brut Champagne", "Veuve Clicquot", 750), "nosecco": ("Nozeco", "Nozeco", 750),
    "nozecco": ("Nozeco", "Nozeco", 750),
}
# Poured from post-mix: one part syrup to five parts water, so a serve uses a sixth of its volume in syrup.
_DILUTED = {"coke", "diet coke", "lemonade", "dash coke", "dash diet coke", "dash lemonade"}
POSTMIX_PARTS = 6
DASH_ML = 25
SHOT_ML = 25
# "Regular" here is a short measure or a bottle, not one whole stock unit.
_REGULAR_SIZE = {"baileys (always 50ml)": 50, "casamigos reposado": 700, "bumbu cream": SHOT_ML,
                 "tequila rose": SHOT_ML, "don julio": SHOT_ML, "mozart dark chocolate": SHOT_ML,
                 "nosecco": 750, "nozecco": 750}
_BAR_CATEGORIES = ("BEER", "COCKTAILS", "DASHES", "MOCKTAILS", "SOFT DRINKS", "SPIRITS", "WINE")
# Live drinks Square holds with no category, alongside door entry and hire items.
_UNCATEGORISED_DRINKS = {
    "don julio", "espresso martini", "fiance fizz", "hooch", "kir royale", "large water still", "long island iced tea",
    "negroni", "pimms and lemonade", "pornstar tree", "san pellegrino blood orange", "sangria jug",
    "sex on beach jug", "virgin pornstar", "virgin rumpunch",
}
_SERVE_ML = {"half pint": 284, "pint": 568, "small": 125, "medium": 175, "large": 250}


def _serve_ml(item: str, variation: str, unit_ml: float) -> float | None:
    v = variation.lower().strip()
    if item.startswith("dash "):
        return DASH_ML / POSTMIX_PARTS if item in _DILUTED else DASH_ML
    if item in _DILUTED:
        return next((ml / POSTMIX_PARTS for word, ml in _SERVE_ML.items() if v.startswith(word)), None)
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
        return _REGULAR_SIZE.get(item, unit_ml)
    if v == "don julio 1942":
        return SHOT_ML
    return None


def import_catalogue(conn, text: str) -> dict[str, int]:
    """Load selling prices from a Square catalogue export. Never touches cost prices or stock.
    Re-importing refreshes prices and keeps any match made by hand."""
    seen = matched = 0
    live = set()
    for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=_dialect_delimiter(text)):
        category = (r.get("Categories") or "").strip()
        name = (r.get("Item Name") or "").strip()
        lowered = name.lower()
        hit = CATALOGUE_MATCH.get(db.item_key(name, r.get("Variation Name") or "")) or CATALOGUE_MATCH.get(lowered)
        wanted = hit or lowered in _UNCATEGORISED_DRINKS or category.upper().startswith(_BAR_CATEGORIES)
        try:
            price = float(r.get("Price") or "")
        except ValueError:
            continue
        if r.get("Archived") == "Y" or not wanted:
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
    """Square Dashboard export → events. Reads the per-transaction Item Sales detail export,
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
                "modifiers": col(row, "modifiers applied"),
                "reason": (_find_reason(hint) or "comp") if comped else "",
            })
        else:
            sold = float(col(row, "items sold", "qty", "quantity") or 0)
            refunded = float(col(row, "items refunded") or 0)
            ts = f"{sale_date}T12:00:00"
            if sold:
                events.append({"key": f"sum:{sale_date}:{key_item}", "ts": ts, "kind": "sale", "item_key": key_item,
                               "item_name": label, "qty": sold, "net": _money(col(row, "net sales"))})
            if refunded:
                events.append({"key": f"sumr:{sale_date}:{key_item}", "ts": ts, "kind": "refund", "item_key": key_item,
                               "item_name": label, "qty": refunded})
    return events
