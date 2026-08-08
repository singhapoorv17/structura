"""Check that every source URL in the corpus resolves.

A citation to a URL that does not exist is worse than no citation. This runs
during ingest, not in the test suite, because it needs the network — but a
record whose URL fails here does not ship.

Run:  python scripts/verify_urls.py
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from collections import OrderedDict

from comps.corpus import iter_records

#: SEC requires a declared User-Agent carrying a contact address, and refuses
#: anonymous agents outright. The same string is polite everywhere else.
UA = "Structura corpus check (singh.apoorv17@gmail.com)"
TIMEOUT = 20


def urls() -> "OrderedDict[str, list[str]]":
    """Every distinct source URL, mapped to the cells that cite it."""
    found: OrderedDict[str, list[str]] = OrderedDict()
    for record in iter_records():
        for name, cell in record.provenanced_cells():
            if cell.source_url:
                found.setdefault(cell.source_url, []).append(f"{record.key}.{name}")
    return found


def check(url: str) -> tuple[bool, str]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return 200 <= response.status < 400, str(response.status)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405):
            # Some hosts refuse HEAD or refuse unknown agents but serve the
            # page. Fall back to a ranged GET before calling it dead.
            return _ranged_get(url)
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - the reason is what we report
        return False, type(exc).__name__


def _ranged_get(url: str) -> tuple[bool, str]:
    request = urllib.request.Request(
        url, headers={"User-Agent": UA, "Range": "bytes=0-2047"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return 200 <= response.status < 400, f"{response.status} (GET)"
    except urllib.error.HTTPError as exc:
        # A 403 from a bot wall is not evidence the page is missing, but it is
        # not evidence it exists either. Report it as unverified.
        return False, f"HTTP {exc.code} (GET)"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__} (GET)"


def main() -> int:
    failures = []
    table = urls()
    for url, cells in table.items():
        ok, detail = check(url)
        print(f"{'ok  ' if ok else 'FAIL'} {detail:<18} {url}")
        if not ok:
            failures.append((url, detail, cells))

    print()
    print(f"{len(table) - len(failures)}/{len(table)} source URLs resolved")
    if failures:
        print()
        for url, detail, cells in failures:
            print(f"  {detail}  {url}")
            print(f"      cited by: {', '.join(cells[:4])}"
                  + (f" (+{len(cells) - 4} more)" if len(cells) > 4 else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
