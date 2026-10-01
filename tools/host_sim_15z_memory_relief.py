from pathlib import Path
import re

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

# Match the proven 15D credential audit semantics: remove C/C++ comments before
# looking for executable TLS weakening. This prevents documentation such as
# "never call setInsecure()" from becoming a false positive after runtime patches.
def strip_cpp_comments(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)

source_code = strip_cpp_comments(source)
assert not re.search(r'\bsetInsecure\s*\(', source_code), \
    'forbidden executable TLS weakening: setInsecure()'
assert 'MBEDTLS_SSL_VERIFY_NONE' not in source_code, \
    'forbidden executable TLS weakening: MBEDTLS_SSL_VERIFY_NONE'

# The 15Z PlatformIO patch itself must retain its fail-closed guard.
assert "for forbidden in ('setInsecure(', 'MBEDTLS_SSL_VERIFY_NONE')" in patch
assert "raise RuntimeError('15Z safety invariant: forbidden '+forbidden)" in patch

print('15Z memory-relief source regression PASS')
