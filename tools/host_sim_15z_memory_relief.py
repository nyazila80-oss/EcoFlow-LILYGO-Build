from pathlib import Path
import re

base=Path('tools/platformio_tls15z_memory_relief_ab.py').read_text(encoding='utf-8')
hard=Path('tools/platformio_tls15z_ab7_hardening.py').read_text(encoding='utf-8')
ab8=Path('tools/platformio_tls15z_ab8_hardware_fix.py').read_text(encoding='utf-8')
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

# AB7 provenance oracle: verify semantics, not Python quoting/formatting.
legacy='tls15zAuxAfter.afterStopFree!=0'
new_expr='tls15zAuxAfter.stopGeneration!=tls15zAuxBefore.stopGeneration'
for x in ('uint32_t stopGeneration=0;','sAuxStopGeneration{0}','sAuxStopGeneration.fetch_add(1','tls15z_stop_generation_before','tls15z_stop_generation_after'):
    assert x in hard,x
assert re.search(r"old_obs\s*=\s*['\"]const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter\.afterStopFree!=0;['\"]",hard)
assert re.search(r"new_obs\s*=\s*['\"]const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter\.stopGeneration!=tls15zAuxBefore\.stopGeneration;['\"]",hard)
assert re.search(r"if\s+old_obs\s+in\s+p\s*:\s*p=p\.replace\(old_obs,new_obs,1\)",hard)
assert "elif new_obs not in p: raise RuntimeError('15Z AB7 stop provenance expression missing')" in hard
assert re.search(r"if\s+['\"]tls15zAuxAfter\.afterStopFree!=0['\"]\s+in\s+p\s*:\s*raise RuntimeError\(['\"]15Z AB7 provenance invariant: heap value used as stop proof['\"]\)",hard)
assert legacy != new_expr and hard.count(legacy) >= 2 and new_expr in hard

# AB7 advertising liveness: pending is cleared only after confirmed active advertising.
assert 'NimBLEDevice::startAdvertising();' in hard
assert 'NimBLEDevice::getAdvertising()->isAdvertising()' in hard
start=hard.index('NimBLEDevice::startAdvertising();')
confirm=hard.index('isAdvertising()',start)
clear=hard.index('sRestartAdvertisingPending.store(false',confirm)
assert start < confirm < clear
old_clear='sRestartAdvertisingPending.store(false,std::memory_order_release);\\n      NimBLEDevice::startAdvertising();'
assert old_clear in hard
assert "if old_restart in j: raise RuntimeError" in hard

# Slot telemetry is explicitly pre-TLS; it is not a release/liveness proof.
# AB7 and AB8 must canonicalize repeated pre-script passes instead of blindly
# appending another suffix. This is a regression oracle for the #316/#317 bug.
assert re.search(r"re\.sub\(r'gTls15zSlotReady\(\?:PreTls\)\*',\s*'gTls15zSlotReadyPreTls',\s*p\)", hard)
assert re.search(r"re\.sub\(r'tls15z_slot_ready\(\?:_pre_tls\)\*',\s*'tls15z_slot_ready_pre_tls',\s*p\)", hard)
assert re.search(r"re\.sub\(r'gTls15zSlotReady\(\?:PreTls\)\+',\s*'gTls15zSlotReadyPreTls',\s*p\)", ab8)
assert re.search(r"re\.sub\(r'tls15z_slot_ready\(\?:_pre_tls\)\+',\s*'tls15z_slot_ready_pre_tls',\s*p\)", ab8)
for script in (hard,ab8):
    assert 'gTls15zSlotReadyPreTlsPreTls' in script or 'tls15z_slot_ready_pre_tls_pre_tls' in script
assert "p=p.replace('gTls15zSlotReady','gTls15zSlotReadyPreTls')" not in hard
assert "p=p.replace('tls15z_slot_ready','tls15z_slot_ready_pre_tls')" not in hard
assert '9.36.7.15Z-MEMORY-RELIEF-AB7' in hard
assert '9.36.7.15Z-MEMORY-RELIEF-AB8' in ab8

# Composition is fail-hard and USB/OTA share the same inherited pre-script chain.
for msg in ('header provenance anchor','source provenance declaration anchor','owner stop marker anchor','advertising retry anchor','before provenance anchor','after provenance anchor','stop provenance expression','JSON provenance anchor'):
    assert msg in hard,msg

# Lifecycle/security invariants. Never scan the Python hardening script itself as
# though it were generated C++: forbidden literals intentionally occur inside
# fail-hard guards. Validate the actual source plus generated C++ templates.
assert 'Tls15zReservationGuard' in base
assert '~Tls15zReservationGuard(){ if(active) jkBleProxyReleaseAuxConnection(); }' in base
probe_start=base.index("probe='''"); probe_end=base.index("'''",probe_start+len("probe='''")); probe_cpp=base[probe_start:probe_end]
obsolete_release='if (tls15zReserved) jkBleProxyReleaseAuxConnection();'
assert obsolete_release not in probe_cpp
assert "if 'if (tls15zReserved) jkBleProxyReleaseAuxConnection();' in p: raise RuntimeError('15Z lifecycle invariant: obsolete path-local release present')" in base

def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
def generated_templates(script):
    # Extract triple-quoted C/C++ replacement/template payloads only. This keeps
    # Python guard strings out of executable-code oracles.
    return '\n'.join(m.group(2) for m in re.finditer(r"(?:r)?('''|\"\"\")(.*?)(?:\1)",script,flags=re.S))

source_code=strip_cpp_comments(source)
generated_code=strip_cpp_comments(generated_templates(base)+'\n'+generated_templates(hard)+'\n'+generated_templates(ab8))
fast_code=source_code+'\n'+generated_code
assert not re.search(r'\bsetInsecure\s*\(',fast_code)
assert 'MBEDTLS_SSL_VERIFY_NONE' not in fast_code
assert 'NimBLEDevice::deinit' not in fast_code
assert "security invariant: executable setInsecure()" in hard
assert "security invariant: executable VERIFY_NONE" in hard
assert "lifecycle invariant: live NimBLE deinit forbidden" in hard

print('15Z AB7/AB8 FAST generated-code gate PASS: TLS verification, NimBLE lifecycle, provenance, advertising retry, idempotent slot telemetry, obsolete-release and USB/OTA composition')
print('15Z AB7/AB8 FMEA regression PASS: semantic provenance oracle, false-pass guard, retry-safe advertising liveness, serialized DENIED paths, idempotent pre-TLS naming, USB/OTA composition, TLS security')
