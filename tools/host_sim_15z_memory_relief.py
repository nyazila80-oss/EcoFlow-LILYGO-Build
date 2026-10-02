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

# AB7 provenance oracle: verify semantics, not obsolete implementation text.
legacy='tls15zAuxAfter.afterStopFree!=0'
new_expr='tls15zAuxAfter.stopGeneration!=tls15zAuxBefore.stopGeneration'
for x in ('uint32_t stopGeneration=0;','sAuxStopGeneration{0}','sAuxStopGeneration.fetch_add(1','tls15z_stop_generation_before','tls15z_stop_generation_after'):
    assert x in hard,x
assert re.search(r"old_obs\s*=\s*['\"]const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter\.afterStopFree!=0;['\"]",hard)
assert re.search(r"new_obs\s*=\s*['\"]const bool tls15zStopObserved=tls15zOwnerRan && tls15zAuxAfter\.stopGeneration!=tls15zAuxBefore\.stopGeneration;['\"]",hard)
assert re.search(r"if\s+old_obs\s+in\s+p\s*:\s*p=p\.replace\(old_obs,new_obs,1\)",hard)
assert "elif new_obs not in p: raise RuntimeError('15Z AB7 stop provenance expression missing')" in hard
assert 'heap value used as stop proof' in hard
assert legacy != new_expr and hard.count(legacy) >= 2 and new_expr in hard

# Current AB7 is provenance/composition hardening only. Advertising restart ownership
# remains in the preceding generator; AB7 must not reintroduce a direct restart path.
assert 'NimBLEDevice::startAdvertising();' not in hard
assert 'NimBLEDevice::deinit' in hard  # appears only in fail-hard lifecycle guard
assert 'live NimBLE deinit forbidden' in hard
assert 'fresh-AB6/repeated-descendant composition' in hard
for v in ('9.36.7.15Z-MEMORY-RELIEF-AB6','9.36.7.15Z-MEMORY-RELIEF-AB7','9.36.7.15Z-MEMORY-RELIEF-AB8','9.36.7.15AF-NO-AUX-RESERVATION','9.36.7.15AG-TLS-PEAK-FIX'):
    assert v in hard,v
assert "present==['9.36.7.15Z-MEMORY-RELIEF-AB6']" in hard
assert 'expected exactly one AB6/AB7-or-later provenance' in hard

# Slot telemetry remains pre-TLS and repeated suffixes are rejected.
assert 'gTls15zSlotReadyPreTlsPreTls|tls15z_slot_ready_pre_tls_pre_tls' in hard
assert re.search(r"re\.sub\(r'gTls15zSlotReady\(\?:PreTls\)\+',\s*'gTls15zSlotReadyPreTls',\s*p\)", ab8)
assert re.search(r"re\.sub\(r'tls15z_slot_ready\(\?:_pre_tls\)\+',\s*'tls15z_slot_ready_pre_tls',\s*p\)", ab8)
assert "p=p.replace('gTls15zSlotReady','gTls15zSlotReadyPreTls')" not in hard
assert "p=p.replace('tls15z_slot_ready','tls15z_slot_ready_pre_tls')" not in hard
assert '9.36.7.15Z-MEMORY-RELIEF-AB8' in ab8

# Composition is fail-hard and USB/OTA share the same inherited pre-script chain.
for msg in ('stopGeneration header anchor','aux stop generation anchor','aux snapshot generation anchor','stop increment anchor','powerstream provenance declaration anchor','stop provenance expression','JSON provenance anchor'):
    assert msg in hard,msg
assert 'member duplicated' in hard
assert 'expected exactly one AB6/AB7-or-later provenance' in hard

# Lifecycle/security invariants. Scan generated C++ templates rather than Python
# fail-hard strings, which intentionally contain forbidden literals.
assert 'Tls15zReservationGuard' in base
assert '~Tls15zReservationGuard(){ if(active) jkBleProxyReleaseAuxConnection(); }' in base
probe_start=base.index("probe='''"); probe_end=base.index("'''",probe_start+len("probe='''")); probe_cpp=base[probe_start:probe_end]
obsolete_release='if (tls15zReserved) jkBleProxyReleaseAuxConnection();'
assert obsolete_release not in probe_cpp
assert "if 'if (tls15zReserved) jkBleProxyReleaseAuxConnection();' in p: raise RuntimeError('15Z lifecycle invariant: obsolete path-local release present')" in base

def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
def generated_templates(script):
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

print('15Z AB7/AB8 FAST generated-code gate PASS: TLS verification, NimBLE lifecycle, provenance, idempotent slot telemetry, obsolete-release and USB/OTA composition')
print('15Z AB7/AB8 FMEA regression PASS: stop-generation provenance, AB6-to-descendant composition, deferred advertising ownership, idempotent pre-TLS naming, USB/OTA composition, TLS security')
