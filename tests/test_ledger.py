import os
import pytest
import square_api
import venue_db as db
import venue_import


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path))
    c.execute("INSERT INTO products (id, name, unit_label, unit_ml) VALUES (1, 'Vodka', '70cl bottle', 700)")
    c.execute("INSERT INTO products (id, name, unit_label, unit_ml) VALUES (2, 'Lime', '1L bottle', 1000)")
    c.execute("INSERT INTO products (id, name, unit_label, unit_ml) VALUES (3, 'Lager', '50L keg', 50000)")
    db.add_count(c, "Bar", {1: 2, 2: 1, 3: 0}, ts="2026-10-23T23:59:00")
    db.add_count(c, "Cellar", {1: 10, 3: 2}, ts="2026-10-23T23:59:00")
    db.set_mapping(c, "vodka|25ml", "Vodka 25ml", product_id=1, ml=25)
    return c


def ev(key, item="vodka|25ml", qty=1, **k):
    return {"key": key, "ts": "2026-10-24T20:00:00", "item_key": item, "item_name": item, "qty": qty, **k}


def test_sale_comes_off_overall_stock(conn):
    db.ingest(conn, [ev("a", qty=4)], "t")
    assert db.on_hand_ml(conn, 1) == 8400 - 100


def test_keg_uses_overall_stock(conn):
    db.set_mapping(conn, "pint", "Pint", product_id=3, ml=568)
    db.ingest(conn, [ev("a", "pint")], "t")
    assert db.on_hand_ml(conn, 3) == 100000 - 568


def test_stock_line_shows_overall_and_last_counts(conn):
    db.ingest(conn, [ev("a", qty=28)], "t")
    line = next(l for l in db.stock_lines(conn) if l["product_id"] == 1)
    assert line["units"] == 11 and line["counted"] == {"Bar": 2, "Cellar": 10}


def test_stocktake_adds_locations_and_resets_stock(conn):
    db.ingest(conn, [ev("a", qty=28)], "t")
    db.save_draft(conn, "Bar", 1, 1.5, "a")
    db.save_draft(conn, "Cellar", 1, 9, "b")
    assert db.on_hand_ml(conn, 1) == 7700  # drafts do not change stock
    assert db.finish_stocktake(conn) == {"Bar": 1, "Cellar": 1}
    assert db.on_hand_ml(conn, 1) == 7350
    assert not conn.execute("SELECT 1 FROM count_drafts").fetchone()
    with pytest.raises(ValueError):
        db.finish_stocktake(conn)


def test_uncounted_product_keeps_its_movements(conn):
    db.ingest(conn, [ev("a", qty=4)], "t")
    db.save_draft(conn, "Bar", 2, 1)
    db.save_draft(conn, "Cellar", 2, 0)
    db.finish_stocktake(conn)
    assert db.on_hand_ml(conn, 1) == 8300


def test_blank_location_keeps_last_figure_and_is_flagged(conn):
    db.save_draft(conn, "Bar", 1, 1)
    assert db.one_sided(conn) == ["Vodka (70cl bottle): Cellar not counted"]
    db.finish_stocktake(conn)
    assert db.on_hand_ml(conn, 1) == 700 + 7000


def test_reimport_never_double_counts(conn):
    assert db.ingest(conn, [ev("a")], "t")["added"] == 1
    r = db.ingest(conn, [ev("a")], "t")
    assert r == {**r, "added": 0, "skipped": 1}
    assert db.on_hand_ml(conn, 1) == 8375


def test_refund_keeps_stock_down_and_cancels_sale(conn):
    db.ingest(conn, [ev("a", qty=2), ev("r", kind="refund", qty=1)], "t")
    assert db.on_hand_ml(conn, 1) == 8350
    t = db.usage_report(conn, "2026-10-24", "2026-10-25")["totals_ml"]
    assert t["sale"] == 25 and t["refunded"] == 25


