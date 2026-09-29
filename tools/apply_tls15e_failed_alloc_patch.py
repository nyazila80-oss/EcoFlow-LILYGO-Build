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

# 15E observes allocator failure without changing TLS buffers, BLE, CAN, credentials or request semantics.
rep('static std::atomic<uint32_t> gTlsInternalGetPostFree{0}, gTlsInternalGetPostLargest{0};', '''static std::atomic<uint32_t> gTlsInternalGetPostFree{0}, gTlsInternalGetPostLargest{0};
// 9.36.7.15E: capture the allocation request that actually fails while http.GET() owns the TLS window.
static std::atomic<bool> gTlsAllocWindow{false};
static std::atomic<uint32_t> gTlsFailedAllocCount{0};
static std::atomic<uint32_t> gTlsFailedAllocSize{0};
static std::atomic<uint32_t> gTlsFailedAllocCaps{0};
static std::atomic<uint32_t> gTlsFailedAllocTask{0};
static std::atomic<int32_t> gTlsAllocHookRc{-999};
static std::atomic<bool> gTlsAllocHookRegistered{false};
static void tlsFailedAllocHook(size_t requestedSize, uint32_t caps, const char*) {
  if(!gTlsAllocWindow.load(std::memory_order_relaxed)) return;
  gTlsFailedAllocCount.fetch_add(1,std::memory_order_relaxed);
  gTlsFailedAllocSize.store((uint32_t)requestedSize,std::memory_order_relaxed);
  gTlsFailedAllocCaps.store(caps,std::memory_order_relaxed);
  gTlsFailedAllocTask.store((uint32_t)(uintptr_t)xTaskGetCurrentTaskHandle(),std::memory_order_relaxed);
}
static void ensureTlsAllocHook(){
  bool expected=false;
  if(gTlsAllocHookRegistered.compare_exchange_strong(expected,true,std::memory_order_relaxed)){
    gTlsAllocHookRc.store((int32_t)heap_caps_register_failed_alloc_callback(tlsFailedAllocHook),std::memory_order_relaxed);
  }
}''','15E failed allocation hook')

rep('void powerStreamApiLoad() {\n  ApiLock lk(pdMS_TO_TICKS(1000)); if(!lk.held) return;', 'void powerStreamApiLoad() {\n  ensureTlsAllocHook();\n  ApiLock lk(pdMS_TO_TICKS(1000)); if(!lk.held) return;', 'register hook')

rep('  int httpCode=http.GET();\n  tlsMemSnap(gTlsHeapGetPost,gTlsLargestGetPost);', '''  gTlsFailedAllocCount.store(0,std::memory_order_relaxed);
  gTlsFailedAllocSize.store(0,std::memory_order_relaxed);
  gTlsFailedAllocCaps.store(0,std::memory_order_relaxed);
  gTlsFailedAllocTask.store(0,std::memory_order_relaxed);
  gTlsAllocWindow.store(true,std::memory_order_release);
  int httpCode=http.GET();
  gTlsAllocWindow.store(false,std::memory_order_release);
  tlsMemSnap(gTlsHeapGetPost,gTlsLargestGetPost);''', 'wrap TLS allocation window')

anchor=',\\"tls_internal_get_post_largest\\":"+String(gTlsInternalGetPostLargest.load())+'
extra=',\\"tls_failed_alloc_count\\":"+String(gTlsFailedAllocCount.load())+",\\"tls_failed_alloc_size\\":"+String(gTlsFailedAllocSize.load())+",\\"tls_failed_alloc_caps\\":"+String(gTlsFailedAllocCaps.load())+",\\"tls_failed_alloc_task\\":"+String(gTlsFailedAllocTask.load())+",\\"tls_alloc_hook_rc\\":"+String(gTlsAllocHookRc.load())+'
rep(anchor,anchor+extra,'status JSON 15E')

p.write_text(s,encoding='utf-8')
out=p.read_text(encoding='utf-8')
for required in ('heap_caps_register_failed_alloc_callback','gTlsAllocWindow.store(true','tls_failed_alloc_size','tls_alloc_hook_rc'):
    if required not in out: raise SystemExit('15E postcondition missing: '+required)
print('15E failed-allocation instrumentation applied deterministically')
