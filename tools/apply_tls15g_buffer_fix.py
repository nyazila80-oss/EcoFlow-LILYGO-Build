#!/usr/bin/env python3
from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

def rep(old,new,name):
    global s
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'{name}: expected exactly one match, got {n}')
    s=s.replace(old,new)

# Hardware 15F proved the failing TLS allocation is 16,717 bytes with caps=2052.
# At that exact instant only 10,576 bytes were free and the largest matching block
# was 6,132 bytes. Avoid a risky live NimBLE teardown first: constrain the
# WiFiClientSecure TLS record buffers to 4 KiB RX/TX. This keeps certificate
# verification enabled and does not change request credentials or cloud-write policy.
rep('  WiFiClientSecure client;\n  tlsMemSnap(gTlsHeapClient,gTlsLargestClient);', '''  WiFiClientSecure client;
  // 9.36.7.15G: measured TLS peak-RAM fix. The previous default RX record buffer
  // produced a 16,717-byte failed allocation. 4096 keeps enough room for normal
  // TLS records while fitting the hardware-proven INTERNAL/8BIT pool.
  client.setBufferSizes(4096,4096);
  tlsMemSnap(gTlsHeapClient,gTlsLargestClient);''', 'TLS record buffer sizing')

p.write_text(s,encoding='utf-8')
out=p.read_text(encoding='utf-8')
if 'client.setBufferSizes(4096,4096);' not in out:
    raise SystemExit('15G postcondition missing: TLS buffer sizing')
if 'client.setInsecure' in out:
    raise SystemExit('15G security regression: insecure TLS present')
print('15G TLS buffer fix applied deterministically')
