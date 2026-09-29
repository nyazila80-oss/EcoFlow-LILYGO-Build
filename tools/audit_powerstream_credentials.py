#!/usr/bin/env python3
"""15D static audit: prove the PowerStream credential provenance chain.

This audit intentionally never reads or prints real credentials. It verifies the
source-level path WebUI POST -> powerStreamApiSave -> NVS -> RAM -> HMAC/header,
and fails closed if a plaintext secret exposure is introduced.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
WEB = (ROOT / "src" / "web.cpp").read_text(encoding="utf-8")
API = (ROOT / "src" / "powerstream_api.cpp").read_text(encoding="utf-8")
HDR = (ROOT / "include" / "powerstream_api.h").read_text(encoding="utf-8")

checks = []
def check(name, cond, detail):
    checks.append((name, bool(cond), detail))

# Browser/API ingress.
check("web reads access POST field", 'hasParam("access",true)' in WEB and 'getParam("access",true)' in WEB,
      "POST access field is read")
check("web reads secret POST field", 'hasParam("secret",true)' in WEB and 'getParam("secret",true)' in WEB,
      "POST secret field is read")
check("web forwards both to save", 'powerStreamApiSave(sn,ak,sk)' in WEB,
      "sn/access/secret are forwarded together")

# RAM/NVS persistence and reload.
check("NVS namespace psapi", 'begin("psapi"' in API, "PowerStream credentials use psapi namespace")
for key, var in (("sn", "gSn"), ("access", "gAccess"), ("secret", "gSecret")):
    check(f"NVS writes {key}", f'putString("{key}", {var})' in API, f"{key} persisted from RAM")
    check(f"NVS reloads {key}", f'{var} = p.getString("{key}"' in API, f"{key} reloaded into RAM")
check("blank access preserves stored value", 'if (a.length()) gAccess=a;' in API,
      "empty AccessKey field does not erase existing key")
check("blank secret preserves stored value", 'if (k.length()) gSecret=k;' in API,
      "empty SecretKey field does not erase existing key")

# Actual request use.
check("request header uses gAccess", 'addHeader("accessKey",gAccess)' in API,
      "RAM AccessKey becomes EcoFlow accessKey header")
check("HMAC uses gSecret", 'hmac256(signBase,gSecret)' in API,
      "RAM SecretKey is the HMAC-SHA256 key")
check("signature base includes gAccess", '"accessKey="+gAccess' in API,
      "same RAM AccessKey is part of signature base")

# Security regression guards: do not expose plaintext secret through public API.
check("no public secret getter", "powerStreamApiSecret" not in HDR,
      "header exposes no SecretKey getter")
check("config endpoint remains masked", 'powerStreamApiAccessMasked()' in WEB,
      "normal config GET uses masked AccessKey")
check("no obvious secret JSON field", not re.search(r'\\?"secret(?:_key)?\\?"\s*:', WEB, re.I),
      "web source contains no plaintext secret JSON member")
check("TLS insecure fallback absent", "setInsecure(" not in API,
      "TLS peer verification cannot silently fall back to insecure mode")

failed = [x for x in checks if not x[1]]
for name, ok, detail in checks:
    print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")
print(f"SUMMARY | pass={len(checks)-len(failed)} fail={len(failed)} total={len(checks)}")
if failed:
    sys.exit(1)
