"""Optional live Square sync. Added in this fork.

Stays off unless SQUARE_ACCESS_TOKEN and SQUARE_LOCATION_ID are set. Feeds the same
event pipeline as the CSV import, so re-reading an order never double-counts.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import venue_db as db

API = "https://connect.squareup.com/v2/orders/search"
OVERLAP = timedelta(minutes=15)
RESCAN = timedelta(hours=72)  # offline POS orders can arrive this late


def _reason(name: str) -> str:
    low = (name or "").lower()
    return next((r for r in db.REASONS if r in low), "")


def _money(obj: dict[str, Any] | None) -> float:
    return (obj or {}).get("amount", 0) / 100


def order_events(order: dict[str, Any]) -> list[dict[str, Any]]:
    """One order > events. A discount named Wastage/Overpour/Training/Staff moves the comped part of a
    line out of sales; a line fully discounted under any other name is an unclassified comp."""
    ts = (order.get("closed_at") or order.get("updated_at") or "")[:19]
    oid = order["id"]
    names = {d.get("uid"): d.get("name", "") for d in order.get("discounts") or []}
    out = []
    for line in order.get("line_items") or []:
        if not line.get("catalog_object_id") and line.get("item_type") == "CUSTOM_AMOUNT":
            continue
        qty = float(line.get("quantity") or 0)
        name, variation = line.get("name", ""), line.get("variation_name", "")
        base = {
            "ts": ts, "item_key": db.item_key(name, variation),
            "item_name": name + (f" - {variation}" if variation and variation.lower() != "regular" else ""),
            "modifiers": ", ".join(m.get("name", "") for m in line.get("modifiers") or []),
        }
        gross = _money(line.get("gross_sales_money"))
        reason, comped = "", 0.0
        for applied in line.get("applied_discounts") or []:
            hit = _reason(names.get(applied.get("discount_uid"), ""))
            if hit:
                reason = hit
                comped += _money(applied.get("applied_money"))
        total_discount = _money(line.get("total_discount_money"))
        if not reason and gross > 0 and total_discount >= gross:
            reason, comped = "comp", gross
        comp_qty = round(qty * min(comped / gross, 1), 3) if gross > 0 and reason else 0.0
        uid = line.get("uid")
        if comp_qty:
            out.append({**base, "key": f"sq:{oid}:{uid}:comp", "kind": "sale", "qty": comp_qty, "reason": reason})
        if qty - comp_qty > 0:
            out.append({**base, "key": f"sq:{oid}:{uid}", "kind": "sale", "qty": qty - comp_qty,
                        "net": _money(line.get("total_money"))})
    for ret in order.get("returns") or []:
        for line in ret.get("return_line_items") or []:
            if not line.get("catalog_object_id"):
                continue
            name, variation = line.get("name", ""), line.get("variation_name", "")
            out.append({
                "key": f"sq:{oid}:{line.get('uid')}:ret", "ts": ts, "kind": "refund",
                "item_key": db.item_key(name, variation), "item_name": name,
                "qty": float(line.get("quantity") or 0),
            })
    return out


def _post(token: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_orders(token: str, location: str, since: datetime, until: datetime,
                 post: Callable[[str, dict[str, Any]], dict[str, Any]] = _post) -> list[dict[str, Any]]:
    fmt = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body: dict[str, Any] = {"location_ids": [location], "limit": 500, "query": {
        "filter": {"state_filter": {"states": ["COMPLETED"]},
                   "date_time_filter": {"updated_at": {"start_at": fmt(since), "end_at": fmt(until)}}},
        "sort": {"sort_field": "UPDATED_AT", "sort_order": "ASC"}}}
    orders: list[dict[str, Any]] = []
    while True:
        page = post(token, body)
        orders.extend(page.get("orders") or [])
        if not page.get("cursor"):
            return orders
        body["cursor"] = page["cursor"]


def sync(conn, token: str, location: str, post=_post, full_rescan: bool = False) -> dict[str, int]:
    until = datetime.now(timezone.utc)
    row = conn.execute("SELECT value FROM meta WHERE key = 'square_last_sync'").fetchone()
    last = datetime.fromisoformat(row[0]) if row else until - RESCAN
    since = until - RESCAN if full_rescan else last - OVERLAP
    events = [e for o in fetch_orders(token, location, since, until, post) for e in order_events(o)]
    result = db.ingest(conn, events, "square-api", user="sync")
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('square_last_sync', ?)", (until.isoformat(),))
    return result


def configured() -> bool:
    return bool(os.environ.get("SQUARE_ACCESS_TOKEN") and os.environ.get("SQUARE_LOCATION_ID"))
