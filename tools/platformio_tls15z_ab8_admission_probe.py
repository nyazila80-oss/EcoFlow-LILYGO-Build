#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# AB8 admission probe: observation only. Do not alter BLE/TLS behavior.
# We need to prove why jkBleProxyReserveAuxConnection() returns before the
# Arduino-loop owner advances aux generation / stops advertising.
proj=Path(env['PROJECT_DIR'])
cpp=proj/'src'/'powerstream_api.cpp'
p=cpp.read_text(encoding='utf-8')

anchor='static std::atomic<uint32_t> gCloudTraceJobId{0};'
state='''
// 15Z AB8 admission probe (read-only provenance).
static std::atomic<int32_t> gTls15zAdmInitialized{-1}, gTls15zAdmApp{-1}, gTls15zAdmBms{-1};
static std::atomic<int32_t> gTls15zAdmEvents{-1}, gTls15zAdmSafeHold{-1};
static std::atomic<int32_t> gTls15zAdmStartupEnabled{-1}, gTls15zAdmStartupApplied{-1};
static std::atomic<int32_t> gTls15zAdmAuxReservedBefore{-1}, gTls15zAdmSlotReadyBefore{-1};
static std::atomic<int32_t> gTls15zAdmAttempted{-1};
'''
if 'gTls15zAdmInitialized' not in p:
    if p.count(anchor)!=1: raise RuntimeError('AB8 admission state anchor missing/non-unique')
    p=p.replace(anchor,anchor+state,1)

old='''bool tls15zAttempted=false, tls15zReserved=false;
    if(!jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
new='''bool tls15zAttempted=false, tls15zReserved=false;
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
    if(!jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }
    gTls15zAdmAttempted.store(tls15zAttempted?1:0);'''
if old in p:
    if p.count(old)!=1: raise RuntimeError('AB8 admission call anchor non-unique')
    p=p.replace(old,new,1)
elif 'gTls15zAdmAttempted.store' not in p:
    raise RuntimeError('AB8 admission call anchor missing')

needle='\\"tls15z_version\\":\\"'
if 'tls15z_adm_initialized' not in p:
    pos=p.find(needle)
    if pos<0: raise RuntimeError('AB8 admission JSON anchor missing')
    fields=('\\"tls15z_adm_initialized\\":"+String(gTls15zAdmInitialized.load())+",'
            '\\"tls15z_adm_app_connected\\":"+String(gTls15zAdmApp.load())+",'
            '\\"tls15z_adm_bms_connected\\":"+String(gTls15zAdmBms.load())+",'
            '\\"tls15z_adm_events_pending\\":"+String(gTls15zAdmEvents.load())+",'
            '\\"tls15z_adm_safe_hold\\":"+String(gTls15zAdmSafeHold.load())+",'
            '\\"tls15z_adm_startup_enabled\\":"+String(gTls15zAdmStartupEnabled.load())+",'
            '\\"tls15z_adm_startup_applied\\":"+String(gTls15zAdmStartupApplied.load())+",'
            '\\"tls15z_adm_aux_reserved_before\\":"+String(gTls15zAdmAuxReservedBefore.load())+",'
            '\\"tls15z_adm_slot_ready_before\\":"+String(gTls15zAdmSlotReadyBefore.load())+",'
            '\\"tls15z_adm_attempted\\":"+String(gTls15zAdmAttempted.load())+",')
    p=p[:pos]+fields+p[pos:]

if 'jkBleProxyReserveAuxConnection();' not in p: raise RuntimeError('AB8 handshake missing')
if 'jkBleProxyReserveAuxConnectionOwner();' in p: raise RuntimeError('AB8 direct owner regression')
for key in ('tls15z_adm_initialized','tls15z_adm_app_connected','tls15z_adm_bms_connected',
            'tls15z_adm_events_pending','tls15z_adm_safe_hold','tls15z_adm_startup_enabled',
            'tls15z_adm_startup_applied','tls15z_adm_aux_reserved_before',
            'tls15z_adm_slot_ready_before','tls15z_adm_attempted'):
    if p.count('\\"'+key+'\\"')!=1: raise RuntimeError('AB8 admission JSON invariant: '+key)

def strip_cpp_comments(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
code=strip_cpp_comments(p)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('AB8 admission security invariant: setInsecure')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('AB8 admission security invariant: VERIFY_NONE')

cpp.write_text(p,encoding='utf-8')
print('[15Z-AB8-ADMISSION] read-only reservation admission provenance enabled')
