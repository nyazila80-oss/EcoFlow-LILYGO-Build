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

# Composition gate: 15Z must anchor only to source state already present before
# the TLS probe chain runs. This catches the exact CI failure where 15Z depended
# on gCloudJobSeq, a symbol not guaranteed after the composed 15D..15Y scripts.
stable_anchor = 'static std::atomic<uint32_t> gCloudTraceJobId{0};'
assert source.count(stable_anchor) == 1, 'base source stable 15Z anchor missing/non-unique'
assert "anchor='static std::atomic<uint32_t> gCloudTraceJobId{0};'" in patch, \
    '15Z patch is not using the stable pre-chain anchor'
assert "gCloudJobSeq{0}" not in patch, '15Z still depends on obsolete composed-state anchor'
assert "p.count(anchor)!=1" in patch, '15Z must fail closed on ambiguous state anchor'

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

# The 15Z PlatformIO patch itself must retain the same fail-closed executable-code
# guard. Do not require the obsolete raw-substring loop that incorrectly matched
# comments containing words such as "setInsecure()".
assert 'def strip_cpp_comments(text):' in patch
assert "code=strip_cpp_comments(p)" in patch
assert "re.search(r'\\bsetInsecure\\s*\\(', code)" in patch
assert "raise RuntimeError('15Z safety invariant: executable setInsecure()')" in patch
assert "if 'MBEDTLS_SSL_VERIFY_NONE' in code:" in patch
assert "raise RuntimeError('15Z safety invariant: executable VERIFY_NONE')" in patch
assert "for forbidden in ('setInsecure(', 'MBEDTLS_SSL_VERIFY_NONE')" not in patch, \
    'obsolete comment-sensitive TLS guard returned'

print('15Z memory-relief source + composed-anchor + executable TLS safety regression PASS')
