from pathlib import Path
import re

patch = Path('tools/platformio_tls15z_memory_relief_ab.py').read_text(encoding='utf-8')
source = Path('src/powerstream_api.cpp').read_text(encoding='utf-8')
main = Path('src/main.cpp').read_text(encoding='utf-8')

required = [
    'MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT',
    '!jkBleProxyAppConnected()',
    '!jkBleProxyBmsConnected()',
    '!jkBleProxyEventsPending()',
    'jkBleProxyReserveAuxConnectionOwner()',
    'Tls15zReservationGuard',
    '~Tls15zReservationGuard(){ if(active) jkBleProxyReleaseAuxConnection(); }',
    'tls15z_delta_free',
    'tls15z_delta_largest',
]
for x in required:
    assert x in patch, x

# Same-task deadlock regression: cloud work is synchronously serviced before the
# normal JK owner tick in Arduino loop(). 15Z therefore must never use the
# worker REQUESTED->wait reservation API from apiRequest().
cloud_pos = main.index('powerStreamApiLoopTick();')
jk_pos = main.index('jkBleProxyTick();')
assert cloud_pos < jk_pos, 'test assumption changed: JK tick now precedes cloud tick'
probe_start = patch.index("probe='''")
probe_end = patch.index("'''", probe_start + len("probe='''"))
probe = patch[probe_start:probe_end]
assert 'jkBleProxyReserveAuxConnectionOwner()' in probe
assert 'jkBleProxyReserveAuxConnection();' not in probe, \
    '15Z reintroduced same-loop REQUESTED/wait self-block'

# The owner primitive must transition IDLE->PROCESSING directly, never publish a
# REQUESTED state that requires a later jkBleProxyTick(). It must re-check live
# server connections and deferred callback events after stopAdvertising().
assert 'AuxReserveState expected=AuxReserveState::IDLE;' in patch
assert 'AuxReserveState::PROCESSING' in patch
owner_start = patch.index("owner_impl=r'''")
owner_end = patch.index("'''", owner_start + len("owner_impl=r'''"))
owner = patch[owner_start:owner_end]
assert 'AuxReserveState::REQUESTED' not in owner
assert 'NimBLEDevice::stopAdvertising();' in owner
assert 'sServer->getConnectedCount()==0' in owner
assert '!bleEventsPending()' in owner

# Lifecycle regression: apiRequest() contains many early returns. Release must be
# RAII, not attached to one textual http.end() path. Declaration order is also
# intentional: guard appears before WiFiClientSecure, so C++ reverse destruction
# destroys HTTP/TLS objects before the guard schedules BLE advertising restart.
assert probe.index('Tls15zReservationGuard') < probe.index('WiFiClientSecure client;')
assert "if (tls15zReserved) jkBleProxyReleaseAuxConnection();" not in patch
assert "lifecycle invariant: obsolete path-local release present" in patch

# Composition gate: 15Z must anchor only to source state already present before
# the TLS probe chain runs.
stable_anchor = 'static std::atomic<uint32_t> gCloudTraceJobId{0};'
assert source.count(stable_anchor) == 1, 'base source stable 15Z anchor missing/non-unique'
assert "anchor='static std::atomic<uint32_t> gCloudTraceJobId{0};'" in patch
assert "gCloudJobSeq{0}" not in patch
assert "p.count(anchor)!=1" in patch

# Fail closed on TLS security. Comments mentioning forbidden APIs are ignored,
# executable uses are not.
def strip_cpp_comments(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
source_code = strip_cpp_comments(source)
assert not re.search(r'\bsetInsecure\s*\(', source_code)
assert 'MBEDTLS_SSL_VERIFY_NONE' not in source_code
assert 'def strip_cpp_comments(text):' in patch
assert "code=strip_cpp_comments(p)" in patch
assert "re.search(r'\\bsetInsecure\\s*\\(', code)" in patch
assert "raise RuntimeError('15Z safety invariant: executable setInsecure()')" in patch
assert "if 'MBEDTLS_SSL_VERIFY_NONE' in code:" in patch
assert "raise RuntimeError('15Z safety invariant: executable VERIFY_NONE')" in patch

# Scope gate: this remains an observation-first advertising/slot A/B. It must
# not introduce live NimBLE deinitialization or TLS verification weakening.
assert 'NimBLEDevice::deinit' not in strip_cpp_comments(patch)
assert '9.36.7.15Z-MEMORY-RELIEF-AB2' in patch

print('15Z AB2 same-loop ownership + RAII + TLS safety regression PASS')
