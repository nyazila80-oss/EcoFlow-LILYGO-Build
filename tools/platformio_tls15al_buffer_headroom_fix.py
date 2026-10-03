#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# Hardware 15AK proved the verified TLS handshake starts with ~47 KiB largest8
# but transiently drives INTERNAL|8BIT down to 1172 B free / 500 B largest and
# then misses one 4-byte allocation. Keep CA verification and the early
# handshake, but reduce BearSSL/mbedTLS record-buffer pressure through the
# supported WiFiClientSecure API. 8 KiB RX + 4 KiB TX leaves materially more
# headroom than the default buffers while retaining enough room for API HTTPS.
ctor='  WiFiClientSecure client;'
fix='''  WiFiClientSecure client;
  // 15AL: bounded TLS record buffers; preserve fail-closed X509 verification.
  // Hardware validation must prove the EcoFlow endpoint accepts these sizes.
  client.setBufferSizes(8192, 4096);'''
if 'client.setBufferSizes(8192, 4096);' not in s:
    if s.count(ctor)!=1: raise RuntimeError('15AL WiFiClientSecure constructor anchor missing/non-unique')
    s=s.replace(ctor,fix,1)
elif s.count('client.setBufferSizes(8192, 4096);')!=1:
    raise RuntimeError('15AL buffer-size call duplicated')

# Export provenance in the existing TLS diagnostic version string.
old='9.36.7.15AG-TLS-PEAK-FIX'
new='9.36.7.15AL-TLS-BUFFER-HEADROOM-FIX'
if new not in s:
    if old not in s: raise RuntimeError('15AL provenance anchor missing')
    s=s.replace(old,new)

# Security/lifecycle invariants: no insecure fallback, CA remains installed,
# and 15AH still performs exactly one explicit verified early handshake.
code=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AL security invariant: setInsecure present')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AL security invariant: VERIFY_NONE present')
if s.count('client.setCACert(ECOFLOW_CA_BUNDLE);')!=1: raise RuntimeError('15AL CA cardinality != 1')
if s.count('client.connect(API_HOST,443)')!=1: raise RuntimeError('15AL early verified handshake cardinality != 1')
if s.count('client.setBufferSizes(8192, 4096);')!=1: raise RuntimeError('15AL TLS buffer fix cardinality != 1')

p.write_text(s,encoding='utf-8')
print('[15AL] TLS RX/TX buffers bounded to 8192/4096; CA verification and early handshake retained')
