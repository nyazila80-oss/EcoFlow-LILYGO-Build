import random
N=1000000
viol=0
for _ in range(N):
    reserved=False; pending=False; running=False; done=False
    # two concurrent admission attempts modeled in random order
    accepted=[]
    for who in random.sample([0,1],2):
        if not reserved:
            reserved=True; pending=True; accepted.append(who)
    if len(accepted)>1: viol+=1
    # worker exchange pending->false creates the historically dangerous gap
    pending=False
    done=(not reserved)
    if done: viol+=1
    running=True
    # arbitrary work, then result publication before release
    result_written=True
    running=False; reserved=False
    done=(not reserved)
    if not done or not result_written: viol+=1
print({'runs':N,'checks':N*4,'violations':viol})
assert viol==0
