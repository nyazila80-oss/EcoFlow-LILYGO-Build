#!/usr/bin/env python3
from pathlib import Path
import re

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
elif s.count('static std::atomic<uint32_t> gTls15aaFailSeq{0};') != 1:
    raise RuntimeError('15AA state duplicated/malformed')

old='''  gTlsFailedAllocCount.fetch_add(1,std::memory_order_relaxed);\n  gTlsFailedAllocSize.store((uint32_t)requestedSize,std::memory_order_relaxed);'''
new='''  const uint32_t seq=gTls15aaFailSeq.fetch_add(1,std::memory_order_relaxed);\n  if(seq<TLS15AA_FAIL_SLOTS){\n    gTls15aaSize[seq].store((uint32_t)requestedSize,std::memory_order_relaxed);\n    gTls15aaCaps[seq].store(caps,std::memory_order_relaxed);\n    gTls15aaInternalFree[seq].store((uint32_t)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),std::memory_order_relaxed);\n    gTls15aaInternalLargest[seq].store((uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),std::memory_order_relaxed);\n  }\n  gTlsFailedAllocCount.fetch_add(1,std::memory_order_relaxed);\n  gTlsFailedAllocSize.store((uint32_t)requestedSize,std::memory_order_relaxed);'''
trace_marker='const uint32_t seq=gTls15aaFailSeq.fetch_add(1,std::memory_order_relaxed);'
trace_count=s.count(trace_marker)
if trace_count == 0:
    if s.count(old)!=1: raise RuntimeError('15AA callback anchor missing/non-unique')
    s=s.replace(old,new,1)
elif trace_count == 1:
    pass
else:
    raise RuntimeError('15AA callback trace duplicated')

old_reset='''    gTlsFailedAllocCount.store(0,std::memory_order_relaxed);\n    gTlsFailedAllocSize.store(0,std::memory_order_relaxed);'''
new_reset='''    gTls15aaFailSeq.store(0,std::memory_order_relaxed);\n    for(uint32_t i=0;i<TLS15AA_FAIL_SLOTS;i++){\n      gTls15aaSize[i].store(0,std::memory_order_relaxed); gTls15aaCaps[i].store(0,std::memory_order_relaxed);\n      gTls15aaInternalFree[i].store(0,std::memory_order_relaxed); gTls15aaInternalLargest[i].store(0,std::memory_order_relaxed);\n    }\n    gTlsFailedAllocCount.store(0,std::memory_order_relaxed);\n    gTlsFailedAllocSize.store(0,std::memory_order_relaxed);'''
reset_marker='gTls15aaFailSeq.store(0,std::memory_order_relaxed);'
reset_count=s.count(reset_marker)
if reset_count == 0:
    if s.count(old_reset)!=1: raise RuntimeError('15AA reset anchor missing/non-unique')
    s=s.replace(old_reset,new_reset,1)
elif reset_count == 1:
    pass
else:
    raise RuntimeError('15AA reset trace duplicated')

needle='\\"tls_failed_alloc_count\\":"+String(gTlsFailedAllocCount.load())+'
json_marker='\\"tls15aa_fail_seq\\":"+String(gTls15aaFailSeq.load())+'
json_count=s.count(json_marker)
if json_count == 0:
    pos=s.find(needle)
    if pos<0: raise RuntimeError('15AA JSON anchor missing')
    def cpp_array(name):
        return '+","+'.join('String(%s[%d].load())' % (name,i) for i in range(8))
    fields=(
        '\\"tls15aa_version\\":\\"9.36.7.15AA-TLS-ALLOC-TRACE\\",'
        '\\"tls15aa_fail_seq\\":"+String(gTls15aaFailSeq.load())+",'
        '\\"tls15aa_size\\":["+'+cpp_array('gTls15aaSize')+'+"],'
        '\\"tls15aa_caps\\":["+'+cpp_array('gTls15aaCaps')+'+"],'
        '\\"tls15aa_internal_free\\":["+'+cpp_array('gTls15aaInternalFree')+'+"],'
        '\\"tls15aa_internal_largest\\":["+'+cpp_array('gTls15aaInternalLargest')+'+"],'
    )
    s=s[:pos]+fields+s[pos:]
elif json_count == 1:
    pass
else:
    raise RuntimeError('15AA JSON trace duplicated')

old_ab='''    if(!jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
new_ab='''    if(gTls15zAdmInitialized.load()==1 && !jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
if old_ab in s:
    if s.count(old_ab)!=1: raise RuntimeError('15AA AB8 anchor non-unique')
    s=s.replace(old_ab,new_ab,1)
elif s.count(new_ab)==1:
    pass
else:
    raise RuntimeError('15AA AB8 anchor missing/non-unique')

def strip_comments(x): return re.sub(r'//[^\n]*|/\*.*?\*/','',x,flags=re.S)
code=strip_comments(s)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AA security invariant: setInsecure')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AA security invariant: VERIFY_NONE')
for req in ('TLS15AA_FAIL_SLOTS=8','gTls15aaFailSeq.fetch_add','tls15aa_internal_largest','gTls15zAdmInitialized.load()==1'):
    if req not in s: raise RuntimeError('15AA postcondition missing: '+req)
if s.count(trace_marker)!=1: raise RuntimeError('15AA postcondition: callback trace count != 1')
if s.count(reset_marker)!=1: raise RuntimeError('15AA postcondition: reset trace count != 1')
if s.count(json_marker)!=1: raise RuntimeError('15AA postcondition: JSON trace count != 1')

p.write_text(s,encoding='utf-8')
print('15AA TLS allocation chronology probe applied/idempotent; AB8 bypass + security invariants PASS')