def test_reasons_split_usage(conn):
    db.ingest(conn, [ev("a", qty=4), ev("b", reason="wastage"), ev("c", reason="training", qty=2),
                     ev("d", reason="overpour")], "t")
    t = db.usage_report(conn, "2026-10-24", "2026-10-25")["totals_ml"]
    assert (t["sale"], t["wastage"], t["training"], t["overpour"]) == (100, 25, 50, 25)


def test_overpour_modifier_is_extra(conn):
    db.ingest(conn, [ev("a", qty=2, modifiers="Overpour +25ml")], "t")
    t = db.usage_report(conn, "2026-10-24", "2026-10-25")["totals_ml"]
    assert t["sale"] == 50 and t["overpour"] == 50


def test_unmapped_applies_once_mapped(conn):
    assert db.ingest(conn, [ev("a", "gin|25ml", 3)], "t")["unmapped"] == 1
    assert db.on_hand_ml(conn, 1) == 8400
    assert db.set_mapping(conn, "gin|25ml", "Gin", product_id=1, ml=10) == 1
    assert db.on_hand_ml(conn, 1) == 8370
    assert db.set_mapping(conn, "gin|25ml", "Gin", product_id=1, ml=10) == 0


def test_undo_import(conn):
    iid = db.ingest(conn, [ev("a")], "t")["import_id"]
    assert db.undo_import(conn, iid) == 1
    assert db.on_hand_ml(conn, 1) == 8400
    assert db.ingest(conn, [ev("a")], "t")["added"] == 1


def test_recipe_depletes_each_ingredient(conn):
    rid = db.save_recipe(conn, "Vodka Lime", [{"product_id": 1, "ml": 50}, {"product_id": 2, "ml": 20}])
    db.set_mapping(conn, "vl", "Vodka Lime", recipe_id=rid)
    db.ingest(conn, [ev("a", "vl", 2)], "t")
    assert db.on_hand_ml(conn, 1) == 8300
    assert db.on_hand_ml(conn, 2) == 960


def test_batch_moves_raw_to_premix_then_sale_uses_premix(conn):
    rid = db.save_recipe(conn, "Espresso Martini Mix", [{"product_id": 1, "ml": 500}, {"product_id": 2, "ml": 500}],
                         batch_yield_ml=1000)
    pid = conn.execute("SELECT batch_product_id FROM recipes WHERE id = ?", (rid,)).fetchone()[0]
    assert db.make_batch(conn, rid, 1) == 1000
    assert db.on_hand_ml(conn, 1) == 7900
    assert db.on_hand_ml(conn, pid) == 1000
    db.set_mapping(conn, "em", "EM", product_id=pid, ml=100)
    db.ingest(conn, [ev("x", "em", 3)], "t")
    assert db.on_hand_ml(conn, pid) == 700
    assert db.on_hand_ml(conn, 1) == 7900


def test_variance_adds_bar_and_cellar(conn):
    # Opening 12 bottles (8400), received 700, sold 100, wasted 25 > expect 8975.
    # Counted 1900 + 7000 = 8900 > −75ml.
    db.ingest(conn, [ev("a", qty=4), ev("b", reason="wastage")], "t")
    db._move(conn, "2026-10-24T10:00:00", 1, 700, "received")
    ts = "2026-10-25T23:00:00"
    db.add_count(conn, "Bar", {1: 1900 / 700}, ts=ts)
    db.add_count(conn, "Cellar", {1: 10}, ts=ts)
    row = next(r for r in db.variance_report(conn) if r["label"].startswith("Vodka"))
    assert row["variance_ml"] == pytest.approx(-75)
    assert row["closing_cellar"] == 10 and row["opening_units"] == 12
    assert db.on_hand_ml(conn, 1) == pytest.approx(8900)


