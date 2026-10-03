#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# 15AM diagnostic A/B only. Transform 15AL 32KiB -> 15AM 24KiB exactly once.
# On repeated PlatformIO invocations, 15AM and 15AN are fixed points: verify the
# canonical 24KiB state and never rewrite a completed downstream lineage.
old_thr='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 32768;'
new_thr='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;'
old_ver='9.36.7.15AL-TLS-DYNAMIC-BUFFER-FIX'
self_ver='9.36.7.15AM-PREFLIGHT-AB-24K'
downstream='9.36.7.15AN-TLS-INTERNAL8-FIX'

versions=re.findall(r'tls15z_version\\\":\\\"([^\\\"]+)',s)
if len(versions)!=1:
    raise RuntimeError('15AM provenance missing/non-unique: '+repr(versions))
version=versions[0]

if version==old_ver:
    if s.count(old_thr)!=1 or s.count(new_thr)!=0:
        raise RuntimeError('15AM transform threshold invariant failed: expected canonical 32KiB')
    s=s.replace(old_thr,new_thr,1)
    if s.count(old_ver)!=1:
        raise RuntimeError('15AM transform provenance cardinality != 1')
    s=s.replace(old_ver,self_ver,1)
    version=self_ver
elif version in (self_ver,downstream):
    if s.count(new_thr)!=1 or s.count(old_thr)!=0:
        raise RuntimeError('15AM downstream threshold invariant failed: expected canonical 24KiB')
else:
    raise RuntimeError('15AM unsupported provenance: '+version)

code=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AM security invariant: setInsecure present')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AM security invariant: VERIFY_NONE present')
if s.count('client.setCACert(ECOFLOW_CA_BUNDLE);')!=1: raise RuntimeError('15AM CA cardinality != 1')
if s.count('client.connect(API_HOST,443)')!=1: raise RuntimeError('15AM verified connect cardinality != 1')
if s.count(new_thr)!=1: raise RuntimeError('15AM threshold cardinality != 1')
if '15ak_first_size' not in s: raise RuntimeError('15AM requires 15AK allocation telemetry')
if 'tls_attempted_this_job' not in s: raise RuntimeError('15AM requires per-job TLS ownership telemetry')

p.write_text(s,encoding='utf-8')
print('[15AM] fixed point PASS; lineage=%s; canonical 24KiB preflight; CA/hostname verification and 15AK telemetry retained' % version)
