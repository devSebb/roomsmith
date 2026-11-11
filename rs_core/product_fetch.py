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

import hashlib
import html
import ipaddress
import json
import re
import socket
import threading
import time
import unicodedata
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser
from typing import Any

from rs_core import dims as dims_mod

USER_AGENT = "Roomsmith/0.1 (+https://github.com/devSebb/roomsmith; reads only pages the user pastes)"
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT_S = 12

_DIM_LINE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:cm|mm|m|in|inch|inches|\"|”|′|'|ft)?\s*[WDHL]?\s*(?:x|×|\*|by)\s*[WDHL]?\s*:?\s*\d", re.I)
_PRIORITY = re.compile(r"overall|dimension|measure|size", re.I)
# the box it ships in, not the thing: "Package: 29 x 25 x 15 | 44 lbs", "(1 of 2) - 83” x 13” x 5”"
_DEMOTE = re.compile(r"packag|box|carton|shipping|ships|parcel|\(\d+ of \d+\)|\blbs?\b|\bkg\b|weight|\breviews?\b|\bI (?:bought|ordered|have|love|returned|purchased)\b|\bstars?\b", re.I)
_SIZE_WORDS = {"bed_single": "twin|single", "bed_double": "full|double", "bed_queen": "queen", "bed_king": "king"}
BED_SIZE_WORDS = _SIZE_WORDS
MAX_SCRIPT_BYTES = 3 * 1024 * 1024


# Outbound requests are bounded per process: a furnishing session reads many pages,
# and a shop must never see a burst from one user's plugin.
MAX_REQUESTS_PER_WINDOW = 80
WINDOW_S = 600.0
MAX_PER_HOST_PER_MINUTE = 12  # a product read is one or two requests
CACHE_OK_S = 24 * 3600.0
CACHE_BLOCKED_S = 30 * 60.0
CACHE_MAX_FILES = 300


class FetchError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


# ------------------------------------------------------------------ HTTP


