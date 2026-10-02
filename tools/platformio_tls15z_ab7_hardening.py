Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
jkh=root/'include'/'jk_ble_proxy.h'
jkc=root/'src'/'jk_ble_proxy.cpp'
cpp=root/'src'/'powerstream_api.cpp'
h=jkh.read_text(encoding='utf-8'); j=jkc.read_text(encoding='utf-8'); p=cpp.read_text(encoding='utf-8')

# AB7 hardening: add explicit stop-generation provenance. This script composes
# with the immediately preceding AB6 generator and later AB8/15AF/15AG scripts.
stop_member='uint32_t stopGeneration=0;'
if stop_member not in h:
    anchor='uint32_t generation=0;'
    if h.count(anchor)!=1: raise RuntimeError('15Z AB7 stopGeneration header anchor missing/non-unique')
    h=h.replace(anchor,anchor+'\n  '+stop_member,1)
elif h.count(stop_member)!=1:
    raise RuntimeError('15Z AB7 stopGeneration member duplicated')

if 'sAuxStopGeneration' not in j:
    anchor='static std::atomic<uint32_t> sAuxGeneration{0};'
    if anchor in j: j=j.replace(anchor,anchor+'\nstatic std::atomic<uint32_t> sAuxStopGeneration{0};',1)
    else: raise RuntimeError('15Z AB7 aux stop generation anchor missing')

old='out.generation=sAuxGeneration.load(std::memory_order_relaxed);'
new=old+'\n  out.stopGeneration=sAuxStopGeneration.load(std::memory_order_relaxed);'
if new not in j:
    if old in j: j=j.replace(old,new,1)
    else: raise RuntimeError('15Z AB7 aux snapshot generation anchor missing')

inc='sAuxStopGeneration.fetch_add(1,std::memory_order_relaxed);'
if inc not in j:
    candidates=('sAuxGeneration.fetch_add(1,std::memory_order_relaxed);','sAuxGeneration.fetch_add(1, std::memory_order_relaxed);')
    found=[x for x in candidates if x in j]
    if len(found)!=1: raise RuntimeError('15Z AB7 stop increment anchor missing/non-unique')
    j=j.replace(found[0],found[0]+'\n  '+inc,1)

for decl in ('static std::atomic<uint32_t> gTls15zStopGenerationBefore{0};','static std::atomic<uint32_t> gTls15zStopGenerationAfter{0};'):
    if decl not in p:
        anchor='static std::atomic<uint32_t> gTls15zAuxGenerationAfter{0};'
        if anchor not in p: raise RuntimeError('15Z AB7 powerstream provenance declaration anchor missing')
        p=p.replace(anchor,anchor+'\n'+decl,1)

# Keep the exact proven AB6 source oracle expected by host_sim_15z_memory_relief.
old_obs='const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter.afterStopFree!=0;'
new_obs='const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter.stopGeneration!=tls15zAuxBefore.stopGeneration;'
if old_obs in p: p=p.replace(old_obs,new_obs,1)
elif new_obs not in p: raise RuntimeError('15Z AB7 stop provenance expression missing')

json_anchor='\\"tls15z_aux_generation_before\\":"+String(gTls15zAuxGenerationBefore.load())+",\\"tls15z_aux_generation_after\\":"+String(gTls15zAuxGenerationAfter.load())+",'
json_new=json_anchor+'\\"tls15z_stop_generation_before\\":"+String(gTls15zStopGenerationBefore.load())+",\\"tls15z_stop_generation_after\\":"+String(gTls15zStopGenerationAfter.load())+",'
if json_anchor in p and json_new not in p: p=p.replace(json_anchor,json_new,1)
elif json_new not in p: raise RuntimeError('15Z AB7 JSON provenance anchor missing')

# Fresh pass: AB6 runs immediately before AB7, so promote AB6 -> AB7 here.
# Repeated pass: preserve exactly one downstream provenance without downgrade.
versions=('9.36.7.15Z-MEMORY-RELIEF-AB6','9.36.7.15Z-MEMORY-RELIEF-AB7','9.36.7.15Z-MEMORY-RELIEF-AB8','9.36.7.15AF-NO-AUX-RESERVATION','9.36.7.15AG-TLS-PEAK-FIX')
present=[v for v in versions if v in p]
if present==['9.36.7.15Z-MEMORY-RELIEF-AB6']:
    p=p.replace('9.36.7.15Z-MEMORY-RELIEF-AB6','9.36.7.15Z-MEMORY-RELIEF-AB7',1)
    present=['9.36.7.15Z-MEMORY-RELIEF-AB7']
if len(present)!=1:
    raise RuntimeError('15Z AB7 provenance invariant: expected exactly one AB6/AB7-or-later provenance, got '+repr(present))

def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
code=strip_cpp_comments(p+'\n'+j)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15Z AB7 security invariant: executable setInsecure()')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15Z AB7 security invariant: executable VERIFY_NONE')
if 'tls15zAuxAfter.afterStopFree!=0' in p: raise RuntimeError('15Z AB7 provenance invariant: heap value used as stop proof')
if 'NimBLEDevice::deinit' in code: raise RuntimeError('15Z AB7 lifecycle invariant: live NimBLE deinit forbidden')
if h.count(stop_member)!=1: raise RuntimeError('15Z AB7 final invariant: stopGeneration member must occur exactly once')
if re.search(r'gTls15zSlotReadyPreTlsPreTls|tls15z_slot_ready_pre_tls_pre_tls',p): raise RuntimeError('15Z AB7 idempotence invariant: repeated slot-ready suffix')
for x in ('stopGeneration','sAuxStopGeneration','tls15z_stop_generation_before','tls15z_stop_generation_after','tls15z_slot_ready_pre_tls'):
    if x not in h+j+p: raise RuntimeError('15Z AB7 composition invariant missing: '+x)

jkh.write_text(h,encoding='utf-8'); jkc.write_text(j,encoding='utf-8'); cpp.write_text(p,encoding='utf-8')
print('[15Z-AB7] explicit stop provenance + fresh-AB6/repeated-descendant composition applied')
