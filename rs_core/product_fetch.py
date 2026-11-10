"""Read a product page the user pasted: title, price, image and dimensions.

Standard library only. One GET to the URL the user gave (plus, for Shopify
stores, the store's public product JSON next to it), with a plain User-Agent
and a size cap. Sources, in order of trust:

1. schema.org ``Product`` JSON-LD  (``<script type="application/ld+json">``)
2. Shopify product JSON            (``/products/<handle>.js``)
3. OpenGraph / meta tags
4. visible page text

Dimensions are found by scanning the candidate texts (structured description
first, then the page) for a line the dimension parser can read in full, giving
preference to lines that say "overall" or "dimensions". Nothing here guesses:
when no dimensions are printed, ``dims`` is None and the caller asks the user.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

from rs_core import dims as dims_mod

USER_AGENT = "Roomsmith/0.1 (+https://github.com/devSebb/roomsmith; reads only pages the user pastes)"
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT_S = 12

_DIM_LINE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:cm|mm|m|in|inch|inches|\"|”|′|'|ft)?\s*(?:x|×|\*|by)\s*[WDHL]?\s*:?\s*\d", re.I)
_PRIORITY = re.compile(r"overall|dimension|measure|size", re.I)


class FetchError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


# ------------------------------------------------------------------ HTTP


def _get(url: str, timeout: float = TIMEOUT_S, accept: str = "text/html,application/json;q=0.9,*/*;q=0.5") -> tuple[bytes, str, str]:
    """Return (body, content_type, final_url). Raises FetchError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "en", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (http/https only, checked by caller)
            data = resp.read(MAX_BYTES + 1)
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                try:
                    data = gzip.decompress(data)
                except OSError:
                    pass
            if len(data) > MAX_BYTES:
                raise FetchError("too_large", "The page is over 8 MB")
            return data, resp.headers.get("Content-Type", ""), resp.geturl()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429, 503):
            raise FetchError("blocked", f"The site refused the request (HTTP {e.code}). Ask the user for the sizes printed on the page.") from e
        raise FetchError("http_error", f"HTTP {e.code} fetching the page") from e
    except urllib.error.URLError as e:
        raise FetchError("unreachable", f"Could not reach the site: {e.reason}") from e
    except TimeoutError as e:
        raise FetchError("timeout", "The site did not answer in time") from e


def _check_url(url: str) -> str:
    u = (url or "").strip()
    p = urllib.parse.urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise FetchError("bad_url", "Give a full http(s) product URL")
    host = p.hostname or ""
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local") or re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.)", host):
        raise FetchError("bad_url", "Only public product pages can be read")
    return u


# ------------------------------------------------------------------ HTML


