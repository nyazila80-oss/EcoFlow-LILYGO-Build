#!/usr/bin/env python3
"""Fail once with the complete list of host tests pinned to historical firmware labels.

Regression tests should protect behaviour/invariants. Exact release provenance belongs in
release/build gates, not in old host simulations. This audit intentionally reports every
offender in one run so CI does not reveal them one-by-one.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
# Historical diagnostic/release labels that caused sequential false negatives in 15I.
# Match only literal 9.36.7.11 labels; family-aware checks such as startswith(...9.36.7.)
# remain valid and are not reported.
LEGACY = re.compile(r"(?:2\.4\.5\.)?9\.36\.7\.11-[A-Za-z0-9_.-]+")

candidates = []
for pat in ("host_sim*.py", "*regression*.py", "*audit*.py"):
    candidates.extend(ROOT.glob(pat))
    candidates.extend((ROOT / "tools").glob(pat))

# This audit contains the regex description itself; never self-scan.
self_path = Path(__file__).resolve()
offenders = []
for path in sorted(set(p.resolve() for p in candidates if p.is_file())):
    if path == self_path:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), 1):
        matches = sorted(set(LEGACY.findall(line)))
        if matches:
            offenders.append((path.relative_to(ROOT), lineno, matches))

if offenders:
    print("LEGACY EXACT-VERSION COUPLINGS FOUND:")
    for path, lineno, matches in offenders:
        print(f"  {path}:{lineno}: {', '.join(matches)}")
    print(f"TOTAL OFFENDING LINES: {len(offenders)}")
    raise SystemExit(1)

print("PASS: no host regression/audit is pinned to a literal 9.36.7.11 diagnostic label")
