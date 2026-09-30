#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess

# Reproduce the complete 15K trust-store baseline first, then add only 15L telemetry.
subprocess.run(['python', 'tools/run_tls15k_patch.py'], check=True)
subprocess.run(['python', 'tools/apply_tls15l_runtime_patch.py'], check=True)

s=Path('src/powerstream_api.cpp').read_text(encoding='utf-8')
c=Path('include/config.h').read_text(encoding='utf-8')
f=Path('data/fs_version.txt').read_text(encoding='utf-8')

# Source/provenance invariants. Framework-specific symbols are injected by
# PlatformIO pre-scripts and are verified again by the dedicated workflow.
required=(
 '9.36.7.15L-CERT-CHAIN-PROBE',
 'tls15l_chain',
 'tls15l_get_depth_flags',
 'tls15j_verify_flags_raw',
 'client.setCACert(ECOFLOW_CA_BUNDLE);',
 'DigiCert Global Root G2',
 'MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSj',
)
for token in required:
    if token not in s: raise RuntimeError('15L source invariant missing: '+token)
if '2.4.5.9.36.7.15L-CERT-CHAIN-PROBE' not in c: raise RuntimeError('15L config provenance missing')
if f.strip()!='2.4.5.9.36.7.15L-CERT-CHAIN-PROBE': raise RuntimeError('15L FS provenance missing')

# Reject an executable insecure fallback, but do not false-positive on comments,
# strings, or diagnostic text that merely mentions setInsecure().  The Actions
# workflow independently applies a second executable-line grep gate.
def strip_cpp_noncode(text: str) -> str:
    out=[]; i=0; n=len(text); state='code'
    while i<n:
        ch=text[i]; nx=text[i+1] if i+1<n else ''
        if state=='code':
            if ch=='/' and nx=='/': state='line'; out.extend('  '); i+=2; continue
            if ch=='/' and nx=='*': state='block'; out.extend('  '); i+=2; continue
            if ch=='"': state='string'; out.append(' '); i+=1; continue
            if ch=="'": state='char'; out.append(' '); i+=1; continue
            out.append(ch); i+=1; continue
        if state=='line':
            if ch=='\n': state='code'; out.append('\n')
            else: out.append(' ')
            i+=1; continue
        if state=='block':
            if ch=='*' and nx=='/': state='code'; out.extend('  '); i+=2
            else: out.append('\n' if ch=='\n' else ' '); i+=1
            continue
        if state in ('string','char'):
            quote='"' if state=='string' else "'"
            if ch=='\\': out.extend('  ' if i+1<n else ' '); i+=2; continue
            if ch==quote: state='code'; out.append(' '); i+=1; continue
            out.append('\n' if ch=='\n' else ' '); i+=1
    return ''.join(out)

code=strip_cpp_noncode(s)
if re.search(r'(?<![A-Za-z0-9_])setInsecure\s*\(', code):
    raise RuntimeError('15L refuses executable insecure TLS fallback')
print('15L patch chain complete: 15K trust store + bounded chain telemetry; fail-closed TLS retained')
