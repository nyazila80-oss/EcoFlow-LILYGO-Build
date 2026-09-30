#!/usr/bin/env python3
from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

# 9.36.7.15G.2: Arduino-ESP32 2.x has no WiFiClientSecure::setBufferSizes().
# Instead reclaim ONLY the disconnected cached PowerStream BLE client before a
# cloud transaction. Do not deinit NimBLE, disconnect the JK/BMS client, weaken
# certificate verification, or enable cloud writes.
if 'client.setBufferSizes(' in s:
    raise SystemExit('15G.2: unsupported WiFiClientSecure::setBufferSizes still present')
if 'client.setInsecure' in s:
    raise SystemExit('15G.2 security regression: insecure TLS present')

inc='#include "powerstream_ble_lab.h"\n'
if inc not in s:
    anchor='#include "cloud_boot_diag.h"\n'
    if s.count(anchor)!=1: raise SystemExit('15G.2 include anchor mismatch')
    s=s.replace(anchor,anchor+inc)

# Instrument the safe reclaim in the cloud worker, after exclusive heavy-owner
# acquisition has already happened in queueJob() and after WebSockets quiesce.
old='''  webCloudQuiesceBegin();
  delay(20);
  gCloudHeapBefore=ESP.getFreeHeap();
  gCloudLargestBefore=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);'''
new='''  webCloudQuiesceBegin();
  delay(20);
  // 15G.2 resource handoff: delete only an IDLE, DISCONNECTED cached
  // PowerStream BLE client. JK proxy/NimBLE host/BMS link stay alive.
  bool psBleClientReleased=false;
  const uint32_t reclaimFreeBefore=ESP.getFreeHeap();
  const uint32_t reclaimLargestBefore=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  const bool reclaimSafe=powerStreamBleLabReclaimIdleClientForCloud(psBleClientReleased);
  const uint32_t reclaimFreeAfter=ESP.getFreeHeap();
  const uint32_t reclaimLargestAfter=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  if(!reclaimSafe){
    setJobResult(false,"Cloud TLS abgebrochen: PowerStream BLE nicht sicher im Idle-Zustand");
    gCloudStackMinBytes=(uint32_t)uxTaskGetStackHighWaterMark(nullptr);
    cloudDiagMark(CLOUD_DIAG_FINISHED,gJobId.load(),-1,0,false);
    gJobRunning=false; gJobReserved=false; heavyOpRelease(HeavyOpOwner::POWERSTREAM_CLOUD);
    webCloudQuiesceEnd();
    return;
  }
  (void)psBleClientReleased;
  (void)reclaimFreeBefore; (void)reclaimLargestBefore;
  (void)reclaimFreeAfter; (void)reclaimLargestAfter;
  gCloudHeapBefore=ESP.getFreeHeap();
  gCloudLargestBefore=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);'''
if s.count(old)!=1: raise SystemExit(f'15G.2 cloud-worker anchor mismatch: {s.count(old)}')
s=s.replace(old,new)

required = [
    'WiFiClientSecure client;',
    'client.setCACert(ECOFLOW_CA_BUNDLE);',
    'static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 10240;',
    'gTlsFailedAllocSize',
    'gTlsFailedCapsLargest',
    'powerStreamBleLabReclaimIdleClientForCloud(psBleClientReleased)',
    'Cloud TLS abgebrochen: PowerStream BLE nicht sicher im Idle-Zustand',
]
for token in required:
    if token not in s:
        raise SystemExit(f'15G.2 invariant missing: {token}')

p.write_text(s,encoding='utf-8')

# Add the reclaim implementation to the BLE lab source. It is deliberately
# conservative: worker must be stopped, state must be IDLE/OFF/COOLDOWN,
# cached client must be disconnected, and no characteristic pointers may be in use.
b=Path('src/powerstream_ble_lab.cpp')
t=b.read_text(encoding='utf-8')
marker='bool powerStreamBleLabReclaimIdleClientForCloud(bool& released)'
if marker not in t:
    anchor='''static bool wifiStaEnabled(){'''
    if t.count(anchor)!=1: raise SystemExit('15G.2 BLE reclaim anchor mismatch')
    impl='''bool powerStreamBleLabReclaimIdleClientForCloud(bool& released){
  released=false;
  if(sWorkerRunning.load(std::memory_order_acquire) || sLinkUp.load(std::memory_order_acquire)) return false;
  const PsState st=sState.load(std::memory_order_acquire);
  if(st!=PsState::IDLE && st!=PsState::OFF && st!=PsState::COOLDOWN && st!=PsState::FAILED && st!=PsState::CONFIRMED) return false;
  if(!sClient) return true;
  if(sClient->isConnected()) return false;
  // No worker can dereference the cached GATT pointers under the heavy-op gate.
  sWrite=nullptr; sNotify=nullptr;
  NimBLEDevice::deleteClient(sClient);
  sClient=nullptr;
  clearNotifyQueue();
  released=true;
  return heapIntegrity();
}

'''
    t=t.replace(anchor,impl+anchor)
for token in ('sWorkerRunning.load(std::memory_order_acquire)','if(sClient->isConnected()) return false;','NimBLEDevice::deleteClient(sClient);','released=true;'):
    if token not in t: raise SystemExit('15G.2 BLE invariant missing: '+token)
b.write_text(t,encoding='utf-8')
print('15G.2 safe resource handoff applied: idle cached PS-BLE client reclaimed; JK/NimBLE host preserved')
