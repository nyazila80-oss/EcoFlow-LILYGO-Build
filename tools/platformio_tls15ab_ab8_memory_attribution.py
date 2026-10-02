#!/usr/bin/env python3
from pathlib import Path
import re

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

# 15AB: attribution only. Measure the cloud-worker AB8 reservation path without
# changing TLS verification, BLE lifecycle, reservation semantics, or CAN.
# Depend on the 15C/base memory state, not the legacy 15AA failed-allocation hook.
anchor='static std::atomic<uint32_t> gTlsInternalFreePost{0}, gTlsInternalLargestPost{0};'
state=r'''
// 9.36.7.15AB: bounded AB8 memory attribution. 0=entry, 1=after admission
// snapshot, 2=before reserve, 3=after reserve, 4=after aux diag, 5=pre TLS client.
static constexpr uint32_t TLS15AB_STEPS=6;
static std::atomic<int32_t> gTls15abFree[TLS15AB_STEPS];
static std::atomic<int32_t> gTls15abLargest[TLS15AB_STEPS];
static std::atomic<int32_t> gTls15abStep{-1};
static inline void tls15abSnap(uint32_t i){
  if(i>=TLS15AB_STEPS) return;
  gTls15abFree[i].store((int32_t)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),std::memory_order_relaxed);
  gTls15abLargest[i].store((int32_t)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),std::memory_order_relaxed);
  gTls15abStep.store((int32_t)i,std::memory_order_release);
}
'''
if 'gTls15abFree' not in s:
    if s.count(anchor)!=1: raise RuntimeError('15AB state anchor missing/non-unique')
    s=s.replace(anchor,anchor+state,1)
elif s.count('static std::atomic<int32_t> gTls15abStep{-1};') != 1:
    raise RuntimeError('15AB state duplicated/malformed')

old='''    bool tls15zAttempted=false, tls15zReserved=false;
    {
      const JkBleStatusDiag adm=jkBleProxyStatusDiag();'''
new='''    bool tls15zAttempted=false, tls15zReserved=false;
    for(uint32_t i=0;i<TLS15AB_STEPS;i++){ gTls15abFree[i].store(-1); gTls15abLargest[i].store(-1); }
    gTls15abStep.store(-1); tls15abSnap(0);
    {
      const JkBleStatusDiag adm=jkBleProxyStatusDiag();'''
if old in s:
    if s.count(old)!=1: raise RuntimeError('15AB entry anchor non-unique')
    s=s.replace(old,new,1)
elif s.count('gTls15abStep.store(-1); tls15abSnap(0);') != 1:
    raise RuntimeError('15AB entry anchor missing/duplicated')

old='''      gTls15zAdmSlotReadyBefore.store(jkBleProxyAuxSlotReady()?1:0);
    }
    if(gTls15zAdmInitialized.load()==1 && !jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }
    gTls15zAdmAttempted.store(tls15zAttempted?1:0);
    const JkBleAuxMemoryDiag tls15zAuxAfter=jkBleProxyAuxMemoryDiag();'''
new='''      gTls15zAdmSlotReadyBefore.store(jkBleProxyAuxSlotReady()?1:0);
    }
    tls15abSnap(1);
    if(gTls15zAdmInitialized.load()==1 && !jkBleProxyAppConnected() && !jkBleProxyEventsPending()){
      tls15zAttempted=true; tls15abSnap(2); tls15zReserved=jkBleProxyReserveAuxConnection(); tls15abSnap(3);
    }
    gTls15zAdmAttempted.store(tls15zAttempted?1:0);
    const JkBleAuxMemoryDiag tls15zAuxAfter=jkBleProxyAuxMemoryDiag(); tls15abSnap(4);'''
if old in s:
    if s.count(old)!=1: raise RuntimeError('15AB reservation anchor non-unique')
    s=s.replace(old,new,1)
elif s.count('tls15abSnap(4);') != 1:
    raise RuntimeError('15AB reservation anchor missing/duplicated')

old='''    WiFiClientSecure client;'''
new='''    tls15abSnap(5);
    WiFiClientSecure client;'''
if 'tls15abSnap(5);' not in s:
    if s.count(old)!=1: raise RuntimeError('15AB TLS-client anchor missing/non-unique')
    s=s.replace(old,new,1)
elif s.count('tls15abSnap(5);') != 1:
    raise RuntimeError('15AB TLS-client checkpoint duplicated')

# Insert beside the consolidated diagnostics, independent of 15AA JSON.
needle='\\"tls15y_version\\":\\"'
if 'tls15ab_version' not in s:
    pos=s.find(needle)
    if pos<0: raise RuntimeError('15AB JSON anchor missing')
    def arr(name): return '+","+'.join('String(%s[%d].load())'%(name,i) for i in range(6))
    fields=('\\"tls15ab_version\\":\\"9.36.7.15AB-AB8-MEMORY-ATTRIBUTION\\",'
            '\\"tls15ab_step\\":"+String(gTls15abStep.load())+",'
            '\\"tls15ab_internal8_free\\":["+'+arr('gTls15abFree')+'+"],'
            '\\"tls15ab_internal8_largest\\":["+'+arr('gTls15abLargest')+'+"],')
    s=s[:pos]+fields+s[pos:]
elif s.count('tls15ab_version') != 1:
    raise RuntimeError('15AB JSON trace duplicated')

# Diagnostic must remain read-only with respect to security/lifecycle behavior.
def strip_comments(x): return re.sub(r'//[^\n]*|/\*.*?\*/','',x,flags=re.S)
code=strip_comments(s)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AB security invariant: setInsecure')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AB security invariant: VERIFY_NONE')
for req in ('TLS15AB_STEPS=6','tls15abSnap(0)','tls15abSnap(3)','tls15abSnap(5)','tls15ab_internal8_largest'):
    if req not in s: raise RuntimeError('15AB postcondition missing: '+req)
if s.count('tls15abSnap(0)') != 1 or s.count('tls15abSnap(3)') != 1 or s.count('tls15abSnap(5)') != 1:
    raise RuntimeError('15AB postcondition: checkpoint duplication')

p.write_text(s,encoding='utf-8')
print('15AB AB8 memory attribution applied; 15C-baseline compatible, behavior unchanged, six checkpoints enabled')
