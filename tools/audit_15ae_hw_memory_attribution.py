#!/usr/bin/env python3
from pathlib import Path
import re,sys
s=(Path(__file__).resolve().parents[1]/'src'/'powerstream_api.cpp').read_text(encoding='utf-8')
c=[]
def ck(n,x,d): c.append((n,bool(x),d))
ck('TLS verified','setCACert(ECOFLOW_CA_BUNDLE)' in s and 'setInsecure(' not in re.sub(r'//[^\n]*','',s),'CA verification retained')
ck('failed allocation telemetry','gTlsFailedAllocSize' in s and 'gTlsFailedInternalLargest' in s,'requested bytes and largest internal block observable')
ck('pre-GET attribution','gTlsInternalGetPreLargest' in s and 'gTlsInternalPreVerifyLargest' in s,'pre-handshake fragmentation observable')
ck('post-GET attribution','gTlsInternalGetPostLargest' in s and 'gTlsInternalPostVerifyLargest' in s,'post-handshake state observable')
ck('15Z telemetry','tls15z' in s.lower(),'memory-relief provenance exported')
ck('legacy preflight recorded','TLS_GET_MIN_LARGEST8 = 10240' in s,'old threshold recorded, not silently changed')
for n,o,d in c: print(f"{'PASS' if o else 'FAIL'} | {n} | {d}")
print(f"SUMMARY | pass={sum(x[1] for x in c)} fail={sum(not x[1] for x in c)} total={len(c)}")
sys.exit(0 if all(x[1] for x in c) else 1)
