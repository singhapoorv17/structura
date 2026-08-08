"""Pull publication dates for corpus sources that were ingested without one.

Reads the page's own metadata — Open Graph article:published_time, JSON-LD
datePublished, or a <time datetime> element — and prints a url -> date map.
Nothing is guessed: a page that does not declare a date stays undated.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request

from comps.corpus import iter_records

UA = "Structura corpus check (singh.apoorv17@gmail.com)"

PATTERNS = [
    r'property=["\']article:published_time["\']\s+content=["\']([\d]{4}-[\d]{2}-[\d]{2})',
    r'content=["\']([\d]{4}-[\d]{2}-[\d]{2})[^"\']*["\']\s+property=["\']article:published_time["\']',
    r'"datePublished"\s*:\s*"([\d]{4}-[\d]{2}-[\d]{2})',
    r'name=["\']publish-date["\']\s+content=["\']([\d]{4}-[\d]{2}-[\d]{2})',
    r'<time[^>]+datetime=["\']([\d]{4}-[\d]{2}-[\d]{2})',
]


def undated_urls():
    seen = {}
    for record in iter_records():
        for _, cell in record.provenanced_cells():
            if cell.provenance.value == "stated" and cell.source_date_unknown:
                seen.setdefault(cell.source_url, record.key)
    return seen


def date_for(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read(400_000).decode("utf-8", "ignore")
    except Exception:
        return None
    for pattern in PATTERNS:
        m = re.search(pattern, html)
        if m:
            return m.group(1)
    return None


if __name__ == "__main__":
    found = {}
    for url, key in undated_urls().items():
        d = date_for(url)
        print(f"{d or '     none':<12} {key:<30} {url}")
        if d:
            found[url] = d
    print()
    print(json.dumps(found, indent=2))
    print(f"\n{len(found)} of {len(undated_urls())} dates captured", file=sys.stderr)
