"""Images the plugin handles: room photos the user picks and product thumbnails.

Standard library, plus Pillow through guarded imports (thumbnails and the
dominant colour are niceties; everything works without it).
"""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

from rs_core import product_fetch

MAX_PHOTO_BYTES = 15 * 1024 * 1024
IMAGE_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def sniff_image(data: bytes) -> str | None:
    """File type by content, never by name: "jpg", "png", "webp" or None."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def product_thumbnail(image_url: str, cache_dir: Path, max_px: int = 384, max_bytes: int = 120_000) -> str | None:
    """Fetch a product image once and return a small data URL for the editor's stand-in
    (cached under ``cache_dir``). None when it cannot be fetched or shrunk enough.
    The request goes through ``product_fetch.http_get``: public hosts only, size-capped."""
    if not image_url or not str(image_url).startswith(("http://", "https://")):
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / (hashlib.sha256(image_url.encode()).hexdigest()[:16] + ".txt")
    if cached.exists():
        return cached.read_text() or None
    try:
        data, _ctype, _final = product_fetch.http_get(image_url, timeout=10, accept="image/*")
    except product_fetch.FetchError:
        return None
    kind = sniff_image(data)
    if kind is None:
        return None
    out_bytes, mime = data, IMAGE_MIME[kind]
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data)).convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))  # product shots often have a transparent background
        bg.alpha_composite(im)
        im = bg.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        out_bytes, mime = buf.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 - no Pillow or odd image: keep the original if it is small
        pass
    if len(out_bytes) > max_bytes:
        cached.write_text("")
        return None
    url = f"data:{mime};base64," + base64.b64encode(out_bytes).decode("ascii")
    cached.write_text(url)
    return url


def product_color(data_url: str) -> str | None:
    """Dominant colour of a product photo as #rrggbb: the median of its non-background
    pixels (white/near-white studio backgrounds and transparent areas ignored).
    None without Pillow or when the photo is all background."""
    try:
        from PIL import Image

        raw = base64.b64decode(data_url.split(",", 1)[1])
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((48, 48))
        px = [p for p in list(im.getdata()) if max(p) < 235 or (max(p) - min(p)) > 25]
        if len(px) < 20:
            return None
        chans = [sorted(c[i] for c in px) for i in range(3)]
        med = [chans[i][len(px) // 2] for i in range(3)]
        return "#%02x%02x%02x" % tuple(med)
    except Exception:  # noqa: BLE001 - a colour is a nicety
        return None
