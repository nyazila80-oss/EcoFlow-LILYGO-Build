from pathlib import Path
import re

base=Path('tools/platformio_tls15z_memory_relief_ab.py').read_text(encoding='utf-8')
hard=Path('tools/platformio_tls15z_ab7_hardening.py').read_text(encoding='utf-8')
source=Path('src/powerstream_api.cpp').read_text(encoding='utf-8')
main=Path('src/main.cpp').read_text(encoding='utf-8')
ini=Path('platformio.ini').read_text(encoding='utf-8')

for x in ('MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT','MALLOC_CAP_INTERNAL','MALLOC_CAP_8BIT','MALLOC_CAP_DMA','MALLOC_CAP_32BIT','tls15z_generation','tls15z_outcome','jkBleProxyReserveAuxConnectionOwner()','Tls15zReservationGuard'):
    assert x in base,x
assert main.index('powerStreamApiLoopTick();') < main.index('jkBleProxyTick();')
assert ini.index('platformio_tls15z_memory_relief_ab.py') < ini.index('platformio_tls15z_ab7_hardening.py')
assert '[env:lilygo_tcan485_ota]' in ini and 'extends = env:lilygo_tcan485' in ini

# Base owner reservation remains synchronous/non-waiting and fail-closed.
owner_start=base.index("owner_impl=r'''"); owner_end=base.index("'''",owner_start+len("owner_impl=r'''")); owner=base[owner_start:owner_end]
assert 'AuxReserveState expected=AuxReserveState::IDLE;' in owner and 'AuxReserveState::PROCESSING' in owner
assert 'AuxReserveState::REQUESTED' not in owner and 'NimBLEDevice::stopAdvertising();' in owner
assert owner.count('sServer->getConnectedCount()==0') >= 2 and '!bleEventsPending()' in owner
assert 'sRestartAdvertisingPending.store(true' in owner
assert 'NimBLEDevice::startAdvertising();' not in owner

# Both failed reservation mechanisms defer restart to the owner.
worker_start=base.index("worker_denied='''"); worker_end=base.index("'''",worker_start+len("worker_denied='''")); worker_old=base[worker_start:worker_end]
worker_new_start=base.index("worker_deferred='''"); worker_new_end=base.index("'''",worker_new_start+len("worker_deferred='''")); worker_new=base[worker_new_start:worker_new_end]
assert 'NimBLEDevice::startAdvertising();' in worker_old
assert 'NimBLEDevice::startAdvertising();' not in worker_new and 'sRestartAdvertisingPending.store(true' in worker_new

# AB7 explicit control-flow provenance: stop proof must be monotonic marker based,
# never inferred from a heap snapshot.
for x in ('uint32_t stopGeneration=0;','sAuxStopGeneration{0}','sAuxStopGeneration.fetch_add(1','tls15zAuxAfter.stopGeneration!=tls15zAuxBefore.stopGeneration','tls15z_stop_generation_before','tls15z_stop_generation_after'):
    assert x in hard,x
assert 'tls15zAuxAfter.afterStopFree!=0' not in hard
assert "if 'tls15zAuxAfter.afterStopFree!=0' in p: raise RuntimeError" in hard

# AB7 advertising liveness: pending is cleared only after confirmed active
# advertising. Failed starts therefore retain the retry token for a later tick.
assert 'NimBLEDevice::startAdvertising();' in hard
assert 'NimBLEDevice::getAdvertising()->isAdvertising()' in hard
start=hard.index('NimBLEDevice::startAdvertising();')
confirm=hard.index('isAdvertising()',start)
clear=hard.index('sRestartAdvertisingPending.store(false',confirm)
assert start < confirm < clear
old_clear='sRestartAdvertisingPending.store(false,std::memory_order_release);\\n      NimBLEDevice::startAdvertising();'
assert old_clear in hard  # fail-hard replacement anchor
assert "if old_restart in j: raise RuntimeError" in hard

# Slot telemetry is explicitly pre-TLS; it is not a release/liveness proof.
assert "p=p.replace('gTls15zSlotReady','gTls15zSlotReadyPreTls')" in hard
assert "p=p.replace('tls15z_slot_ready','tls15z_slot_ready_pre_tls')" in hard
assert '9.36.7.15Z-MEMORY-RELIEF-AB7' in hard

# Composition is fail-hard and USB/OTA share the same inherited pre-script chain.
for msg in ('header provenance anchor','source provenance declaration anchor','owner stop marker anchor','advertising retry anchor','before provenance anchor','after provenance anchor','stop provenance expression','JSON provenance anchor'):
    assert msg in hard,msg

# Lifecycle/security invariants remain unchanged.
assert 'Tls15zReservationGuard' in base
assert '~Tls15zReservationGuard(){ if(active) jkBleProxyReleaseAuxConnection(); }' in base
assert 'if (tls15zReserved) jkBleProxyReleaseAuxConnection();' not in base

def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
source_code=strip_cpp_comments(source); hard_code=strip_cpp_comments(hard)
assert not re.search(r'\bsetInsecure\s*\(',source_code)
assert 'MBEDTLS_SSL_VERIFY_NONE' not in source_code
assert "security invariant: executable setInsecure()" in hard
assert "security invariant: executable VERIFY_NONE" in hard
assert 'NimBLEDevice::deinit' not in hard_code

print('15Z AB7 FMEA regression PASS: explicit stop provenance, retry-safe advertising liveness, serialized DENIED paths, USB/OTA composition, TLS security')
