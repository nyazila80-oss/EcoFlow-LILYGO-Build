Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
jkh=root/'include'/'jk_ble_proxy.h'
jkc=root/'src'/'jk_ble_proxy.cpp'
cpp=root/'src'/'powerstream_api.cpp'
h=jkh.read_text(encoding='utf-8'); j=jkc.read_text(encoding='utf-8'); p=cpp.read_text(encoding='utf-8')

# AB7 hardening: add explicit stop-generation provenance. Compose with both the
# legacy sAuxGeneration snapshot and current AB6 seqlock (sAuxDiagGeneration/2).
stop_member='uint32_t stopGeneration=0;'
if stop_member not in h:
    anchor='uint32_t generation=0;'
    if h.count(anchor)!=1: raise RuntimeError('15Z AB7 stopGeneration header anchor missing/non-unique')
    h=h.replace(anchor,anchor+'\n  '+stop_member,1)
elif h.count(stop_member)!=1:
    raise RuntimeError('15Z AB7 stopGeneration member duplicated')

if 'sAuxStopGeneration' not in j:
    old_anchor='static std::atomic<uint32_t> sAuxGeneration{0};'
    current_anchor='sAuxDiagGeneration{0};'
    if old_anchor in j:
        j=j.replace(old_anchor,old_anchor+'\nstatic std::atomic<uint32_t> sAuxStopGeneration{0};',1)
    elif j.count(current_anchor)==1:
        line_end=j.find('\n',j.index(current_anchor))
        if line_end<0: raise RuntimeError('15Z AB7 aux declaration line end missing')
        j=j[:line_end+1]+'static std::atomic<uint32_t> sAuxStopGeneration{0};\n'+j[line_end+1:]
    else:
        raise RuntimeError('15Z AB7 aux stop generation anchor missing/non-unique')

stop_snap='d.stopGeneration=sAuxStopGeneration.load(std::memory_order_relaxed);'
legacy_stop_snap='out.stopGeneration=sAuxStopGeneration.load(std::memory_order_relaxed);'
if stop_snap not in j and legacy_stop_snap not in j:
    current_re=re.compile(r'if\s*\(\s*before\s*==\s*after\s*\)\s*\{\s*d\.generation\s*=\s*after\s*/\s*2U\s*;\s*return\s+d\s*;\s*\}')
    matches=list(current_re.finditer(j))
    if len(matches)==1:
        compact='if(before==after){d.generation=after/2U;d.stopGeneration=sAuxStopGeneration.load(std::memory_order_relaxed);return d;}'
        j=j[:matches[0].start()]+compact+j[matches[0].end():]
    elif len(matches)>1: raise RuntimeError('15Z AB7 aux snapshot generation anchor non-unique')
    else:
        legacy_re=re.compile(r'out\.generation\s*=\s*sAuxGeneration\.load\(std::memory_order_relaxed\)\s*;')
        legacy=list(legacy_re.finditer(j))
        if len(legacy)==1:
            m=legacy[0]; j=j[:m.end()]+'\n  '+legacy_stop_snap+j[m.end():]
        elif len(legacy)>1: raise RuntimeError('15Z AB7 legacy aux snapshot generation anchor non-unique')
        else: raise RuntimeError('15Z AB7 aux snapshot generation anchor missing; seqlock=%s generation=%s' % ('sAuxDiagGeneration.load' in j,'d.generation' in j))

inc='sAuxStopGeneration.fetch_add(1,std::memory_order_relaxed);'
if inc not in j:
    owner_start='bool jkBleProxyReserveAuxConnectionOwner(){'; owner_end='bool jkBleProxyReserveAuxConnection(){'
    if j.count(owner_start)!=1 or j.count(owner_end)!=1: raise RuntimeError('15Z AB7 owner reservation function boundary missing/non-unique')
    a=j.index(owner_start); b=j.index(owner_end,a+len(owner_start)); owner=j[a:b]
    stop_re=re.compile(r'NimBLEDevice::stopAdvertising\s*\(\s*\)\s*;'); stops=list(stop_re.finditer(owner))
    if len(stops)!=1: raise RuntimeError('15Z AB7 owner stopAdvertising anchor missing/non-unique; owner=%d global=%d' % (len(stops),len(list(stop_re.finditer(j)))))
    mm=stops[0]; owner=owner[:mm.end()]+'\n    '+inc+owner[mm.end():]; j=j[:a]+owner+j[b:]

