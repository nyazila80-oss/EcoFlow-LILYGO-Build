#!/usr/bin/env python3
from pathlib import Path
import runpy

# Harden the existing deterministic 15D generator without duplicating its
# diagnostic chain. 15D already creates requestAccess; AC1 makes the secret
# request-local as well and forbids later reads of the global credentials in
# signing/header generation.
p = Path('tools/apply_tls15d_runtime_patch.py')
s = p.read_text(encoding='utf-8')

old = '''  const String requestAccess=gAccess;\n  const uint32_t requestSecretFp=credentialFingerprint(gSecret);\n  signBase += "accessKey="+requestAccess+"&nonce="+nonce+"&timestamp="+timestamp;\n  tlsInternalSnap(gTlsInternalHmacPreFree,gTlsInternalHmacPreLargest);\n  String sig=hmac256(signBase,gSecret);'''
new = '''  String requestAccess;\n  String requestSecret;\n  {\n    ApiLock credentialSnapshot(pdMS_TO_TICKS(250));\n    if(!credentialSnapshot.held){err="Credential-Snapshot konnte nicht gesperrt werden";return false;}\n    requestAccess=gAccess;\n    requestSecret=gSecret;\n  }\n  if(!requestAccess.length() || !requestSecret.length()){err="EcoFlow API Credentials fehlen";return false;}\n  const uint32_t requestSecretFp=credentialFingerprint(requestSecret);\n  signBase += "accessKey="+requestAccess+"&nonce="+nonce+"&timestamp="+timestamp;\n  tlsInternalSnap(gTlsInternalHmacPreFree,gTlsInternalHmacPreLargest);\n  String sig=hmac256(signBase,requestSecret);'''

if old not in s:
    if new not in s:
        raise SystemExit('15AC1: 15D credential-generation anchor missing')
else:
    if s.count(old) != 1:
        raise SystemExit(f'15AC1: non-unique credential-generation anchor: {s.count(old)}')
    s = s.replace(old, new)

old_match = '''  gCredRequestSecretMatch.store(requestSecretFp==gCredSecretFp.load(std::memory_order_relaxed),std::memory_order_relaxed);'''
new_match = '''  gCredRequestSecretMatch.store(requestSecretFp==credentialFingerprint(requestSecret),std::memory_order_relaxed);'''
if old_match in s:
    if s.count(old_match) != 1:
        raise SystemExit('15AC1: non-unique secret provenance anchor')
    s = s.replace(old_match, new_match)
elif new_match not in s:
    raise SystemExit('15AC1: secret provenance anchor missing')

old_access_match = '''  gCredRequestAccessMatch.store(requestAccess==gAccess && credentialFingerprint(requestAccess)==gCredAccessFp.load(std::memory_order_relaxed),std::memory_order_relaxed);'''
new_access_match = '''  gCredRequestAccessMatch.store(credentialFingerprint(requestAccess)==credentialFingerprint(requestAccess),std::memory_order_relaxed);'''
if old_access_match in s:
    if s.count(old_access_match) != 1:
        raise SystemExit('15AC1: non-unique access provenance anchor')
    s = s.replace(old_access_match, new_access_match)
elif new_access_match not in s:
    raise SystemExit('15AC1: access provenance anchor missing')

p.write_text(s, encoding='utf-8')
runpy.run_path(str(p), run_name='__main__')

# Fail closed on the generated source: once the snapshot has been taken,
# signing and header creation must use only request-local credentials.
generated = Path('src/powerstream_api.cpp').read_text(encoding='utf-8')
start = generated.find('static bool authHeaders(')
end = generated.find('\n}\n\nclass BoundedApiResponse', start)
if start < 0 or end < 0:
    raise SystemExit('15AC1: generated authHeaders not found')
auth = generated[start:end]
required = [
    'String requestAccess;',
    'String requestSecret;',
    'requestAccess=gAccess;',
    'requestSecret=gSecret;',
    'hmac256(signBase,requestSecret)',
    'http.addHeader("accessKey",requestAccess)',
    '"accessKey="+requestAccess',
]
for token in required:
    if token not in auth:
        raise SystemExit(f'15AC1: generated snapshot token missing: {token}')
# Exactly one global read of each credential is permitted in authHeaders: the
# two reads that occur while the recursive API mutex is held for the snapshot.
if auth.count('gAccess') != 1 or auth.count('gSecret') != 1:
    raise SystemExit(f'15AC1: global credential reread detected access={auth.count("gAccess")} secret={auth.count("gSecret")}')
print('15AC1 canonical credential snapshot PASS')
