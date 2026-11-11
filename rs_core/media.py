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


# Colour words shops put in a product's name, longest first so "dark red" wins over "red".
_COLOUR_WORDS = {
    "dark red": "#7a1f26", "burgundy": "#6e1f2b", "terracotta": "#b5694a", "rust": "#a4532f", "red": "#b23a32", "pink": "#d9a3a8",
    "orange": "#cf7a3a", "mustard": "#c79a2f", "yellow": "#d8b84a", "olive": "#6f7244", "sage": "#9aa88a", "dark green": "#2f4a3a", "green": "#4f7a4a",
    "navy": "#27324d", "dark blue": "#2b3d5c", "light blue": "#a9c1d6", "blue": "#3d5f8f", "teal": "#2f6f73", "purple": "#6a4c7a",
    "anthracite": "#3a3c40", "charcoal": "#3a3c40", "dark gray": "#4a4c50", "dark grey": "#4a4c50", "light gray": "#bfc1c4", "light grey": "#bfc1c4",
    "gray": "#8c8f94", "grey": "#8c8f94", "black": "#26262a", "off-white": "#ece8df", "white": "#f1efea", "ivory": "#ece5d4", "cream": "#e6dcc6",
    "beige": "#d6c7ac", "linen": "#d9cdb8", "taupe": "#a3978a", "sand": "#d3c2a3", "natural": "#c9ad85",
    "dark walnut": "#4f3524", "walnut": "#6b4a32", "espresso": "#3b2a20", "mahogany": "#5a2e22", "dark brown": "#4a3324", "brown": "#6b4a32",
    "light oak": "#d3b88c", "oak": "#c2a06b", "pine": "#d9bd8a", "birch": "#dcc9a3", "ash": "#d6c6a5", "bamboo": "#c9a86a", "rattan": "#c2a06b",
    "light wood": "#d3b88c", "teak": "#9a6b3f", "acacia": "#8a5a36", "brass": "#b08d4c", "gold": "#c2a14d", "chrome": "#b9bcc0", "silver": "#b9bcc0",
}


def colour_from_words(text: str | None) -> str | None:
    """The colour a product's own name states ("…, dark red", "Nightstand - pine"), as #rrggbb."""
    if not text:
        return None
    low = " " + " ".join(str(text).lower().replace("/", " ").replace(",", " ").replace("-", " ").split()) + " "
    best: tuple[int, int, str] | None = None
    for words, hexcode in _COLOUR_WORDS.items():
        at = low.rfind(" " + words.replace("-", " ") + " ")  # the colour is usually the last thing in the name
        end = at + len(words)  # compare where the phrase ends, so "dark red" beats the "red" inside it
        if at >= 0 and (best is None or (end, len(words)) > (best[0], best[1])):
            best = (end, len(words), hexcode)
    return best[2] if best else None


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
    except Exception:  # noqa: BLE001 - a picture is a nicety: no thumbnail, never a failed add
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
        im.thumbnail((96, 96))  # large enough that a thin piece (a floor lamp) still has pixels to read
        px = [p for p in list(im.getdata()) if max(p) < 235 or (max(p) - min(p)) > 25]
        if len(px) < 12:
            return None
        chans = [sorted(c[i] for c in px) for i in range(3)]
        med = [chans[i][len(px) // 2] for i in range(3)]
        return "#%02x%02x%02x" % tuple(med)
    except Exception:  # noqa: BLE001 - a colour is a nicety
        return None
