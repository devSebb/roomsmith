#!/usr/bin/env python3
"""Which shops can Roomsmith read? One row per product URL.

    .venv/bin/python scripts/survey-stores.py urls.txt

urls.txt: one product URL per line, optionally followed by a category
(`https://shop.example/products/desk desk`). Lines starting with # are skipped.
One request sequence per URL, a pause between requests to the same host, and a
host that refuses once is not asked again.
"""

from __future__ import annotations

import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rs_core import product_fetch as pf  # noqa: E402

PAUSE_S = 1.5


def main(path: str) -> int:
    refused: set[str] = set()
    last: dict[str, float] = {}
    print("| host | result | title | price | size (w x h x d m) | source | ms |")
    print("|---|---|---|---|---|---|---|")
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, category = line.partition(" ")
        host = urllib.parse.urlparse(url).hostname or "?"
        if host in refused:
            print(f"| {host} | skipped (refused earlier) | | | | | |")
            continue
        wait = PAUSE_S - (time.time() - last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        t0 = time.time()
        r = pf.fetch_product(url, category=category.strip() or None)
        last[host] = time.time()
        ms = int((last[host] - t0) * 1000)
        if not r.get("ok"):
            code = (r.get("error") or {}).get("code", "error")
            if code in ("blocked", "rate_limited"):
                refused.add(host)
            print(f"| {host} | {code} | | | | | {ms} |")
            continue
        d = r.get("dimensions_m")
        size = " x ".join(f"{v:.2f}" for v in d) if d else "—"
        print(f"| {host} | ok | {(r.get('title') or '')[:48]} | {r.get('price') or '—'} | {size} | {r.get('source') or ''} | {ms} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else (print(__doc__) or 2))