class _Page(HTMLParser):
    """Collect JSON-LD blocks, meta tags, title and visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.jsonld: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self.text: list[str] = []
        self._in: str | None = None
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script":
            self._in = "jsonld" if a.get("type", "").lower().strip() == "application/ld+json" else "skip"
        elif tag in ("style", "noscript", "svg"):
            self._in = "skip"
        elif tag == "title":
            self._in = "title"
        elif tag == "meta":
            key = a.get("property") or a.get("name") or a.get("itemprop")
            if key and a.get("content"):
                self.meta.setdefault(key.lower(), a["content"])
        elif tag in ("br", "li", "p", "div", "tr", "h1", "h2", "h3", "h4", "dd", "dt", "td", "th"):
            self.text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg", "title"):
            self._in = None
        if tag in ("li", "p", "div", "tr", "h1", "h2", "h3", "h4", "dd", "td"):
            self.text.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in == "jsonld":
            self.jsonld.append(data)
        elif self._in == "title":
            self.title += data
        elif self._in is None:
            self.text.append(data)


def _strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>|</li>|</div>|</tr>|</h\d>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(s)


def _lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            out.append(line)
    return out


# ------------------------------------------------------------------ structured data


def _walk_products(node: Any) -> list[dict]:
    """All objects typed Product (or ProductGroup) in a JSON-LD document."""
    found: list[dict] = []
    if isinstance(node, dict):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(isinstance(x, str) and x.lower() in ("product", "productgroup", "individualproduct") for x in types):
            found.append(node)
        for v in node.values():
            if isinstance(v, (dict, list)):
                found.extend(_walk_products(v))
    elif isinstance(node, list):
        for v in node:
            found.extend(_walk_products(v))
    return found


def _first_str(v: Any) -> str | None:
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, list) and v:
        return _first_str(v[0])
    if isinstance(v, dict):
        for k in ("url", "contentUrl", "name", "@id"):
            if isinstance(v.get(k), str):
                return v[k]
    return None


def _price_from_offers(offers: Any) -> str | None:
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        return None
    price = offers.get("price") or offers.get("lowPrice") or (offers.get("priceSpecification") or {}).get("price")
    cur = offers.get("priceCurrency") or (offers.get("priceSpecification") or {}).get("priceCurrency") or ""
    if price is None:
        return None
    return f"{cur} {price}".strip()


def _qv(v: Any) -> str | None:
    """schema.org QuantitativeValue -> '180 cm'."""
    if isinstance(v, dict):
        val, unit = v.get("value"), (v.get("unitCode") or v.get("unitText") or "")
        if val is None:
            return None
        unit = {"CMT": "cm", "MMT": "mm", "MTR": "m", "INH": "in", "FOT": "ft"}.get(str(unit).upper(), str(unit))
        return f"{val} {unit}".strip()
    if isinstance(v, (int, float, str)):
        return str(v)
    return None


def _from_jsonld(blocks: list[str]) -> dict | None:
    for raw in blocks:
        try:
            doc = json.loads(raw.strip())
        except json.JSONDecodeError:
            # some sites leave trailing commas or comments; try a lenient trim
            try:
                doc = json.loads(re.sub(r",\s*([}\]])", r"\1", raw.strip()))
            except json.JSONDecodeError:
                continue
        for p in _walk_products(doc):
            out: dict[str, Any] = {"source": "json-ld"}
            out["title"] = _first_str(p.get("name"))
            out["image_url"] = _first_str(p.get("image"))
            out["price"] = _price_from_offers(p.get("offers"))
            desc = p.get("description")
            texts: list[str] = []
            if isinstance(desc, str):
                texts.append(_strip_tags(desc))
            w, d, h = _qv(p.get("width")), _qv(p.get("depth")), _qv(p.get("height"))
            if w and h and d:
                texts.insert(0, f"Width {w}, Depth {d}, Height {h}")
            props = p.get("additionalProperty")
            if isinstance(props, list):
                for ap in props:
                    if isinstance(ap, dict) and ap.get("name") and ap.get("value") is not None:
                        unit = ap.get("unitText") or ap.get("unitCode") or ""
                        texts.append(f"{ap['name']}: {ap['value']} {unit}".strip())
            out["texts"] = texts
            if out["title"]:
                return out
    return None


def _shopify_json_url(page_url: str) -> str | None:
    p = urllib.parse.urlparse(page_url)
    m = re.match(r"^(.*?/products/[^/?#]+)", p.path)
    if not m:
        return None
    return urllib.parse.urlunparse((p.scheme, p.netloc, m.group(1) + ".js", "", "", ""))


def _from_shopify(data: bytes) -> dict | None:
    try:
        j = json.loads(data.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None
    if not isinstance(j, dict) or "title" not in j:
        return None
    out: dict[str, Any] = {"source": "shopify", "title": j.get("title")}
    price = j.get("price")
    if isinstance(price, (int, float)):
        out["price"] = f"{price / 100:.2f}"
    imgs = j.get("images") or ([j["featured_image"]] if j.get("featured_image") else [])
    if imgs:
        img = imgs[0]
        out["image_url"] = ("https:" + img) if isinstance(img, str) and img.startswith("//") else img
    out["texts"] = [_strip_tags(j.get("description") or "")]
    return out


def _from_meta(page: _Page) -> dict:
    m = page.meta
    out: dict[str, Any] = {"source": "og" if any(k.startswith("og:") for k in m) else "page"}
    out["title"] = m.get("og:title") or m.get("twitter:title") or page.title.strip() or None
    out["image_url"] = m.get("og:image") or m.get("og:image:secure_url") or m.get("twitter:image")
    amt = m.get("product:price:amount") or m.get("og:price:amount")
    cur = m.get("product:price:currency") or m.get("og:price:currency") or ""
    out["price"] = f"{cur} {amt}".strip() if amt else None
    out["texts"] = [m.get("og:description") or m.get("description") or ""]
    return out


# ------------------------------------------------------------------ dimensions


def find_dimensions(texts: list[str], category: str | None = None) -> dict | None:
    """First fully parseable dimension line, preferring lines that announce themselves."""
    candidates: list[tuple[int, str]] = []
    for text in texts:
        for line in _lines(text):
            if not _DIM_LINE.search(line) and not re.search(r"\b(width|depth|height|length|dimensions?)\b", line, re.I):
                continue
            score = 0 if _PRIORITY.search(line) else 1
            candidates.append((score, line))
    candidates.sort(key=lambda t: t[0])
    for _, line in candidates:
        parsed = dims_mod.parse_dimensions(line, category=category)
        if parsed and not parsed.get("partial"):
            parsed["dimensions_text"] = line[:200]
            return parsed
    # labelled values scattered over several lines ("Width 180 cm" / "Depth 90 cm" / "Height 75 cm")
    for text in texts:
        joined = ", ".join(l for l in _lines(text) if re.search(r"\b(width|depth|height|length|w|d|h)\b", l, re.I) and re.search(r"\d", l))
        parsed = dims_mod.parse_dimensions(joined, category=category) if joined else None
        if parsed and not parsed.get("partial"):
            parsed["dimensions_text"] = joined[:200]
            return parsed
    return None


_CHALLENGE = re.compile(rb"awsWaf|aws-waf|captcha|cf-chl|cf_chl|challenge-platform|Just a moment|Access Denied|PerimeterX|_px[A-Za-z]|datadome", re.I)


def _looks_like_challenge(body: bytes) -> bool:
    """A tiny page whose job is to verify the browser, not to show a product."""
    return len(body) < 20_000 and bool(_CHALLENGE.search(body))


# ------------------------------------------------------------------ entry point


def fetch_product(url: str, category: str | None = None, _get=_get) -> dict:
    """Read one product page. Never raises for site problems: returns ok False with a code."""
    try:
        url = _check_url(url)
    except FetchError as e:
        return {"ok": False, "url": url, "error": {"code": e.code, "message": e.message}}

    notes: list[str] = []
    found: dict | None = None
    final_url = url
    # Shopify-style URL: the store's small public product JSON first (title, price, images, description)
    shop_url = _shopify_json_url(url)
    if shop_url:
        try:
            sdata, _, _ = _get(shop_url, accept="application/json")
            found = _from_shopify(sdata)
        except FetchError as e:
            if e.code == "blocked":
                return {"ok": False, "url": url, "error": {"code": e.code, "message": e.message}}
            notes.append(f"No Shopify product JSON ({e.code}); reading the page itself.")
    page = _Page()
    if found is None or not any(t.strip() for t in found.get("texts", [])):
        try:
            body, ctype, final_url = _get(url)
        except FetchError as e:
            return {"ok": False, "url": url, "error": {"code": e.code, "message": e.message}}
        if _looks_like_challenge(body):
            return {"ok": False, "url": final_url, "error": {"code": "blocked", "message": "The site answered with a bot-check page instead of the product. Ask the user for the sizes printed on the page."}}
        try:
            page.feed(body.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 - a broken page is not an exception for the user
            pass
        ld = _from_jsonld(page.jsonld)
        if ld:
            found = {**ld, **{k: v for k, v in (found or {}).items() if v and k != "texts"}, "texts": ld.get("texts", []) + (found or {}).get("texts", [])}
    meta = _from_meta(page)
    if found is None:
        found = meta
    else:
        for k in ("title", "image_url", "price"):
            found[k] = found.get(k) or meta.get(k)
    texts = list(found.get("texts") or []) + [meta["texts"][0], "\n".join(page.text)]
    parsed = find_dimensions([t for t in texts if t], category=category)

    out: dict[str, Any] = {
        "ok": True,
        "url": final_url,
        "title": (found.get("title") or "").strip()[:120] or None,
        "price": found.get("price"),
        "image_url": found.get("image_url"),
        "source": found.get("source"),
        "notes": notes,
    }
    if parsed:
        out["dimensions_text"] = parsed.pop("dimensions_text")
        out["dimensions_m"] = [parsed["width_m"], parsed["height_m"], parsed["depth_m"]]
        out["dims"] = parsed
    else:
        out["dims"] = None
        out["dimensions_m"] = None
        out["notes"].append("No readable dimensions on the page. Ask the user for the printed size.")
    return out
