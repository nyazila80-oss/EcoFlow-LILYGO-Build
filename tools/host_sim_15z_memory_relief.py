from pathlib import Path
import re

patch=Path('tools/platformio_tls15z_memory_relief_ab.py').read_text(encoding='utf-8')
source=Path('src/powerstream_api.cpp').read_text(encoding='utf-8')
main=Path('src/main.cpp').read_text(encoding='utf-8')

# Required diagnostic dimensions: compare the same capability families already
# exposed by the 15F allocation-failure evidence, without changing allocation.
for x in ('MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT','MALLOC_CAP_INTERNAL','MALLOC_CAP_8BIT','MALLOC_CAP_DMA','MALLOC_CAP_32BIT',
          'tls15z_generation','tls15z_a_internal8_free','tls15z_b_internal8_free','tls15z_a_dma_free','tls15z_b_dma_free',
          'jkBleProxyReserveAuxConnectionOwner()','Tls15zReservationGuard'):
    assert x in patch,x

# Same-task deadlock gate.
assert main.index('powerStreamApiLoopTick();') < main.index('jkBleProxyTick();')
probe_start=patch.index("probe='''"); probe_end=patch.index("'''",probe_start+len("probe='''")); probe=patch[probe_start:probe_end]
assert 'jkBleProxyReserveAuxConnectionOwner()' in probe
assert 'jkBleProxyReserveAuxConnection();' not in probe

# Owner primitive: direct IDLE->PROCESSING; post-stop race checks mandatory.
owner_start=patch.index("owner_impl=r'''"); owner_end=patch.index("'''",owner_start+len("owner_impl=r'''")); owner=patch[owner_start:owner_end]
assert 'AuxReserveState expected=AuxReserveState::IDLE;' in owner
assert 'AuxReserveState::PROCESSING' in owner
assert 'AuxReserveState::REQUESTED' not in owner
assert 'NimBLEDevice::stopAdvertising();' in owner
assert owner.count('sServer->getConnectedCount()==0') >= 2
assert '!bleEventsPending()' in owner

# RAII must dominate every apiRequest early return and be constructed before TLS
# objects, so reverse destruction releases BLE only after WiFiClientSecure dies.
assert probe.index('Tls15zReservationGuard') < probe.index('WiFiClientSecure client;')
assert '~Tls15zReservationGuard(){ if(active) jkBleProxyReleaseAuxConnection(); }' in probe
assert 'if (tls15zReserved) jkBleProxyReleaseAuxConnection();' not in patch

# Provenance/stale-data gate: every attempt increments generation and clears
# outcome flags before the reservation decision.
gen=probe.index('gTls15zGeneration.fetch_add(1)')
reset=probe.index('gTls15zReserved.store(0)')
decision=probe.index('jkBleProxyReserveAuxConnectionOwner()')
assert gen < reset < decision
assert 'gTls15zSlotReady.store(0)' in probe

# A must precede reservation, B must follow it. Capability probes are observation
# only: no malloc/free/deinit is allowed in the A/B probe.
assert probe.index('gTls15zAInternal.store') < decision < probe.index('gTls15zBInternal.store')
assert probe.index('gTls15zADma.store') < decision < probe.index('gTls15zBDma.store')
assert 'heap_caps_malloc' not in probe and 'heap_caps_free' not in probe and 'NimBLEDevice::deinit' not in probe

# Composition anchor remains pre-chain stable.
stable_anchor='static std::atomic<uint32_t> gCloudTraceJobId{0};'
assert source.count(stable_anchor)==1
assert "anchor='static std::atomic<uint32_t> gCloudTraceJobId{0};'" in patch
assert "p.count(anchor)!=1" in patch

# TLS security remains fail-closed.
def strip_cpp_comments(text): return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
source_code=strip_cpp_comments(source); patch_code=strip_cpp_comments(patch)
assert not re.search(r'\bsetInsecure\s*\(',source_code)
assert 'MBEDTLS_SSL_VERIFY_NONE' not in source_code
assert "raise RuntimeError('15Z safety invariant: executable setInsecure()')" in patch
assert "raise RuntimeError('15Z safety invariant: executable VERIFY_NONE')" in patch
assert 'NimBLEDevice::deinit' not in patch_code
assert '9.36.7.15Z-MEMORY-RELIEF-AB3' in patch

print('15Z AB3 FMEA regression PASS: ownership, RAII, provenance, capability telemetry, TLS security')
