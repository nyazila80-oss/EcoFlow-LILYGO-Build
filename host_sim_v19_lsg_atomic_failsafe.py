import random, threading
N=1_500_000
# packed config invariant simulation
v=(1)|(10<<8)|(12<<16)
checks=0
for i in range(N):
    en=random.getrandbits(1); stop=random.randrange(0,100); resume=random.randrange(stop+1,101)
    v=(en)|stop<<8|resume<<16
    e=bool(v&1); s=(v>>8)&255; r=(v>>16)&255
    assert e==bool(en) and s==stop and r==resume and r>s
    checks+=1
# state machine: stale always requests block; only valid SOC>=resume releases
block=False
trans=0
stop,resume=10,12
for i in range(N):
    valid=random.random()>.08
    soc=random.randrange(0,101)
    old=block
    if not valid: block=True
    elif not block and soc<=stop: block=True
    elif block and soc>=resume: block=False
    if block!=old: trans+=1
    if not valid: assert block
    if valid and old and soc<resume: assert block
    if valid and (not old) and soc>stop: assert not block
    checks+=3
print(f'PASS LSG atomic/failsafe model: {checks:,} checks; transitions={trans:,}')
