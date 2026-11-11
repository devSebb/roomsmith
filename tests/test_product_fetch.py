"""Product page reading, offline: JSON-LD, Shopify JSON, OpenGraph, visible text."""

import json

from rs_core import product_fetch as pf

JSONLD_PAGE = b"""<!doctype html><html><head><title>Sven Charme Tan Sofa | Shop</title>
<meta property="og:image" content="https://img.example.com/og.jpg">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"Shop"},
{"@type":"Product","name":"Sven Charme Tan Sofa","image":["https://img.example.com/sven.jpg"],
"description":"<p>Mid-century sofa.</p><p>Overall dimensions: 88\\"W x 35\\"D x 34\\"H</p>",
"offers":{"@type":"Offer","price":"1799.00","priceCurrency":"USD"}}]}</script>
</head><body><h1>Sven</h1><p>Seat height 17".</p></body></html>"""

SHOPIFY_PAGE = """<!doctype html><html><head><title>The Bed Frame</title>
<meta property="og:title" content="The Bed Frame - Floyd"><meta property="og:image" content="https://cdn.shopify.com/s/files/bed.jpg">
<script src="https://cdn.shopify.com/s/javascripts/x.js"></script></head><body>Loading…</body></html>""".encode()
SHOPIFY_JSON = json.dumps({
    "title": "The Bed Frame", "price": 107000, "images": ["//cdn.shopify.com/s/files/bed-1.jpg", "//cdn.shopify.com/s/files/bed-2.jpg"],
    "description": "<p>A platform bed.</p><ul><li>Twin: Overall: 45” W x 86\" L x 7.5” H</li><li>Full/Queen: Overall: 67” W x 86\" L x 7.5” H</li></ul>",
}).encode()

OG_ONLY = b"""<html><head><title>Lamp</title><meta property="og:title" content="Arc Floor Lamp"><meta property="og:description" content="Dimensions: H 200 cm, W 35 cm, D 35 cm">
<meta property="product:price:amount" content="149"><meta property="product:price:currency" content="EUR"></head><body></body></html>"""

TEXT_ONLY = b"""<html><body><h1>Oak dining table</h1><div class="specs"><div>Material: oak</div><div>Size: 160 x 90 x 75 cm</div></div></body></html>"""


def fake_get(responses):
    calls = []

    def _get(url, timeout=0, accept=""):
        calls.append(url)
        for key, body in responses.items():
            if key in url:
                return body, "text/html", url
        raise pf.FetchError("http_error", "HTTP 404 fetching the page")

    _get.calls = calls
    return _get


def test_jsonld_product_with_dimensions_in_description():
    r = pf.fetch_product("https://shop.example.com/products/sven", category="sofa", _get=fake_get({"sven": JSONLD_PAGE}))
    assert r["ok"] and r["source"] == "json-ld"
    assert r["title"] == "Sven Charme Tan Sofa" and r["price"] == "USD 1799.00" and r["image_url"] == "https://img.example.com/sven.jpg"
    assert [round(v, 3) for v in r["dimensions_m"]] == [2.235, 0.864, 0.889]
    assert "Overall dimensions" in r["dimensions_text"]


def test_shopify_store_falls_back_to_product_json_and_bed_axes():
    g = fake_get({"the-bed-frame.js": SHOPIFY_JSON, "the-bed-frame": SHOPIFY_PAGE})
    r = pf.fetch_product("https://floyd.example.com/products/the-bed-frame?variant=1", category="bed_double", _get=g)
    assert r["ok"] and r["source"] in ("shopify", "og")
    assert g.calls[0].endswith("/products/the-bed-frame.js") and len(g.calls) == 1  # JSON first; HTML not needed
    assert r["title"] == "The Bed Frame" and r["price"] == "1070.00"
    assert r["image_url"] == "https://cdn.shopify.com/s/files/bed-1.jpg"
    # the user asked about a double: the Full/Queen line wins over the Twin; a bed's L is its length (depth)
    assert round(r["dimensions_m"][0], 2) == 1.70 and round(r["dimensions_m"][2], 2) == 2.18
    assert pf.fetch_product("https://floyd.example.com/products/the-bed-frame", category="bed_single", _get=g)["dimensions_m"][0] == 1.143


