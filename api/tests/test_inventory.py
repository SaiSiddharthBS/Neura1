"""Inventory: stock, purchase orders, deliveries and prices, consistent with each other and with the rest of the graph."""

from datetime import date

from neura1 import access, inventory
from neura1.ingest.validate import validate

TODAY = date(2026, 10, 17)


def test_every_ledger_adds_up_to_the_stock_on_record(graph):
    for row in inventory.items(graph, TODAY):
        if row["on_hand"] is None:
            continue
        ledger = inventory.item(graph, row["id"], TODAY)["ledger"]
        assert ledger and ledger[-1]["balance"] == row["on_hand"], row["id"]
        assert all(m["balance"] >= 0 for m in ledger)


def test_one_part_answered_completely(graph):
    nb = inventory.item(graph, "NB54360", TODAY)
    assert nb["last_order"]["id"] == "PO-2026-0097" and nb["last_order"]["supplier"].startswith("Deccan")
    assert [p["price"] for p in nb["price_history"] if p["kind"] == "paid"] == [212, 220, 230, 250]
    assert any(p["kind"] == "notice" and p["price"] == 320 for p in nb["price_history"])
    assert nb["planned_need"] == 480 and nb["stock"]["free"] == 60
    # The same arithmetic as the impact engine: 480 needed, 60 free, so 420 to buy.
    assert any("420 must be bought" in s for s in nb["insights"])
    assert nb["suppliers"][0]["on_time"] == 4 and nb["stock"]["status"] == "short"
    status = {r["id"]: r["status"] for r in inventory.items(graph, TODAY)}
    # CT-1051's 60 free all go to BO-0415; VX7-MCU is covered by the order already placed.
    assert status["CT-1051"] == "below_reorder" and status["VX7-MCU"] == "ok" and status["MC-3812"] == "ok"
    vx = inventory.item(graph, "VX7-MCU", TODAY)
    assert vx["stock"]["on_order"] == 200 and vx["orders"][0]["status"] == "open"
    assert sum(o["rejected_qty"] for o in vx["orders"]) == 5


def test_a_migrated_part_has_no_invented_price(graph):
    ct = inventory.item(graph, "CT-1051", TODAY)
    assert ct["orders"] == [] and ct["stock"]["last_price"] is None
    assert any("no price paid" in s for s in ct["insights"])


def test_prices_are_hidden_from_people_who_may_not_see_money(graph):
    shown = access.redact_money(inventory.item(graph, "NB54360", TODAY))
    assert all(p["price"] is None for p in shown["price_history"])
    assert shown["stock"]["last_price"] is None and all(o["unit_price"] is None for o in shown["orders"])


def test_stock_ledger_imports_accept_stock_leaving_the_stores():
    head = "id,item_id,date,qty,kind,ref,location,note\n"
    ok = validate({"stock_moves.csv": head + "SM-9,NB54360,2026-10-01,-40,issue,BO-1,A2,\n"},
                  {"items": {"NB54360"}})
    assert not [i for i in ok["issues"] if i["level"] == "error"]
    bad = validate({"stock_moves.csv": head + "SM-9,NB54360,2026-10-01,-40,teleport,BO-1,A2,\n"},
                   {"items": {"NB54360"}})
    assert any(i["column"] == "kind" for i in bad["issues"])
