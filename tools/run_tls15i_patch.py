#!/usr/bin/env python3
import runpy

# One canonical 15I chain: execute every X509 prerequisite/contract in CI.
# Every stage is fail-closed and preserves CA verification.
CHAIN = (
    'tools/apply_tls15d_runtime_patch.py',
    'tools/apply_tls15h_x509_diag_patch.py',
    'tools/apply_tls15i_x509_rootcause_patch.py',
    'tools/apply_tls15i_runtime_patch.py',
)

for script in CHAIN:
    print(f'15I apply: {script}')
    runpy.run_path(script, run_name='__main__')

print('15I canonical X509 diagnostic chain complete')
