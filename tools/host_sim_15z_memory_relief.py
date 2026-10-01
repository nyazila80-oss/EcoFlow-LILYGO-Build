from pathlib import Path

patch = Path('tools/platformio_tls15z_memory_relief_ab.py').read_text(encoding='utf-8')
source = Path('src/powerstream_api.cpp').read_text(encoding='utf-8')

required = [
    'MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT',
    '!jkBleProxyAppConnected()',
    '!jkBleProxyBmsConnected()',
    '!jkBleProxyEventsPending()',
    'jkBleProxyReserveAuxConnection()',
    'jkBleProxyReleaseAuxConnection()',
    'tls15z_delta_free',
    'tls15z_delta_largest',
]
for x in required:
    assert x in patch, x

# Safety policy must inspect firmware source, not the diagnostic script that
# necessarily contains these strings as forbidden-pattern guards.
for x in ('setInsecure(', 'MBEDTLS_SSL_VERIFY_NONE'):
    assert x not in source, f'forbidden TLS weakening in firmware source: {x}'

# Also require the patch itself to retain its fail-closed safety invariant.
assert "for forbidden in ('setInsecure(', 'MBEDTLS_SSL_VERIFY_NONE')" in patch
assert "raise RuntimeError('15Z safety invariant: forbidden '+forbidden)" in patch

print('15Z memory-relief source regression PASS')
