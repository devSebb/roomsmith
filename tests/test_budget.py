"""The budget is the user's number. Code adds up exactly and reports; it never
blocks an add and never invents a price or a buffer."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rs_core import money  # noqa: E402
from rs_core.service import RoomService  # noqa: E402


@pytest.mark.parametrize(
    "text, want",
    [
        (1899, (1899.0, None)),
        ("1899.00", (1899.0, None)),
        ("USD 1899", (1899.0, "USD")),
        ("$1,899.00", (1899.0, "USD")),
        ("1.899,00 €", (1899.0, "EUR")),
        ("£649", (649.0, "GBP")),
        ("1 299,00 EUR", (1299.0, "EUR")),
        ("from $1,299", (1299.0, "USD")),
        ("$1,299 – $1,599", (1299.0, "USD")),
        ("2 seats, $499", (499.0, "USD")),
        ("Sale 20% off now $349.99", (349.99, "USD")),
        ("0,99 €", (0.99, "EUR")),
        ("CA$ 399", (399.0, "CAD")),
        ("2000 usd", (2000.0, "USD")),
    ],
)
def test_printed_prices_are_read(text, want):
    assert money.parse_price(text) == want


@pytest.mark.parametrize("bad", ["", "free", "call us", -5, 0, float("nan"), float("inf"), "99999999999", True, None, [], {}])
def test_things_that_are_not_prices_are_not_prices(bad):
    assert money.parse_price(bad) is None


def test_default_currency_only_fills_a_gap():
    assert money.parse_price("249", "USD") == (249.0, "USD")
    assert money.parse_price("€249", "USD") == (249.0, "EUR")


@pytest.fixture
def svc(tmp_path):
    s = RoomService(tmp_path / "data.db", tmp_path)
    yield s
    s.close()


@pytest.fixture
def room(svc):
    return svc.create_project("Bedroom", 3.0, 4.0, 2.5)["project_id"]


def ops(svc, room, *operations):
    return svc.apply({"project_id": room, "operations": list(operations), "actor": "agent"})


def add(svc, room, title, price, dims=(0.5, 0.5, 0.5)):
    return svc.add_product(room, title=title, dimensions_m=list(dims), price=price, actor="agent")


def test_no_budget_means_no_budget_anywhere(svc, room):
    r = add(svc, room, "Lamp", "$40")
    assert r["ok"] and "budget" not in r and "budget_note" not in r
    out = svc.inspect(room)
    assert "budget" not in out and "Budget" not in out["text"]
    assert svc.scene(room)["budget"] is None


def test_the_user_sets_the_amount_and_there_is_no_buffer_unless_asked(svc, room):
    r = ops(svc, room, {"op": "set_budget", "limit": 1500, "currency": "usd"})
    assert r["ok"] and r["summary"] == "Set the budget to USD 1,500"
    b = r["budget"]
    assert (b["limit"], b["reserve"], b["spendable"], b["spent"], b["remaining"]) == (1500.0, 0.0, 1500.0, 0.0, 1500.0)
    assert "kept back" not in b["text"]
    r = ops(svc, room, {"op": "set_budget", "limit": "$2,000", "reserve_percent": 10})
    assert r["budget"]["reserve"] == 200.0 and r["budget"]["spendable"] == 1800.0 and r["budget"]["currency"] == "USD"
    assert "USD 200 kept back" in r["summary"]
    r = ops(svc, room, {"op": "set_budget", "limit": 2000, "reserve": 150})
    assert r["budget"]["reserve"] == 150.0


@pytest.mark.parametrize("op", [{"op": "set_budget"}, {"op": "set_budget", "limit": "lots"}, {"op": "set_budget", "limit": -5}, {"op": "set_budget", "limit": 100, "reserve": 100}, {"op": "set_budget", "limit": 100, "reserve_percent": 80}, {"op": "set_budget", "limit": 100, "currency": "dollars"}])
def test_bad_budgets_are_typed_errors_and_change_nothing(svc, room, op):
    before = svc.head(room)["revision"]
    r = ops(svc, room, op)
    assert r["ok"] is False and r["error"]["code"] in ("missing_field", "invalid_value", "out_of_range")
    assert svc.head(room)["revision"] == before


def test_totals_are_exact_and_unknowns_are_listed_not_counted(svc, room):
    ops(svc, room, {"op": "set_budget", "limit": 1000, "currency": "USD"})
    add(svc, room, "Desk", "$249.99")
    add(svc, room, "Chair", "USD 129.01")
    add(svc, room, "Shelf", "0.10")
    add(svc, room, "Rug", None)
    add(svc, room, "Lamp", "€80")
    svc.apply({"project_id": room, "operations": [{"op": "add_object", "name": "Old wardrobe", "category": "wardrobe"}]})
    b = svc.inspect(room)["budget"]
    assert b["spent"] == 379.10 and b["remaining"] == 620.90
    assert len(b["items"]) == 3 and len(b["unpriced"]) == 1 and len(b["other_currency"]) == 1
    assert b["other_currency"][0]["currency"] == "EUR"
    assert b["text"] == "Budget USD 1,000 · spent USD 379.10 · USD 620.90 left · 1 without a price, not counted · 1 in another currency, not counted"
    assert "Budget USD 1,000" in svc.inspect(room)["text"]


def test_going_over_is_reported_never_blocked(svc, room):
    ops(svc, room, {"op": "set_budget", "limit": 500, "currency": "USD"})
    before = svc.head(room)["revision"]
    r = add(svc, room, "Sofa", "$649")
    assert r["ok"] and svc.head(room)["revision"] == before + 1  # it was added
    assert r["budget"]["over_limit"] and r["budget"]["remaining"] == -149.0
    assert "USD 149 over" in r["budget_note"] and "ask" in r["budget_note"].lower()
    issue = [i for i in svc.scene(room)["issues"] if i["code"] == "over_budget"]
    assert issue and issue[0]["severity"] == "warning" and "USD 149 over" in issue[0]["message"]
    svc.undo(room)
    assert not [i for i in svc.scene(room)["issues"] if i["code"] == "over_budget"]


def test_the_buffer_note_only_exists_when_the_user_asked_for_a_buffer(svc, room):
    ops(svc, room, {"op": "set_budget", "limit": 1000, "currency": "USD"})
    r = add(svc, room, "Desk", "$950")
    assert r["ok"] and "budget_note" not in r
    ops(svc, room, {"op": "set_budget", "limit": 1000, "currency": "USD", "reserve": 100})
    r = add(svc, room, "Lamp", "$20")
    assert r["budget"]["uses_reserve"] and "USD 70 of the USD 100" in r["budget_note"]


def test_notes_for_missing_and_foreign_prices(svc, room):
    ops(svc, room, {"op": "set_budget", "limit": 1000, "currency": "USD"})
    assert "No readable price" in add(svc, room, "Rug", None)["budget_note"]
    assert "does not convert" in add(svc, room, "Lamp", "€80")["budget_note"]


def test_lowering_the_budget_below_the_total_raises_the_issue(svc, room):
    add(svc, room, "Desk", "$300")
    r = ops(svc, room, {"op": "set_budget", "limit": 200, "currency": "USD"})
    assert r["ok"] and [i for i in r["issues"] if i["code"] == "over_budget"]
    r = ops(svc, room, {"op": "clear_budget"})
    assert r["ok"] and "budget" not in r and svc.scene(room)["budget"] is None


def test_budget_changes_are_revisions_with_undo(svc, room):
    ops(svc, room, {"op": "set_budget", "limit": 800, "currency": "USD"})
    assert svc.scene(room)["budget"]["limit"] == 800.0
    svc.undo(room)
    assert svc.scene(room)["budget"] is None
    svc.redo(room)
    assert svc.scene(room)["budget"]["limit"] == 800.0


def test_a_price_typed_in_the_editor_updates_the_total(svc, room):
    ops(svc, room, {"op": "set_budget", "limit": 1000, "currency": "USD"})
    r = add(svc, room, "Rug", None)
    oid = r["results"][0]["created_id"]
    r = svc.apply({"project_id": room, "actor": "user", "operations": [{"op": "update_object", "id": oid, "product": {"price": "$120"}}]})
    assert r["ok"] and r["budget"]["spent"] == 120.0 and r["budget"]["unpriced"] == []
    scene = svc.scene(room)["scene"]
    assert scene["objects"][0]["product"]["title"] == "Rug" and scene["objects"][0]["product"]["price_amount"] == 120.0


def test_products_keep_known_fields_only_and_public_links_only(svc, room):
    r = svc.apply({"project_id": room, "operations": [{"op": "add_object", "name": "Box", "category": "box", "product": {"title": "x" * 300, "url": "http://127.0.0.1/admin", "image_url": "file:///etc/passwd", "price": "$5", "evil": "<script>", "image_data": "javascript:alert(1)"}}]})
    assert r["ok"], r
    p = svc.scene(room)["scene"]["objects"][0]["product"]
    assert set(p) == {"title", "price", "price_amount", "price_currency"} and len(p["title"]) == 120


def test_scenes_without_a_budget_field_still_work_and_bad_budgets_do_not_import(svc, room):
    exported = json.loads(svc.export_bytes(room, "json")[0])
    assert "budget" not in exported["scene"]
    assert svc.import_json(exported)["ok"]
    exported["scene"]["budget"] = {"limit": -1}
    assert svc.import_json(exported)["ok"] is False


def test_shopping_list_has_prices_and_a_total(svc, room):
    ops(svc, room, {"op": "set_budget", "limit": 1000, "currency": "USD"})
    add(svc, room, "Desk", "$249.99")
    add(svc, room, "Chair", "$100")
    add(svc, room, "Rug", None)
    text = svc.export_bytes(room, "summary")[0].decode()
    assert "Desk" in text and "USD 249.99" in text and "Total: USD 349.99" in text and "price not known" in text and "Budget USD 1,000" in text


def test_style_is_the_users_words_stored_shown_and_undoable(svc, room):
    r = ops(svc, room, {"op": "set_style", "style": "  warm   minimalist, <b>light wood</b>  "})
    assert r["ok"] and r["summary"] == "Set the style to 'warm minimalist, light wood'"
    out = svc.inspect(room)
    assert out["style"] == "warm minimalist, light wood" and "Style the user asked for: warm minimalist, light wood." in out["text"]
    short = svc.shortlist(room, "desk", [{"title": "Desk", "dimensions_m": [1.0, 0.75, 0.5], "price": "$90"}])
    assert short["style"] == "warm minimalist, light wood" and "not style" in short["style_note"]
    assert len(svc.scene(room)["scene"]["style"]) <= 120
    assert ops(svc, room, {"op": "set_style", "style": "x" * 500})["ok"] and len(svc.scene(room)["scene"]["style"]) == 120
    svc.undo(room)
    assert svc.scene(room)["scene"]["style"] == "warm minimalist, light wood"
    assert ops(svc, room, {"op": "set_style"})["summary"] == "Removed the style" and "style" not in svc.scene(room)["scene"]
    assert "style" not in svc.inspect(room)
