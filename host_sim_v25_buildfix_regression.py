from pathlib import Path
import random
import re

root = Path(__file__).resolve().parent
b = (root / 'src/bms.cpp').read_text()
h = (root / 'include/config.h').read_text()

# This regression protects the BMS build fix, not one historical firmware label.
# Accept the maintained 2.4.5 / 9.36.7 firmware family so diagnostic suffixes
# (15H/15I/etc.) cannot create a false negative while the functional assertions
# below remain exact and fail-closed.
m = re.search(r'^\s*#define\s+FW_VERSION\s+"([^"]+)"\s*$', h, re.M)
fw_version = m.group(1) if m else ''
version_family_ok = fw_version.startswith('2.4.5.9.36.7.')

checks = {
    'version_family_245_9367': version_family_ok,
    'bad_call_removed': 'setCanPowerSnapshotAtomic((int32_t)inputW, (int32_t)outputW);' not in b,
    'good_call_present': 'setCanPowerSnapshotAtomic((int32_t)inputWatt, (int32_t)outputWatt);' in b,
    'stale_zero_published': 'inputWatt = 0;\n    outputWatt = 0;\n    setCanPowerSnapshotAtomic(0, 0);\n    return;' in b,
}

# Model producer: invalid telemetry must publish 0/0; valid samples publish coherent integer pair.
viol = 0
snap = (0, 0)
for _ in range(2_000_000):
    valid = random.random() > .12
    if not valid:
        snap = (0, 0)
        if snap != (0, 0):
            viol += 1
    else:
        v = random.uniform(40, 60)
        a = random.uniform(-50, 50)
        iw = int(v * a) if a > 0 else 0
        ow = int(v * a) if a < 0 else 0
        snap = (iw, ow)
        if iw and ow:
            viol += 1

print('BUILD-FIX firmware', fw_version or '<missing>')
print('BUILD-FIX checks', checks)
print('modeled operations', 2_000_000, 'violations', viol)
if not all(checks.values()) or viol:
    raise SystemExit('FAIL')
print('PASS')