class RateLimit:
    """Sliding-window cap on outbound requests (all hosts, and per host)."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._all: list[float] = []
        self._hosts: dict[str, list[float]] = {}

    def take(self, host: str) -> None:
        now = self._clock()
        with self._lock:
            self._all = [t for t in self._all if now - t < WINDOW_S]
            mine = [t for t in self._hosts.get(host, []) if now - t < 60.0]
            if len(self._all) >= MAX_REQUESTS_PER_WINDOW or len(mine) >= MAX_PER_HOST_PER_MINUTE:
                raise FetchError("rate_limited", "Roomsmith has read many pages in the last few minutes. Wait a little, or give the size and price printed on the page.")
            self._all.append(now)
            mine.append(now)
            self._hosts[host] = mine
            if len(self._hosts) > 200:
                self._hosts = {h: ts for h, ts in self._hosts.items() if ts and now - ts[-1] < 60.0}


RATE_LIMIT = RateLimit()

_TAG = re.compile(r"<[^>]{0,200}>")


def clean_text(value: Any, limit: int) -> str | None:
    """A short string from a web page, safe to hand to the model: tags, control and
    invisible characters removed, whitespace collapsed, length capped."""
    if value is None:
        return None
    text = _TAG.sub(" ", html.unescape(str(value)))
    text = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in text)
    text = " ".join(text.split())
    return text[:limit].rstrip() or None


def _public_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    # is_global excludes loopback, private, link-local, shared (100.64/10), reserved, multicast, unspecified
    return bool(ip.is_global) and not ip.is_multicast


def check_url(url: str) -> str:
    """Syntactic check: a full http(s) URL whose host is not obviously private. No DNS here."""
    u = (url or "").strip()
    try:
        p = urllib.parse.urlparse(u)
        host = (p.hostname or "").rstrip(".").lower()
    except ValueError:
        raise FetchError("bad_url", "Give a full http(s) product URL") from None
    if p.scheme not in ("http", "https") or not host:
        raise FetchError("bad_url", "Give a full http(s) product URL")
    literal: str | None = None
    try:
        literal = str(ipaddress.ip_address(host.strip("[]")))
    except ValueError:
        try:  # "2130706433", "0x7f.1", "127.1": forms the resolver reads as an IPv4 address
            literal = str(ipaddress.ip_address(socket.inet_aton(host)))
        except OSError:
            pass
    if literal is not None and not _public_ip(literal):
        raise FetchError("bad_url", "Only public product pages can be read")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
        raise FetchError("bad_url", "Only public product pages can be read")
    return u


def _assert_public(url: str) -> None:
    """Resolve the host and refuse unless every address it maps to is public.
    Called for the first request and again for every redirect hop."""
    check_url(url)
    p = urllib.parse.urlparse(url)
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise FetchError("unreachable", f"Could not resolve the site: {e}") from e
    if not infos or not all(_public_ip(info[4][0].split("%")[0]) for info in infos):
        raise FetchError("bad_url", "Only public product pages can be read")


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, PLR0913
        _assert_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_PublicRedirects)


def _gunzip_capped(data: bytes) -> bytes:
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(data, MAX_BYTES + 1)
    if d.unconsumed_tail:
        raise FetchError("too_large", "The page is over 8 MB")
    return out


def http_get(url: str, timeout: float = TIMEOUT_S, accept: str = "text/html,application/json;q=0.9,*/*;q=0.5") -> tuple[bytes, str, str]:
    """GET a public http(s) URL. Returns (body, content_type, final_url). Raises FetchError.

    The host (and the host of every redirect) must resolve to public addresses only;
    the body is capped at MAX_BYTES before and after decompression."""
    _assert_public(url)
    RATE_LIMIT.take((urllib.parse.urlparse(url).hostname or "").lower())
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "en", "Accept-Encoding": "gzip"})
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            data = resp.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise FetchError("too_large", "The page is over 8 MB")
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                try:
                    data = _gunzip_capped(data)
                except (OSError, EOFError, zlib.error):
                    pass  # mislabelled or truncated: keep the bytes as sent
            if len(data) > MAX_BYTES:
                raise FetchError("too_large", "The page is over 8 MB")
            return data, resp.headers.get("Content-Type", ""), resp.geturl()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429, 503):
            raise FetchError("blocked", f"The site refused the request (HTTP {e.code}). Ask the user for the sizes printed on the page.") from e
        raise FetchError("http_error", f"HTTP {e.code} fetching the page") from e
    except urllib.error.URLError as e:
        raise FetchError("unreachable", f"Could not reach the site: {e.reason}") from e
    except (TimeoutError, OSError, ValueError) as e:
        raise FetchError("unreachable", f"Could not read the site: {type(e).__name__}") from e


# ------------------------------------------------------------------ HTML


class _Page(HTMLParser):
    """Collect JSON-LD blocks, meta tags, title and visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.jsonld: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self.text: list[str] = []
        self.scripts: list[str] = []  # inline JS/JSON: modern stores keep the spec sheet here
        self._script_bytes = 0
        self._in: str | None = None
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script":
            kind = a.get("type", "").lower().strip()
            self._in = "jsonld" if kind == "application/ld+json" else ("script" if a.get("src") is None else "skip")
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
        elif self._in == "script":
            if self._script_bytes < MAX_SCRIPT_BYTES:
                self.scripts.append(data)
                self._script_bytes += len(data)
        elif self._in == "title":
            self.title += data
        elif self._in is None:
            self.text.append(data)


def _strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>|</li>|</div>|</tr>|</h\d>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(s)


_ESCAPES = (("\\u003c", "<"), ("\\u003e", ">"), ("\\u0026", "&"), ("\\u201d", "”"), ("\\u201c", "“"), ("\\/", "/"), ('\\"', '"'), ("\\n", "\n"), ("\\r", ""), ("\\t", " "))


