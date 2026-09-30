#!/usr/bin/env python3
from pathlib import Path

patch=Path('tools/apply_tls15h_x509_diag_patch.py').read_text(encoding='utf-8')
chain=Path('tools/apply_tls15d_runtime_patch.py').read_text(encoding='utf-8')
fmea=Path('AUDIT_15H_X509_FMEA.md').read_text(encoding='utf-8')

required_patch=[
    'client.setCACert(ECOFLOW_CA_BUNDLE);',
    'gTlsEpochPre', 'gTlsEpochPost',
    'gTlsTimeSanePre', 'gTlsTimeSanePost',
    'gTlsInternalPreVerifyFree', 'gTlsInternalPreVerifyLargest',
    'gTlsInternalPostVerifyFree', 'gTlsInternalPostVerifyLargest',
    'tlsEpochSane',
]
for token in required_patch:
    if token not in patch: raise SystemExit('15H audit missing token: '+token)
if "runpy.run_path('tools/apply_tls15h_x509_diag_patch.py'" not in chain:
    raise SystemExit('15H patch is not chained into deterministic build')
if 'setInsecure() is forbidden' not in fmea:
    raise SystemExit('15H FMEA security gate missing')
# The patch may mention setInsecure only in its guard/comment; it must never add a call.
if "client.setInsecure(" in patch:
    raise SystemExit('15H audit: insecure TLS call introduced')
print('15H X509/time/INTERNAL-RAM FMEA static audit PASS')
