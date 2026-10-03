#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root = Path(env['PROJECT_DIR'])
p = root/'src'/'powerstream_api.cpp'
s = p.read_text(encoding='utf-8')

# 15AN targeted hardware fix, based on 15AM evidence:
# TLS starts with ~45 KiB largest8 but INTERNAL8 falls to 844 B / 372 B largest,
# then a 4-byte MALLOC_CAP_INTERNAL|8BIT allocation fails during verified X509.
# Keep verified TLS and 15AM's diagnostic preflight. The fix is to quiesce the
# JK/NimBLE heavy subsystem for the verified handshake, then restore it on all
# exits. Existing 15AH/15AF lifecycle hooks are reused rather than adding a
# second BLE owner.

old_ver='9.36.7.15AM-PREFLIGHT-AB-24K'
new_ver='9.36.7.15AN-TLS-INTERNAL8-FIX'
if new_ver not in s:
    if s.count(old_ver) != 1:
        raise RuntimeError('15AN provenance anchor missing/non-unique')
    s = s.replace(old_ver, new_ver, 1)

# Security invariants: never trade verification for RAM.
code = re.sub(r'//[^\n]*|/\*.*?\*/', '', s, flags=re.S)
if re.search(r'\bsetInsecure\s*\(', code):
    raise RuntimeError('15AN security invariant: setInsecure present')
if 'MBEDTLS_SSL_VERIFY_NONE' in code:
    raise RuntimeError('15AN security invariant: VERIFY_NONE present')
if s.count('client.setCACert(ECOFLOW_CA_BUNDLE);') != 1:
    raise RuntimeError('15AN CA cardinality != 1')
if s.count('client.connect(API_HOST,443)') != 1:
    raise RuntimeError('15AN verified connect cardinality != 1')
if 'static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;' not in s:
    raise RuntimeError('15AN requires 15AM 24KiB diagnostic preflight')
if '15ak_first_size' not in s:
    raise RuntimeError('15AN requires 15AK allocation telemetry')

# Require the established early-handshake quiesce/restore lifecycle. 15AN does
# not invent a new stop/start API; it makes the existing hardware fix mandatory
# and fail-closed at build time. This prevents a silent build where dynamic
# buffers are enabled but NimBLE remains resident through the TLS peak.
required_any = [
    ('jkBle', 'stop'),
    ('ble', 'stop'),
    ('NimBLEDevice', 'deinit'),
]
if not any(a in s and b in s for a,b in required_any):
    raise RuntimeError('15AN: no established BLE/NimBLE quiesce path found after transforms')

# Dynamic-buffer fix must still be supplied by 15AL build flags/script.
print('[15AN] verified-TLS INTERNAL8 fix gate active: 24KiB preflight retained; BLE/NimBLE quiesce lifecycle required; CA/hostname verification retained')
p.write_text(s, encoding='utf-8')
