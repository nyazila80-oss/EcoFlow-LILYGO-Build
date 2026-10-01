#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# 15Z AB7 hardening runs after AB6. It changes only BLE arbitration/provenance
# and diagnostics; TLS verification remains fail-closed.
proj=Path(env['PROJECT_DIR'])
jkh=proj/'include'/'jk_ble_proxy.h'; jkc=proj/'src'/'jk_ble_proxy.cpp'; cpp=proj/'src'/'powerstream_api.cpp'
h=jkh.read_text(encoding='utf-8'); j=jkc.read_text(encoding='utf-8'); p=cpp.read_text(encoding='utf-8')

# Explicit control-flow provenance: a heap value is never used as proof that
# stopAdvertising() executed.
old='''  uint32_t afterDecisionFree=0, afterDecisionLargest=0;\n  uint32_t generation=0;'''
new='''  uint32_t afterDecisionFree=0, afterDecisionLargest=0;\n  uint32_t generation=0;\n  uint32_t stopGeneration=0;'''
if old in h: h=h.replace(old,new,1)
elif 'uint32_t stopGeneration=0;' not in h: raise RuntimeError('15Z AB7 header provenance anchor missing/non-unique')

old_decl='sAuxAfterDecisionFree{0},sAuxAfterDecisionLargest{0},sAuxDiagGeneration{0};'
new_decl='sAuxAfterDecisionFree{0},sAuxAfterDecisionLargest{0},sAuxDiagGeneration{0},sAuxStopGeneration{0};'
if old_decl in j: j=j.replace(old_decl,new_decl,1)
elif 'sAuxStopGeneration{0}' not in j: raise RuntimeError('15Z AB7 source provenance declaration anchor missing')

old_stop='NimBLEDevice::stopAdvertising(); auxMemSnap(sAuxAfterStopFree,sAuxAfterStopLargest);'
new_stop='NimBLEDevice::stopAdvertising(); sAuxStopGeneration.fetch_add(1,std::memory_order_acq_rel); auxMemSnap(sAuxAfterStopFree,sAuxAfterStopLargest);'
if old_stop in j: j=j.replace(old_stop,new_stop,1)
elif new_stop not in j: raise RuntimeError('15Z AB7 owner stop marker anchor missing')

needle='d.afterStopFree=sAuxAfterStopFree.load();d.afterStopLargest=sAuxAfterStopLargest.load();'
replacement=needle+'d.stopGeneration=sAuxStopGeneration.load(std::memory_order_acquire);'
if replacement not in j:
    if j.count(needle)!=1: raise RuntimeError('15Z AB7 aux diag snapshot anchor missing/non-unique')
    j=j.replace(needle,replacement,1)

old_restart='''      sRestartAdvertisingPending.store(false,std::memory_order_release);\n      NimBLEDevice::startAdvertising();'''
new_restart='''      NimBLEDevice::startAdvertising();\n      if(NimBLEDevice::getAdvertising() && NimBLEDevice::getAdvertising()->isAdvertising())\n        sRestartAdvertisingPending.store(false,std::memory_order_release);'''
if old_restart in j: j=j.replace(old_restart,new_restart,1)
elif new_restart not in j: raise RuntimeError('15Z AB7 advertising retry anchor missing/non-unique')

old_state='static std::atomic<uint32_t> gTls15zGeneration{0}, gTls15zAuxGenerationBefore{0}, gTls15zAuxGenerationAfter{0};'
new_state='static std::atomic<uint32_t> gTls15zGeneration{0}, gTls15zAuxGenerationBefore{0}, gTls15zAuxGenerationAfter{0}, gTls15zStopGenerationBefore{0}, gTls15zStopGenerationAfter{0};'
if old_state in p: p=p.replace(old_state,new_state,1)
elif 'gTls15zStopGenerationBefore' not in p: raise RuntimeError('15Z AB7 TLS state anchor missing')

p=p.replace('gTls15zSlotReady','gTls15zSlotReadyPreTls')
p=p.replace('tls15z_slot_ready','tls15z_slot_ready_pre_tls')
p=p.replace('9.36.7.15Z-MEMORY-RELIEF-AB6','9.36.7.15Z-MEMORY-RELIEF-AB7')

old_before='const JkBleAuxMemoryDiag tls15zAuxBefore=jkBleProxyAuxMemoryDiag(); gTls15zAuxGenerationBefore.store(tls15zAuxBefore.generation);'
new_before=old_before+' gTls15zStopGenerationBefore.store(tls15zAuxBefore.stopGeneration);'
if old_before in p and new_before not in p: p=p.replace(old_before,new_before,1)
elif new_before not in p: raise RuntimeError('15Z AB7 before provenance anchor missing')
old_after='const JkBleAuxMemoryDiag tls15zAuxAfter=jkBleProxyAuxMemoryDiag(); gTls15zAuxGenerationAfter.store(tls15zAuxAfter.generation);'
new_after=old_after+' gTls15zStopGenerationAfter.store(tls15zAuxAfter.stopGeneration);'
if old_after in p and new_after not in p: p=p.replace(old_after,new_after,1)
elif new_after not in p: raise RuntimeError('15Z AB7 after provenance anchor missing')
old_obs='const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter.afterStopFree!=0;'
new_obs='const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter.stopGeneration!=tls15zAuxBefore.stopGeneration;'
if old_obs in p: p=p.replace(old_obs,new_obs,1)
elif new_obs not in p: raise RuntimeError('15Z AB7 stop provenance expression missing')

json_anchor='\\"tls15z_aux_generation_before\\":"+String(gTls15zAuxGenerationBefore.load())+",\\"tls15z_aux_generation_after\\":"+String(gTls15zAuxGenerationAfter.load())+",'
json_new=json_anchor+'\\"tls15z_stop_generation_before\\":"+String(gTls15zStopGenerationBefore.load())+",\\"tls15z_stop_generation_after\\":"+String(gTls15zStopGenerationAfter.load())+",'
if json_anchor in p and json_new not in p: p=p.replace(json_anchor,json_new,1)
elif json_new not in p: raise RuntimeError('15Z AB7 JSON provenance anchor missing')

# Composition/safety invariants: fail the build if any old dangerous form survives.
# These regexes intentionally use normal regex escapes (single backslashes in raw strings).
def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
code=strip_cpp_comments(p+'\n'+j)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15Z AB7 security invariant: executable setInsecure()')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15Z AB7 security invariant: executable VERIFY_NONE')
if 'tls15zAuxAfter.afterStopFree!=0' in p: raise RuntimeError('15Z AB7 provenance invariant: heap value used as stop proof')
if old_restart in j: raise RuntimeError('15Z AB7 liveness invariant: restart token consumed before confirmation')
if 'NimBLEDevice::deinit' in code: raise RuntimeError('15Z AB7 lifecycle invariant: live NimBLE deinit forbidden')
for x in ('stopGeneration','sAuxStopGeneration','tls15z_stop_generation_before','tls15z_stop_generation_after','tls15z_slot_ready_pre_tls','9.36.7.15Z-MEMORY-RELIEF-AB7'):
    if x not in h+j+p: raise RuntimeError('15Z AB7 composition invariant missing: '+x)

jkh.write_text(h,encoding='utf-8'); jkc.write_text(j,encoding='utf-8'); cpp.write_text(p,encoding='utf-8')
print('[15Z-AB7] explicit stop provenance + confirmed advertising restart + fail-hard composition applied')
