from pathlib import Path
import re

patch=Path('tools/platformio_tls15z_memory_relief_ab.py').read_text(encoding='utf-8')
source=Path('src/powerstream_api.cpp').read_text(encoding='utf-8')
main=Path('src/main.cpp').read_text(encoding='utf-8')

for x in ('MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT','MALLOC_CAP_INTERNAL','MALLOC_CAP_8BIT','MALLOC_CAP_DMA','MALLOC_CAP_32BIT','tls15z_generation','tls15z_a_internal8_free','tls15z_b_internal8_free','tls15z_a_dma_free','tls15z_b_dma_free','jkBleProxyReserveAuxConnectionOwner()','Tls15zReservationGuard'):
    assert x in patch,x
assert main.index('powerStreamApiLoopTick();') < main.index('jkBleProxyTick();')
probe_start=patch.index("probe='''"); probe_end=patch.index("'''",probe_start+len("probe='''")); probe=patch[probe_start:probe_end]
assert 'jkBleProxyReserveAuxConnectionOwner()' in probe and 'jkBleProxyReserveAuxConnection();' not in probe
owner_start=patch.index("owner_impl=r'''"); owner_end=patch.index("'''",owner_start+len("owner_impl=r'''")); owner=patch[owner_start:owner_end]
assert 'AuxReserveState expected=AuxReserveState::IDLE;' in owner and 'AuxReserveState::PROCESSING' in owner
assert 'AuxReserveState::REQUESTED' not in owner and 'NimBLEDevice::stopAdvertising();' in owner
assert owner.count('sServer->getConnectedCount()==0') >= 2 and '!bleEventsPending()' in owner

# AB5 race/liveness gate: neither reservation mechanism may restart advertising
# inside a failed transaction. Both must defer to the Arduino-loop owner.
assert 'sRestartAdvertisingPending.store(true' in owner
assert 'NimBLEDevice::startAdvertising();' not in owner
worker_start=patch.index("worker_denied='''"); worker_end=patch.index("'''",worker_start+len("worker_denied='''")); worker_old=patch[worker_start:worker_end]
worker_new_start=patch.index("worker_deferred='''"); worker_new_end=patch.index("'''",worker_new_start+len("worker_deferred='''")); worker_new=patch[worker_new_start:worker_new_end]
assert 'NimBLEDevice::startAdvertising();' in worker_old  # exact legacy pattern being removed
assert 'NimBLEDevice::startAdvertising();' not in worker_new
assert 'sRestartAdvertisingPending.store(true' in worker_new
assert "if worker_denied in j: j=j.replace(worker_denied,worker_deferred,1)" in patch
assert "elif worker_deferred not in j: raise RuntimeError" in patch

# Main-loop restart gate must wait until deferred transitions are drained and no
# app/server connection or pending callback exists.
assert 'processDeferredTransitions();' in patch or 'processDeferredTransitions();' in Path('src/jk_ble_proxy.cpp').read_text(encoding='utf-8')
for x in ('!bleEventsPending()','!sAppConnected.load(std::memory_order_acquire)','sServer && sServer->getConnectedCount()==0'):
    assert x in patch,x
assert patch.index('!bleEventsPending()') < patch.rindex('NimBLEDevice::startAdvertising();')

assert probe.index('Tls15zReservationGuard') < probe.index('WiFiClientSecure client;')
assert '~Tls15zReservationGuard(){ if(active) jkBleProxyReleaseAuxConnection(); }' in probe
assert 'if (tls15zReserved) jkBleProxyReleaseAuxConnection();' not in patch
gen=probe.index('gTls15zGeneration.fetch_add(1)'); reset=probe.index('gTls15zReserved.store(0)'); decision=probe.index('jkBleProxyReserveAuxConnectionOwner()')
assert gen < reset < decision and 'gTls15zSlotReady.store(0)' in probe
assert probe.index('gTls15zAInternal.store') < decision < probe.index('gTls15zBInternal.store')
assert probe.index('gTls15zADma.store') < decision < probe.index('gTls15zBDma.store')
assert 'heap_caps_malloc' not in probe and 'heap_caps_free' not in probe and 'NimBLEDevice::deinit' not in probe
stable_anchor='static std::atomic<uint32_t> gCloudTraceJobId{0};'
assert source.count(stable_anchor)==1 and "anchor='static std::atomic<uint32_t> gCloudTraceJobId{0};'" in patch and "p.count(anchor)!=1" in patch

def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
source_code=strip_cpp_comments(source); patch_code=strip_cpp_comments(patch)
assert not re.search(r'\bsetInsecure\s*\(',source_code)
assert 'MBEDTLS_SSL_VERIFY_NONE' not in source_code
assert "raise RuntimeError('15Z safety invariant: executable setInsecure()')" in patch
assert "raise RuntimeError('15Z safety invariant: executable VERIFY_NONE')" in patch
assert 'NimBLEDevice::deinit' not in patch_code
assert '9.36.7.15Z-MEMORY-RELIEF-AB5' in patch
print('15Z AB5 FMEA regression PASS: both restart paths serialized, ownership, RAII, provenance, capability telemetry, TLS security')
