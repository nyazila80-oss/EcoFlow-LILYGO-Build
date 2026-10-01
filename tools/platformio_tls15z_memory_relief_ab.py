#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# 15Z is deliberately observation-first: it does not deinit NimBLE, weaken TLS,
# or change cloud request semantics. It adds lifecycle/memory evidence around a
# safe JK auxiliary reservation so hardware data can prove whether closing the
# connectable proxy window materially changes INTERNAL|8BIT headroom.
proj=Path(env['PROJECT_DIR'])
cpp=proj/'src'/'powerstream_api.cpp'
p=cpp.read_text(encoding='utf-8')

# The cloud transaction runs synchronously on the Arduino loop task, before the
# normal jkBleProxyTick() later in loop(). A worker-style REQUESTED->wait API
# would therefore self-block waiting for a later tick on this same task. Install
# a strictly owner-only, non-waiting reservation primitive into the JK module.
jkh=proj/'include'/'jk_ble_proxy.h'
jkc=proj/'src'/'jk_ble_proxy.cpp'
h=jkh.read_text(encoding='utf-8')
j=jkC=jkC if False else jkc.read_text(encoding='utf-8')
decl='bool jkBleProxyReserveAuxConnectionOwner();'
if decl not in h:
    anchor='bool jkBleProxyReserveAuxConnection();'
    if h.count(anchor)!=1: raise RuntimeError('15Z JK header reservation anchor missing/non-unique')
    h=h.replace(anchor,'// Arduino-loop owner only: synchronous non-waiting reservation for same-task TLS A/B.\n'+decl+'\n'+anchor,1)
owner_impl=r'''bool jkBleProxyReserveAuxConnectionOwner(){
  // This API is intentionally synchronous and must only be called by the
  // Arduino-loop owner. It avoids REQUESTED->wait self-deadlock when TLS is
  // itself running inside powerStreamApiLoopTick() before jkBleProxyTick().
  if(!sInitialized.load(std::memory_order_acquire) ||
     sSafeHold.load(std::memory_order_acquire) ||
     sAppConnected.load(std::memory_order_acquire) ||
     sBmsConnected.load(std::memory_order_acquire) || bleEventsPending()) return false;
  AuxReserveState expected=AuxReserveState::IDLE;
  if(!sAuxReserveState.compare_exchange_strong(expected,AuxReserveState::PROCESSING,
                                                std::memory_order_acq_rel)) return false;
  sAuxDiagGeneration.fetch_add(1,std::memory_order_acq_rel); // odd: snapshot in progress
  auxMemSnap(sAuxBeforeFree,sAuxBeforeLargest);
  sAuxAfterStopFree=0; sAuxAfterStopLargest=0;
  bool grant = sServer && sServer->getConnectedCount()==0;
  if(grant){
    NimBLEDevice::stopAdvertising();
    auxMemSnap(sAuxAfterStopFree,sAuxAfterStopLargest);
    // A host callback can race the stop request. Re-check both NimBLE's live
    // connection count and the fixed callback FIFO before granting the slot.
    grant = sServer->getConnectedCount()==0 &&
            !sAppConnected.load(std::memory_order_acquire) &&
            !sBmsConnected.load(std::memory_order_acquire) && !bleEventsPending();
  }
  auxMemSnap(sAuxAfterDecisionFree,sAuxAfterDecisionLargest);
  sAuxDiagGeneration.fetch_add(1,std::memory_order_release); // even: complete
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
state='''\n// 15Z safe memory-relief A/B evidence. A=pre reservation, B=post reservation.\nstatic std::atomic<int32_t> gTls15zAFree{-1}, gTls15zALargest{-1};\nstatic std::atomic<int32_t> gTls15zBFree{-1}, gTls15zBLargest{-1};\nstatic std::atomic<int32_t> gTls15zDeltaFree{0}, gTls15zDeltaLargest{0};\nstatic std::atomic<int32_t> gTls15zReserved{0}, gTls15zSlotReady{0};\n'''
if 'gTls15zAFree' not in p:
    if p.count(anchor)!=1: raise RuntimeError('15Z stable state anchor missing/non-unique')
    p=p.replace(anchor,anchor+state,1)

