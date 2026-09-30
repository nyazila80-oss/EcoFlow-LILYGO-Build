#!/usr/bin/env python3
from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

def rep(old,new,name):
    global s
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'{name}: expected exactly one match, got {n}')
    s=s.replace(old,new)

# 15F extends the hardware-proven 15E failed-allocation probe. It remains diagnostic-only:
# no TLS buffer tuning, BLE/CAN lifecycle change, credential change or request semantic change.
rep('static std::atomic<uint32_t> gTlsInternalGetPostFree{0}, gTlsInternalGetPostLargest{0};', '''static std::atomic<uint32_t> gTlsInternalGetPostFree{0}, gTlsInternalGetPostLargest{0};
// 9.36.7.15F: capture the failed allocation and the allocator pool that had to satisfy it.
static std::atomic<bool> gTlsAllocWindow{false};
static std::atomic<uint32_t> gTlsFailedAllocCount{0};
static std::atomic<uint32_t> gTlsFailedAllocSize{0};
static std::atomic<uint32_t> gTlsFailedAllocCaps{0};
static std::atomic<uint32_t> gTlsFailedAllocTask{0};
static std::atomic<uint32_t> gTlsFailedCapsFree{0}, gTlsFailedCapsLargest{0};
static std::atomic<uint32_t> gTlsFailedInternalFree{0}, gTlsFailedInternalLargest{0};
static std::atomic<uint32_t> gTlsFailed8BitFree{0}, gTlsFailed8BitLargest{0};
static std::atomic<uint32_t> gTlsFailedDmaFree{0}, gTlsFailedDmaLargest{0};
static std::atomic<uint32_t> gTlsFailed32BitFree{0}, gTlsFailed32BitLargest{0};
static std::atomic<int32_t> gTlsAllocHookRc{-999};
static std::atomic<bool> gTlsAllocHookRegistered{false};
static void tlsFailedAllocHook(size_t requestedSize, uint32_t caps, const char*) {
  if(!gTlsAllocWindow.load(std::memory_order_relaxed)) return;
  gTlsFailedAllocCount.fetch_add(1,std::memory_order_relaxed);
  gTlsFailedAllocSize.store((uint32_t)requestedSize,std::memory_order_relaxed);
  gTlsFailedAllocCaps.store(caps,std::memory_order_relaxed);
  gTlsFailedAllocTask.store((uint32_t)(uintptr_t)xTaskGetCurrentTaskHandle(),std::memory_order_relaxed);
  // Snapshot only allocator metadata; do not allocate/log/String-build inside the failure callback.
  gTlsFailedCapsFree.store((uint32_t)heap_caps_get_free_size(caps),std::memory_order_relaxed);
  gTlsFailedCapsLargest.store((uint32_t)heap_caps_get_largest_free_block(caps),std::memory_order_relaxed);
  gTlsFailedInternalFree.store((uint32_t)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),std::memory_order_relaxed);
  gTlsFailedInternalLargest.store((uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),std::memory_order_relaxed);
  gTlsFailed8BitFree.store((uint32_t)heap_caps_get_free_size(MALLOC_CAP_8BIT),std::memory_order_relaxed);
  gTlsFailed8BitLargest.store((uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),std::memory_order_relaxed);
  gTlsFailedDmaFree.store((uint32_t)heap_caps_get_free_size(MALLOC_CAP_DMA),std::memory_order_relaxed);
  gTlsFailedDmaLargest.store((uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_DMA),std::memory_order_relaxed);
  gTlsFailed32BitFree.store((uint32_t)heap_caps_get_free_size(MALLOC_CAP_32BIT),std::memory_order_relaxed);
  gTlsFailed32BitLargest.store((uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_32BIT),std::memory_order_relaxed);
}
static void ensureTlsAllocHook(){
  bool expected=false;
  if(gTlsAllocHookRegistered.compare_exchange_strong(expected,true,std::memory_order_relaxed)){
    gTlsAllocHookRc.store((int32_t)heap_caps_register_failed_alloc_callback(tlsFailedAllocHook),std::memory_order_relaxed);
  }
}''','15F failed allocation hook')

rep('void powerStreamApiLoad() {\n  ApiLock lk(pdMS_TO_TICKS(1000)); if(!lk.held) return;', 'void powerStreamApiLoad() {\n  ensureTlsAllocHook();\n  ApiLock lk(pdMS_TO_TICKS(1000)); if(!lk.held) return;', 'register hook')

