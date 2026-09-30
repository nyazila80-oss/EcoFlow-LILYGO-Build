#!/usr/bin/env python3
from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

# 9.36.7.15G.1 compatibility correction.
# Arduino-ESP32 2.x / framework-arduinoespressif32 4.20017 does not expose
# WiFiClientSecure::setBufferSizes(). Do not fake a per-client buffer reduction
# and do not weaken certificate verification. Keep the 15F allocation evidence,
# the fail-closed TLS preflight, and the existing CA verification intact while
# the next hardware-safe resource-handoff experiment is prepared.
if 'client.setBufferSizes(' in s:
    raise SystemExit('15G.1: unsupported WiFiClientSecure::setBufferSizes still present')
if 'client.setInsecure' in s:
    raise SystemExit('15G.1 security regression: insecure TLS present')
required = [
    'WiFiClientSecure client;',
    'client.setCACert(ECOFLOW_CA_BUNDLE);',
    'static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 10240;',
    'gTlsFailedAllocSize',
    'gTlsFailedCapsLargest',
]
for token in required:
    if token not in s:
        raise SystemExit(f'15G.1 invariant missing: {token}')

p.write_text(s,encoding='utf-8')
print('15G.1 ESP32 TLS compatibility gate applied: unsupported per-client buffer API removed; CA verification + fail-closed diagnostics preserved')
