#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root = Path(env['PROJECT_DIR'])
p = root/'src'/'powerstream_api.cpp'
main_p = root/'src'/'main.cpp'
s = p.read_text(encoding='utf-8')
m = main_p.read_text(encoding='utf-8')

# 15AN hardware fix A/B based on 15AM evidence:
# verified TLS reached an INTERNAL8 minimum of 844 B / 372 B largest and then a
# 4-byte INTERNAL|8BIT allocation failed. Avoid unsafe live NimBLE deinit: the
# first TLS job gets ownership before NimBLE is initialized, then BLE starts.
old_ver='9.36.7.15AM-PREFLIGHT-AB-24K'
new_ver='9.36.7.15AN-TLS-INTERNAL8-FIX'
if new_ver not in s:
    if s.count(old_ver) != 1:
        raise RuntimeError('15AN provenance anchor missing/non-unique')
    s = s.replace(old_ver, new_ver, 1)

code = re.sub(r'//[^\n]*|/\*.*?\*/', '', s, flags=re.S)
if re.search(r'\bsetInsecure\s*\(', code):
    raise RuntimeError('15AN security invariant: setInsecure present')
if 'MBEDTLS_SSL_VERIFY_NONE' in code:
    raise RuntimeError('15AN security invariant: VERIFY_NONE present')
if s.count('client.setCACert(ECOFLOW_CA_BUNDLE);') != 1:
    raise RuntimeError('15AN CA cardinality != 1')
if s.count('client.connect(API_HOST,443)') != 1:
    raise RuntimeError('15AN verified connect cardinality != 1')
if 'static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;' not in s:
    raise RuntimeError('15AN requires 15AM 24KiB preflight')
if '15ak_first_size' not in s:
    raise RuntimeError('15AN requires 15AK allocation telemetry')

# Fail closed if the TLS-first scheduling fix disappears or is weakened.
anchors = [
    'TLS15AN_BLE_FAILSAFE_MS = 120000',
    'if (s15anBleReleased) jkBleProxyTick();',
    'if (s15anBleReleased) powerStreamBleLabTick();',
    'powerStreamApiJobStatusJson()',
    '\"done\":true',
    'cloudCompleted || failsafe',
]
for a in anchors:
    if a not in m:
        raise RuntimeError('15AN TLS-first scheduling anchor missing: '+a)

# Ordering invariant: the cloud/TLS scheduler must execute before the guarded
# BLE ticks in the Arduino loop.
pos_tls = m.find('powerStreamApiLoopTick();')
pos_jk = m.find('if (s15anBleReleased) jkBleProxyTick();')
pos_ps = m.find('if (s15anBleReleased) powerStreamBleLabTick();')
if min(pos_tls,pos_jk,pos_ps) < 0 or not (pos_tls < pos_jk and pos_tls < pos_ps):
    raise RuntimeError('15AN ordering invariant failed: TLS must precede BLE ticks')

print('[15AN] TLS-first INTERNAL8 fix active: verified TLS retained; 24KiB preflight retained; NimBLE startup gated until cloud_done or 120s failsafe')
p.write_text(s, encoding='utf-8')
