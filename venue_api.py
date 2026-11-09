"""HTTP API for the stock screens. Added in this fork."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, Flask, jsonify, request, send_from_directory

import square_api
import venue_db as db
import venue_import
from invoice_parse import parse_invoice

bp = Blueprint("venue", __name__, url_prefix="/api/venue")
_ctx: dict[str, Any] = {}


JOBS = {"count": "do stocktakes", "waste": "log wastage", "batch": "record batches"}


def can_do(job: str) -> bool:
    """Admins change everything. Anyone else only views and uploads sales, unless an admin has
    switched on one of these everyday jobs for them in People."""
    if _ctx["has_role"]("admin"):
        return True
    return bool(((_ctx["user"]() or {}).get("stock_jobs") or {}).get(job))


def needs(role: str):
    """role is staff/manager/admin, or job:<name> for a job an admin can allow per person."""
    def deco(fn: Callable):
        @wraps(fn)
        def wrapper(*a, **k):
            if role.startswith("job:"):
                if not can_do(role[4:]):
                    return jsonify({"error": f"Ask an admin to let you {JOBS[role[4:]]}"}), 403
            elif not _ctx["has_role"](role):
                return jsonify({"error": "Only an admin can change this" if role == "admin"
                                else f"{role.title()} access needed"}), 403
            conn = db.connect(_ctx["data"])
            try:
                with conn:
                    return fn(conn, *a, **k)
            except (ValueError, KeyError, TypeError) as e:
                return jsonify({"error": str(e)}), 400
            except sqlite3.IntegrityError:
                return jsonify({"error": "That item no longer exists. Refresh the page and try again"}), 400
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
        "phone_url": os.environ.get("OSB_PHONE_URL", "https://calebclarkson.github.io/bar-stock/"),
        "reasons": db.custom_reasons(conn),
    })


@bp.get("/count")
@needs("staff")
def count_drafts(conn):
    return jsonify({"drafts": db.rows(conn, "SELECT location, product_id, units, user FROM count_drafts"),
                    "one_sided": db.one_sided(conn)})


@bp.post("/count/draft")
@needs("job:count")
def count_draft(conn):
    b = _body()
    units = b.get("units")
    db.save_draft(conn, b["location"], int(b["product_id"]), None if units in ("", None) else float(units), _who())
    return jsonify({"status": "ok"})


@bp.post("/count/finish")
@needs("job:count")
def count_finish(conn):
    b = _body()
    return jsonify(db.finish_stocktake(conn, ts=b.get("ts") or "", label=b.get("label", ""), user=_who()))


@bp.post("/count/upload")
@needs("job:count")
def count_upload(conn):
    """Fill the count from an Excel stocktake. Stock changes only when the count is finished."""
    upload = request.files.get("file")
    if not upload:
        raise ValueError("Choose an Excel stocktake file")
    sheet = venue_import.read_stocktake(conn, upload.read(), add_new=request.form.get("add_new") == "1")
    conn.execute("DELETE FROM count_drafts")
    for loc, lines in sheet.pop("lines").items():
        for pid, units in lines.items():
            db.save_draft(conn, loc, pid, units, _who())
    return jsonify(sheet)


@bp.get("/stocktakes")
@needs("staff")
def stocktakes(conn):
    return jsonify({"stocktakes": db.stocktakes(conn)})


@bp.post("/stocktakes/undo")
@needs("admin")
def stocktake_undo(conn):
    return jsonify({"reopened": db.undo_stocktake(conn, str(_body().get("ts") or ""))})


@bp.post("/count/clear")
@needs("job:count")
def count_clear(conn):
    return jsonify({"cleared": db.clear_drafts(conn)})


@bp.post("/count/phone")
@needs("job:count")
def count_phone(conn):
    """Fill the count from a phone's count file. Stock changes only when the count is finished."""
    b = _body()
    return jsonify(db.phone_count(conn, b.get("file") or {}, add_new=bool(b.get("add_new")), user=_who()))


