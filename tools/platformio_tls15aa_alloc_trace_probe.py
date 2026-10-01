#!/usr/bin/env python3
from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

anchor='static std::atomic<int32_t> gTlsAllocHookRc{-999};'
state=r'''
// 9.36.7.15AA: bounded, allocation-free chronology of TLS failed allocations.
// Keep this diagnostic-only: the callback must never allocate, log, or weaken TLS.
static constexpr uint32_t TLS15AA_FAIL_SLOTS=8;
static std::atomic<uint32_t> gTls15aaFailSeq{0};
static std::atomic<uint32_t> gTls15aaSize[TLS15AA_FAIL_SLOTS];
static std::atomic<uint32_t> gTls15aaCaps[TLS15AA_FAIL_SLOTS];
static std::atomic<uint32_t> gTls15aaInternalFree[TLS15AA_FAIL_SLOTS];
static std::atomic<uint32_t> gTls15aaInternalLargest[TLS15AA_FAIL_SLOTS];
'''
if 'gTls15aaFailSeq' not in s:
    if s.count(anchor)!=1: raise RuntimeError('15AA state anchor missing/non-unique')
    s=s.replace(anchor,anchor+state,1)

old='''  gTlsFailedAllocCount.fetch_add(1,std::memory_order_relaxed);\n  gTlsFailedAllocSize.store((uint32_t)requestedSize,std::memory_order_relaxed);'''
new='''  const uint32_t seq=gTls15aaFailSeq.fetch_add(1,std::memory_order_relaxed);\n  if(seq<TLS15AA_FAIL_SLOTS){\n    gTls15aaSize[seq].store((uint32_t)requestedSize,std::memory_order_relaxed);\n    gTls15aaCaps[seq].store(caps,std::memory_order_relaxed);\n    gTls15aaInternalFree[seq].store((uint32_t)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),std::memory_order_relaxed);\n    gTls15aaInternalLargest[seq].store((uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),std::memory_order_relaxed);\n  }\n  gTlsFailedAllocCount.fetch_add(1,std::memory_order_relaxed);\n  gTlsFailedAllocSize.store((uint32_t)requestedSize,std::memory_order_relaxed);'''
if old in s:
    if s.count(old)!=1: raise RuntimeError('15AA callback anchor non-unique')
    s=s.replace(old,new,1)
elif 'const uint32_t seq=gTls15aaFailSeq.fetch_add' not in s:
    raise RuntimeError('15AA callback anchor missing')

old_reset='''    gTlsFailedAllocCount.store(0,std::memory_order_relaxed);\n    gTlsFailedAllocSize.store(0,std::memory_order_relaxed);'''
new_reset='''    gTls15aaFailSeq.store(0,std::memory_order_relaxed);\n    for(uint32_t i=0;i<TLS15AA_FAIL_SLOTS;i++){\n      gTls15aaSize[i].store(0,std::memory_order_relaxed); gTls15aaCaps[i].store(0,std::memory_order_relaxed);\n      gTls15aaInternalFree[i].store(0,std::memory_order_relaxed); gTls15aaInternalLargest[i].store(0,std::memory_order_relaxed);\n    }\n    gTlsFailedAllocCount.store(0,std::memory_order_relaxed);\n    gTlsFailedAllocSize.store(0,std::memory_order_relaxed);'''
if old_reset in s:
    if s.count(old_reset)!=1: raise RuntimeError('15AA reset anchor non-unique')
    s=s.replace(old_reset,new_reset,1)
elif 'gTls15aaFailSeq.store(0' not in s:
    raise RuntimeError('15AA reset anchor missing')

# Append compact fixed-size arrays next to existing failed-allocation diagnostics.
needle='\\"tls_failed_alloc_count\\":"+String(gTlsFailedAllocCount.load())+'
if 'tls15aa_fail_seq' not in s:
    pos=s.find(needle)
    if pos<0: raise RuntimeError('15AA JSON anchor missing')
    fields='\\"tls15aa_version\\":\\"9.36.7.15AA-TLS-ALLOC-TRACE\\",\\"tls15aa_fail_seq\\":"+String(gTls15aaFailSeq.load())+",\\"tls15aa_size\\":["+String(gTls15aaSize[0].load())+","+String(gTls15aaSize[1].load())+","+String(gTls15aaSize[2].load())+","+String(gTls15aaSize[3].load())+","+String(gTls15aaSize[4].load())+","+String(gTls15aaSize[5].load())+","+String(gTls15aaSize[6].load())+","+String(gTls15aaSize[7].load())+"],\\"tls15aa_caps\\":["+String(gTls15aaCaps[0].load())+","+String(gTls15aaCaps[1].load())+","+String(gTls15aaCaps[2].load())+","+String(gTls15aaCaps[3].load())+","+String(gTls15aaCaps[4].load())+","+String(gTls15aaCaps[5].load())+","+String(gTls15aaCaps[6].load())+","+String(gTls15aaCaps[7].load())+"],\\"tls15aa_internal_free\\":["+String(gTls15aaInternalFree[0].load())+","+String(gTls15aaInternalFree[1].load())+","+String(gTls15aaInternalFree[2].load())+","+String(gTls15aaInternalFree[3].load())+","+String(gTls15aaInternalFree[4].load())+","+String(gTls15aaInternalFree[5].load())+","+String(gTls15aaInternalFree[6].load())+","+String(gTls15aaInternalFree[7].load())+"],\\"tls15aa_internal_largest\\":["+String(gTls15aaInternalLargest[0].load())+","+String(gTls15aaInternalLargest[1].load())+","+String(gTls15aaInternalLargest[2].load())+","+String(gTls15aaInternalLargest[3].load())+","+String(gTls15aaInternalLargest[4].load())+","+String(gTls15aaInternalLargest[5].load())+","+String(gTls15aaInternalLargest[6].load())+","+String(gTls15aaInternalLargest[7].load())+"],'+
    s=s[:pos]+fields+s[pos:]

# AB8 was disproved on hardware when the proxy was not initialized. Avoid trying
# to reserve an auxiliary BLE slot in that state; preserve behavior if initialized.
old_ab='''    if(!jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
new_ab='''    if(gTls15zAdmInitialized.load()==1 && !jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
if old_ab in s:
    if s.count(old_ab)!=1: raise RuntimeError('15AA AB8 anchor non-unique')
    s=s.replace(old_ab,new_ab,1)
elif new_ab not in s:
    raise RuntimeError('15AA AB8 anchor missing')

# Security invariants.
import re
def strip_comments(x): return re.sub(r'//[^\n]*|/\*.*?\*/','',x,flags=re.S)
code=strip_comments(s)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AA security invariant: setInsecure')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AA security invariant: VERIFY_NONE')
for req in ('TLS15AA_FAIL_SLOTS=8','gTls15aaFailSeq.fetch_add','tls15aa_internal_largest','gTls15zAdmInitialized.load()==1'):
    if req not in s: raise RuntimeError('15AA postcondition missing: '+req)

p.write_text(s,encoding='utf-8')
print('15AA TLS allocation chronology probe applied; AB8 uninitialized bypass + security invariants PASS')
