#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# 15AF hardware-derived A/B fix.
# 15AE/AB8 evidence showed the BLE aux reservation itself consumed/fragmented
# INTERNAL|8BIT heap before TLS. For this controlled branch only, do not
# request/release the BLE auxiliary slot in the cloud TLS path.
# JK BLE otherwise remains untouched and TLS peer verification remains mandatory.
#
# PlatformIO executes pre-scripts for clean/build/OTA/buildfs. A later pass can
# therefore receive an already transformed 15AF..15AN source. Treat that as a
# valid fixed point only when canonical no-aux provenance is present and the
# executable reservation has not returned.
root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

version='9.36.7.15AF-NO-AUX-RESERVATION'
marker='gTls15zAdmAttempted.store(0);'
lineage_versions={
    version,
    '9.36.7.15AG-TLS-PEAK-FIX',
    '9.36.7.15AH-EARLY-TLS-HANDSHAKE',
    '9.36.7.15AI-PS-BLE-RECLAIM-DIAG',
    '9.36.7.15AK-TLS-ALLOC-PEAK-DIAG',
    '9.36.7.15AL-TLS-DYNAMIC-BUFFER-FIX',
    '9.36.7.15AM-PREFLIGHT-AB-24K',
    '9.36.7.15AN-TLS-INTERNAL8-FIX',
}

# Read the canonical JSON provenance value, not arbitrary historical strings in
# comments/scripts. The generated C++ contains exactly one tls15z_version field.
version_re=re.compile(r'tls15z_version\\\":\\\"([^\\\"]+)')
versions=version_re.findall(s)
if len(versions)!=1:
    raise RuntimeError('15AF provenance: tls15z_version missing/non-unique: '+repr(versions))
current_version=versions[0]

# AB8+admission generated form expected on the first transform pass.
pat=re.compile(r'''bool tls15zAttempted=false, tls15zReserved=false;\n    \{\n      const JkBleStatusDiag adm=jkBleProxyStatusDiag\(\);.*?\n    \}\n    if\([^\n]*\)\{ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection\(\); \}\n    gTls15zAdmAttempted\.store\(tls15zAttempted\?1:0\);''',re.S)
m=pat.search(s)

replacement='''bool tls15zAttempted=false, tls15zReserved=false;
    {
      const JkBleStatusDiag adm=jkBleProxyStatusDiag();
      gTls15zAdmInitialized.store(adm.initialized?1:0);
      gTls15zAdmApp.store(adm.appConnected?1:0);
      gTls15zAdmBms.store(adm.bmsConnected?1:0);
      gTls15zAdmEvents.store(adm.eventsPending?1:0);
      gTls15zAdmSafeHold.store(adm.safeHold?1:0);
      gTls15zAdmStartupEnabled.store(adm.startupEnabled?1:0);
      gTls15zAdmStartupApplied.store(jkBleStartupAppliedEnabled()?1:0);
      gTls15zAdmAuxReservedBefore.store(adm.auxReserved?1:0);
      gTls15zAdmSlotReadyBefore.store(jkBleProxyAuxSlotReady()?1:0);
    }
    // 15AF A/B: deliberately no jkBleProxyReserveAuxConnection() here.
    // Preserve telemetry: attempted=0/reserved=0 identifies the bypass run.
    gTls15zAdmAttempted.store(0);'''

if m:
    s=s[:m.start()]+replacement+s[m.end():]
    # First 15AF transform advances only AB8 provenance. Later transforms own
    # their own version changes; never rewrite a downstream version backwards.
    s=s.replace('9.36.7.15Z-MEMORY-RELIEF-AB8',version)
elif current_version in lineage_versions and marker in s:
    if s.count(marker)!=1:
        raise RuntimeError('15AF idempotence invariant: no-aux marker non-unique')
    # Downstream fixed point: observation/verification only.
else:
    raise RuntimeError('15AF expected AB8 admission/reservation block or canonical 15AF..15AN no-aux state missing')

code=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
if 'jkBleProxyReserveAuxConnection();' in code:
    raise RuntimeError('15AF invariant: executable aux reservation remains in TLS path')
if marker not in s or s.count(marker)!=1:
    raise RuntimeError('15AF invariant: canonical no-aux marker missing/non-unique')
if re.search(r'\bsetInsecure\s*\(',code):
    raise RuntimeError('15AF security invariant: setInsecure')
if 'MBEDTLS_SSL_VERIFY_NONE' in code:
    raise RuntimeError('15AF security invariant: VERIFY_NONE')
if 'setCACert(ECOFLOW_CA_BUNDLE)' not in s:
    raise RuntimeError('15AF security invariant: CA verification missing')

# Re-read provenance after an optional first-pass replacement and require either
# 15AF itself or a known later descendant. This prevents silent lineage drift.
post_versions=version_re.findall(s)
if len(post_versions)!=1 or post_versions[0] not in lineage_versions:
    raise RuntimeError('15AF provenance invariant after transform: '+repr(post_versions))

p.write_text(s,encoding='utf-8')
print('[15AF] controlled TLS A/B verified; lineage=%s; BLE aux reservation bypassed; CA verification retained' % post_versions[0])
