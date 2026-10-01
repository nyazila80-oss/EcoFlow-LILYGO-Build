#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# 15Z solution step: keep the already-proven 15X/15Y diagnostic state/getters,
# but remove their active diagnostic work from the real certificate-verify hotpath.
# The production mbedTLS X.509/RSA verification remains untouched and required.
pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15Z relief: framework unresolved')
cpp=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'/'ssl_client.cpp'
s=cpp.read_text(encoding='utf-8')

# These calls were inserted by 15X/15Y solely for root-cause observation. 15Y
# performs an additional mbedtls_pk_verify; 15X hashes/copies certificate data.
# They are now diagnostic overhead after the root cause was narrowed to the
# transient INTERNAL|8BIT crypto peak, so remove calls, not security checks.
patterns=(
    r'^\s*tls15x_capture_cert\(depth,crt\);\s*\n',
    r'^\s*tls15x_probe_pair\(depth-1\);\s*\n',
    r'^\s*tls15x_probe_pair\(depth\);\s*\n',
    r'^\s*tls15y_probe_pair\(depth-1\);\s*\n',
    r'^\s*tls15y_probe_pair\(depth\);\s*\n',
)
for pat in patterns:
    s2,n=re.subn(pat,'',s,count=1,flags=re.M)
    if n!=1: raise RuntimeError('15Z relief hotpath anchor missing/non-unique: '+pat)
    s=s2

# Security/composition invariant, scoped to the path this firmware actually
# uses. Arduino-ESP32 intentionally contains a VERIFY_NONE branch for callers
# that explicitly request `insecure`; its mere presence in the framework is not
# evidence that this firmware uses it. Our EcoFlow client supplies a CA via
# setCACert(), so require the CA branch to remain VERIFY_REQUIRED and the 15J
# verify callback to remain attached there.
required='mbedtls_ssl_conf_authmode(&ssl_client->ssl_conf, MBEDTLS_SSL_VERIFY_REQUIRED);'
ca_anchor='else if (rootCABuff != NULL)'
verify_cb='mbedtls_ssl_conf_verify(&ssl_client->ssl_conf, tls15j_verify_cb, NULL);'
if ca_anchor not in s: raise RuntimeError('15Z relief: CA verification branch lost')
ca=s[s.index(ca_anchor):]
# Limit the proof to the CA branch, before the next top-level alternative.
next_branch=ca.find('else if (',len(ca_anchor))
if next_branch >= 0: ca=ca[:next_branch]
if required not in ca: raise RuntimeError('15Z relief: CA path VERIFY_REQUIRED lost')
if verify_cb not in ca: raise RuntimeError('15Z relief: 15J verify callback lost from CA path')

# Project-side fail-closed proof: EcoFlow code must install a CA and must never
# request Arduino's insecure branch. This checks the actual caller rather than
# banning a legitimate unused framework capability.
proj=Path(env['PROJECT_DIR'])
ps=(proj/'src'/'powerstream_api.cpp').read_text(encoding='utf-8')
def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
ps_code=strip_cpp_comments(ps)
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in ps_code:
    raise RuntimeError('15Z relief: EcoFlow CA installation lost')
if re.search(r'\bsetInsecure\s*\(',ps_code):
    raise RuntimeError('15Z relief: EcoFlow caller requests insecure TLS')

# Framework VERIFY_NONE is allowed only as Arduino's stock opt-in insecure
# branch. Prove it is still guarded by `if (insecure)` rather than globally
# rejecting the token (the old #308/#309 false gate).
none_stmt='mbedtls_ssl_conf_authmode(&ssl_client->ssl_conf, MBEDTLS_SSL_VERIFY_NONE);'
if none_stmt in s:
    pos=s.index(none_stmt)
    guard=s.rfind('if (insecure)',0,pos)
    ca_pos=s.find(ca_anchor,guard if guard >= 0 else 0)
    if guard < 0 or ca_pos < 0 or not (guard < pos < ca_pos):
        raise RuntimeError('15Z relief: VERIFY_NONE escaped stock insecure guard')

for fn in ('static void tls15x_capture_cert','static void tls15x_probe_pair','static void tls15y_probe_pair'):
    if fn not in s: raise RuntimeError('15Z relief: diagnostic compatibility helper missing: '+fn)
for call in ('tls15x_capture_cert(depth,crt);','tls15x_probe_pair(depth-1);','tls15x_probe_pair(depth);','tls15y_probe_pair(depth-1);','tls15y_probe_pair(depth);'):
    if call in s: raise RuntimeError('15Z relief: diagnostic hotpath call survived: '+call)

cpp.write_text(s,encoding='utf-8')
print('15Z crypto hotpath relief installed: active probes removed; EcoFlow CA path VERIFY_REQUIRED; stock insecure branch isolated')
