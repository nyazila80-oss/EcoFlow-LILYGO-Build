#!/usr/bin/env python3
import runpy

# 15I remains the proven baseline. 15J only adds observation of the mbedTLS
# verification flags; it does not alter the CA, auth mode, hostname, or request.
runpy.run_path('tools/run_tls15i_patch.py', run_name='__main__')
runpy.run_path('tools/apply_tls15j_runtime_patch.py', run_name='__main__')
print('15J canonical chain complete: 15I baseline -> verify-flag telemetry')
