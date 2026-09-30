#!/usr/bin/env python3
import runpy
from pathlib import Path
runpy.run_path('tools/run_tls15m_patch.py',run_name='__main__')
runpy.run_path('tools/apply_tls15n_runtime_patch.py',run_name='__main__')
cfg=Path('include/config.h'); c=cfg.read_text(encoding='utf-8').replace('2.4.5.9.36.7.15M-CLEAN-CHAIN-PROBE','2.4.5.9.36.7.15N-LEAF-VERIFY-ROOTCAUSE'); cfg.write_text(c,encoding='utf-8')
Path('data/fs_version.txt').write_text('2.4.5.9.36.7.15N-LEAF-VERIFY-ROOTCAUSE\n',encoding='utf-8')
s=Path('src/powerstream_api.cpp').read_text(encoding='utf-8')
for t in ('TLS15N_VERSION="9.36.7.15N-LEAF-VERIFY-ROOTCAUSE"','tls15n_verify_detail','tls15m_chain','DigiCert Global Root G2','client.setCACert(ECOFLOW_CA_BUNDLE);'):
    if t not in s: raise RuntimeError('15N invariant missing: '+t)
if 'MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSj' in s: raise RuntimeError('15N contaminated by 15K/15L trust anchor')
print('15N canonical chain complete: frozen 15M + observation-only leaf verification detail')
