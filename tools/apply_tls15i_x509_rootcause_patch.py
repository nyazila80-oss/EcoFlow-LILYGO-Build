from pathlib import Path

p = Path('src/powerstream_api.cpp')
s = p.read_text(encoding='utf-8')

# 9.36.7.15I: preserve verified TLS and make the root-cause contract explicit.
# Runtime already exposes the 15H time/internal-RAM probes; 15I first locks
# down the invariants needed for a trustworthy X509 diagnosis.

def executable_set_insecure(text: str) -> bool:
    for line in text.splitlines():
        code = line.split('//', 1)[0]
        if 'setInsecure(' in code and not code.lstrip().startswith(('#', '"', "'")):
            return True
    return False

required = [
    'client.setCACert(ECOFLOW_CA_BUNDLE);',
    'api-e.ecoflow.com',
    'gTlsEpochPre',
    'gTlsEpochPost',
    'gTlsTimeSanePre',
    'gTlsTimeSanePost',
    'gTlsInternalPreVerifyFree',
    'gTlsInternalPreVerifyLargest',
    'gTlsInternalPostVerifyFree',
    'gTlsInternalPostVerifyLargest',
]
for token in required:
    if token not in s:
        raise SystemExit('15I invariant missing: ' + token)

if executable_set_insecure(s):
    raise SystemExit('15I security regression: executable setInsecure() present')

# Do not silently replace the trust anchor while diagnosing the failure.
if 'DigiCert Global Root G2' not in s:
    raise SystemExit('15I trust-anchor invariant: DigiCert Global Root G2 marker missing')

# The next runtime instrumentation must decode mbedTLS verification flags.
# Keep these expected flag names in the generated source as a provenance marker
# without changing TLS behaviour.
marker = '''\n// 15I X509 root-cause diagnostic contract:\n// MBEDTLS_X509_BADCERT_EXPIRED\n// MBEDTLS_X509_BADCERT_CN_MISMATCH\n// MBEDTLS_X509_BADCERT_NOT_TRUSTED\n// MBEDTLS_X509_BADCERT_FUTURE\n// MBEDTLS_X509_BADCERT_KEY_USAGE\n// MBEDTLS_X509_BADCERT_EXT_KEY_USAGE\n// MBEDTLS_X509_BADCERT_BAD_MD\n// MBEDTLS_X509_BADCERT_BAD_PK\n// MBEDTLS_X509_BADCERT_BAD_KEY\n'''
if '15I X509 root-cause diagnostic contract:' not in s:
    s += marker

p.write_text(s, encoding='utf-8')
print('15I X509 root-cause invariants applied; verified TLS remains fail-closed')