def _script_lines(scripts: list[str]) -> str:
    """Dimension-looking lines buried in inline scripts (Shopify section JSON, Next.js
    payloads). Escapes are undone twice because framework payloads are often JSON
    inside JSON; then tags are stripped and string literals become lines."""
    out: list[str] = []
    for body in scripts:
        if not re.search(r"\d\s*(?:\\?\"|”|\\u201d|&quot;|cm|mm|in(?:ch(?:es)?)?\b)", body, re.I):
            continue
        t = body
        for _ in range(2):
            for a, b in _ESCAPES:
                t = t.replace(a, b)
        t = _strip_tags(t)
        for chunk in re.split(r'["\n]', t):
            line = re.sub(r"\s+", " ", chunk).strip()
            if 6 <= len(line) <= 200 and (_DIM_LINE.search(line) or _PRIORITY.search(line)) and re.search(r"\d", line):
                out.append(line)
    return "\n".join(out)


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
    offers = _first_dict(offers)
    if offers is None:
        return None
    spec = _first_dict(offers.get("priceSpecification")) or {}  # schema.org allows one, or a list of them
    price = offers.get("price") or offers.get("lowPrice") or spec.get("price")
    cur = offers.get("priceCurrency") or spec.get("priceCurrency") or ""
    if isinstance(price, (dict, list)) or isinstance(cur, (dict, list)):
        return None
    if price is None:
        return None
    return f"{cur} {price}".strip()


def _first_dict(v: Any) -> dict | None:
    """schema.org values come as one object or a list of them."""
    if isinstance(v, list):
        v = next((x for x in v if isinstance(x, dict)), None)
    return v if isinstance(v, dict) else None


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
    candidates: list[tuple[int, int, str]] = []
    size_word = re.compile(r"\b(?:%s)\b" % _SIZE_WORDS[category], re.I) if category in _SIZE_WORDS else None
    for ti, text in enumerate(texts):
        for line in _lines(text):
            if not _DIM_LINE.search(line) and not re.search(r"\b(width|depth|height|length|dimensions?)\b", line, re.I):
                continue
            score = 0 if _PRIORITY.search(line) else 1
            if _DEMOTE.search(line):
                score += 2
            if size_word and size_word.search(line):  # "Queen: 68” W x 93” D" when the user asked about a queen bed
                score -= 2
            candidates.append((score, ti, line))
    candidates.sort(key=lambda t: (t[0], t[1]))
    partial_fallback: dict | None = None
    for _, _, line in candidates:
        parsed = dims_mod.parse_dimensions(line, category=category)
        if parsed and not dims_mod.plausible(parsed, category):
            continue  # a number triple that cannot be this kind of thing: a review, a part, a box
        if parsed and not parsed.get("partial"):
            parsed["dimensions_text"] = line[:200]
            return parsed
        if parsed and partial_fallback is None and parsed.get("missing") == ["height_m"] and category:
            partial_fallback = parsed
            partial_fallback["dimensions_text"] = line[:200]
    # labelled values scattered over several lines ("Width 180 cm" / "Depth 90 cm" / "Height 75 cm")
    for text in texts:
        joined = ", ".join(l for l in _lines(text) if re.search(r"\b(width|depth|height|length|w|d|h)\b", l, re.I) and re.search(r"\d", l))
        parsed = dims_mod.parse_dimensions(joined, category=category) if joined else None
        if parsed and not parsed.get("partial") and dims_mod.plausible(parsed, category):
            parsed["dimensions_text"] = joined[:200]
            return parsed
    if partial_fallback is not None:
        # footprint printed, height not (desks sold by top size): take the category's usual height
        from rs_core.catalog import spec_for

        spec = spec_for(category)
        partial_fallback["height_m"] = round(float(spec.default[1]), 4)
        partial_fallback["height_assumed"] = True
        partial_fallback.pop("partial", None)
        return partial_fallback
    return None