def test_opengraph_only_page():
    r = pf.fetch_product("https://lamps.example.com/arc", _get=fake_get({"arc": OG_ONLY}))
    assert r["ok"] and r["title"] == "Arc Floor Lamp" and r["price"] == "EUR 149"
    assert [round(v, 2) for v in r["dimensions_m"]] == [0.35, 2.0, 0.35]


def test_visible_text_only_and_no_dimensions():
    r = pf.fetch_product("https://tables.example.com/oak", category="table_dining", _get=fake_get({"oak": TEXT_ONLY}))
    assert r["ok"] and r["dimensions_m"] == [1.6, 0.75, 0.9]
    r2 = pf.fetch_product("https://tables.example.com/oak", _get=fake_get({"oak": b"<html><body><h1>Chair</h1></body></html>"}))
    assert r2["ok"] and r2["dims"] is None and any("No readable dimensions" in n for n in r2["notes"])


def test_site_problems_are_results_not_exceptions():
    def blocked(url, timeout=0, accept=""):
        raise pf.FetchError("blocked", "The site refused the request (HTTP 429). Ask the user for the sizes printed on the page.")

    r = pf.fetch_product("https://shop.example.com/products/x", _get=blocked)
    assert r["ok"] is False and r["error"]["code"] == "blocked"
    assert pf.fetch_product("ftp://nope", _get=blocked)["error"]["code"] == "bad_url"
    assert pf.fetch_product("http://127.0.0.1:8080/admin", _get=blocked)["error"]["code"] == "bad_url"


def test_bot_check_page_is_reported_as_blocked():
    waf = b"<!DOCTYPE html><html><head><title></title><script>window.awsWafCookieDomainList=['x.com'];</script></head><body></body></html>"
    r = pf.fetch_product("https://shop.example.com/product/1", _get=fake_get({"product/1": waf}))
    assert r["ok"] is False and r["error"]["code"] == "blocked" and "bot-check" in r["error"]["message"]


def test_add_product_from_url_alone(tmp_path, monkeypatch):
    """The agent passes only the link: the service reads the page, parses the size,
    keeps title/price/link and a thumbnail on the object."""
    from rs_core import service as svc_mod
    from rs_core.service import RoomService

    monkeypatch.setattr(svc_mod.product_fetch, "fetch_product", lambda url, category=None: {
        "ok": True, "url": url, "title": "Hamilton Sofa", "price": "USD 1899", "image_url": "https://img.example.com/h.png",
        "source": "json-ld", "dimensions_text": 'Dimension: W88.6" x D39.4" x H32.3"', "dimensions_m": [2.2504, 0.8204, 1.0008], "notes": []})
    monkeypatch.setattr(RoomService, "product_thumbnail", lambda self, u: "data:image/jpeg;base64,/9j/4AAQ")
    s = RoomService(tmp_path / "data.db", tmp_path)
    pid = s.create_project("L", width_m=4, depth_m=5)["project_id"]
    r = s.add_product(pid, title="", url="https://www.castlery.com/us/products/hamilton-sofa", place={"against_wall": "back", "align": "center"})
    assert r["ok"], r
    o = r["object"]
    assert o["name"] == "Hamilton Sofa" and o["category"] == "sofa"
    assert [round(v, 2) for v in o["dimensions_m"]] == [2.25, 0.82, 1.0]
    assert o["product"]["price"] == "USD 1899" and o["product"]["url"].startswith("https://www.castlery.com")
    scene = s.scene(pid)["scene"]
    assert scene["objects"][0]["product"]["image_data"].startswith("data:image/jpeg;base64,")
    # no printed size -> a clear error with what was read, nothing added
    monkeypatch.setattr(svc_mod.product_fetch, "fetch_product", lambda url, category=None: {
        "ok": True, "url": url, "title": "Classic Bed", "price": None, "image_url": None, "source": "json-ld", "dimensions_text": None, "dimensions_m": None, "dims": None, "notes": ["No readable dimensions on the page."]})
    r2 = s.add_product(pid, title="", url="https://www.thuma.co/products/the-bed")
    assert r2["ok"] is False and r2["error"]["code"] == "dimensions_not_found" and r2["error"]["fetched"]["title"] == "Classic Bed"
    assert len(s.scene(pid)["scene"]["objects"]) == 1


