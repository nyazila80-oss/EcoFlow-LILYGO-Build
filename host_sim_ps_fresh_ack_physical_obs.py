import random
R=random.Random(0x598)
N=3_000_000
viol=0
# Exact command-epoch model: callback stamps epoch at reception. The command epoch
# advances only after writeValue() returns. Therefore a pre-barrier packet cannot ACK.
for _ in range(N):
    old_epoch=R.randrange(0,2**32)
    command_epoch=(old_epoch+1)&0xffffffff
    packet_after_barrier=R.choice([True,False])
    packet_epoch=command_epoch if packet_after_barrier else old_epoch
    before=R.randrange(0,2**32)
    fresh_gen=R.choice([True,False])
    gen=(before+1)&0xffffffff if fresh_gen else before
    mode=R.choice([0,1]); got=R.choice([0,1])
    accepted=(gen!=before and got==mode and packet_epoch==command_epoch)
    if accepted and (not packet_after_barrier or not fresh_gen or got!=mode): viol+=1
print(f'fresh_ack_epoch_cases={N} violations={viol}')
assert viol==0
M=1_000_000
bad=0
for _ in range(M):
    mode=R.choice([0,1]); valid=R.choice([True,True,True,False])
    samples=[R.randint(-2000,3000) for __ in range(R.randint(0,40))]
    if mode!=1: state='ACKNOWLEDGED'
    elif not valid or not samples: state='TELEMETRY_INVALID'
    elif any(x < -500 for x in samples): state='OBSERVED_DISCHARGE'
    else: state='OBSERVED_NO_DISCHARGE'
    if state=='OBSERVED_NO_DISCHARGE' and (mode!=1 or not valid or not samples or any(x < -500 for x in samples)): bad+=1
print(f'physical_obs_cases={M} violations={bad}')
assert bad==0