def test_delivery_changes_stock_only_on_approval_and_remembers(conn):
    cur = conn.execute("INSERT INTO deliveries (ts, supplier, ref, lines) VALUES ('2026-10-28T12:00:00', 'Acme Drinks', '1', ?)",
                       ('[{"description":"Vodka 70cl","product_id":1,"units":5,"unit_cost":15.73}]',))
    assert db.on_hand_ml(conn, 1) == 8400
    db.approve_delivery(conn, cur.lastrowid)
    assert db.on_hand_ml(conn, 1) == 11900
    assert conn.execute("SELECT unit_cost FROM products WHERE id = 1").fetchone()[0] == 15.73
    assert conn.execute("SELECT product_id FROM supplier_map").fetchone()[0] == 1
    with pytest.raises(ValueError):
        db.approve_delivery(conn, cur.lastrowid)


DETAIL = """Date,Time,Time Zone,Category,Item,Qty,Price Point Name,SKU,Modifiers Applied,Gross Sales,Discounts,Net Sales,Tax,Transaction ID,Event Type,Notes
2026-10-24,20:01:00,London,Spirits,Vodka,1,25ml,,,£4.50,£0.00,£4.50,£0.75,T1,Payment,
2026-10-24,20:01:00,London,Spirits,Vodka,1,25ml,,,£4.50,£0.00,£4.50,£0.75,T1,Payment,
2026-10-24,20:05:00,London,Spirits,Vodka,1,25ml,,,£4.50,-£4.50,£0.00,£0.00,T2,Payment,Wastage
2026-10-24,20:06:00,London,Spirits,Vodka,1,25ml,,,£4.50,-£4.50,£0.00,£0.00,T3,Payment,
2026-10-24,21:00:00,London,Spirits,Vodka,-1,25ml,,,-£4.50,£0.00,-£4.50,-£0.75,T1,Refund,
"""


def test_csv_detail(conn):
    events = venue_import.parse_square_csv(DETAIL)
    assert len({e["key"] for e in events}) == 5
    assert [e["reason"] for e in events[2:4]] == ["wastage", "comp"]
    assert events[4]["kind"] == "refund"
    db.ingest(conn, events, "t")
    assert db.ingest(conn, venue_import.parse_square_csv(DETAIL), "t")["added"] == 0
    t = db.usage_report(conn, "2026-10-24", "2026-10-25")["totals_ml"]
    assert (t["sale"], t["wastage"], t["comp"], t["refunded"]) == (25, 25, 25, 25)
    cid = conn.execute("SELECT id FROM events WHERE reason = 'comp'").fetchone()[0]
    db.set_reason(conn, cid, "training")
    t = db.usage_report(conn, "2026-10-24", "2026-10-25")["totals_ml"]
    assert t["comp"] == 0 and t["training"] == 25


def test_csv_summary_needs_date():
    text = "Item Name,Item Variation,Items Sold,Net Sales\nVodka,25ml,12,£54.00\n"
    with pytest.raises(ValueError):
        venue_import.parse_square_csv(text)
    assert venue_import.parse_square_csv(text, "2026-10-24")[0]["qty"] == 12


ORDER = {
    "id": "O1", "closed_at": "2026-10-24T20:00:00Z",
    "discounts": [{"uid": "d1", "name": "Wastage"}],
    "line_items": [
        {"uid": "l1", "catalog_object_id": "V1", "name": "Vodka", "variation_name": "25ml", "quantity": "3",
         "gross_sales_money": {"amount": 1350}, "total_discount_money": {"amount": 450},
         "applied_discounts": [{"discount_uid": "d1", "applied_money": {"amount": 450}}],
         "total_money": {"amount": 900}},
        {"uid": "l2", "item_type": "CUSTOM_AMOUNT", "name": "Custom", "quantity": "1"},
    ],
}
RETURN = {"id": "O2", "closed_at": "2026-10-24T21:00:00Z", "returns": [{"source_order_id": "O1", "return_line_items": [
    {"uid": "r1", "catalog_object_id": "V1", "name": "Vodka", "variation_name": "25ml", "quantity": "1"}]}]}


def test_square_order_partial_comp_and_return(conn):
    db.ingest(conn, square_api.order_events(ORDER) + square_api.order_events(RETURN), "t")
    t = db.usage_report(conn, "2026-10-24", "2026-10-25")["totals_ml"]
    assert (t["wastage"], t["sale"], t["refunded"]) == (25, 25, 25)


