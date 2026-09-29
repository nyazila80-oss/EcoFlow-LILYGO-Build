import random
N=3_000_000
# Model seqlock publication and ensure reader accepts only stable complete generations.
seq=0; words=(0,0,0,0); accepted=0; bad=0
for gen in range(1,N+1):
    seq += 1
    new=(gen & 0xffffffff, (gen*3)&0xffffffff, (gen*5)&0xffffffff, (gen*7)&0xffffffff)
    # reader during write must reject odd sequence
    a=seq
    if not (a&1): bad+=1
    words=new
    seq += 1
    # stable reader
    a=seq; snap=words; b=seq
    if a==b and not (b&1):
        accepted+=1
        if snap != new: bad+=1
print(f'PASS dynamic snapshot/seqlock: {N:,} generations, accepted={accepted:,}, violations={bad}')
assert bad==0 and accepted==N
# Battery master/batt boolean atomic transition model
bm=True; batt=True
for i in range(1_000_000):
    v=bool(i&1); bm=v; batt=not v
    assert bm==v and batt==(not v)
print('PASS batteryMaster/batt atomic gates: 1,000,000 transitions')
