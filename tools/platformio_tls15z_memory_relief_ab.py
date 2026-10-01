#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# 15Z remains observation-first: no NimBLE deinit and no TLS weakening.
proj=Path(env['PROJECT_DIR'])
cpp=proj/'src'/'powerstream_api.cpp'
p=cpp.read_text(encoding='utf-8')
jkh=proj/'include'/'jk_ble_proxy.h'
jkc=proj/'src'/'jk_ble_proxy.cpp'
h=jkh.read_text(encoding='utf-8')
j=jkc.read_text(encoding='utf-8')

# Same-loop owner primitive: cloud TLS runs before jkBleProxyTick(), so a
# REQUESTED->wait API would self-block on the Arduino loop task.
decl='bool jkBleProxyReserveAuxConnectionOwner();'
if decl not in h:
    anchor='bool jkBleProxyReserveAuxConnection();'
    if h.count(anchor)!=1: raise RuntimeError('15Z JK header reservation anchor missing/non-unique')
    h=h.replace(anchor,'// Arduino-loop owner only: synchronous non-waiting reservation for same-task TLS A/B.\n'+decl+'\n'+anchor,1)
owner_impl=r'''bool jkBleProxyReserveAuxConnectionOwner(){
  if(!sInitialized.load(std::memory_order_acquire) ||
     sSafeHold.load(std::memory_order_acquire) ||
     sAppConnected.load(std::memory_order_acquire) ||
     sBmsConnected.load(std::memory_order_acquire) || bleEventsPending()) return false;
  AuxReserveState expected=AuxReserveState::IDLE;
  if(!sAuxReserveState.compare_exchange_strong(expected,AuxReserveState::PROCESSING,
                                                std::memory_order_acq_rel)) return false;
  sAuxDiagGeneration.fetch_add(1,std::memory_order_acq_rel);
  auxMemSnap(sAuxBeforeFree,sAuxBeforeLargest);
  sAuxAfterStopFree=0; sAuxAfterStopLargest=0;
  bool grant = sServer && sServer->getConnectedCount()==0;
  if(grant){
    NimBLEDevice::stopAdvertising();
    auxMemSnap(sAuxAfterStopFree,sAuxAfterStopLargest);
    grant = sServer->getConnectedCount()==0 &&
            !sAppConnected.load(std::memory_order_acquire) &&
            !sBmsConnected.load(std::memory_order_acquire) && !bleEventsPending();
  }
  auxMemSnap(sAuxAfterDecisionFree,sAuxAfterDecisionLargest);
  sAuxDiagGeneration.fetch_add(1,std::memory_order_release);
  if(grant){
    sAuxReserved.store(true,std::memory_order_release);
    sAuxReserveState.store(AuxReserveState::GRANTED,std::memory_order_release);
    return true;
  }
  sAuxReserved.store(false,std::memory_order_release);
  sAuxReserveState.store(AuxReserveState::DENIED,std::memory_order_release);
  if(sServer && sServer->getConnectedCount()==0 && !sAppConnected.load(std::memory_order_acquire))
    NimBLEDevice::startAdvertising();
  sAuxReserveState.store(AuxReserveState::IDLE,std::memory_order_release);
  return false;
}
'''
if 'bool jkBleProxyReserveAuxConnectionOwner(){' not in j:
    anchor='bool jkBleProxyReserveAuxConnection(){'
    if j.count(anchor)!=1: raise RuntimeError('15Z JK implementation reservation anchor missing/non-unique')
    j=j.replace(anchor,owner_impl+'\n'+anchor,1)
jkh.write_text(h,encoding='utf-8')
jkc.write_text(j,encoding='utf-8')

inc='#include <WiFiClientSecure.h>'
extra='''#include "jk_ble_proxy.h"\n#include "esp_heap_caps.h"'''
if extra not in p:
    if inc not in p: raise RuntimeError('15Z include anchor missing')
    p=p.replace(inc,inc+'\n'+extra,1)

