#!/usr/bin/env python3
import runpy
runpy.run_path('tools/run_tls15j_patch.py', run_name='__main__')
runpy.run_path('tools/apply_tls15k_runtime_patch.py', run_name='__main__')
print('15K canonical chain complete: 15J proven baseline -> bounded X509 chain telemetry')