def test_square_sync_pages_and_is_idempotent(conn):
    calls = []

    def post(token, body):
        calls.append(body.get("cursor"))
        return {"orders": [ORDER], "cursor": "c"} if len(calls) % 2 else {"orders": [RETURN]}

    assert square_api.sync(conn, "t", "L", post=post)["added"] == 3
    assert square_api.sync(conn, "t", "L", post=post)["added"] == 0
    assert calls == [None, "c", None, "c"]


CATALOGUE = """Token,Item Name,Variation Name,Categories,Price,Archived
T1,Gin,25ml,"SPIRITS > GIN",4.80,N
T2,Gin,Bottle/Mixers,"SPIRITS > GIN",120.00,N
T3,House Cognac,25ml,SPIRITS > COGNACS,6.00,N
T4,Cola,Pint,SOFT DRINKS,3.90,N
T5,Old Thing,25ml,SPIRITS > GIN,9.00,Y
T6,Chips,Regular,FOOD,4.00,N
T7,Open Tab,Regular,COCKTAILS,variable,N
"""


def catalogue_db(tmp_path):
    c = db.connect(str(tmp_path))
    c.execute("INSERT INTO products (id, name, variant, unit_label, unit_ml, unit_cost) VALUES (1, 'Bombay Sapphire Gin', 'Original', '70cl bottle', 700, 19.18)")
    c.execute("INSERT INTO products (id, name, variant, unit_label, unit_ml, unit_cost) VALUES (2, 'Coca-Cola', 'Original', '7L box', 7000, 83.25)")
    return c


def test_catalogue_sets_sell_prices_not_costs(tmp_path):
    c = catalogue_db(tmp_path)
    assert venue_import.import_catalogue(c, CATALOGUE) == {"prices": 4, "matched": 3, "removed": 0}
    assert c.execute("SELECT unit_cost FROM products WHERE id = 1").fetchone()[0] == 19.18
    lines = {l["token"]: l for l in db.price_lines(c)}
    assert set(lines) == {"T1", "T2", "T3", "T4"}
    # 25ml of a £19.18 bottle costs 69p; £4.80 is £4.00 before VAT.
    assert lines["T1"]["cost"] == 0.69 and lines["T1"]["gp_pct"] == 82.9
    assert lines["T2"]["ml"] == 700
    assert lines["T3"]["product_id"] is None  # the cognac is not in this test's stock
    # A pint of post-mix uses a sixth of its volume in syrup: 94.7ml of a £83.25 7L box is £1.13.
    assert lines["T4"]["product_id"] == 2 and round(lines["T4"]["ml"], 1) == 94.7 and lines["T4"]["cost"] == 1.13


def test_catalogue_reimport_refreshes_price_and_keeps_manual_match(tmp_path):
    c = catalogue_db(tmp_path)
    venue_import.import_catalogue(c, CATALOGUE)
    c.execute("UPDATE sell_prices SET product_id = 1, ml = 25 WHERE token = 'T3'")
    r = venue_import.import_catalogue(c, CATALOGUE.replace("T3,House Cognac,25ml,SPIRITS > COGNACS,6.00", "T3,House Cognac,25ml,SPIRITS > COGNACS,6.50").replace("T4,Cola,Pint,SOFT DRINKS,3.90,N\n", ""))
    assert r["removed"] == 1
    t3 = next(l for l in db.price_lines(c) if l["token"] == "T3")
    assert t3["price"] == 6.5 and t3["product_id"] == 1


def test_bottled_water_sizes_are_whole_bottles_and_uncategorised_drinks_load(tmp_path):
    c = db.connect(str(tmp_path))
    c.execute("INSERT INTO products (id, name, variant, unit_label, unit_ml) VALUES (1, 'Small Water', 'Sparkling', '330ml bottle', 330)")
    venue_import.import_catalogue(c, "Token,Item Name,Variation Name,Categories,Price,Archived\n"
                                     "A,Water Sparkling,Small,SOFT DRINKS,2.50,N\nB,Negroni,Regular,,13.00,N\nC,Venue Hire,Regular,,9.00,N\n")
    lines = {l["token"]: l for l in db.price_lines(c)}
    assert lines["A"]["ml"] == 330 and "B" in lines and "C" not in lines