anchor='static std::atomic<uint32_t> gCloudTraceJobId{0};'
state='''\n// 15Z AB3: provenance + capability-specific A/B evidence.\nstatic std::atomic<uint32_t> gTls15zGeneration{0};\nstatic std::atomic<int32_t> gTls15zAFree{-1}, gTls15zALargest{-1}, gTls15zBFree{-1}, gTls15zBLargest{-1};\nstatic std::atomic<int32_t> gTls15zDeltaFree{0}, gTls15zDeltaLargest{0};\nstatic std::atomic<int32_t> gTls15zAInternal{-1}, gTls15zAInternalLargest{-1}, gTls15zBInternal{-1}, gTls15zBInternalLargest{-1};\nstatic std::atomic<int32_t> gTls15zA8{-1}, gTls15zA8Largest{-1}, gTls15zB8{-1}, gTls15zB8Largest{-1};\nstatic std::atomic<int32_t> gTls15zADma{-1}, gTls15zADmaLargest{-1}, gTls15zBDma{-1}, gTls15zBDmaLargest{-1};\nstatic std::atomic<int32_t> gTls15zA32{-1}, gTls15zA32Largest{-1}, gTls15zB32{-1}, gTls15zB32Largest{-1};\nstatic std::atomic<int32_t> gTls15zReserved{0}, gTls15zSlotReady{0};\n'''
if 'gTls15zAFree' not in p:
    if p.count(anchor)!=1: raise RuntimeError('15Z stable state anchor missing/non-unique')
    p=p.replace(anchor,anchor+state,1)

anchor2='WiFiClientSecure client;'
probe='''const uint32_t tls15zCaps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;\n    const uint32_t tls15zGen=gTls15zGeneration.fetch_add(1)+1; (void)tls15zGen;\n    // Reset per-attempt outcome before any reservation decision: stale success cannot leak forward.\n    gTls15zReserved.store(0); gTls15zSlotReady.store(0);\n    auto tls15zFree=[](uint32_t c){ return (int32_t)heap_caps_get_free_size(c); };\n    auto tls15zLargest=[](uint32_t c){ return (int32_t)heap_caps_get_largest_free_block(c); };\n    int32_t tls15zAFree=tls15zFree(tls15zCaps), tls15zALargest=tls15zLargest(tls15zCaps);\n    gTls15zAFree.store(tls15zAFree); gTls15zALargest.store(tls15zALargest);\n    gTls15zAInternal.store(tls15zFree(MALLOC_CAP_INTERNAL)); gTls15zAInternalLargest.store(tls15zLargest(MALLOC_CAP_INTERNAL));\n    gTls15zA8.store(tls15zFree(MALLOC_CAP_8BIT)); gTls15zA8Largest.store(tls15zLargest(MALLOC_CAP_8BIT));\n    gTls15zADma.store(tls15zFree(MALLOC_CAP_DMA)); gTls15zADmaLargest.store(tls15zLargest(MALLOC_CAP_DMA));\n    gTls15zA32.store(tls15zFree(MALLOC_CAP_32BIT)); gTls15zA32Largest.store(tls15zLargest(MALLOC_CAP_32BIT));\n    bool tls15zReserved=false;\n    if (!jkBleProxyAppConnected() && !jkBleProxyBmsConnected() && !jkBleProxyEventsPending()) tls15zReserved=jkBleProxyReserveAuxConnectionOwner();\n    struct Tls15zReservationGuard { bool active; ~Tls15zReservationGuard(){ if(active) jkBleProxyReleaseAuxConnection(); } } tls15zGuard{tls15zReserved};\n    int32_t tls15zBFree=tls15zFree(tls15zCaps), tls15zBLargest=tls15zLargest(tls15zCaps);\n    gTls15zBFree.store(tls15zBFree); gTls15zBLargest.store(tls15zBLargest);\n    gTls15zBInternal.store(tls15zFree(MALLOC_CAP_INTERNAL)); gTls15zBInternalLargest.store(tls15zLargest(MALLOC_CAP_INTERNAL));\n    gTls15zB8.store(tls15zFree(MALLOC_CAP_8BIT)); gTls15zB8Largest.store(tls15zLargest(MALLOC_CAP_8BIT));\n    gTls15zBDma.store(tls15zFree(MALLOC_CAP_DMA)); gTls15zBDmaLargest.store(tls15zLargest(MALLOC_CAP_DMA));\n    gTls15zB32.store(tls15zFree(MALLOC_CAP_32BIT)); gTls15zB32Largest.store(tls15zLargest(MALLOC_CAP_32BIT));\n    gTls15zDeltaFree.store(tls15zBFree-tls15zAFree); gTls15zDeltaLargest.store(tls15zBLargest-tls15zALargest);\n    gTls15zReserved.store(tls15zReserved?1:0); gTls15zSlotReady.store(jkBleProxyAuxSlotReady()?1:0);\n    WiFiClientSecure client;'''
if 'tls15zCaps' not in p:
    if anchor2 not in p: raise RuntimeError('15Z TLS anchor missing')
    p=p.replace(anchor2,probe,1)

