#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# 15AK proved the verified TLS handshake transiently exhausts INTERNAL|8BIT.
# ESP32 WiFiClientSecure in this pinned Arduino/IDF line has no setBufferSizes().
# 15AL therefore enables Espressif's compile-time mbedTLS dynamic-buffer path.
# The extra script is executed for every PlatformIO invocation, so provenance
# transformation must be idempotent for later 15AM/15AN lineages.
old='9.36.7.15AG-TLS-PEAK-FIX'
self_ver='9.36.7.15AL-TLS-DYNAMIC-BUFFER-FIX'
downstream=(
    '9.36.7.15AM-PREFLIGHT-AB-24K',
    '9.36.7.15AN-TLS-INTERNAL8-FIX',
)

versions=re.findall(r'tls15z_version\\\":\\\"([^\\\"]+)',s)
if len(versions)!=1:
    raise RuntimeError('15AL provenance missing/non-unique: '+repr(versions))
version=versions[0]

if version==old:
    if s.count(old)!=1:
        raise RuntimeError('15AL transform provenance cardinality != 1')
    s=s.replace(old,self_ver,1)
    version=self_ver
elif version==self_ver or version in downstream:
    # Fixed point: never rewrite a completed downstream lineage backwards.
    pass
else:
    raise RuntimeError('15AL unsupported provenance: '+version)

# Configure the IDF mbedTLS path on every build invocation. These flags are
# build-environment state, not persisted source state, so idempotent source
# provenance must not suppress them.
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

thr32='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 32768;'
thr24='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;'
if version in downstream:
    if s.count(thr24)!=1 or s.count(thr32)!=0:
        raise RuntimeError('15AL downstream threshold invariant failed: expected canonical 24KiB')
else:
    if s.count(thr32)!=1:
        raise RuntimeError('15AL pre-15AM threshold invariant failed: expected canonical 32KiB')

p.write_text(s,encoding='utf-8')
print('[15AL] fixed point PASS; lineage=%s; dynamic TX/RX buffer defines active; verified TLS retained' % version)