def test_new_product_shows_on_stock_before_first_count(conn):
    conn.execute("INSERT INTO products (id, name, unit_label, unit_ml) VALUES (9, 'Roku Gin', '70cl bottle', 700)")
    line = next(l for l in db.stock_lines(conn) if l["product_id"] == 9)
    assert line["units"] == 0 and line["counted"] == {"Bar": 0, "Cellar": 0}


def test_merge_adds_counts_keeps_stock_movements_and_hides_source(conn):
    conn.execute("INSERT INTO products (id, name, unit_label, unit_ml, unit_cost) VALUES (8, 'Vodka Two', '70cl bottle', 700, 9.5)")
    bar_count = conn.execute("SELECT id FROM counts WHERE location = 'Bar'").fetchone()[0]
    conn.execute("INSERT INTO count_lines (count_id, product_id, units) VALUES (?, 8, 1)", (bar_count,))
    db._move(conn, "2026-10-28T12:00:00", 8, 700, "received")
    db.set_mapping(conn, "two", "Two", product_id=8, ml=25)
    db.merge_products(conn, 8, 1)
    assert db.on_hand_ml(conn, 1) == 8400 + 700 + 700
    assert conn.execute("SELECT unit_cost FROM products WHERE id = 1").fetchone()[0] == 9.5
    assert 8 not in [l["product_id"] for l in db.stock_lines(conn)]
    assert conn.execute("SELECT product_id FROM mappings WHERE item_key = 'two'").fetchone()[0] == 1


def test_batch_and_cocktail_cost_follow_ingredient_costs(conn):
    conn.execute("UPDATE products SET unit_cost = 7 WHERE id = 1")  # £1 per 100ml
    conn.execute("UPDATE products SET unit_cost = 10 WHERE id = 2")  # £1 per 100ml
    rid = db.save_recipe(conn, "Mix", [{"product_id": 1, "ml": 700}, {"product_id": 2, "ml": 300}], batch_yield_ml=1500)
    pid = conn.execute("SELECT batch_product_id FROM recipes WHERE id = ?", (rid,)).fetchone()[0]
    drink = db.save_recipe(conn, "Drink", [{"product_id": pid, "ml": 75}], note="Top: soda")
    assert round(db.recipe_cost(conn, drink), 2) == 0.5
    conn.execute("UPDATE products SET unit_cost = 14 WHERE id = 1")
    db.refresh_batch_costs(conn)
    assert round(db.recipe_cost(conn, drink), 2) == 0.85
    assert conn.execute("SELECT note FROM recipes WHERE id = ?", (drink,)).fetchone()[0] == "Top: soda"


def test_price_line_uses_recipe_cost_and_keeps_link_on_reimport(conn):
    conn.execute("UPDATE products SET unit_cost = 14 WHERE id = 1")
    rid = db.save_recipe(conn, "Negroni", [{"product_id": 1, "ml": 50}])
    text = "Token,Item Name,Variation Name,Categories,Price,Archived\nN,Negroni,Regular,,12.00,N\n"
    venue_import.import_catalogue(conn, text)
    conn.execute("UPDATE sell_prices SET recipe_id = ? WHERE token = 'N'", (rid,))
    venue_import.import_catalogue(conn, text.replace("12.00", "13.20"))
    line = db.price_lines(conn)[0]
    assert line["product"] == "Recipe: Negroni" and line["cost"] == 1 and line["price"] == 13.2 and line["gp_pct"] == 90.9


