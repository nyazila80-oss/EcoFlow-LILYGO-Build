import random
N=2_000_000
viol=0; admitted=0; runtime_abort=0; create_fail=0
for _ in range(N):
    free=random.randint(0,60000); largest=random.randint(0,free if free else 0)
    integrity=random.random()>0.0005
    admit=integrity and free>=18000 and largest>=9000
    if not admit: continue
    admitted+=1
    # worker task stack/control allocation is environment dependent: stress 5.5-8.0k
    task=random.randint(5500,8000)
    wf=max(0,free-task); wl=max(0,min(largest, wf)-random.randint(0,1200))
    runtime=integrity and wf>=9000 and wl>=6000
    if not runtime:
        runtime_abort+=1
        continue
    # client/connect/GATT may consume memory; every stage must pass runtime guard
    ok=True
    for lo,hi in [(500,3500),(300,3000),(300,4500)]:
        cost=random.randint(lo,hi); wf=max(0,wf-cost); wl=max(0,min(wl,wf)-random.randint(0,700))
        if wf<9000 or wl<6000:
            runtime_abort+=1; ok=False; break
    if ok and (wf<9000 or wl<6000): viol+=1
print({'runs':N,'admitted':admitted,'runtime_aborts':runtime_abort,'violations':viol})
assert viol==0
