#!/usr/bin/env python3
import runpy

# One deterministic 15I entry point.
# apply_tls15d_runtime_patch.py already chains 15E -> 15G -> 15H, so 15H must
# NOT be invoked a second time here.  Then validate the X509 invariants and add
# the 15I runtime failure/provenance telemetry.  Every stage is fail-closed and
# CA verification remains enabled.
CHAIN = (
    'tools/apply_tls15d_runtime_patch.py',
    'tools/apply_tls15i_x509_rootcause_patch.py',
    'tools/apply_tls15i_runtime_patch.py',
)

for script in CHAIN:
    print(f'15I apply: {script}')
    runpy.run_path(script, run_name='__main__')

print('15I canonical chain complete: 15D -> 15E -> 15G -> 15H -> X509 contract -> 15I runtime')