# Same shape as a real Square export: UTF-16, tabs, and Gross Sales meaning after discounts.
REAL_HEAD = "Date\tTime\tTime Zone\tCategory\tItem\tQty\tPrice Point Name\tSKU\tModifiers Applied\tProduct Sales\tDiscounts\tNet Sales\tTax\tGross Sales\tTransaction ID\tNotes\tEvent Type\t\n"
REAL_ROWS = (
    '2026-10-24\t20:00:00\tLondon\tVODKA\tHouse Vodka\t1.0\t25ml\t""\t""\t£4.90\t£0.00\t£4.90\t£0.00\t£4.90\tA\t""\tPayment\t\n'
    '2026-10-24\t20:01:00\tLondon\tSPRITZ\tAperol Spritz\t1.0\tRegular\t""\t""\t£12.00\t-£7.59\t£4.41\t£0.00\t£4.41\tB\t""\tPayment\t\n'
    '2026-10-24\t20:02:00\tLondon\tVODKA\tHouse Vodka\t1.0\t25ml\t""\t""\t£4.90\t-£4.90\t£0.00\t£0.00\t£0.00\tC\tRUM\tPayment\t\n'
)


def test_real_square_export_shape():
    raw = (REAL_HEAD + REAL_ROWS).encode("utf-16")
    events = venue_import.parse_square_csv(venue_import.decode_export(raw))
    assert [e["item_key"] for e in events] == ["house vodka|25ml", "aperol spritz", "house vodka|25ml"]
    assert [e["reason"] for e in events] == ["", "", "comp"]  # a part discount is still a sale


def test_decode_keeps_plain_csv():
    assert venue_import.decode_export(b"\xef\xbb\xbfItem,Qty") == "Item,Qty"


def test_no_stock_item_stops_waiting_and_uses_nothing(conn):
    assert db.ingest(conn, [ev("s", "soda|pint", 2)], "t")["unmapped"] == 1
    assert db.set_mapping(conn, "soda|pint", "Soda", no_stock=True) == 1
    assert conn.execute("SELECT status FROM events WHERE key = 's'").fetchone()[0] == "no_stock"
    assert db.ingest(conn, [ev("t", "soda|pint")], "t")["unmapped"] == 0
    assert not conn.execute("SELECT 1 FROM movements WHERE event_id IS NOT NULL").fetchone()


def test_shots_are_25ml_and_bottles_stay_whole():
    assert venue_import._serve_ml("house shot", "Regular", 700) == 25
    assert venue_import._serve_ml("house shot", "Bottle", 700) == 700
    assert venue_import._serve_ml("house tequila", "Reserve", 700) == 25


def test_staff_drinks_are_a_usage_reason(conn):
    pid = conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0]
    db.log_usage(conn, pid, 50, "staff", user="T")
    t = db.usage_report(conn, "2000", "2100")["totals_ml"]
    assert t["staff"] == 50 and t["wastage"] == 0


def _sheet(rows):
    import io
    import openpyxl
    from datetime import datetime

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "03NOV26"
    ws.append(["WET STOCK"])
    ws.append([])
    ws.append([])
    ws.append(["Location", "Category", "Sub-Category", "Item Name", "Variant", "Unit Size / Format", "Units Counted",
               "Unit Cost (£)", "Total Value (£)", "Par Level", "Reorder?", "Supplier", "Date Counted", "Notes"])
    for loc, name, variant, fmt, units in rows:
        ws.append([loc, "Spirits", "", name, variant, fmt, units, None, 0, None, None, "", datetime(2026, 11, 3)])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_excel_count_matches_merged_and_lists_new(conn):
    conn.execute("INSERT INTO products (id, name, variant, unit_label, unit_ml) VALUES (4, 'Rioja', '', '75cl bottle', 750)")
    conn.execute("INSERT INTO products (id, name, variant, unit_label, unit_ml, active) VALUES (5, 'Rioja', 'Old', '75cl bottle', 750, 0)")
    conn.execute("INSERT INTO products (id, name, variant, unit_label, unit_ml) VALUES (6, 'Gomme Syrup', 'Original', '70cl bottle', 700)")
    raw = _sheet([("Bar", "Vodka", "", "70cl bottle", 1.5), ("Cellar", "Vodka", "", "70cl bottle", 6),
                  ("Bar", "Rioja", "Old", "75cl bottle", 1), ("Bar", "Rioja", "New Label", "75cl bottle", 2),
                  ("Bar", "Acme Syrups", "Plain Sugar", "750mL bottle", 0.5),
                  ("Bar", "Lillet", "Rose", "750mL bottle", None)])
    r = venue_import.read_stocktake(conn, raw)
    assert r["date"] == "2026-11-03" and r["sheet"] == "03NOV26"
    assert r["lines"]["Bar"] == {1: 1.5, 4: 3, 6: 0.5} and r["lines"]["Cellar"] == {1: 6}
    assert [u["name"] for u in r["unmatched"]] == ["Lillet"] and r["blank"] == 1
    assert conn.execute("SELECT unit_ml FROM products WHERE id = 6").fetchone()[0] == 750
    r = venue_import.read_stocktake(conn, raw, add_new=True)
    assert not r["unmatched"] and r["added"] == ["Lillet Rose (750mL bottle)"]


