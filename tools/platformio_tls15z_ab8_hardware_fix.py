#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# AB8 hardware fix. Repeated PlatformIO pre-script passes may encounter the
# downstream 15AF no-aux A/B state; that is a valid descendant, not corruption.
proj=Path(env['PROJECT_DIR'])
cpp=proj/'src'/'powerstream_api.cpp'
p=cpp.read_text(encoding='utf-8')

old_call='''if(!jkBleProxyAppConnected() && !jkBleProxyBmsConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnectionOwner(); }'''
new_call='''if(!jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
aa_call='''if(gTls15zAdmInitialized.load()==1 && !jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
# 15AF deliberately replaces the reservation/admission block with this stable
# telemetry assignment. Detect it together with provenance to avoid accepting a
# coincidental line elsewhere.
af_marker='gTls15zAdmAttempted.store(0);'
af_version='9.36.7.15AF-NO-AUX-RESERVATION'

if af_marker in p and af_version in p:
    if p.count(af_marker)!=1:
        raise RuntimeError('15Z AB8/15AF no-aux marker non-unique')
    # Downstream target already applied: do not recreate the reservation call.
    downstream_af=True
else:
    downstream_af=False
    if old_call in p:
        if p.count(old_call)!=1: raise RuntimeError('15Z AB8 reservation call anchor non-unique')
        p=p.replace(old_call,new_call,1)
    elif new_call in p:
        pass
    elif aa_call in p:
        if p.count(aa_call)!=1: raise RuntimeError('15Z AB8/15AA reservation anchor non-unique')
    elif ('gTls15zAdmAttempted.store(tls15zAttempted?1:0);' in p and
          'tls15zReserved=jkBleProxyReserveAuxConnection();' in p and
          'jkBleProxyReserveAuxConnectionOwner();' not in p and
          ('if(!jkBleProxyAppConnected() && !jkBleProxyEventsPending())' in p or
           'if(gTls15zAdmInitialized.load()==1 && !jkBleProxyAppConnected() && !jkBleProxyEventsPending())' in p)):
        pass
    else:
        raise RuntimeError('15Z AB8 reservation call anchor missing or malformed')

# AB6 deliberately emits the unsuffixed slot-ready telemetry. AB8 owns the
# transition to the canonical pre-TLS name. First promote the plain form, then
# collapse any repeated suffixes from repeated pre-script passes.
p=re.sub(r'\bgTls15zSlotReady\b', 'gTls15zSlotReadyPreTls', p)
p=re.sub(r'\btls15z_slot_ready\b', 'tls15z_slot_ready_pre_tls', p)
p=re.sub(r'gTls15zSlotReady(?:PreTls)+', 'gTls15zSlotReadyPreTls', p)
p=re.sub(r'tls15z_slot_ready(?:_pre_tls)+', 'tls15z_slot_ready_pre_tls', p)

# Do not overwrite downstream 15AF provenance on a repeated pass.
if not downstream_af:
    p=p.replace('9.36.7.15Z-MEMORY-RELIEF-AB7','9.36.7.15Z-MEMORY-RELIEF-AB8')

# Fail-hard invariants shared by AB8 and its 15AF descendant.
if 'jkBleProxyReserveAuxConnectionOwner();' in p:
    raise RuntimeError('15Z AB8 ownership invariant: direct owner call survives in TLS path')
if '!jkBleProxyBmsConnected() && !jkBleProxyEventsPending()' in p:
    raise RuntimeError('15Z AB8 admission invariant: BMS-connected gate survives')
if p.count('\\"tls15z_slot_ready_pre_tls\\"') != 1:
    raise RuntimeError('15Z AB8 JSON invariant: canonical slot-ready field must occur exactly once')
if re.search(r'tls15z_slot_ready_pre_tls_pre_tls',p):
    raise RuntimeError('15Z AB8 idempotence invariant: repeated pre_tls suffix survives')

if downstream_af:
    # 15AF's purpose is specifically that no executable aux reservation survives.
    code_no_comments=re.sub(r'//[^\n]*|/\*.*?\*/','',p,flags=re.S)
    if 'jkBleProxyReserveAuxConnection();' in code_no_comments:
        raise RuntimeError('15Z AB8/15AF invariant: executable aux reservation unexpectedly restored')
    if af_version not in p:
        raise RuntimeError('15Z AB8/15AF provenance missing')
else:
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
print('[15Z-AB8] REQUESTED->loop-owner state or downstream 15AF no-aux state verified; provenance canonicalized')
