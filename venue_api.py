"""HTTP API for the stock screens. Added by the Tranquil Turtle fork."""

from __future__ import annotations

import json
import os
import threading
import time
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, Flask, jsonify, request

import square_api
import venue_db as db
import venue_import
from invoice_parse import parse_invoice

bp = Blueprint("venue", __name__, url_prefix="/api/venue")
_ctx: dict[str, Any] = {}


def needs(role: str):
    def deco(fn: Callable):
        @wraps(fn)
        def wrapper(*a, **k):
            if not _ctx["has_role"](role):
                return jsonify({"error": f"{role.title()} access needed"}), 403
            conn = db.connect(_ctx["data"])
            try:
                with conn:
                    return fn(conn, *a, **k)
            except (ValueError, KeyError, TypeError) as e:
                return jsonify({"error": str(e)}), 400
            finally:
                conn.close()
        return wrapper
    return deco


def _who() -> str:
    u = _ctx["user"]() or {}
    return u.get("name", "")


def _body() -> dict[str, Any]:
    return request.get_json(force=True) or {}


@bp.get("/overview")
@needs("staff")
def overview(conn):
    return jsonify({
        "stock": db.stock_lines(conn),
        "products": [{**p, "label": db.product_label(p)} for p in db.rows(
            conn, "SELECT * FROM products WHERE active = 1 ORDER BY name, variant")],
        "unmapped": conn.execute("SELECT COUNT(DISTINCT item_key) FROM events WHERE status = 'unmapped'").fetchone()[0],
        "square_api": square_api.configured(),
    })


@bp.get("/count")
@needs("staff")
def count_drafts(conn):
    return jsonify({"drafts": db.rows(conn, "SELECT location, product_id, units, user FROM count_drafts"),
                    "one_sided": db.one_sided(conn)})


@bp.post("/count/draft")
@needs("staff")
def count_draft(conn):
    b = _body()
    units = b.get("units")
    db.save_draft(conn, b["location"], int(b["product_id"]), None if units in ("", None) else float(units), _who())
    return jsonify({"status": "ok"})


@bp.post("/count/finish")
@needs("staff")
def count_finish(conn):
    return jsonify(db.finish_stocktake(conn, label=_body().get("label", ""), user=_who()))


@bp.post("/usage")
@needs("staff")
def usage(conn):
    b = _body()
    db.log_usage(conn, int(b["product_id"]), float(b["ml"]), b["reason"], b.get("note", ""), _who())
    return jsonify({"status": "ok"})


@bp.patch("/products/<int:pid>")
@needs("manager")
def product_edit(conn, pid: int):
    b = _body()
    if "unit_cost" in b:
        cost = b["unit_cost"]
        conn.execute("UPDATE products SET unit_cost = ? WHERE id = ?", (None if cost in ("", None) else float(cost), pid))
    if "par" in b:
        conn.execute("DELETE FROM pars WHERE product_id = ?", (pid,))
        if b["par"] not in ("", None):
            conn.execute("INSERT INTO pars (product_id, location, units) VALUES (?, ?, ?)",
                         (pid, db.ALL, float(b["par"])))
    db.refresh_batch_costs(conn)
    return jsonify({"status": "ok"})


@bp.post("/products")
@needs("manager")
def product_add(conn):
    b = _body()
    unit_ml, measure = venue_import.parse_unit(b["unit_label"])
    cur = conn.execute(
        "INSERT INTO products (name, variant, category, subcategory, unit_label, unit_ml, measure, unit_cost) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (b["name"].strip(), b.get("variant", "").strip(), b.get("category", ""), b.get("subcategory", ""),
         b["unit_label"], unit_ml, measure, b.get("unit_cost") or None))
    return jsonify({"id": cur.lastrowid})


@bp.post("/import/square")
@needs("manager")
def import_square(conn):
    upload = request.files.get("file")
    if not upload:
        raise ValueError("Choose a Square CSV file")
    text = venue_import.decode_export(upload.read())
    events = venue_import.parse_square_csv(text, request.form.get("sale_date", ""))
    return jsonify(db.ingest(conn, events, "square-csv", upload.filename or "", _who()))