@bp.post("/usage")
@needs("job:waste")
def usage(conn):
    b = _body()
    db.log_usage(conn, int(b["product_id"]), float(b["ml"]), b["reason"], b.get("note", ""), _who())
    return jsonify({"status": "ok"})


@bp.get("/products/all")
@needs("manager")
def products_all(conn):
    pars = {r["product_id"]: r["units"] for r in db.rows(conn, "SELECT * FROM pars")}
    out = db.rows(conn, "SELECT p.*, (SELECT COUNT(*) FROM recipe_lines l WHERE l.product_id = p.id) in_recipes "
                        "FROM products p ORDER BY active DESC, category, subcategory, name, variant")
    for p in out:
        p["label"], p["par"] = db.product_label(p), pars.get(p["id"])
    return jsonify({"products": out})


@bp.patch("/products/<int:pid>")
@needs("admin")
def product_edit(conn, pid: int):
    db.save_product(conn, _body(), pid, user=_who())
    return jsonify({"status": "ok"})


@bp.post("/products")
@needs("admin")
def product_add(conn):
    return jsonify({"id": db.save_product(conn, _body(), user=_who())})


@bp.get("/dashboard")
@needs("staff")
def dashboard(conn):
    end = request.args.get("to") or db.last_trading_day(conn) or db.now()[:10]
    start = request.args.get("from") or end
    if start > end:
        start, end = end, start
    out = db.dashboard(conn, start, end)
    if not _ctx["has_role"]("manager"):
        # Staff see what to count and restock, not takings or margins.
        out = {"from": out["from"], "to": out["to"], "nights": out["nights"], "reorder": out["reorder"],
               "kpis": {k: out["kpis"][k] for k in ("drinks", "prev_drinks", "below_par", "negative", "reorder",
                                                     "waiting", "last_import", "last_count")}}
    return jsonify(out)


@bp.post("/import/square")
@needs("staff")
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
@needs("admin")
def imports_undo(conn, iid: int):
    return jsonify({"removed": db.undo_import(conn, iid)})


@bp.get("/mappings")
@needs("manager")
def mappings(conn):
    return jsonify({
        "unmapped": db.rows(conn, "SELECT item_key, MAX(item_name) item_name, SUM(qty) qty FROM events "
                                  "WHERE status = 'unmapped' GROUP BY item_key ORDER BY qty DESC"),
        "mapped": db.rows(conn, "SELECT m.*, r.name recipe, (SELECT SUM(qty) FROM events e WHERE e.item_key = m.item_key) "
                                "qty FROM mappings m LEFT JOIN recipes r ON r.id = m.recipe_id ORDER BY m.item_name"),
    })


@bp.post("/mappings")
@needs("admin")
def mapping_set(conn):
    b = _body()
    applied = db.set_mapping(conn, b["item_key"], b["item_name"], b.get("recipe_id") or None,
                             b.get("product_id") or None, b.get("ml") or None, bool(b.get("no_stock")))
    return jsonify({"applied": applied})


@bp.post("/mappings/delete")
@needs("admin")
def mapping_delete(conn):
    db.delete_mapping(conn, _body()["item_key"])
    return jsonify({"status": "ok"})


@bp.get("/recipes")
@needs("staff")
def recipes(conn):
    # Square's catalogue price for each button, so a drink's GP follows price changes made in Square.
    square_price = {db.item_key(p["item"], p["variation"]): p["price"] for p in db.rows(conn, "SELECT * FROM sell_prices")}
    out = []
    for r in db.rows(conn, "SELECT * FROM recipes ORDER BY active DESC, name"):
        r["lines"] = db.rows(conn, "SELECT l.product_id, l.ml, p.name, p.variant, p.unit_label FROM recipe_lines l "
                                   "JOIN products p ON p.id = l.product_id WHERE l.recipe_id = ?", r["id"])
        for line in r["lines"]:
            line["label"] = db.product_label(line)
        r["cost"] = db.recipe_cost(conn, r["id"])
        r["square_items"] = db.rows(conn, "SELECT item_key, item_name FROM mappings WHERE recipe_id = ?", r["id"])
        found = [square_price[s["item_key"]] for s in r["square_items"] if s["item_key"] in square_price]
        r["square_price"] = max(found) if found else None
        out.append(r)
    return jsonify({"recipes": out})


