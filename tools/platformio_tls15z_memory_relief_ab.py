#!/usr/bin/env python3
Import('env')
from pathlib import Path

# 15Z is deliberately observation-first: it does not deinit NimBLE, weaken TLS,
# or change cloud request semantics. It adds lifecycle/memory evidence around the
# already existing JK auxiliary reservation so hardware data can prove whether
# the safe relief path materially changes INTERNAL|8BIT headroom.
proj=Path(env['PROJECT_DIR'])
cpp=proj/'src'/'powerstream_api.cpp'
p=cpp.read_text(encoding='utf-8')

inc='#include <WiFiClientSecure.h>'
extra='''#include "jk_ble_proxy.h"\n#include "esp_heap_caps.h"'''
if extra not in p:
    if inc not in p: raise RuntimeError('15Z include anchor missing')
    p=p.replace(inc,inc+'\n'+extra,1)

# Add scalar diagnostic state only. No dynamic allocation. Anchor on the
# long-lived cloud trace state that exists in the base source and is preserved
# by the composed 15D..15Y pre-scripts. Do not depend on later probe-local state.
anchor='static std::atomic<uint32_t> gCloudTraceJobId{0};'
state='''\n// 15Z safe memory-relief A/B evidence. A=pre reservation, B=post reservation.\nstatic std::atomic<int32_t> gTls15zAFree{-1}, gTls15zALargest{-1};\nstatic std::atomic<int32_t> gTls15zBFree{-1}, gTls15zBLargest{-1};\nstatic std::atomic<int32_t> gTls15zDeltaFree{0}, gTls15zDeltaLargest{0};\nstatic std::atomic<int32_t> gTls15zReserved{0}, gTls15zSlotReady{0};\n'''
if 'gTls15zAFree' not in p:
    if p.count(anchor)!=1: raise RuntimeError('15Z stable state anchor missing/non-unique')
    p=p.replace(anchor,anchor+state,1)

# Instrument immediately before the existing TLS client construction. Reservation
# is only attempted when the JK proxy reports no app/BMS session and no pending
# callback transition; otherwise 15Z records A==B and leaves BLE untouched.
anchor2='WiFiClientSecure client;'
probe='''const uint32_t tls15zCaps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;\n    int32_t tls15zAFree=(int32_t)heap_caps_get_free_size(tls15zCaps);\n    int32_t tls15zALargest=(int32_t)heap_caps_get_largest_free_block(tls15zCaps);\n    gTls15zAFree.store(tls15zAFree); gTls15zALargest.store(tls15zALargest);\n    bool tls15zReserved=false;\n    if (!jkBleProxyAppConnected() && !jkBleProxyBmsConnected() && !jkBleProxyEventsPending()) {\n      tls15zReserved = jkBleProxyReserveAuxConnection();\n    }\n    delay(1);\n    int32_t tls15zBFree=(int32_t)heap_caps_get_free_size(tls15zCaps);\n    int32_t tls15zBLargest=(int32_t)heap_caps_get_largest_free_block(tls15zCaps);\n    gTls15zBFree.store(tls15zBFree); gTls15zBLargest.store(tls15zBLargest);\n    gTls15zDeltaFree.store(tls15zBFree-tls15zAFree);\n    gTls15zDeltaLargest.store(tls15zBLargest-tls15zALargest);\n    gTls15zReserved.store(tls15zReserved?1:0);\n    gTls15zSlotReady.store(jkBleProxyAuxSlotReady()?1:0);\n    WiFiClientSecure client;'''
if 'tls15zCaps' not in p:
    if anchor2 not in p: raise RuntimeError('15Z TLS anchor missing')
    p=p.replace(anchor2,probe,1)

# Always release a reservation after the HTTP transaction is ended. Existing
# resource gate remains authoritative and TLS semantics are unchanged.
anchor3='http.end();'
release='''http.end();\n    if (tls15zReserved) jkBleProxyReleaseAuxConnection();'''
if 'if (tls15zReserved) jkBleProxyReleaseAuxConnection();' not in p:
    if anchor3 not in p: raise RuntimeError('15Z http.end anchor missing')
    p=p.replace(anchor3,release,1)

# Append 15Z evidence to existing JSON status immediately before heavy_owner.
field='\\"heavy_owner\\":\\"'
if 'tls15z_version' not in p:
    pos=p.find(field)
    if pos<0: raise RuntimeError('15Z JSON anchor missing')
    ins=('\\"tls15z_version\\":\\"9.36.7.15Z-MEMORY-RELIEF-AB\\",'
         '\\"tls15z_a_internal_free\\":"+String(gTls15zAFree.load())+",'
         '\\"tls15z_a_internal_largest\\":"+String(gTls15zALargest.load())+",'
         '\\"tls15z_b_internal_free\\":"+String(gTls15zBFree.load())+",'
         '\\"tls15z_b_internal_largest\\":"+String(gTls15zBLargest.load())+",'
         '\\"tls15z_delta_free\\":"+String(gTls15zDeltaFree.load())+",'
         '\\"tls15z_delta_largest\\":"+String(gTls15zDeltaLargest.load())+",'
         '\\"tls15z_reserved\\":"+(gTls15zReserved.load()?"true":"false")+",'
         '\\"tls15z_slot_ready\\":"+(gTls15zSlotReady.load()?"true":"false")+",')
    p=p[:pos]+ins+p[pos:]

# Safety invariants: never permit diagnostic patch to introduce insecure TLS.
for forbidden in ('setInsecure(', 'MBEDTLS_SSL_VERIFY_NONE'):
    if forbidden in p: raise RuntimeError('15Z safety invariant: forbidden '+forbidden)
for key in ('tls15z_version','tls15z_a_internal_free','tls15z_b_internal_free','tls15z_delta_free','tls15z_reserved'):
    if p.count(key)!=1: raise RuntimeError('15Z JSON invariant failed: '+key)
cpp.write_text(p,encoding='utf-8')
print('15Z safe memory-relief A/B probe installed; stable composed-state anchor PASS; no NimBLE deinit; TLS verification unchanged')
