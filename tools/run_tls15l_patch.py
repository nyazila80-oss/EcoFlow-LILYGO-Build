#!/usr/bin/env python3
from pathlib import Path
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
if 'setInsecure(' in s: raise RuntimeError('15L refuses insecure TLS fallback')
print('15L patch chain complete: 15K trust store + bounded chain telemetry; fail-closed TLS retained')
