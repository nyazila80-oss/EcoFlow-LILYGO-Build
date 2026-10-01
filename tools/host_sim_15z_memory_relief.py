from pathlib import Path
p=Path('tools/platformio_tls15z_memory_relief_ab.py').read_text(encoding='utf-8')
required=[
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
    assert x in p, x
for x in ('setInsecure(', 'MBEDTLS_SSL_VERIFY_NONE'):
    assert x not in p, x
print('15Z memory-relief source regression PASS')