@bp.post("/recipes")
@needs("admin")
def recipe_save(conn):
    b = _body()
    return jsonify({"id": db.save_recipe(conn, b["name"], b["lines"], b.get("menu_price") or None,
                                         b.get("yield_ml") or None, b.get("note", ""),
                                         recipe_id=b.get("id") or None, special=bool(b.get("special")),
                                         square_items=b.get("square_items") or [])})


@bp.post("/recipes/<int:rid>/active")
@needs("admin")
def recipe_active(conn, rid: int):
    db.set_recipe_active(conn, rid, bool(_body().get("active")))
    return jsonify({"status": "ok"})


@bp.delete("/recipes/<int:rid>")
@needs("admin")
def recipe_delete(conn, rid: int):
    db.delete_recipe(conn, rid)
    return jsonify({"status": "ok"})


@bp.post("/batches")
@needs("job:batch")
def batch(conn):
    b = _body()
    made = b.get("made_ml")
    return jsonify({"made_ml": db.make_batch(conn, int(b["recipe_id"]), float(b.get("runs") or 1), user=_who(),
                                             made_ml=float(made) if made not in ("", None) else None)})


@bp.get("/deliveries")
@needs("manager")
def deliveries(conn):
    out = db.rows(conn, "SELECT * FROM deliveries ORDER BY status = 'draft' DESC, id DESC LIMIT 30")
    for d in out:
        d["lines"] = json.loads(d["lines"])
    return jsonify({"deliveries": out})


@bp.post("/deliveries")
@needs("admin")
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
@needs("admin")
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
@needs("admin")
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
@needs("admin")
def comp_reason(conn, eid: int):
    db.set_reason(conn, eid, _body()["reason"])
    return jsonify({"status": "ok"})


@bp.get("/prices")
@needs("manager")
def prices(conn):
    return jsonify({"prices": db.price_lines(conn)})


@bp.get("/prices/history")
@needs("manager")
def price_history(conn):
    return jsonify({"changes": db.rows(conn, "SELECT * FROM price_history ORDER BY id DESC LIMIT 300")})


@bp.post("/prices/catalogue")
@needs("admin")
def prices_import(conn):
    upload = request.files.get("file")
    if not upload:
        raise ValueError("Choose a Square catalogue CSV")
    return jsonify(venue_import.import_catalogue(conn, venue_import.decode_export(upload.read())))


@bp.post("/prices/<token>")
@needs("admin")
def price_match(conn, token: str):
    b = _body()
    conn.execute("UPDATE sell_prices SET product_id = ?, ml = ? WHERE token = ?",
                 (b.get("product_id") or None, b.get("ml") or None, token))
    return jsonify({"status": "ok"})


@bp.post("/square/sync")
@needs("admin")
def square_sync(conn):
    if not square_api.configured():
        raise ValueError("Square API is not set up. Use the CSV import, or add a token to venue.env")
    return jsonify(square_api.sync(conn, os.environ["SQUARE_ACCESS_TOKEN"], os.environ["SQUARE_LOCATION_ID"]))


# ── Branding ─────────────────────────────────────────────────────────────────
# Kept in the data folder beside the stock database, so a venue's logo and colours never go into git,
# survive updates, and travel with backups and data bundles.

_LOGO_TYPES = {b"\x89PNG\r\n\x1a\n": ("png", "image/png"), b"\xff\xd8\xff": ("jpg", "image/jpeg"),
               b"RIFF": ("webp", "image/webp")}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
