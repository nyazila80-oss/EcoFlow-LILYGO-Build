#!/usr/bin/env python3
import runpy
runpy.run_path('tools/apply_tls15d_runtime_patch.py', run_name='__main__')
runpy.run_path('tools/apply_tls15i_runtime_patch.py', run_name='__main__')
print('15I chain complete')
