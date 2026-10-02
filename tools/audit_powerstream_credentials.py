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

# Browser/API ingress. Allow harmless whitespace introduced by formatting.
check("web reads access POST field",
      re.search(r'hasParam\(\s*"access"\s*,\s*true\s*\)', WEB) is not None and
      re.search(r'getParam\(\s*"access"\s*,\s*true\s*\)', WEB) is not None,
      "POST access field is read")
check("web reads secret POST field",
      re.search(r'hasParam\(\s*"secret"\s*,\s*true\s*\)', WEB) is not None and
      re.search(r'getParam\(\s*"secret"\s*,\s*true\s*\)', WEB) is not None,
      "POST secret field is read")
check("web forwards both to save",
      re.search(r'powerStreamApiSave\(\s*sn\s*,\s*ak\s*,\s*sk\s*\)', WEB) is not None,
      "sn/access/secret are forwarded together")

# RAM/NVS persistence and reload. These checks deliberately describe the
# storage generation; request construction below must not reread it later.
check("NVS namespace psapi", re.search(r'begin\(\s*"psapi"', API) is not None,
      "PowerStream credentials use psapi namespace")
for key, var in (("sn", "gSn"), ("access", "gAccess"), ("secret", "gSecret")):
    check(f"NVS writes {key}",
          re.search(rf'putString\(\s*"{key}"\s*,\s*{var}\s*\)', API) is not None,
          f"{key} persisted from RAM")
    check(f"NVS reloads {key}",
          re.search(rf'{var}\s*=\s*p\.getString\(\s*"{key}"', API) is not None,
          f"{key} reloaded into RAM")
check("blank access preserves stored value",
      re.search(r'if\s*\(\s*a\.length\(\)\s*\)\s*gAccess\s*=\s*a\s*;', API_CODE) is not None,
      "empty AccessKey field does not erase existing key")
check("blank secret preserves stored value",
      re.search(r'if\s*\(\s*k\.length\(\)\s*\)\s*gSecret\s*=\s*k\s*;', API_CODE) is not None,
      "empty SecretKey field does not erase existing key")

# AC1 request invariant. Locate authHeaders structurally, then prove that both
# mutable credential globals are copied under ONE ApiLock. All subsequent
# request material must derive exclusively from requestAccess/requestSecret.
auth_start = re.search(r'static\s+bool\s+authHeaders\s*\([^)]*\)\s*\{', API_CODE)
auth_body = ""
if auth_start:
    pos = auth_start.end()
    depth = 1
    i = pos
    in_string = False
    escaped = False
    quote = ''
    while i < len(API_CODE) and depth:
        c = API_CODE[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == quote:
                in_string = False
        elif c in ('"', "'"):
            in_string = True
            quote = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    if depth == 0:
        auth_body = API_CODE[pos:i-1]

snapshot_re = re.compile(
    r'String\s+requestAccess\s*;\s*String\s+requestSecret\s*;\s*'
    r'\{\s*ApiLock\s+credentialSnapshot\s*\([^;]+;\s*'
    r'if\s*\(\s*!credentialSnapshot\.held\s*\)\s*\{.*?return\s+false\s*;\s*\}\s*'
    r'requestAccess\s*=\s*gAccess\s*;\s*requestSecret\s*=\s*gSecret\s*;\s*\}',
    re.S,
)
snapshot_match = snapshot_re.search(auth_body)
request_use = auth_body[snapshot_match.end():] if snapshot_match else ""

check("AC1 snapshots access+secret under one lock", snapshot_match is not None,
      "request-local AccessKey and SecretKey originate from the same locked RAM generation")
check("request header uses AccessKey snapshot",
      re.search(r'addHeader\(\s*"accessKey"\s*,\s*requestAccess\s*\)', request_use) is not None,
      "request-local AccessKey becomes EcoFlow accessKey header")
check("signature base uses AccessKey snapshot",
      re.search(r'"accessKey="\s*\+\s*requestAccess', request_use) is not None,
      "the same request-local AccessKey is part of the signature base")
check("HMAC uses SecretKey snapshot",
      re.search(r'hmac256\(\s*signBase\s*,\s*requestSecret\s*\)', request_use) is not None,
      "the request-local SecretKey is the HMAC-SHA256 key")
check("no post-snapshot global credential reads",
      snapshot_match is not None and not re.search(r'\bg(?:Access|Secret)\b', request_use),
      "after the atomic snapshot, authHeaders never rereads mutable credential globals")

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