SCRIPT_PAGE = r"""<!doctype html><html><head><title>Neva Sofa</title><meta property="og:title" content="Neva Sofa">
<script src="/app.js"></script>
<script>window.sections = {"dimensions":{"html":"<ul>\n<li>Overall dimensions: 84”W x 41”D x 33”H<\/li>\n<li>Seat height: 18”<\/li><\/ul>"}};</script>
<script>self.__next_f.push([1,"{\"_168\":145},\"Classic Bed (1 of 2) - 83” x 13” x 5”\",[],\"\\nQueen: 68” W x 93” D x 11.6” H\",\"King: 84” W x 93” D x 11.6” H\""])</script>
</head><body><h1>Neva Sofa</h1><p>Soft.</p></body></html>""".encode()

DESK_PAGE = b"""<html><head><title>Tria Standing Desk</title></head><body><h1>Desk</h1><select><option>48 inches x 27 inches Desk Size</option></select></body></html>"""


def test_dimensions_buried_in_inline_scripts_and_variant_preference():
    g = fake_get({"neva": SCRIPT_PAGE})
    r = pf.fetch_product("https://sixpenny.example.com/neva", category="sofa", _get=g)
    assert r["ok"] and r["dimensions_text"].startswith("Overall dimensions: 84”W x 41”D x 33”H")
    assert [round(v, 3) for v in r["dimensions_m"]] == [2.134, 0.838, 1.041]
    # a queen bed: the Queen line wins over the shipping-box line and the King line
    r = pf.fetch_product("https://sixpenny.example.com/neva", category="bed_queen", _get=g)
    assert r["dimensions_text"] == "Queen: 68” W x 93” D x 11.6” H" and round(r["dimensions_m"][2], 3) == 2.362
    r = pf.fetch_product("https://sixpenny.example.com/neva", category="bed_king", _get=g)
    assert r["dimensions_text"].startswith("King: 84”")


def test_shopify_json_without_sizes_falls_through_to_the_page():
    g = fake_get({"neva-sofa-84.js": json.dumps({"title": "Neva Sofa", "price": 289900, "images": [], "description": "<p>Soft.</p>"}).encode(), "neva-sofa-84": SCRIPT_PAGE})
    r = pf.fetch_product("https://sixpenny.example.com/products/neva-sofa-84", category="sofa", _get=g)
    assert len(g.calls) == 2 and r["source"] == "shopify" and r["price"] == "2899.00"
    assert r["dimensions_text"].startswith("Overall dimensions: 84”W")


def test_footprint_only_takes_the_usual_height_for_the_category():
    r = pf.fetch_product("https://desks.example.com/tria", category="desk", _get=fake_get({"tria": DESK_PAGE}))
    assert r["ok"] and [round(v, 3) for v in r["dimensions_m"]] == [1.219, 0.75, 0.686]
    assert r["dims"]["height_assumed"] is True and any("usual desk height" in n for n in r["notes"])
    # without a category there is nothing to assume: no dimensions, honest note
    r2 = pf.fetch_product("https://desks.example.com/tria", _get=fake_get({"tria": DESK_PAGE}))
    assert r2["dimensions_m"] is None


