import random
# Model: any bridge packet loss/write failure latches forwarding off until app disconnect.
r=random.Random(5925)
latched=False; pending=False; app=True; forwarded=0; blocked=0; faults=0
for i in range(5_000_000):
    ev=r.randrange(1000)
    if ev < 4: # queue overflow / oversize / forward-write failure
        pending=True
    elif ev < 8: # owner consumes fault
        if pending:
            pending=False; latched=True; faults+=1
    elif ev < 10: # app disconnect = clean session boundary
        app=False; pending=False; latched=False
    elif ev < 12:
        app=True
    else: # attempted forwarding
        allowed=app and not pending and not latched
        if allowed: forwarded+=1
        else: blocked+=1
        assert not ((pending or latched) and allowed)
print({'steps':5_000_000,'faults':faults,'forwarded':forwarded,'blocked':blocked,'violations':0})
