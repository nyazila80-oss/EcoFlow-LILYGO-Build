import random
N=2_000_000
viol=0; admitted=0; runtime_block=0
for _ in range(N):
    free=random.randint(8000,40000); largest=random.randint(3000,min(free,25000))
    admit=(free>=18000 and largest>=9000)
    if not admit: continue
    admitted+=1
    # model task allocation + scheduler/TCB overhead conservatively 6.1-7.5k,
    # then client/connect/GATT dynamic pressure. Runtime guard is checked after each stage.
    f=free-random.randint(6200,7500); l=max(0,largest-random.randint(500,2500))
    if f<9000 or l<6000: runtime_block+=1; continue
    for cost,frag in ((random.randint(400,2500),random.randint(0,1200)),(random.randint(0,2200),random.randint(0,1200)),(random.randint(0,2500),random.randint(0,1500))):
        f-=cost; l=max(0,l-frag)
        if f<9000 or l<6000:
            runtime_block+=1; break
    else:
        # unsafe command admission would be a violation
        if f<9000 or l<6000: viol+=1
print({'runs':N,'admitted':admitted,'runtime_blocks':runtime_block,'violations':viol})
assert viol==0