@bp.get("/imports")
@needs("manager")
def imports(conn):
    return jsonify({"imports": db.rows(conn, "SELECT * FROM imports ORDER BY id DESC LIMIT 30")})


@bp.post("/imports/<int:iid>/undo")
@needs("manager")
def imports_undo(conn, iid: int):
    return jsonify({"removed": db.undo_import(conn, iid)})


@bp.get("/mappings")
@needs("manager")
def mappings(conn):
    return jsonify({
        "unmapped": db.rows(conn, "SELECT item_key, MAX(item_name) item_name, SUM(qty) qty FROM events "
                                  "WHERE status = 'unmapped' GROUP BY item_key ORDER BY qty DESC"),
        "mapped": db.rows(conn, "SELECT m.*, r.name recipe FROM mappings m LEFT JOIN recipes r ON r.id = m.recipe_id "
                                "ORDER BY m.item_name"),
    })


@bp.post("/mappings")
@needs("manager")
def mapping_set(conn):
    b = _body()
    applied = db.set_mapping(conn, b["item_key"], b["item_name"], b.get("recipe_id") or None,
                             b.get("product_id") or None, b.get("ml") or None, bool(b.get("no_stock")))
    return jsonify({"applied": applied})


@bp.get("/recipes")
@needs("staff")
def recipes(conn):
    out = []
    for r in db.rows(conn, "SELECT * FROM recipes ORDER BY name"):
        r["lines"] = db.rows(conn, "SELECT l.product_id, l.ml, p.name, p.variant, p.unit_label FROM recipe_lines l "
                                   "JOIN products p ON p.id = l.product_id WHERE l.recipe_id = ?", r["id"])
        for line in r["lines"]:
            line["label"] = db.product_label(line)
        r["cost"] = db.recipe_cost(conn, r["id"])
        out.append(r)
    return jsonify({"recipes": out})


@bp.post("/recipes")
@needs("manager")
def recipe_save(conn):
    b = _body()
    return jsonify({"id": db.save_recipe(conn, b["name"], b["lines"], b.get("menu_price") or None,
                                         b.get("yield_ml") or None, b.get("note", ""))})


@bp.post("/batches")
@needs("staff")
def batch(conn):
    b = _body()
    return jsonify({"made_ml": db.make_batch(conn, int(b["recipe_id"]), float(b.get("runs") or 1), user=_who())})


@bp.get("/deliveries")
@needs("manager")
def deliveries(conn):
    out = db.rows(conn, "SELECT * FROM deliveries ORDER BY status = 'draft' DESC, id DESC LIMIT 30")
    for d in out:
        d["lines"] = json.loads(d["lines"])
    return jsonify({"deliveries": out})


@bp.post("/deliveries")
@needs("manager")
def delivery_save(conn):
    b = _body()
    lines = json.dumps(b.get("lines") or [])
    if b.get("id"):
        conn.execute("UPDATE deliveries SET supplier = ?, ref = ?, lines = ? WHERE id = ? AND status = 'draft'",
                     (b.get("supplier", ""), b.get("ref", ""), lines, int(b["id"])))
        return jsonify({"id": b["id"]})
    cur = conn.execute("INSERT INTO deliveries (ts, supplier, ref, lines) VALUES (?, ?, ?, ?)",
                       (b.get("ts") or db.now(), b.get("supplier", ""), b.get("ref", ""), lines))
    return jsonify({"id": cur.lastrowid})


