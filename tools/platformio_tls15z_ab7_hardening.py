#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# 15Z AB7 hardening runs after AB6. It changes only BLE arbitration/provenance
# and diagnostics; TLS verification remains fail-closed.
proj=Path(env['PROJECT_DIR'])
jkh=proj/'include'/'jk_ble_proxy.h'; jkc=proj/'src'/'jk_ble_proxy.cpp'; cpp=proj/'src'/'powerstream_api.cpp'
h=jkh.read_text(encoding='utf-8'); j=jkc.read_text(encoding='utf-8'); p=cpp.read_text(encoding='utf-8')

old='''  uint32_t afterDecisionFree=0, afterDecisionLargest=0;\n  uint32_t generation=0;'''
new='''  uint32_t afterDecisionFree=0, afterDecisionLargest=0;\n  uint32_t generation=0;\n  uint32_t stopGeneration=0;'''
stop_member='uint32_t stopGeneration=0;'
stop_count=h.count(stop_member)
if stop_count==0:
    if h.count(old)!=1: raise RuntimeError('15Z AB7 header provenance anchor missing/non-unique')
    h=h.replace(old,new,1)
elif stop_count!=1:
    raise RuntimeError(f'15Z AB7 header provenance cardinality violation: stopGeneration count={stop_count}')

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

# Idempotent canonicalization across USB/OTA and repeated pre-script passes.
p=re.sub(r'gTls15zSlotReady(?:PreTls)*', 'gTls15zSlotReadyPreTls', p)
p=re.sub(r'tls15z_slot_ready(?:_pre_tls)*', 'tls15z_slot_ready_pre_tls', p)
p=p.replace('9.36.7.15Z-MEMORY-RELIEF-AB6','9.36.7.15Z-MEMORY-RELIEF-AB7')

# Provenance insertion: bind to the semantic snapshot declaration, not the exact
# formatting produced by AB6. This keeps clean-build composition deterministic.
def add_stop_generation(text, which, dst):
    if dst in text:
        if text.count(dst) != 1: raise RuntimeError('15Z AB7 '+which+' provenance duplicated')
        return text
    pat=(r'(const\s+JkBleAuxMemoryDiag\s+tls15zAux'+which+r'\s*=\s*jkBleProxyAuxMemoryDiag\(\)\s*;'
         r'\s*gTls15zAuxGeneration'+which+r'\.store\(tls15zAux'+which+r'\.generation\)\s*;)')
    matches=list(re.finditer(pat,text))
    if len(matches)!=1: raise RuntimeError('15Z AB7 '+which.lower()+' provenance anchor missing/non-unique: '+str(len(matches)))
    m=matches[0]
    return text[:m.end()]+ ' '+dst + text[m.end():]

p=add_stop_generation(p,'Before','gTls15zStopGenerationBefore.store(tls15zAuxBefore.stopGeneration);')
p=add_stop_generation(p,'After','gTls15zStopGenerationAfter.store(tls15zAuxAfter.stopGeneration);')

old_obs='const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter.afterStopFree!=0;'
new_obs='const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter.stopGeneration!=tls15zAuxBefore.stopGeneration;'
if old_obs in p: p=p.replace(old_obs,new_obs,1)
elif new_obs not in p: raise RuntimeError('15Z AB7 stop provenance expression missing')

json_anchor='\\"tls15z_aux_generation_before\\":"+String(gTls15zAuxGenerationBefore.load())+",\\"tls15z_aux_generation_after\\":"+String(gTls15zAuxGenerationAfter.load())+",'
json_new=json_anchor+'\\"tls15z_stop_generation_before\\":"+String(gTls15zStopGenerationBefore.load())+",\\"tls15z_stop_generation_after\\":"+String(gTls15zStopGenerationAfter.load())+",'
if json_anchor in p and json_new not in p: p=p.replace(json_anchor,json_new,1)
elif json_new not in p: raise RuntimeError('15Z AB7 JSON provenance anchor missing')

def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
code=strip_cpp_comments(p+'\n'+j)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15Z AB7 security invariant: executable setInsecure()')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15Z AB7 security invariant: executable VERIFY_NONE')
if 'tls15zAuxAfter.afterStopFree!=0' in p: raise RuntimeError('15Z AB7 provenance invariant: heap value used as stop proof')
if old_restart in j: raise RuntimeError('15Z AB7 liveness invariant: restart token consumed before confirmation')
if 'NimBLEDevice::deinit' in code: raise RuntimeError('15Z AB7 lifecycle invariant: live NimBLE deinit forbidden')
if h.count(stop_member)!=1: raise RuntimeError('15Z AB7 final invariant: stopGeneration member must occur exactly once')
if re.search(r'gTls15zSlotReadyPreTlsPreTls|tls15z_slot_ready_pre_tls_pre_tls',p): raise RuntimeError('15Z AB7 idempotence invariant: repeated slot-ready suffix')
for x in ('stopGeneration','sAuxStopGeneration','tls15z_stop_generation_before','tls15z_stop_generation_after','tls15z_slot_ready_pre_tls'):
    if x not in h+j+p: raise RuntimeError('15Z AB7 composition invariant missing: '+x)
# Repeated PlatformIO pre-script passes may see downstream AB8 or 15AF provenance.
# Those are valid descendants of AB7; require exactly one recognized version,
# rather than forcing the intermediate AB7 label to be restored.
versions=('9.36.7.15Z-MEMORY-RELIEF-AB7','9.36.7.15Z-MEMORY-RELIEF-AB8','9.36.7.15AF-NO-AUX-RESERVATION')
present=[v for v in versions if v in p]
if len(present)!=1:
    raise RuntimeError('15Z AB7 provenance invariant: expected exactly one AB7-or-later provenance, got '+repr(present))

jkh.write_text(h,encoding='utf-8'); jkc.write_text(j,encoding='utf-8'); cpp.write_text(p,encoding='utf-8')
print('[15Z-AB7] explicit stop provenance + confirmed advertising restart + downstream-idempotent provenance applied')
