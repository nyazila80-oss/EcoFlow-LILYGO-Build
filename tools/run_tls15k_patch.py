#!/usr/bin/env python3
from pathlib import Path
import subprocess

# Reproduce the proven 15J diagnostic baseline first.
subprocess.run(['python', 'tools/run_tls15j_patch.py'], check=True)

p = Path('src/powerstream_api.cpp')
s = p.read_text(encoding='utf-8')

# 15J hardware evidence: MBEDTLS_X509_BADCERT_NOT_TRUSTED (0x8), depth 2.
# api-e.ecoflow.com has historically used GeoTrust RSA CN CA G3, whose issuer
# is DigiCert Global Root CA. Keep the existing Global Root G2 anchor as well
# to tolerate DigiCert hierarchy transitions while preserving VERIFY_REQUIRED.
root_ca = '''
-----BEGIN CERTIFICATE-----
MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSjANBgkqhkiG9w0BAQUFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBD
QTAeFw0wNjExMTAwMDAwMDBaFw0zMTExMTAwMDAwMDBaMGExCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xIDAeBgNVBAMTF0RpZ2lDZXJ0IEdsb2JhbCBSb290IENBMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEA4jvhEXLeqKTTo1eqUKKPC3eQyaKl7hLOllsB
CSDMAZOnTjC3U/dDxGkAV53ijSLdhwZAAIEJzs4bg7/fzTtxRuLWZscFs3YnFo97
nh6Vfe63SKMI2tavegw5BmV/Sl0fvBf4q77uKNd0f3p4mVmFaG5cIzJLv07A6Fpt
43C/dxC//AH2hdmoRBBYMql1GNXRor5H4idq9Joz+EkIYIvUX7Q6hL+hqkpMfT7P
T19sdl6gSzeRntwi5m3OFBqOasv+zbMUZBfHWymeMr/y7vrTC0LUq7dBMtoM1O/4
gdW7jVg/tRvoSSiicNoxBN33shbyTApOB6jtSj1etX+jkMOvJwIDAQABo2MwYTAO
BgNVHQ8BAf8EBAMCAYYwDwYDVR0TAQH/BAUwAwEB/zAdBgNVHQ4EFgQUA95QNVbR
TLtm8KPiGxvDl7I90VUwHwYDVR0jBBgwFoAUA95QNVbRTLtm8KPiGxvDl7I90VUw
DQYJKoZIhvcNAQEFBQADggEBAMucN6pIExIK+t1EnE9SsPTfrgT1eXkIoyQY/Esr
hMAtudXH/vTBH1jLuG2cenTnmCmrEbXjcKChzUyImZOMkXDiqw8cvpOp/2PV5Adg
06O/nVsJ8dWO41P0jmP6P6fbtGbfYmbW0W5BjfIttep3Sp+dWOIrWcBAI+0tKIJF
PnlUkiaY4IBIqDfv8NZ5YBberOgOzW6sRBc4L0na4UU+Krk2U886UAb3LujEV0ls
YSEY1QSteDwsOoBrp+uvFRTp2InBuThs4pFsiv9kuXclVzDAGySj4dzp30d8tbQk
CAUw7C29C79Fv1C5qfPrmAESrciIxpg0X40KPMbp1ZWVbd4=
-----END CERTIFICATE-----
'''

end = '-----END CERTIFICATE-----\n)EOF";'
if root_ca.strip() not in s:
    if end not in s:
        raise RuntimeError('15K: CA bundle end anchor missing')
    s = s.replace(end, '-----END CERTIFICATE-----\n' + root_ca + ')EOF";', 1)

s = s.replace('9.36.7.15J-X509-VERIFY-FLAGS', '9.36.7.15K-ECOFLOW-TRUST-CHAIN')
p.write_text(s, encoding='utf-8')

cfg = Path('include/config.h')
c = cfg.read_text(encoding='utf-8').replace('2.4.5.9.36.7.15J-X509-VERIFY-FLAGS', '2.4.5.9.36.7.15K-ECOFLOW-TRUST-CHAIN')
cfg.write_text(c, encoding='utf-8')
Path('data/fs_version.txt').write_text('2.4.5.9.36.7.15K-ECOFLOW-TRUST-CHAIN\n', encoding='utf-8')

# Fail closed: CA verification and 15J proof instrumentation must remain.
assert 'client.setCACert(ECOFLOW_CA_BUNDLE);' in s
assert 'tls15j_verify_flags_raw' in s
assert 'DigiCert Global Root G2' in s
assert 'MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSj' in s
print('15K trust-chain patch applied: DigiCert Global Root CA + Global Root G2, VERIFY_REQUIRED retained')