def test_product_color_is_the_photo_s_dominant_colour():
    import base64
    import io

    import pytest

    PIL = pytest.importorskip("PIL.Image")
    from rs_core.media import product_color

    im = PIL.new("RGB", (40, 40), (255, 255, 255))  # studio white
    for x in range(8, 32):
        for y in range(14, 34):
            im.putpixel((x, y), (193, 189, 180))  # a cream sofa
    buf = io.BytesIO(); im.save(buf, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    assert product_color(url) == "#c1bdb4"
    assert product_color("data:image/png;base64,AAAA") is None


def test_fractional_inches_are_read(tmp_path):
    from rs_core import dims

    assert dims.unfraction('18 7/8x15 3/8x24 3/8 "') == '18.875x15.375x24.375 "'
    assert dims.unfraction("3/4 in, 1-1/2 in, 11/10/2026, 7/0") == "0.75 in, 1.5 in, 11/10/2026, 7/0"
    n = dims.parse_dimensions('18 7/8x15 3/8x24 3/8 "', category="nightstand")
    assert [round(n[k], 2) for k in ("width_m", "depth_m", "height_m")] == [0.48, 0.39, 0.62]
    b = dims.parse_dimensions('Length: 82 1/4 "; Width: 63 "; Headboard height: 36 1/4 "', category="bed_queen")
    assert [round(b[k], 2) for k in ("width_m", "depth_m", "height_m")] == [1.6, 2.09, 0.92]


def test_a_size_in_the_product_name_wins_over_a_number_triple_in_a_review():
    """Found live on an IKEA page: the size was in the name, and '8 x 8 x 2' from a
    customer review was read as the product's size and reported as verified."""
    ld = {"@type": "Product", "name": 'TARVA Nightstand - pine 18 7/8x15 3/8x24 3/8 "', "offers": {"@type": "Offer", "price": "79.99", "priceCurrency": "USD"}}
    body = ("<html><head><script type='application/ld+json'>" + json.dumps(ld) + "</script></head><body><p>I bought 4 of these. Each box was 8 x 8 x 2 inches of screws.</p></body></html>").encode()
    r = pf.fetch_product("https://shop.example.com/p/tarva", category="nightstand", _get=lambda *a, **k: (body, "text/html", "https://shop.example.com/p/tarva"))
    assert r["ok"] and [round(v, 2) for v in r["dimensions_m"]] == [0.48, 0.62, 0.39]
    review_only = ("<html><head><script type='application/ld+json'>" + json.dumps({**ld, "name": "TARVA Nightstand"}) + "</script></head><body><p>Dimensions of the bag of screws: 8 x 8 x 2 inches.</p></body></html>").encode()
    r = pf.fetch_product("https://shop.example.com/p/tarva2", category="nightstand", _get=lambda *a, **k: (review_only, "text/html", "https://shop.example.com/p/tarva2"))
    assert r["ok"] and r["dimensions_m"] is None  # implausible for a nightstand: say there is no size, never a wrong one


def test_offers_shaped_as_lists_and_pages_that_break_the_reader_do_not_raise():
    """Found live: schema.org priceSpecification as a list raised AttributeError through the tool."""
    ld = {"@type": "Product", "name": "Bed", "description": "W 160 cm x D 200 cm x H 90 cm", "offers": [{"@type": "Offer", "priceSpecification": [{"price": "199", "priceCurrency": "USD"}]}]}
    body = ("<script type='application/ld+json'>" + json.dumps(ld) + "</script>").encode()
    r = pf.fetch_product("https://shop.example.com/p/bed", category="bed_queen", _get=lambda *a, **k: (body, "text/html", "https://shop.example.com/p/bed"))
    assert r["ok"] and r["price"] == "USD 199" and r["dimensions_m"]
    weird = ("<script type='application/ld+json'>" + json.dumps({"@type": "Product", "name": "X", "offers": {"price": {"oops": 1}, "priceSpecification": 7}}) + "</script>").encode()
    assert pf.fetch_product("https://shop.example.com/p/x", _get=lambda *a, **k: (weird, "text/html", "u"))["ok"] in (True, False)

    def boom(*a, **k):
        raise RuntimeError("anything")

    r = pf.fetch_product("https://shop.example.com/p/y", _get=boom)
    assert r["ok"] is False and r["error"]["code"] == "unreadable" and "RuntimeError" in r["error"]["message"]
