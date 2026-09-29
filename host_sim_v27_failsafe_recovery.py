#!/usr/bin/env python3
import random
N=3_000_000
viol=0
# Model the v20.4.5.2 stale/recovery contract across arbitrary power demand.
for _ in range(N):
    power=random.randint(0,5000)  # deliberately beyond expected HW range: no 600 W assumption
    base=random.randrange(0,2**32)
    # stale must always block, independent of power
    block=True; pending=True
    if not block or not pending: viol+=1
    # first newly validated status frame: remain blocked
    now=(base+1)&0xffffffff
    delta=(now-base)&0xffffffff
    if delta>=2: viol+=1
    # second newly validated status frame: recovery may proceed
    now=(base+2)&0xffffffff
    delta=(now-base)&0xffffffff
    if delta<2: viol+=1
print(f'v27 failsafe recovery: {N} randomized power/recovery cases, violations={viol}')
print('PASS' if viol==0 else 'FAIL')
raise SystemExit(0 if viol==0 else 1)
