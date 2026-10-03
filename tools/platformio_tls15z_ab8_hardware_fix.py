#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

# AB8 hardware fix. PlatformIO executes pre-scripts even for `pio ... -t clean`.
# Therefore a subsequent build in the same checkout sees the already transformed
# downstream source. Treat a proven 15AF+ no-aux descendant as idempotent state,
# not as a missing AB8 reservation anchor.
proj=Path(env['PROJECT_DIR'])
cpp=proj/'src'/'powerstream_api.cpp'
p=cpp.read_text(encoding='utf-8')

old_call='''if(!jkBleProxyAppConnected() && !jkBleProxyBmsConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnectionOwner(); }'''
new_call='''if(!jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
aa_call='''if(gTls15zAdmInitialized.load()==1 && !jkBleProxyAppConnected() && !jkBleProxyEventsPending()){ tls15zAttempted=true; tls15zReserved=jkBleProxyReserveAuxConnection(); }'''
af_marker='gTls15zAdmAttempted.store(0);'

# Read the one canonical provenance value instead of looking for one historical
# version string anywhere in the translation unit.
version_re=re.compile(r'tls15z_version\\\":\\\"([^\\\"]+)')
vm=version_re.findall(p)
if len(vm)!=1:
    raise RuntimeError('15Z AB8 provenance invariant: tls15z_version missing/non-unique: '+repr(vm))
current_version=vm[0]
downstream_no_aux_versions={
    '9.36.7.15AF-NO-AUX-RESERVATION',
    '9.36.7.15AG-TLS-PEAK-FIX',
    '9.36.7.15AH-EARLY-TLS-HANDSHAKE',
    '9.36.7.15AI-PS-BLE-RECLAIM-DIAG',
    '9.36.7.15AK-TLS-ALLOC-PEAK-DIAG',
    '9.36.7.15AL-TLS-DYNAMIC-BUFFER-FIX',
    '9.36.7.15AM-PREFLIGHT-AB-24K',
    '9.36.7.15AN-TLS-INTERNAL8-FIX',
}

downstream_af=(af_marker in p and current_version in downstream_no_aux_versions)
if downstream_af:
    if p.count(af_marker)!=1:
        raise RuntimeError('15Z AB8/15AF+ no-aux marker non-unique')
    # Downstream target already applied: never recreate the reservation call.
else:
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
        raise RuntimeError('15Z AB8 reservation call anchor missing or malformed; version='+current_version+' no_aux_marker='+str(af_marker in p))

# AB6 deliberately emits the unsuffixed slot-ready telemetry. AB8 owns the
# transition to the canonical pre-TLS name. First promote the plain form, then
# collapse any repeated suffixes from repeated pre-script passes.
p=re.sub(r'\bgTls15zSlotReady\b', 'gTls15zSlotReadyPreTls', p)
p=re.sub(r'\btls15z_slot_ready\b', 'tls15z_slot_ready_pre_tls', p)
p=re.sub(r'gTls15zSlotReady(?:PreTls)+', 'gTls15zSlotReadyPreTls', p)
p=re.sub(r'tls15z_slot_ready(?:_pre_tls)+', 'tls15z_slot_ready_pre_tls', p)

# Promote only AB7 -> AB8. Never rewrite a later descendant backwards.
if not downstream_af and current_version=='9.36.7.15Z-MEMORY-RELIEF-AB7':
    p=p.replace('tls15z_version\\\":\\\"9.36.7.15Z-MEMORY-RELIEF-AB7',
                'tls15z_version\\\":\\\"9.36.7.15Z-MEMORY-RELIEF-AB8',1)

# Fail-hard invariants shared by AB8 and its 15AF+ descendants.
if 'jkBleProxyReserveAuxConnectionOwner();' in p:
    raise RuntimeError('15Z AB8 ownership invariant: direct owner call survives in TLS path')
if '!jkBleProxyBmsConnected() && !jkBleProxyEventsPending()' in p:
    raise RuntimeError('15Z AB8 admission invariant: BMS-connected gate survives')
if p.count('\\"tls15z_slot_ready_pre_tls\\"') != 1:
    raise RuntimeError('15Z AB8 JSON invariant: canonical slot-ready field must occur exactly once')
if re.search(r'tls15z_slot_ready_pre_tls_pre_tls',p):
    raise RuntimeError('15Z AB8 idempotence invariant: repeated pre_tls suffix survives')

if downstream_af:
    # 15AF+ deliberately has no executable aux reservation in the TLS path.
    code_no_comments=re.sub(r'//[^\n]*|/\*.*?\*/','',p,flags=re.S)
    if 'jkBleProxyReserveAuxConnection();' in code_no_comments:
        raise RuntimeError('15Z AB8/15AF+ invariant: executable aux reservation unexpectedly restored')
    if current_version not in downstream_no_aux_versions:
        raise RuntimeError('15Z AB8/15AF+ provenance missing')
else:
    vm_after=version_re.findall(p)
    if vm_after != ['9.36.7.15Z-MEMORY-RELIEF-AB8']:
        raise RuntimeError('15Z AB8 provenance invariant missing: '+repr(vm_after))

def strip_cpp_comments(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S)
code=strip_cpp_comments(p)
if re.search(r'\bsetInsecure\s*\(',code):
    raise RuntimeError('15Z AB8 security invariant: executable setInsecure()')
if 'MBEDTLS_SSL_VERIFY_NONE' in code:
    raise RuntimeError('15Z AB8 security invariant: executable VERIFY_NONE')

cpp.write_text(p,encoding='utf-8')
print('[15Z-AB8] REQUESTED->loop-owner state or downstream 15AF+ no-aux state verified; provenance canonicalized')
