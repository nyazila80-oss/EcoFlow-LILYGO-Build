#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# AB8 is driven by the first real 15Z hardware run:
# heavy_acquires=1 but stopGeneration stayed 0->0 because AB6 gated the
# reservation on !BMS-connected and then called a synchronous helper from the
# cloud worker. The existing jkBleProxyReserveAuxConnection() already provides
# the correct REQUESTED -> Arduino-loop owner -> GRANTED handshake and is safe
# while the real JK central link is connected (provided no phone/app occupies
# the proxy slot). Keep NimBLE lifecycle intact: no deinit and no TLS weakening.
proj=Path(env['PROJECT_DIR'])
cpp=proj/'src'/'powerstream_api.cpp'
p=cpp.read_text(encoding='utf-8')

old_call='''if(!jkBleProxyAppConnected() && !jkBleProxyBmsConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnectionOwner(); }'''
new_call='''if(!jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
if old_call in p:
    if p.count(old_call)!=1: raise RuntimeError('15Z AB8 reservation call anchor non-unique')
    p=p.replace(old_call,new_call,1)
elif new_call in p:
    # Already at the AB8 target state (normal repeated pre-script pass).
    pass
elif ('gTls15zAdmAttempted.store(tls15zAttempted?1:0);' in p and
      'tls15zReserved=jkBleProxyReserveAuxConnection();' in p and
      'if(!jkBleProxyAppConnected() && !jkBleProxyEventsPending())' in p and
      'jkBleProxyReserveAuxConnectionOwner();' not in p):
    # A later AB8 admission probe deliberately expands the exact new_call
    # anchor with read-only provenance. USB and OTA environments share the
    # project source tree, so a second PlatformIO pre-script pass sees this
    # downstream-instrumented form. Treat it as an idempotent no-op only when
    # the complete AB8 handshake/admission invariants are still present.
    pass
else:
    raise RuntimeError('15Z AB8 reservation call anchor missing or malformed')

# AB7 used unrestricted substring replacement, so repeated pre-script passes
# produced tls15z_slot_ready_pre_tls_pre_tls... . Canonicalize exactly once.
p=re.sub(r'gTls15zSlotReady(?:PreTls)+', 'gTls15zSlotReadyPreTls', p)
p=re.sub(r'tls15z_slot_ready(?:_pre_tls)+', 'tls15z_slot_ready_pre_tls', p)

# Version provenance for the hardware-derived fix.
p=p.replace('9.36.7.15Z-MEMORY-RELIEF-AB7','9.36.7.15Z-MEMORY-RELIEF-AB8')

# Fail-hard invariants. AB8 must never regress to the cloud-worker direct owner
# call, must not block relief merely because the real JK BMS is connected, and
# must expose one canonical JSON field after arbitrary repeated script passes.
if 'jkBleProxyReserveAuxConnectionOwner();' in p:
    raise RuntimeError('15Z AB8 ownership invariant: direct owner call survives in TLS path')
if '!jkBleProxyBmsConnected() && !jkBleProxyEventsPending()' in p:
    raise RuntimeError('15Z AB8 admission invariant: BMS-connected gate survives')
if p.count('\\"tls15z_slot_ready_pre_tls\\"') != 1:
    raise RuntimeError('15Z AB8 JSON invariant: canonical slot-ready field must occur exactly once')
if re.search(r'tls15z_slot_ready_pre_tls_pre_tls',p):
    raise RuntimeError('15Z AB8 idempotence invariant: repeated pre_tls suffix survives')
if '9.36.7.15Z-MEMORY-RELIEF-AB8' not in p:
    raise RuntimeError('15Z AB8 provenance invariant missing')

def strip_cpp_comments(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
code=strip_cpp_comments(p)
if re.search(r'\bsetInsecure\s*\(',code):
    raise RuntimeError('15Z AB8 security invariant: executable setInsecure()')
if 'MBEDTLS_SSL_VERIFY_NONE' in code:
    raise RuntimeError('15Z AB8 security invariant: executable VERIFY_NONE')

cpp.write_text(p,encoding='utf-8')
print('[15Z-AB8] TLS relief routed through REQUESTED->loop-owner handshake; slot-ready provenance canonicalized')
