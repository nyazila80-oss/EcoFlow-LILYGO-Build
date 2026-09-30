#!/usr/bin/env python3
import runpy
from pathlib import Path
runpy.run_path('tools/run_tls15j_patch.py',run_name='__main__')
runpy.run_path('tools/apply_tls15m_runtime_patch.py',run_name='__main__')
# Provenance only; trust store is intentionally unchanged from 15J.
cfg=Path('include/config.h'); c=cfg.read_text(encoding='utf-8').replace('2.4.5.9.36.7.15I-X509-ROOTCAUSE','2.4.5.9.36.7.15M-CLEAN-CHAIN-PROBE').replace('2.4.5.9.36.7.15J-X509-VERIFY-DIAG','2.4.5.9.36.7.15M-CLEAN-CHAIN-PROBE'); cfg.write_text(c,encoding='utf-8')
Path('data/fs_version.txt').write_text('2.4.5.9.36.7.15M-CLEAN-CHAIN-PROBE\n',encoding='utf-8')
s=Path('src/powerstream_api.cpp').read_text(encoding='utf-8')
for t in ('TLS15M_VERSION="9.36.7.15M-CLEAN-CHAIN-PROBE"','tls15m_chain','DigiCert Global Root G2','client.setCACert(ECOFLOW_CA_BUNDLE);'):
    if t not in s: raise RuntimeError('15M invariant missing: '+t)
if 'MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSj' in s: raise RuntimeError('15M contaminated by 15K/15L trust anchor')
print('15M canonical chain complete: 15J baseline + observation-only chain probe')