# Look & feel choices. Each is one of a fixed list, so nothing typed in can reach the page's styles.
STYLE_CHOICES = {
    "theme": ("light", "dark", "auto"), "header": ("light", "dark", "brand"), "banner": ("brand", "dark", "plain"),
    "font": ("modern", "elegant", "classic", "times", "soft"), "size": ("s", "m", "l"),
    "corners": ("sharp", "soft", "round"), "density": ("compact", "comfy"),
}
STYLE_DEFAULTS = {"theme": "light", "header": "light", "banner": "brand", "font": "modern", "size": "m",
                  "corners": "soft", "density": "comfy"}


def _brand_path(name: str = "branding.json") -> str:
    return os.path.join(_ctx["data"], name)


def _branding() -> dict[str, Any]:
    try:
        with open(_brand_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_branding(b: dict[str, Any]) -> None:
    tmp = _brand_path("branding.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(b, fh)
    os.replace(tmp, _brand_path())


@bp.get("/branding")
def branding():
    """Public, so the sign-in screen can show the venue's logo and name. Holds nothing sensitive."""
    b = _branding()
    style = {k: b.get(k, d) for k, d in STYLE_DEFAULTS.items()}
    if "banner" not in b and b.get("header") == "dark":
        style["banner"] = "dark"  # looks saved before the banner had its own setting
    return jsonify({"name": b.get("name", ""), "color": b.get("color", ""), "logo": bool(b.get("logo")),
                    "logo_color": b.get("logo_color", ""), "v": b.get("v", 0), **style})


@bp.get("/branding/logo")
def branding_logo():
    b = _branding()
    if not b.get("logo") or b["logo"] not in {f"logo.{e}" for e, _ in _LOGO_TYPES.values()}:
        return ("", 404)
    resp = send_from_directory(_ctx["data"], b["logo"], mimetype=b.get("mime", "image/png"), max_age=86400)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "default-src 'none'"
    return resp


@bp.post("/branding")
@needs("admin")
def branding_save(conn):
    b, body = _branding(), _body()
    if "name" in body:
        b["name"] = str(body["name"]).strip()[:60]
    if "color" in body:
        if body["color"] and not _HEX.match(str(body["color"])):
            raise ValueError("Pick a colour")
        b["color"] = body["color"] or ""
    for key, allowed in STYLE_CHOICES.items():
        if key in body:
            if body[key] not in allowed:
                raise ValueError(f"Unknown {key} setting")
            b[key] = body[key]
    if "logo_color" in body:
        if body["logo_color"] and not _HEX.match(str(body["logo_color"])):
            raise ValueError("Pick a colour")
        b["logo_color"] = body["logo_color"] or ""
    if body.get("reset_style"):
        for key in list(STYLE_CHOICES) + ["color"]:
            b.pop(key, None)
    if body.get("remove_logo") and b.get("logo"):
        try:
            os.remove(_brand_path(b["logo"]))
        except OSError:
            pass
        b.pop("logo", None)
    b["v"] = int(time.time())
    _save_branding(b)
    return jsonify({"status": "ok"})


@bp.post("/branding/logo")
@needs("admin")
def branding_logo_upload(conn):
    """PNG, JPEG or WebP only, checked by content. SVG is refused because it can carry script."""
    upload = request.files.get("file")
    raw = upload.read(2 * 1024 * 1024 + 1) if upload else b""
    if not raw:
        raise ValueError("Choose a logo file")
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Keep the logo under 2 MB")
    kind = next((v for magic, v in _LOGO_TYPES.items() if raw.startswith(magic)), None)
    if not kind or (kind[0] == "webp" and raw[8:12] != b"WEBP"):
        raise ValueError("Use a PNG, JPG or WebP image")
    b = _branding()
    if b.get("logo"):
        try:
            os.remove(_brand_path(b["logo"]))
        except OSError:
            pass
    name = f"logo.{kind[0]}"
    with open(_brand_path(name), "wb") as fh:
        fh.write(raw)
    b.update(logo=name, mime=kind[1], v=int(time.time()))
    _save_branding(b)
    return jsonify({"status": "ok"})


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
