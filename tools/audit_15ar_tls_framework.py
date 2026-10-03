#!/usr/bin/env python3
"""15AR: prove whether the installed Arduino-ESP32 framework can be reconfigured
for mbedTLS dynamic-buffer/free options from the application build.

Read-only audit: no framework or project files are modified.
"""
from pathlib import Path
import re, sys

ROOT = Path.home() / ".platformio" / "packages"
FRAMEWORK = ROOT / "framework-arduinoespressif32"
OPTIONS = [
    "CONFIG_MBEDTLS_DYNAMIC_BUFFER",
    "CONFIG_MBEDTLS_DYNAMIC_FREE_PEER_CERT",
    "CONFIG_MBEDTLS_DYNAMIC_FREE_CONFIG_DATA",
    "CONFIG_MBEDTLS_DYNAMIC_FREE_CA_CERT",
]

if not FRAMEWORK.exists():
    print(f"FAIL framework not found: {FRAMEWORK}")
    sys.exit(2)

print("15AR TLS FRAMEWORK CAPABILITY AUDIT")
print("framework:", FRAMEWORK)

# Locate precompiled TLS archives.
archives = []
for name in ("libmbedtls.a", "libmbedx509.a", "libmbedcrypto.a", "libmbedtls_2.a"):
    archives.extend(FRAMEWORK.rglob(name))
for p in sorted(set(archives)):
    print("ARCHIVE", p.relative_to(FRAMEWORK))
print("archive_count=", len(set(archives)))

# Search textual framework configuration/source for the exact Kconfig options.
hits = {o: [] for o in OPTIONS}
text_suffixes = {".h", ".hpp", ".c", ".cc", ".cpp", ".txt", ".cmake", ".mk", ".py"}
scanned = 0
for p in FRAMEWORK.rglob("*"):
    if not p.is_file() or (p.suffix.lower() not in text_suffixes and p.name not in {"Kconfig", "Kconfig.projbuild", "sdkconfig", "sdkconfig.defaults"}):
        continue
    try:
        s = p.read_text(errors="ignore")
    except OSError:
        continue
    scanned += 1
    for o in OPTIONS:
        if o in s:
            hits[o].append(str(p.relative_to(FRAMEWORK)))

print("text_files_scanned=", scanned)
for o in OPTIONS:
    print(o, "hits=", len(hits[o]))
    for h in hits[o][:10]:
        print("  ", h)

# sdkconfig presence matters: Arduino's packaged precompiled IDF libs cannot be
# rebuilt merely by adding -D CONFIG_* to application build_flags.
sdkconfigs = [p for p in FRAMEWORK.rglob("sdkconfig*") if p.is_file()]
print("sdkconfig_like_files=", len(sdkconfigs))
for p in sdkconfigs[:30]:
    print("SDKCONFIG", p.relative_to(FRAMEWORK))

if archives and not any(hits.values()):
    verdict = "PRECOMPILED_FRAMEWORK_NO_TEXTUAL_DYNAMIC_MBEDTLS_SUPPORT"
elif archives:
    verdict = "PRECOMPILED_FRAMEWORK_HAS_TEXTUAL_MBEDTLS_OPTION_EVIDENCE_REVIEW_REQUIRED"
else:
    verdict = "NO_PRECOMPILED_TLS_ARCHIVES_FOUND_REVIEW_REQUIRED"
print("15AR_VERDICT=", verdict)

# This audit is evidence collection, not a forced failure: CI should preserve
# the baseline build and expose the verdict in logs.
sys.exit(0)