_CHALLENGE = re.compile(rb"awsWaf|aws-waf|captcha|cf-chl|cf_chl|challenge-platform|Just a moment|Access Denied|PerimeterX|_px[A-Za-z]|datadome", re.I)


def _looks_like_challenge(body: bytes) -> bool:
    """A tiny page whose job is to verify the browser, not to show a product."""
    return len(body) < 20_000 and bool(_CHALLENGE.search(body))


# ------------------------------------------------------------------ entry point


def fetch_product(url: str, category: str | None = None, _get=http_get) -> dict:
    """Read one product page. Never raises: a site problem or a page shaped in a way
    this reader did not expect comes back as ok False with a code."""
    try:
        url = check_url(url)
    except FetchError as e:
        return {"ok": False, "url": url, "error": {"code": e.code, "message": e.message}}
    try:
        return _read_page(url, category, _get)
    except Exception as e:  # noqa: BLE001 - product pages are arbitrary; one odd page must not fail the call
        return {"ok": False, "url": url, "error": {"code": "unreadable", "message": f"The page could not be read ({type(e).__name__}). Ask the user for the size and price printed on it."}}


def _read_page(url: str, category: str | None, _get) -> dict:

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
    if found is None or not find_dimensions([t for t in found.get("texts", []) if t], category=category):
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
    # the product's own name first: some shops print the size there ("Nightstand 18 7/8x15 3/8x24 3/8")
    texts = [str(found.get("title") or "")] + list(found.get("texts") or []) + [meta["texts"][0], "\n".join(page.text), _script_lines(page.scripts)]
    parsed = find_dimensions([t for t in texts if t], category=category)

    out: dict[str, Any] = {
        "ok": True,
        "url": final_url,
        "title": clean_text(found.get("title"), 120),
        "price": clean_text(found.get("price"), 40),
        "image_url": found.get("image_url"),
        "source": found.get("source"),
        "notes": notes,
    }
    if parsed:
        out["dimensions_text"] = clean_text(parsed.pop("dimensions_text"), 160)
        out["dimensions_m"] = [parsed["width_m"], parsed["height_m"], parsed["depth_m"]]
        out["dims"] = parsed
        if parsed.get("height_assumed"):
            out["notes"].append(f"The page prints only the footprint; height {parsed['height_m']:.2f} m is the usual {category} height.")
    else:
        out["dims"] = None
        out["dimensions_m"] = None
        out["notes"].append("No readable dimensions on the page. Ask the user for the printed size.")
    return out


# ------------------------------------------------------------------ cache


def read_cached(url: str, category: str | None, cache_dir: Path, _get=http_get, now=time.time) -> dict:
    """``fetch_product`` with a small on-disk cache of results (never page bodies).

    A page that read is reused for a day; a site that refused is not asked again
    for half an hour; other failures are not cached."""
    key = hashlib.sha256(f"{(url or '').strip()}|{category or ''}".encode()).hexdigest()[:24]
    folder = Path(cache_dir) / "pages"
    path = folder / f"{key}.json"
    try:
        saved = json.loads(path.read_text())
        age = now() - float(saved["fetched_at"])
        blocked = not saved.get("ok") and (saved.get("error") or {}).get("code") == "blocked"
        if 0 <= age < (CACHE_BLOCKED_S if blocked else CACHE_OK_S) and (saved.get("ok") or blocked):
            return {**saved, "cached": True}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    out = fetch_product(url, category=category) if _get is http_get else fetch_product(url, category=category, _get=_get)
    out["fetched_at"] = now()
    out["cached"] = False
    if out.get("ok") or (out.get("error") or {}).get("code") == "blocked":
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out))
            files = sorted(folder.glob("*.json"), key=lambda f: f.stat().st_mtime)
            for old in files[: max(0, len(files) - CACHE_MAX_FILES)]:
                old.unlink(missing_ok=True)
        except OSError:
            pass  # a cache that cannot be written is not an error
    return out