rep('  if(method=="GET") httpCode=http.GET(); else if(method=="PUT") httpCode=http.PUT(body); else {err="Interner HTTP-Methodenfehler";http.end();return false;}', '''  if(method=="GET") {
    gTlsFailedAllocCount.store(0,std::memory_order_relaxed);
    gTlsFailedAllocSize.store(0,std::memory_order_relaxed);
    gTlsFailedAllocCaps.store(0,std::memory_order_relaxed);
    gTlsFailedAllocTask.store(0,std::memory_order_relaxed);
    gTlsFailedCapsFree.store(0,std::memory_order_relaxed); gTlsFailedCapsLargest.store(0,std::memory_order_relaxed);
    gTlsFailedInternalFree.store(0,std::memory_order_relaxed); gTlsFailedInternalLargest.store(0,std::memory_order_relaxed);
    gTlsFailed8BitFree.store(0,std::memory_order_relaxed); gTlsFailed8BitLargest.store(0,std::memory_order_relaxed);
    gTlsFailedDmaFree.store(0,std::memory_order_relaxed); gTlsFailedDmaLargest.store(0,std::memory_order_relaxed);
    gTlsFailed32BitFree.store(0,std::memory_order_relaxed); gTlsFailed32BitLargest.store(0,std::memory_order_relaxed);
    gTlsAllocWindow.store(true,std::memory_order_release);
    httpCode=http.GET();
    gTlsAllocWindow.store(false,std::memory_order_release);
  } else if(method=="PUT") httpCode=http.PUT(body); else {err="Interner HTTP-Methodenfehler";http.end();return false;}''', 'wrap TLS allocation window')

anchor=',\\"tls_internal_get_post_largest\\":"+String(gTlsInternalGetPostLargest.load())+'
extra='",\\"tls_failed_alloc_count\\":"+String(gTlsFailedAllocCount.load())+",\\"tls_failed_alloc_size\\":"+String(gTlsFailedAllocSize.load())+",\\"tls_failed_alloc_caps\\":"+String(gTlsFailedAllocCaps.load())+",\\"tls_failed_alloc_task\\":"+String(gTlsFailedAllocTask.load())+",\\"tls_failed_caps_free\\":"+String(gTlsFailedCapsFree.load())+",\\"tls_failed_caps_largest\\":"+String(gTlsFailedCapsLargest.load())+",\\"tls_failed_internal_free\\":"+String(gTlsFailedInternalFree.load())+",\\"tls_failed_internal_largest\\":"+String(gTlsFailedInternalLargest.load())+",\\"tls_failed_8bit_free\\":"+String(gTlsFailed8BitFree.load())+",\\"tls_failed_8bit_largest\\":"+String(gTlsFailed8BitLargest.load())+",\\"tls_failed_dma_free\\":"+String(gTlsFailedDmaFree.load())+",\\"tls_failed_dma_largest\\":"+String(gTlsFailedDmaLargest.load())+",\\"tls_failed_32bit_free\\":"+String(gTlsFailed32BitFree.load())+",\\"tls_failed_32bit_largest\\":"+String(gTlsFailed32BitLargest.load())+",\\"tls_alloc_hook_rc\\":"+String(gTlsAllocHookRc.load())+'
rep(anchor,anchor+extra,'status JSON 15F')

p.write_text(s,encoding='utf-8')
out=p.read_text(encoding='utf-8')
for required in ('heap_caps_register_failed_alloc_callback','gTlsAllocWindow.store(true','tls_failed_alloc_size','tls_failed_caps_largest','tls_failed_internal_largest','tls_failed_dma_largest','tls_failed_32bit_largest','tls_alloc_hook_rc'):
    if required not in out: raise SystemExit('15F postcondition missing: '+required)
bad='String(gTlsInternalGetPostLargest.load())+,\\"tls_failed_alloc_count'
good='String(gTlsInternalGetPostLargest.load())+",\\"tls_failed_alloc_count\\":"+String(gTlsFailedAllocCount.load())'
if bad in out: raise SystemExit('15F malformed C++ JSON concatenation survived generator')
if good not in out: raise SystemExit('15F expected C++ JSON concatenation not generated')
print('15F failed-capability pool instrumentation applied deterministically; JSON boundary invariant PASS')
