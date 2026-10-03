#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# 15AM diagnostic A/B only.
# Hardware evidence shows verified TLS has previously reached the handshake with
# ~30.7 KiB largest8, while 15AL Run #1 was blocked at 31,732 B solely by the
# historical 32 KiB preflight. Lower only the preflight to 24 KiB so 15AL's
# dynamic-buffer path can actually execute. Do not weaken TLS verification or
# alter BLE ownership/lifecycle.
old_thr='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 32768;'
new_thr='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;'
if s.count(new_thr)==1:
    pass
elif s.count(new_thr)>1:
    raise RuntimeError('15AM threshold duplicated')
elif s.count(old_thr)==1:
    s=s.replace(old_thr,new_thr,1)
else:
    raise RuntimeError('15AM 32KiB threshold anchor missing/non-unique')

old_ver='9.36.7.15AL-TLS-DYNAMIC-BUFFER-FIX'
new_ver='9.36.7.15AM-PREFLIGHT-AB-24K'
if new_ver not in s:
    if s.count(old_ver)!=1: raise RuntimeError('15AM provenance anchor missing/non-unique')
    s=s.replace(old_ver,new_ver,1)

code=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AM security invariant: setInsecure present')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AM security invariant: VERIFY_NONE present')
if s.count('client.setCACert(ECOFLOW_CA_BUNDLE);')!=1: raise RuntimeError('15AM CA cardinality != 1')
if s.count('client.connect(API_HOST,443)')!=1: raise RuntimeError('15AM verified connect cardinality != 1')
if s.count(new_thr)!=1: raise RuntimeError('15AM threshold cardinality != 1')
if '15ak_first_size' not in s: raise RuntimeError('15AM requires 15AK allocation telemetry')
if 'tls_attempted_this_job' not in s: raise RuntimeError('15AM requires per-job TLS ownership telemetry')

p.write_text(s,encoding='utf-8')
print('[15AM] diagnostic A/B: TLS preflight 32KiB -> 24KiB; CA/hostname verification and 15AK telemetry retained')
