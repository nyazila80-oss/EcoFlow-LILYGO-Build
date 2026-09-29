import random
R=random.Random(5932)
viol=0; checks=0; stale_rejected=0; resets=0
for run in range(100):
    epoch=1; active=False; active_epoch=None; q=[]
    for step in range(100000):
        x=R.random()
        if x < .015: # BUS-OFF/software boundary
            epoch=(epoch+1)&0xffffffff; active=False; active_epoch=None; resets+=1
        elif x < .45: # receive captures generation before potential queue delay
            captured=epoch
            if R.random()<.02: # boundary while receive was blocked
                epoch=(epoch+1)&0xffffffff; active=False; active_epoch=None; resets+=1
            q.append((captured,R.choice(('S','M','E'))))
            if len(q)>24: q.pop(0)
        elif q:
            e,k=q.pop(0); checks+=1
            if e!=epoch:
                stale_rejected+=1; continue
            if k=='S': active=True; active_epoch=e
            elif k in ('M','E') and active:
                if active_epoch!=epoch: viol+=1
                if k=='E': active=False; active_epoch=None
print({'runs':100,'steps':10_000_000,'checks':checks,'stale_rejected':stale_rejected,'boundary_resets':resets,'violations':viol})
assert viol==0 and stale_rejected>0 and resets>0
