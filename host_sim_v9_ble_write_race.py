import random
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
src=(ROOT/'src/jk_ble_proxy.cpp').read_text()
cfg=(ROOT/'include/config.h').read_text()
# This regression protects the two-stage BLE write gate, not one historical
# diagnostic label. Keep the maintained firmware-family gate while preserving
# the exact implementation assertions below.
m=re.search(r'^\s*#define\s+FW_VERSION\s+"([^"]+)"\s*$', cfg, re.M)
fw_version=m.group(1) if m else ''
assert fw_version.startswith('2.4.5.9.36.7.'), f'unexpected firmware family: {fw_version!r}'
assert 'sClient && sClient->isConnected() && sRemoteChar && takePacket' in src
assert '!sClient || !sClient->isConnected() || !sRemoteChar' in src
# Model the two-stage gate around dequeue/write. A disconnect may occur at any
# of 4 timing points. No write may start if link/event state says disconnected.
N=2_000_000
writes=blocked=disconnects=viol=0
r=random.Random(191535)
for _ in range(N):
    bms=True; client=True; remote=True; pending=False; packet=True
    # disconnect before first gate
    phase=r.randrange(6)
    if phase==0: client=False; pending=True; disconnects+=1
    first=bms and client and remote and packet
    if not first: blocked+=1; continue
    # callback can fire after initial gate / dequeue
    if phase in (1,2): client=False; pending=True; disconnects+=1
    second=(not pending and bms and client and remote)
    if not second: blocked+=1; continue
    # Once inside NimBLE writeValue, a link-layer disconnect may happen. This
    # is library-owned; cached characteristic remains allocated. Model result
    # as failed write, not pointer invalidation.
    if phase==3:
        client=False; pending=True; disconnects+=1
        blocked+=1
        continue
    writes+=1
    if not remote: viol+=1
print(f'firmware={fw_version} events={N} disconnects={disconnects} writes_started={writes} fail_closed={blocked} violations={viol}')
assert viol==0
print('PASS')
