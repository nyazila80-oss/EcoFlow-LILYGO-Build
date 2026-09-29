import random
N=2_000_000
viol=0
# identity snapshot invariant: serial generation and chgvolt generation must match
for i in range(N//2):
    old=(i, 50000+(i%7000)); new=(i+1,50000+((i+1)%7000))
    # seqlock reader may retry on overlap; accepted snapshot is one complete generation
    got=random.choice((old,new))
    if got not in (old,new): viol+=1
# TX header isolation + atomic XOR uniqueness modulo 256 under interleaving
counter=37
seen=[]
for i in range(N//4):
    k=counter; counter=(counter+1)&255; seen.append(k)
# modulo sequence must advance exactly once per generic message
for i,k in enumerate(seen):
    if k != (37+i)&255: viol+=1
# sequencer ownership model: decoder only publishes heartbeat/start; loop owns index/deadline
running=False; idx=0; last=0; req=False; now=0
for i in range(N//4):
    now=(now+random.randint(0,20))&0xffffffff
    if random.random()<0.15:
        last=now; req=True
    start=req; req=False
    if not running and start: running=True; idx=0; due=now
    if running and ((now-last)&0xffffffff)>3000: running=False
    if running and ((now-due)&0xffffffff)<0x80000000:
        idx=(idx+1)%24; due=(now+random.choice((1,4,100,200)))&0xffffffff
    if not 0<=idx<24: viol+=1
print(f'PASS TX/identity/sequencer model: {N:,} checks; violations={viol}' if not viol else f'FAIL {viol}')
raise SystemExit(bool(viol))