field='\\"heavy_owner\\":\\"'
if 'tls15z_version' not in p:
    pos=p.find(field)
    if pos<0: raise RuntimeError('15Z JSON anchor missing')
    ins=('\\"tls15z_version\\":\\"9.36.7.15Z-MEMORY-RELIEF-AB3\\",'
         '\\"tls15z_generation\\":"+String(gTls15zGeneration.load())+",'
         '\\"tls15z_a_internal8_free\\":"+String(gTls15zAFree.load())+",\\"tls15z_a_internal8_largest\\":"+String(gTls15zALargest.load())+",'
         '\\"tls15z_b_internal8_free\\":"+String(gTls15zBFree.load())+",\\"tls15z_b_internal8_largest\\":"+String(gTls15zBLargest.load())+",'
         '\\"tls15z_delta_free\\":"+String(gTls15zDeltaFree.load())+",\\"tls15z_delta_largest\\":"+String(gTls15zDeltaLargest.load())+",'
         '\\"tls15z_a_internal_free\\":"+String(gTls15zAInternal.load())+",\\"tls15z_a_internal_largest\\":"+String(gTls15zAInternalLargest.load())+",'
         '\\"tls15z_b_internal_free\\":"+String(gTls15zBInternal.load())+",\\"tls15z_b_internal_largest\\":"+String(gTls15zBInternalLargest.load())+",'
         '\\"tls15z_a_8bit_free\\":"+String(gTls15zA8.load())+",\\"tls15z_a_8bit_largest\\":"+String(gTls15zA8Largest.load())+",'
         '\\"tls15z_b_8bit_free\\":"+String(gTls15zB8.load())+",\\"tls15z_b_8bit_largest\\":"+String(gTls15zB8Largest.load())+",'
         '\\"tls15z_a_dma_free\\":"+String(gTls15zADma.load())+",\\"tls15z_a_dma_largest\\":"+String(gTls15zADmaLargest.load())+",'
         '\\"tls15z_b_dma_free\\":"+String(gTls15zBDma.load())+",\\"tls15z_b_dma_largest\\":"+String(gTls15zBDmaLargest.load())+",'
         '\\"tls15z_a_32bit_free\\":"+String(gTls15zA32.load())+",\\"tls15z_a_32bit_largest\\":"+String(gTls15zA32Largest.load())+",'
         '\\"tls15z_b_32bit_free\\":"+String(gTls15zB32.load())+",\\"tls15z_b_32bit_largest\\":"+String(gTls15zB32Largest.load())+",'
         '\\"tls15z_reserved\\":"+(gTls15zReserved.load()?"true":"false")+",\\"tls15z_slot_ready\\":"+(gTls15zSlotReady.load()?"true":"false")+",')
    p=p[:pos]+ins+p[pos:]

def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
code=strip_cpp_comments(p)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15Z safety invariant: executable setInsecure()')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15Z safety invariant: executable VERIFY_NONE')
if 'if (tls15zReserved) jkBleProxyReleaseAuxConnection();' in p: raise RuntimeError('15Z lifecycle invariant: obsolete path-local release present')
for key in ('tls15z_version','tls15z_generation','tls15z_a_internal8_free','tls15z_b_internal8_free','tls15z_a_dma_free','tls15z_b_dma_free','tls15z_reserved'):
    if p.count(key)!=1: raise RuntimeError('15Z JSON invariant failed: '+key)
for required in ('jkBleProxyReserveAuxConnectionOwner();','Tls15zReservationGuard','jkBleProxyReleaseAuxConnection();'):
    if required not in p+h+j: raise RuntimeError('15Z lifecycle invariant missing: '+required)
cpp.write_text(p,encoding='utf-8')
print('15Z AB3 installed: owner reservation + RAII + capability/provenance telemetry PASS; TLS verification unchanged')