def test_excel_count_rejects_other_files(conn):
    with pytest.raises(ValueError):
        venue_import.read_stocktake(conn, b"Item,Qty\n")


def test_finish_at_an_earlier_time_keeps_later_sales(conn):
    db.ingest(conn, [{**ev("late", qty=4), "ts": "2026-11-04T20:00:00"}], "t")
    db.save_draft(conn, "Bar", 1, 1)
    db.save_draft(conn, "Cellar", 1, 5)
    with pytest.raises(ValueError):
        db.finish_stocktake(conn, ts="2026-10-01T12:00")
    db.finish_stocktake(conn, ts="2026-11-03T23:59")
    assert db.on_hand_ml(conn, 1) == 6 * 700 - 100


def test_square_item_named_like_a_recipe_links_itself(conn):
    db.save_recipe(conn, "Vodka Lime", [{"product_id": 1, "ml": 50}, {"product_id": 2, "ml": 20}])
    r = db.ingest(conn, [ev("a", item=db.item_key("Vodka Lime"), qty=2)], "t")
    assert r["unmapped"] == 0
    assert db.on_hand_ml(conn, 1) == 8400 - 100


def test_recipe_edit_renames_and_links_square_items(conn):
    db.ingest(conn, [ev("a", item="house spritz", qty=1)], "t")
    rid = db.save_recipe(conn, "Spritz", [{"product_id": 1, "ml": 25}], special=True)
    db.save_recipe(conn, "Summer Spritz", [{"product_id": 1, "ml": 25}], recipe_id=rid,
                   square_items=[{"item_key": "house spritz", "item_name": "House Spritz"}])
    row = conn.execute("SELECT name, special FROM recipes WHERE id = ?", (rid,)).fetchone()
    assert tuple(row) == ("Summer Spritz", 0)
    assert db.on_hand_ml(conn, 1) == 8400 - 25


def test_recipe_in_use_cannot_be_deleted_only_archived(conn):
    rid = db.save_recipe(conn, "Typo", [{"product_id": 1, "ml": 25}])
    db.delete_recipe(conn, rid)
    rid = db.save_recipe(conn, "Used", [{"product_id": 1, "ml": 25}])
    db.set_mapping(conn, "used", "Used", recipe_id=rid)
    with pytest.raises(ValueError):
        db.delete_recipe(conn, rid)
    db.set_recipe_active(conn, rid, False)
    assert not db._auto_map(conn, "used", "Used")  # archived drinks stop linking new buttons


def test_product_size_is_locked_once_it_has_stock(conn):
    with pytest.raises(ValueError):
        db.save_product(conn, {"unit_label": "1L bottle"}, 1)
    pid = db.save_product(conn, {"name": "Gin", "unit_label": "70cl bottle", "unit_cost": "18", "par": "3"})
    db.save_product(conn, {"unit_label": "1L bottle"}, pid)
    assert conn.execute("SELECT unit_ml FROM products WHERE id = ?", (pid,)).fetchone()[0] == 1000