stop_decls=('static std::atomic<uint32_t> gTls15zStopGenerationBefore{0};','static std::atomic<uint32_t> gTls15zStopGenerationAfter{0};')
missing=[decl for decl in stop_decls if decl not in p]
if missing:
    decl_re=re.compile(r'^static\s+std::atomic<uint32_t>[^\n;]*(?:;[^\n;]*)*gTls15zAuxGenerationAfter\{0\}[^\n]*;\s*$',re.M)
    decl_matches=list(decl_re.finditer(p))
    if len(decl_matches)!=1: raise RuntimeError('15Z AB7 powerstream provenance declaration anchor missing/non-unique; matches=%d' % len(decl_matches))
    mm=decl_matches[0]; p=p[:mm.end()]+'\n'+'\n'.join(missing)+p[mm.end():]
for decl in stop_decls:
    if p.count(decl)!=1: raise RuntimeError('15Z AB7 powerstream provenance declaration duplicated/missing: '+decl)

old_obs='const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter.afterStopFree!=0;'
new_obs='const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter.stopGeneration!=tls15zAuxBefore.stopGeneration;'
if old_obs in p: p=p.replace(old_obs,new_obs,1)
elif new_obs not in p: raise RuntimeError('15Z AB7 stop provenance expression missing')

json_anchor='\\"tls15z_aux_generation_before\\":"+String(gTls15zAuxGenerationBefore.load())+",\\"tls15z_aux_generation_after\\":"+String(gTls15zAuxGenerationAfter.load())+",'
json_new=json_anchor+'\\"tls15z_stop_generation_before\\":"+String(gTls15zStopGenerationBefore.load())+",\\"tls15z_stop_generation_after\\":"+String(gTls15zStopGenerationAfter.load())+",'
if json_anchor in p and json_new not in p: p=p.replace(json_anchor,json_new,1)
elif json_new not in p: raise RuntimeError('15Z AB7 JSON provenance anchor missing')

# Validate exactly one canonical tls15z_version value. AB7 may run on a source
# that already contains a later, security-preserving descendant in the same
# 15Z->15AN diagnostic lineage. Only AB6 is promoted by this script; later
# versions are accepted as already downstream and are never rewritten backwards.
version_re=re.compile(r'tls15z_version\\\":\\\"([^\\\"]+)')
vm=version_re.findall(p)
if len(vm)!=1: raise RuntimeError('15Z AB7 provenance invariant: tls15z_version missing/non-unique: '+repr(vm))
if vm[0]=='9.36.7.15Z-MEMORY-RELIEF-AB6':
    p=p.replace('tls15z_version\\\":\\\"9.36.7.15Z-MEMORY-RELIEF-AB6','tls15z_version\\\":\\\"9.36.7.15Z-MEMORY-RELIEF-AB7',1)
else:
    allowed_exact={
        '9.36.7.15Z-MEMORY-RELIEF-AB7',
        '9.36.7.15Z-MEMORY-RELIEF-AB8',
        '9.36.7.15AF-NO-AUX-RESERVATION',
        '9.36.7.15AG-TLS-PEAK-FIX',
        '9.36.7.15AH-EARLY-TLS-HANDSHAKE',
        '9.36.7.15AI-PS-BLE-RECLAIM-DIAG',
        '9.36.7.15AK-TLS-ALLOC-PEAK-DIAG',
        '9.36.7.15AL-TLS-DYNAMIC-BUFFER-FIX',
        '9.36.7.15AM-PREFLIGHT-AB-24K',
        '9.36.7.15AN-TLS-INTERNAL8-FIX',
    }
    if vm[0] not in allowed_exact:
        raise RuntimeError('15Z AB7 provenance invariant: unexpected tls15z_version '+vm[0])

def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
code=strip_cpp_comments(p+'\n'+j)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15Z AB7 security invariant: executable setInsecure()')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15Z AB7 security invariant: executable VERIFY_NONE')
if 'tls15zAuxAfter.afterStopFree!=0' in p: raise RuntimeError('15Z AB7 provenance invariant: heap value used as stop proof')
if 'NimBLEDevice::deinit' in code: raise RuntimeError('15Z AB7 lifecycle invariant: live NimBLE deinit forbidden')
if h.count(stop_member)!=1: raise RuntimeError('15Z AB7 final invariant: stopGeneration member must occur exactly once')
if re.search(r'gTls15zSlotReadyPreTlsPreTls|tls15z_slot_ready_pre_tls_pre_tls',p): raise RuntimeError('15Z AB7 idempotence invariant: repeated slot-ready suffix')
for x in ('stopGeneration','sAuxStopGeneration','tls15z_stop_generation_before','tls15z_stop_generation_after','tls15z_slot_ready'):
    if x not in h+j+p: raise RuntimeError('15Z AB7 composition invariant missing: '+x)

jkh.write_text(h,encoding='utf-8'); jkc.write_text(j,encoding='utf-8'); cpp.write_text(p,encoding='utf-8')
print('[15Z-AB7] explicit stop provenance + owner-scoped AB6 composition applied')
