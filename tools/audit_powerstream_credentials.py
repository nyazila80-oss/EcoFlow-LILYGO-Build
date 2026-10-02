#!/usr/bin/env python3
"""Static audit: prove the PowerStream credential provenance chain and AC1 snapshot invariant.

This audit intentionally never reads or prints real credentials. It verifies the
source-level path WebUI POST -> powerStreamApiSave -> NVS -> RAM -> one locked
request snapshot -> signature/header, and fails closed if plaintext secret
exposure, insecure TLS, or a post-snapshot direct credential read is introduced.
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

def strip_cpp_comments(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)

API_CODE = strip_cpp_comments(API)

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

# AC1 request invariant: AccessKey and SecretKey must be copied together while
# holding the API lock. After that point this request must use only the immutable
# local copies. In particular, do NOT require a later gAccess/gSecret comparison:
# that would re-open a mixed-generation race if credentials were changed mid-request.
snapshot_re = re.compile(
    r'String\s+requestAccess\s*;\s*String\s+requestSecret\s*;\s*'
    r'\{\s*ApiLock\s+credentialSnapshot\s*\([^;]+;\s*'
    r'if\s*\(!credentialSnapshot\.held\)\s*\{[^}]*return\s+false;\s*\}\s*'
    r'requestAccess\s*=\s*gAccess\s*;\s*requestSecret\s*=\s*gSecret\s*;\s*\}',
    re.S,
)
snapshot_match = snapshot_re.search(API_CODE)
request_tail = API_CODE[snapshot_match.end():] if snapshot_match else ""
# Limit the no-global-read proof to the request construction function: the next
# top-level helper/class declaration marks the end of that path in this source.
tail_end = re.search(r'\n(?:class|static\s+(?:bool|void|String|int|uint32_t)|bool\s+powerStreamApi|void\s+powerStreamApi|String\s+powerStreamApi)', request_tail)
request_use = request_tail[:tail_end.start()] if tail_end else request_tail

check("AC1 snapshots access+secret under one lock", snapshot_match is not None,
      "request-local AccessKey and SecretKey originate from the same locked RAM generation")
check("request header uses AccessKey snapshot", 'addHeader("accessKey",requestAccess)' in request_use,
      "request-local AccessKey becomes EcoFlow accessKey header")
check("signature base uses AccessKey snapshot", '"accessKey="+requestAccess' in request_use,
      "the same request-local AccessKey is part of the signature base")
check("HMAC uses SecretKey snapshot", 'hmac256(signBase,requestSecret)' in request_use,
      "the request-local SecretKey is the HMAC-SHA256 key")
check("no post-snapshot global credential reads", not re.search(r'\bg(?:Access|Secret)\b', request_use),
      "after the atomic snapshot, request construction does not reread mutable credential globals")

# Security regression guards: do not expose plaintext secret through public API.
check("no public secret getter", "powerStreamApiSecret" not in HDR,
      "header exposes no SecretKey getter")
check("config endpoint remains masked", 'powerStreamApiAccessMasked()' in WEB,
      "normal config GET uses masked AccessKey")
check("no obvious secret JSON field", not re.search(r'\\?"secret(?:_key)?\\?"\s*:', WEB, re.I),
      "web source contains no plaintext secret JSON member")
check("TLS insecure fallback absent", not re.search(r'\bsetInsecure\s*\(', API_CODE),
      "no executable setInsecure() call; comments are ignored")

failed = [x for x in checks if not x[1]]
for name, ok, detail in checks:
    print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")
print(f"SUMMARY | pass={len(checks)-len(failed)} fail={len(failed)} total={len(checks)}")
if failed:
    sys.exit(1)
