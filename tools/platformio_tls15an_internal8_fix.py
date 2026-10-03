#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root = Path(env['PROJECT_DIR'])
p = root/'src'/'powerstream_api.cpp'
main_p = root/'src'/'main.cpp'
s = p.read_text(encoding='utf-8')
m = main_p.read_text(encoding='utf-8')

# 15AN hardware fix A/B based on 15AM evidence. Transform 15AM -> 15AN once;
# repeated PlatformIO invocations must verify the exact final state without
# source mutation. Verified TLS and the 24KiB preflight remain mandatory.
old_ver='9.36.7.15AM-PREFLIGHT-AB-24K'
new_ver='9.36.7.15AN-TLS-INTERNAL8-FIX'
versions=re.findall(r'tls15z_version\\\":\\\"([^\\\"]+)',s)
if len(versions)!=1:
    raise RuntimeError('15AN provenance missing/non-unique: '+repr(versions))
version=versions[0]
if version==old_ver:
    if s.count(old_ver)!=1:
        raise RuntimeError('15AN transform provenance cardinality != 1')
    s=s.replace(old_ver,new_ver,1)
    version=new_ver
elif version==new_ver:
    pass
else:
    raise RuntimeError('15AN unsupported provenance: '+version)

code = re.sub(r'//[^\n]*|/\*.*?\*/', '', s, flags=re.S)
if re.search(r'\bsetInsecure\s*\(', code): raise RuntimeError('15AN security invariant: setInsecure present')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AN security invariant: VERIFY_NONE present')
if s.count('client.setCACert(ECOFLOW_CA_BUNDLE);') != 1: raise RuntimeError('15AN CA cardinality != 1')
if s.count('client.connect(API_HOST,443)') != 1: raise RuntimeError('15AN verified connect cardinality != 1')
thr24='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;'
thr32='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 32768;'
if s.count(thr24)!=1 or s.count(thr32)!=0: raise RuntimeError('15AN requires canonical 15AM 24KiB preflight')
if '15ak_first_size' not in s: raise RuntimeError('15AN requires 15AK allocation telemetry')
if 'tls_attempted_this_job' not in s: raise RuntimeError('15AN requires per-job TLS ownership telemetry')

anchors = [
    'TLS15AN_BLE_FAILSAFE_MS = 120000',
    'if (s15anBleReleased) jkBleProxyTick();',
    'if (s15anBleReleased) powerStreamBleLabTick();',
    'powerStreamApiJobStatusJson()',
    'js.indexOf("\\\"done\\\":true") >= 0',
    'cloudCompleted || failsafe',
]
for a in anchors:
    if a not in m: raise RuntimeError('15AN TLS-first scheduling anchor missing: '+a)

pos_tls=m.find('powerStreamApiLoopTick();')
pos_jk=m.find('if (s15anBleReleased) jkBleProxyTick();')
pos_ps=m.find('if (s15anBleReleased) powerStreamBleLabTick();')
if min(pos_tls,pos_jk,pos_ps)<0 or not (pos_tls<pos_jk and pos_tls<pos_ps):
    raise RuntimeError('15AN ordering invariant failed: TLS must precede BLE ticks')

p.write_text(s,encoding='utf-8')
print('[15AN] fixed point PASS; final lineage=%s; verified TLS + canonical 24KiB preflight + TLS-first BLE gating retained' % version)
