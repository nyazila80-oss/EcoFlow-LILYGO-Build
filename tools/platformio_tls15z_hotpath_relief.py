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

# Security and composition invariants: the genuine TLS verifier remains present;
# no insecure mode is introduced, and the diagnostic helper definitions remain
# available so existing JSON/API fields keep ABI/source compatibility.
if 'MBEDTLS_SSL_VERIFY_REQUIRED' not in s: raise RuntimeError('15Z relief: VERIFY_REQUIRED lost')
if re.search(r'\bsetInsecure\s*\(',s): raise RuntimeError('15Z relief: executable setInsecure() forbidden')

# Do not use a raw substring search here. Earlier diagnostic instrumentation may
# legitimately mention VERIFY_NONE in comments/strings used by security guards.
# Strip comments and string/character literals, then reject the token if it is
# present in executable C/C++ source. This keeps the fail-closed invariant while
# avoiding the false positive seen in CI #308.
def _strip_noncode(src):
    out=[]
    i=0
    n=len(src)
    while i<n:
        if src.startswith('//',i):
            j=src.find('\n',i+2)
            if j<0: break
            out.append('\n'); i=j+1; continue
        if src.startswith('/*',i):
            j=src.find('*/',i+2)
            if j<0: raise RuntimeError('15Z relief: unterminated block comment while auditing VERIFY_NONE')
            out.append('\n'*src[i:j+2].count('\n')); i=j+2; continue
        if src[i] in ('"', "'"):
            quote=src[i]; out.append(' '); i+=1
            while i<n:
                if src[i]=='\\':
                    out.append(' '); i+=1
                    if i<n: out.append('\n' if src[i]=='\n' else ' '); i+=1
                    continue
                if src[i]==quote:
                    out.append(' '); i+=1; break
                out.append('\n' if src[i]=='\n' else ' '); i+=1
            continue
        out.append(src[i]); i+=1
    return ''.join(out)

code_only=_strip_noncode(s)
if re.search(r'\bMBEDTLS_SSL_VERIFY_NONE\b',code_only):
    raise RuntimeError('15Z relief: executable VERIFY_NONE forbidden')

for fn in ('static void tls15x_capture_cert','static void tls15x_probe_pair','static void tls15y_probe_pair'):
    if fn not in s: raise RuntimeError('15Z relief: diagnostic compatibility helper missing: '+fn)
for call in ('tls15x_capture_cert(depth,crt);','tls15x_probe_pair(depth-1);','tls15x_probe_pair(depth);','tls15y_probe_pair(depth-1);','tls15y_probe_pair(depth);'):
    if call in s: raise RuntimeError('15Z relief: diagnostic hotpath call survived: '+call)

cpp.write_text(s,encoding='utf-8')
print('15Z crypto hotpath relief installed: active probes removed; executable VERIFY_NONE rejected; VERIFY_REQUIRED preserved')