# RAII is essential here. apiRequest() has many early-return paths. Declaring the
# guard before WiFiClientSecure means reverse destruction tears down HTTP/TLS
# first, then releases the BLE reservation; release only schedules advertising
# restart for the later owner tick and never calls NimBLE from a foreign task.
anchor2='WiFiClientSecure client;'
probe='''const uint32_t tls15zCaps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;\n    int32_t tls15zAFree=(int32_t)heap_caps_get_free_size(tls15zCaps);\n    int32_t tls15zALargest=(int32_t)heap_caps_get_largest_free_block(tls15zCaps);\n    gTls15zAFree.store(tls15zAFree); gTls15zALargest.store(tls15zALargest);\n    bool tls15zReserved=false;\n    if (!jkBleProxyAppConnected() && !jkBleProxyBmsConnected() && !jkBleProxyEventsPending()) {\n      tls15zReserved = jkBleProxyReserveAuxConnectionOwner();\n    }\n    struct Tls15zReservationGuard {\n      bool active;\n      ~Tls15zReservationGuard(){ if(active) jkBleProxyReleaseAuxConnection(); }\n    } tls15zGuard{tls15zReserved};\n    int32_t tls15zBFree=(int32_t)heap_caps_get_free_size(tls15zCaps);\n    int32_t tls15zBLargest=(int32_t)heap_caps_get_largest_free_block(tls15zCaps);\n    gTls15zBFree.store(tls15zBFree); gTls15zBLargest.store(tls15zBLargest);\n    gTls15zDeltaFree.store(tls15zBFree-tls15zAFree);\n    gTls15zDeltaLargest.store(tls15zBLargest-tls15zALargest);\n    gTls15zReserved.store(tls15zReserved?1:0);\n    gTls15zSlotReady.store(jkBleProxyAuxSlotReady()?1:0);\n    WiFiClientSecure client;'''
if 'tls15zCaps' not in p:
    if anchor2 not in p: raise RuntimeError('15Z TLS anchor missing')
    p=p.replace(anchor2,probe,1)

# Append 15Z evidence to existing JSON status immediately before heavy_owner.
field='\\"heavy_owner\\":\\"'
if 'tls15z_version' not in p:
    pos=p.find(field)
    if pos<0: raise RuntimeError('15Z JSON anchor missing')
    ins=('\\"tls15z_version\\":\\"9.36.7.15Z-MEMORY-RELIEF-AB2\\",'
         '\\"tls15z_a_internal_free\\":"+String(gTls15zAFree.load())+",'
         '\\"tls15z_a_internal_largest\\":"+String(gTls15zALargest.load())+",'
         '\\"tls15z_b_internal_free\\":"+String(gTls15zBFree.load())+",'
         '\\"tls15z_b_internal_largest\\":"+String(gTls15zBLargest.load())+",'
         '\\"tls15z_delta_free\\":"+String(gTls15zDeltaFree.load())+",'
         '\\"tls15z_delta_largest\\":"+String(gTls15zDeltaLargest.load())+",'
         '\\"tls15z_reserved\\":"+(gTls15zReserved.load()?"true":"false")+",'
         '\\"tls15z_slot_ready\\":"+(gTls15zSlotReady.load()?"true":"false")+",')
    p=p[:pos]+ins+p[pos:]

# Safety invariants: executable TLS verification remains mandatory. Also prove
# the obsolete explicit-release injection cannot coexist with RAII.
def strip_cpp_comments(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
code=strip_cpp_comments(p)
if re.search(r'\bsetInsecure\s*\(', code):
    raise RuntimeError('15Z safety invariant: executable setInsecure()')
if 'MBEDTLS_SSL_VERIFY_NONE' in code:
    raise RuntimeError('15Z safety invariant: executable VERIFY_NONE')
if 'if (tls15zReserved) jkBleProxyReleaseAuxConnection();' in p:
    raise RuntimeError('15Z lifecycle invariant: obsolete path-local release present')
for key in ('tls15z_version','tls15z_a_internal_free','tls15z_b_internal_free','tls15z_delta_free','tls15z_reserved'):
    if p.count(key)!=1: raise RuntimeError('15Z JSON invariant failed: '+key)
for required in ('jkBleProxyReserveAuxConnectionOwner();','Tls15zReservationGuard','jkBleProxyReleaseAuxConnection();'):
    if required not in p+h+j: raise RuntimeError('15Z lifecycle invariant missing: '+required)
cpp.write_text(p,encoding='utf-8')
print('15Z AB2 installed: same-loop owner reservation + RAII release PASS; no NimBLE deinit; TLS verification unchanged')
