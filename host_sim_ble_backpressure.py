import random

def run(depth, seed, steps=250000):
    rng=random.Random(seed); q=[]; faults=0; delivered=0; maxq=0; expired=0
    now=0
    for _ in range(steps):
        now += rng.randint(1,5)
        # mostly one callback, occasional short bursts that real host scheduling can coalesce
        n = rng.choices([0,1,2,3,4,5],[18,55,15,7,4,1])[0]
        for _ in range(n):
            if len(q)>=depth:
                faults+=1; q.clear(); break
            q.append(now); maxq=max(maxq,len(q))
        # owner drains one packet per loop, matching firmware bounded work
        if q:
            t=q.pop(0)
            if ((now-t)&0xffffffff)>250:
                expired+=1; faults+=1; q.clear()
            else: delivered+=1
    return faults,delivered,maxq,expired

base=deep=0
for seed in range(40):
    f2,d2,m2,e2=run(2,seed); f4,d4,m4,e4=run(4,seed)
    base+=f2; deep+=f4
    assert m4<=4 and m2<=2
    assert e4==0 and e2==0
    assert f4<=f2
print({'steps':10_000_000,'depth2_faults':base,'depth4_faults':deep,'reduction_pct':round((base-deep)*100/base,2)})
print('BACKPRESSURE MODEL PASS')
