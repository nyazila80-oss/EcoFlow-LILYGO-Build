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
if 'MBEDTLS_SSL_VERIFY_NONE' in s: raise RuntimeError('15Z relief: VERIFY_NONE forbidden')
for fn in ('static void tls15x_capture_cert','static void tls15x_probe_pair','static void tls15y_probe_pair'):
    if fn not in s: raise RuntimeError('15Z relief: diagnostic compatibility helper missing: '+fn)
for call in ('tls15x_capture_cert(depth,crt);','tls15x_probe_pair(depth-1);','tls15x_probe_pair(depth);','tls15y_probe_pair(depth-1);','tls15y_probe_pair(depth);'):
    # one occurrence is allowed in the helper definition/name context only for
    # function names; exact call sites must be gone from executable verify path.
    if call in s: raise RuntimeError('15Z relief: diagnostic hotpath call survived: '+call)

cpp.write_text(s,encoding='utf-8')
print('15Z crypto hotpath relief installed: 15X/15Y active probes removed; production VERIFY_REQUIRED preserved')
