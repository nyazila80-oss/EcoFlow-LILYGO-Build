#!/usr/bin/env python3
import runpy

CHAIN=(
 'tools/run_tls15i_patch.py',
 'tools/apply_tls15j_x509_diag_patch.py',
)
for script in CHAIN:
    print('15J apply:',script)
    runpy.run_path(script,run_name='__main__')
print('15J canonical chain complete: 15I baseline -> 15J X509 diagnostics')
