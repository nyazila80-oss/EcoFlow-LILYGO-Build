#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
ble=root/'src'/'powerstream_ble_lab.cpp'
api=root/'src'/'powerstream_api.cpp'
b=ble.read_text(encoding='utf-8')
p=api.read_text(encoding='utf-8')

# 15AG solution: the PowerStream one-shot path intentionally caches its disconnected
# NimBLE client/GATT database. On this no-PSRAM ESP32 that retained client competes
# with mbedTLS for the same INTERNAL|8BIT pool. Reclaim only that idle PS client
# immediately before Cloud TLS; never deinit NimBLE and never touch the JK client.
fn='''
bool powerStreamBleLabReclaimIdleClientForCloud(bool& released){
  released=false;
  bool gate=false;
  if(!sConfigGate.compare_exchange_strong(gate,true)) return false;
  if(sWorkerRunning.load() || sLinkUp.load() || (sClient && sClient->isConnected())){
    sConfigGate.store(false);
    return false;
  }
  if(sClient){
    NimBLEDevice::deleteClient(sClient);
    sClient=nullptr; sWrite=nullptr; sNotify=nullptr;
    clearNotifyQueue();
    released=true;
  }
  sConfigGate.store(false);
  return true;
}
'''
if 'bool powerStreamBleLabReclaimIdleClientForCloud(bool& released)' not in b:
    anchor='static bool wifiStaEnabled(){'
    if b.count(anchor)!=1: raise RuntimeError('15AG BLE reclaim anchor missing/non-unique')
    b=b.replace(anchor,fn+'\n'+anchor,1)
elif b.count('bool powerStreamBleLabReclaimIdleClientForCloud(bool& released)')!=1:
    raise RuntimeError('15AG BLE reclaim function duplicated')

# Place reclaim before WiFiClientSecure construction so TLS sees the recovered
# contiguous heap. Fail closed if PS BLE is active; cloud must never race BLE.
call='''  bool psBleReleased=false;
  if(!powerStreamBleLabReclaimIdleClientForCloud(psBleReleased)){
    err="Cloud TLS blockiert: PowerStream BLE aktiv/busy";
    return false;
  }
  if(psBleReleased) vTaskDelay(pdMS_TO_TICKS(1));
  if(!heap_caps_check_integrity_all(false)){
    err="Cloud TLS blockiert: Heap-Integritaet fehlgeschlagen";
    return false;
  }
'''
anchor='''  tlsInternalSnap(gTlsInternalFreePre,gTlsInternalLargestPre);\n\n  WiFiClientSecure client;'''
if call.strip() not in p:
    if p.count(anchor)!=1: raise RuntimeError('15AG TLS reclaim call anchor missing/non-unique')
    p=p.replace(anchor,'  tlsInternalSnap(gTlsInternalFreePre,gTlsInternalLargestPre);\n\n'+call+'\n  WiFiClientSecure client;',1)

# Raise the preflight to the actual measured requirement. 15AF showed mbedTLS later
# asks for 16717 contiguous bytes after consuming roughly 18 kB during handshake;
# entering TLS below 32 kB largest8 only creates a deterministic allocation failure.
p=p.replace('static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 10240;',
            'static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 32768;')

# Provenance: preserve 15AF marker for historical diagnostics but identify solution.
p=p.replace('9.36.7.15AF-NO-AUX-RESERVATION','9.36.7.15AG-TLS-PEAK-FIX')

code=re.sub(r'//[^\n]*|/\*.*?\*/','',p+'\n'+b,flags=re.S)
for bad in ('setInsecure(', 'MBEDTLS_SSL_VERIFY_NONE'):
    if bad in code: raise RuntimeError('15AG security invariant: '+bad)
if 'setCACert(ECOFLOW_CA_BUNDLE)' not in p: raise RuntimeError('15AG CA verification missing')
if 'NimBLEDevice::deinit' in fn: raise RuntimeError('15AG must not deinit shared NimBLE host')
if 'jkBleProxy' in fn: raise RuntimeError('15AG must not manipulate JK proxy/client')
if 'NimBLEDevice::deleteClient(sClient)' not in b: raise RuntimeError('15AG idle client reclaim missing')
if 'TLS_GET_MIN_LARGEST8 = 32768' not in p: raise RuntimeError('15AG TLS admission threshold missing')
if '9.36.7.15AG-TLS-PEAK-FIX' not in p: raise RuntimeError('15AG provenance missing')

ble.write_text(b,encoding='utf-8')
api.write_text(p,encoding='utf-8')
print('[15AG] idle PowerStream BLE client reclaimed before TLS; JK/NimBLE host retained; CA verify retained')