@bp.post("/deliveries/parse")
@needs("manager")
def delivery_parse(conn):
    """Read pasted text or a photo into a draft. Nothing touches stock until approval."""
    key, provider = os.environ.get("AI_API_KEY", ""), os.environ.get("AI_PROVIDER", "claude")
    upload = request.files.get("image")
    if upload:
        parsed = parse_invoice(image_bytes=upload.read(), media_type=upload.mimetype or "image/jpeg",
                               api_key=key, provider=provider)
    else:
        parsed = parse_invoice(text=_body().get("text", ""), api_key=key, provider=provider)
    supplier = parsed.get("vendor", "")
    known = {r["description"]: r for r in db.rows(conn, "SELECT * FROM supplier_map WHERE supplier = ?", supplier)}
    lines = []
    for l in parsed.get("lines") or []:
        hit = known.get((l.get("product") or "").lower())
        per = hit["units_per_line"] if hit else 1
        lines.append({"description": l.get("product", ""), "product_id": hit["product_id"] if hit else None,
                      "units": float(l.get("qty") or 0) * per, "units_per_line": per,
                      "unit_cost": (float(l.get("unit_cost") or 0) / per) or None})
    cur = conn.execute("INSERT INTO deliveries (ts, supplier, ref, lines) VALUES (?, ?, ?, ?)",
                       (db.now(), supplier, parsed.get("invoice_number", ""), json.dumps(lines)))
    return jsonify({"id": cur.lastrowid})


@bp.post("/deliveries/<int:did>/approve")
@needs("manager")
def delivery_approve(conn, did: int):
    return jsonify({"lines": db.approve_delivery(conn, did, _who())})


@bp.get("/reports/usage")
@needs("manager")
def report_usage(conn):
    return jsonify(db.usage_report(conn, request.args["from"], request.args["to"] + "T99"))


@bp.get("/reports/variance")
@needs("manager")
def report_variance(conn):
    return jsonify({"lines": db.variance_report(conn)})


@bp.get("/comps")
@needs("manager")
def comps(conn):
    return jsonify({"comps": db.rows(conn, "SELECT id, ts, item_name, qty FROM events WHERE reason = 'comp' ORDER BY ts DESC")})


@bp.post("/comps/<int:eid>")
@needs("manager")
def comp_reason(conn, eid: int):
    db.set_reason(conn, eid, _body()["reason"])
    return jsonify({"status": "ok"})


@bp.get("/prices")
@needs("manager")
def prices(conn):
    return jsonify({"prices": db.price_lines(conn)})


@bp.post("/prices/catalogue")
@needs("manager")
def prices_import(conn):
    upload = request.files.get("file")
    if not upload:
        raise ValueError("Choose a Square catalogue CSV")
    return jsonify(venue_import.import_catalogue(conn, venue_import.decode_export(upload.read())))


@bp.post("/prices/<token>")
@needs("manager")
def price_match(conn, token: str):
    b = _body()
    conn.execute("UPDATE sell_prices SET product_id = ?, ml = ? WHERE token = ?",
                 (b.get("product_id") or None, b.get("ml") or None, token))
    return jsonify({"status": "ok"})


@bp.post("/square/sync")
@needs("manager")
def square_sync(conn):
    if not square_api.configured():
        raise ValueError("Square API is not set up. Use the CSV import, or add a token to venue.env")
    return jsonify(square_api.sync(conn, os.environ["SQUARE_ACCESS_TOKEN"], os.environ["SQUARE_LOCATION_ID"]))


def _poll_forever(data: str) -> None:
    minutes = int(os.environ.get("SQUARE_POLL_MINUTES", "5"))
    while True:
        conn = db.connect(data)
        try:
            with conn:
                square_api.sync(conn, os.environ["SQUARE_ACCESS_TOKEN"], os.environ["SQUARE_LOCATION_ID"])
        except Exception as e:  # keep polling through network blips
            print(f"[square] sync failed: {e}")
        finally:
            conn.close()
        time.sleep(minutes * 60)


def start_poller(data: str) -> None:
    if square_api.configured():
        threading.Thread(target=_poll_forever, args=(data,), daemon=True).start()


def register(app: Flask, data: str, has_role: Callable, user: Callable) -> None:
    _ctx.update(data=data, has_role=has_role, user=user)
    app.register_blueprint(bp)
