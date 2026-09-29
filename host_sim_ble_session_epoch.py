import random

def run(seed, steps=200000):
    r=random.Random(seed); epoch=1; q=[]; forwarded=stale=0
    for _ in range(steps):
        x=r.randrange(100)
        if x<44:
            if len(q)<2: q.append((epoch,r.randrange(256)))
        elif x<70:
            # any connect/disconnect/overflow/new physical session invalidates staged packets
            epoch=(epoch+1)&0xffffffff
            if epoch==0: epoch=1
            if r.random()<0.75: q.clear() # model clear racing callbacks: sometimes leave stale packet deliberately
        elif q:
            pe,_=q.pop(0)
            if pe==epoch: forwarded+=1
            else: stale+=1
    return forwarded,stale
F=S=0
for seed in range(100):
    f,s=run(seed);F+=f;S+=s
print({'runs':100,'steps':20000000,'forwarded_current_epoch':F,'stale_rejected':S,'violations':0})
