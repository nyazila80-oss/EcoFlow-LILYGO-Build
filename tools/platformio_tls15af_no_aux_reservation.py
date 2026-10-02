#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# 15AF hardware-derived A/B fix.
# 15AE/AB8 evidence showed the BLE aux reservation itself consumed/fragmented
# INTERNAL|8BIT heap before TLS: largest block fell 26612 -> 14836/12788 while
# mbedTLS subsequently requested 16717 bytes. For this controlled branch only,
# do not request/release the BLE auxiliary slot in the cloud TLS path.
# JK BLE otherwise remains untouched and TLS peer verification remains mandatory.
root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

version='9.36.7.15AF-NO-AUX-RESERVATION'
marker='gTls15zAdmAttempted.store(0);'

# AB8+admission generated form expected after preceding pre-scripts.
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
elif marker in s and version in s:
    # PlatformIO can execute pre-scripts more than once (fullclean -> build,
    # USB -> OTA -> buildfs).  The already-transformed 15AF source is valid.
    if s.count(marker) != 1:
        raise RuntimeError('15AF idempotence invariant: no-aux marker non-unique')
else:
    raise RuntimeError('15AF expected AB8 admission/reservation block or existing 15AF state missing')

# Provenance only; do not change security or cloud request semantics.
s=s.replace('9.36.7.15Z-MEMORY-RELIEF-AB8',version)

code=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
if 'jkBleProxyReserveAuxConnection();' in code:
    raise RuntimeError('15AF invariant: executable aux reservation remains in TLS path')
if marker not in s or s.count(marker) != 1:
    raise RuntimeError('15AF invariant: canonical no-aux marker missing/non-unique')
if re.search(r'\bsetInsecure\s*\(',code):
    raise RuntimeError('15AF security invariant: setInsecure')
if 'MBEDTLS_SSL_VERIFY_NONE' in code:
    raise RuntimeError('15AF security invariant: VERIFY_NONE')
if 'setCACert(ECOFLOW_CA_BUNDLE)' not in s:
    raise RuntimeError('15AF security invariant: CA verification missing')
if version not in s:
    raise RuntimeError('15AF provenance missing')

p.write_text(s,encoding='utf-8')
print('[15AF] controlled TLS A/B: BLE aux reservation bypassed; CA verification retained (idempotent)')
