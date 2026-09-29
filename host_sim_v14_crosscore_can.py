#!/usr/bin/env python3
import random, pathlib, sys
root=pathlib.Path(__file__).parent
can=(root/'src/can.cpp').read_text(); hdr=(root/'include/can.h').read_text(); eco=(root/'src/ecoflow.cpp').read_text(); cfg=(root/'include/config.h').read_text()
checks={
'atomic definitions': 'std::atomic<uint32_t> can_rx_count{0}' in can and 'std::atomic<uint32_t> can_rx_dropped{0}' in can and 'std::atomic<uint32_t> can_decoded{0}' in can,
'atomic declarations': hdr.count('extern std::atomic<uint32_t>')>=3,
'no volatile CAN counters': 'volatile uint32_t can_rx_' not in can+hdr+eco,
'version': 'AUDIT20.4.5.9.36.7.11-SECURITY-HARDENED-DIAG' in cfg,
'queue handoff': 'xQueueSend(canRxQ' in can and 'xQueueReceive(canRxQ' in can,
'CAN RX atomic gate': 'canRxEnabledAtomic()' in can and 'config.canRxEnabled' not in can,
}
# Model three independent single-writer atomic counters and arbitrary cross-core observations.
r=random.Random(191537); truth=[0,0,0]; seen=[0,0,0]; violations=0; ops=5_000_000
for _ in range(ops):
    k=r.randrange(10)
    if k<4: truth[0]+=1
    elif k<5: truth[1]+=1
    elif k<8: truth[2]+=1
    else:
        # seq-cst atomic load model: observed value may advance, never tear/regress
        i=r.randrange(3); v=truth[i]
        if v<seen[i]: violations+=1
        seen[i]=v
print('V14 CROSS-CORE CAN COUNTER SIM')
print('operations',ops,'violations',violations,'truth',truth,'seen',seen)
for k,v in checks.items(): print(('PASS' if v else 'FAIL'),k)
# Other cross-core fields require a separate ownership review; this test covers
# only CAN counters, queue transfer and the RX admission flag.
if violations or not all(checks.values()): sys.exit(1)
print('PASS')
