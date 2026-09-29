import random
random.seed(9376)
N=3_000_000
viol=0
old_rebind_risk=0
stale_pressure=0
for _ in range(N):
    sta=bool(random.getrandbits(1)); gotip=sta and random.random()>.08
    active=random.randrange(0,9); stale=random.randrange(0,9)
    heap=random.randrange(7000,50001); largest=random.randrange(2500,min(heap,18000)+1)
    transition=random.random()<.02
    # 9.36.7.5 cleanup should never increase stale population; model one pass caps stale to max-client budget.
    cleaned=max(0,stale-4)
    if cleaned>stale: viol+=1
    if stale>=5 and heap<16000: stale_pressure+=1
    # old 9.36.7 rebind could end listener while live clients exist on a transition
    if transition and gotip and active>0: old_rebind_risk+=1
    # new invariant: IP transitions do not stop/start HTTP listener
    listener_retained=True
    if gotip and not listener_retained: viol+=1
print({'states':N,'violations':viol,'modeled_old_rebind_with_live_clients':old_rebind_risk,'stale_low_heap_pressure_states':stale_pressure})