def test_dashboard_counts_after_midnight_towards_the_night_before(conn):
    conn.execute("UPDATE products SET unit_cost = 14 WHERE id = 1")
    db.ingest(conn, [ev("a", qty=2, net=10.0), {**ev("b", qty=1, net=5.0), "ts": "2026-10-25T01:30:00"}], "t")
    d = db.dashboard(conn, "2026-10-24", "2026-10-24")
    assert d["kpis"]["drinks"] == 3 and d["kpis"]["takings"] == 15.0
    assert d["by_day"] == [{"day": "2026-10-24", "drinks": 3.0, "takings": 15.0, "cost": 1.5}]
    assert d["items"][0]["gp_pct"] == 88.0  # 75ml of a £14 70cl bottle against £12.50 ex VAT


def test_custom_wastage_reason_is_kept_and_reported(conn):
    db.log_usage(conn, 1, 50, "breakage")
    db.log_usage(conn, 1, 25, "Staff drink")
    kinds = [r[0] for r in conn.execute("SELECT kind FROM movements ORDER BY id")]
    assert kinds == ["other:Breakage", "staff"]
    assert db.custom_reasons(conn) == ["Breakage"]
    with pytest.raises(ValueError):
        db.log_usage(conn, 1, 50, "")


def test_past_sales_keep_the_cost_they_had(conn):
    db.set_cost(conn, 1, 14.0, "test")
    db.ingest(conn, [ev("a", qty=1, net=5.0)], "t")
    db.set_cost(conn, 1, 28.0, "test")
    d = db.dashboard(conn, "2026-10-24", "2026-10-24")
    assert d["kpis"]["cost_of_sales"] == 0.5  # 25ml at the old £14 bottle price
    assert [c["new"] for c in conn.execute("SELECT new FROM price_history ORDER BY id")] == [14.0, 28.0]


def test_batch_can_record_what_actually_came_out(conn):
    rid = db.save_recipe(conn, "Mix", [{"product_id": 1, "ml": 700}], batch_yield_ml=1000)
    assert db.make_batch(conn, rid, 1, made_ml=950) == 950


def test_without_venue_rules_nothing_is_matched_and_everything_is_kept(tmp_path, venue_rules):
    os.remove(venue_import.rules_path())
    c = catalogue_db(tmp_path)
    assert venue_import.import_catalogue(c, CATALOGUE) == {"prices": 5, "matched": 0, "removed": 0}
    with open(venue_import.rules_path(), "w") as fh:  # put it back for the fixture to clean up
        fh.write("{}")


def test_phone_count_fills_only_what_was_counted_and_lists_new_items(conn):
    db.save_draft(conn, "Cellar", 1, 9)
    data = {"kind": "bar-stock-count", "by": "Sam",
            "counts": {"Bar": [[1, 2.5, "Vodka"], [99, 1, "Gone"]], "Cellar": []},
            "new": [{"loc": "Bar", "name": "Lillet Rose", "size": "75cl bottle", "units": 3, "category": "Wine"},
                    {"loc": "Bar", "name": "vodka", "size": "70cl bottle", "units": 1}]}
    r = db.phone_count(conn, data)
    assert r["filled"] == {"Bar": 2, "Cellar": 0} and r["skipped"] == ["Gone"] and r["by"] == "Sam (phone)"
    assert [n["name"] for n in r["new"]] == ["Lillet Rose"]
    drafts = {(d["location"], d["product_id"]): d["units"] for d in db.rows(conn, "SELECT * FROM count_drafts")}
    assert drafts[("Cellar", 1)] == 9 and drafts[("Bar", 1)] == 1  # the typed-in "vodka" matched the product
    r = db.phone_count(conn, data, add_new=True)
    assert r["added"] == ["Lillet Rose (75cl bottle)"] and not r["new"]
    with pytest.raises(ValueError):
        db.phone_count(conn, {"kind": "something else"})
    with pytest.raises(ValueError):
        db.phone_count(conn, {**data, "counts": {"Bar": [[1, -5]]}})
