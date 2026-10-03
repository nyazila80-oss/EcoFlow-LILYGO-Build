#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# 15AK proved the verified TLS handshake transiently exhausts INTERNAL|8BIT.
# ESP32 WiFiClientSecure in this pinned Arduino/IDF line has no setBufferSizes().
# 15AL therefore uses Espressif's compile-time mbedTLS dynamic TX/RX buffer
# facility. Do not alter CA/hostname verification or the 32 KiB admission gate.
# The flags themselves are injected via env.Append below; this source transform
# only exports provenance and enforces security/lifecycle invariants.
old='9.36.7.15AG-TLS-PEAK-FIX'
new='9.36.7.15AL-TLS-DYNAMIC-BUFFER-FIX'
if new not in s:
    if old not in s: raise RuntimeError('15AL provenance anchor missing')
    s=s.replace(old,new)

# Configure the IDF mbedTLS path supported by this ESP32 framework.
# Dynamic buffers are allocated only when needed and released afterwards.
env.Append(CPPDEFINES=[
    ('CONFIG_MBEDTLS_DYNAMIC_BUFFER', 1),
    ('CONFIG_MBEDTLS_DYNAMIC_FREE_PEER_CERT', 1),
    ('CONFIG_MBEDTLS_DYNAMIC_FREE_CONFIG_DATA', 1),
    ('CONFIG_MBEDTLS_DYNAMIC_FREE_CA_CERT', 1),
])

code=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AL security invariant: setInsecure present')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AL security invariant: VERIFY_NONE present')
if 'setBufferSizes(' in code: raise RuntimeError('15AL incompatible setBufferSizes API still present')
if s.count('client.setCACert(ECOFLOW_CA_BUNDLE);')!=1: raise RuntimeError('15AL CA cardinality != 1')
if s.count('client.connect(API_HOST,443)')!=1: raise RuntimeError('15AL early verified handshake cardinality != 1')

p.write_text(s,encoding='utf-8')
print('[15AL] ESP32 mbedTLS dynamic TX/RX buffers enabled; verified TLS retained')
