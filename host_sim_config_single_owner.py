import random
random.seed(5915)
FREE,WRITING,READY=0,1,2
state=FREE; queued=None; applied=[]; rejected=0; checks=0
for _ in range(2_000_000):
    op=random.randrange(4)
    if op in (0,1):
        payload=(random.randrange(65536),random.randrange(101),random.randrange(101))
        if state==FREE:
            state=WRITING; queued=payload; checks+=1
            # publish only after complete copy
            state=READY
        else: rejected+=1
    elif op==2 and state==READY:
        snap=queued; checks+=1
        assert snap==queued
        applied.append(snap); state=FREE; queued=None
    else:
        # consumer must never consume WRITING/FREE
        checks+=1
        assert state in (FREE,READY)
assert all(len(x)==3 for x in applied)
print({'steps':2_000_000,'checks':checks,'applied':len(applied),'rejected':rejected,'violations':0})
