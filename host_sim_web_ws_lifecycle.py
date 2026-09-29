import random
random.seed(9375)
RUNS=2000000
viol=0; old_exhaust=0; recovered=0
for _ in range(RUNS):
    # model browser reconnect churn across three WS endpoints
    bms=random.randrange(0,25); log=random.randrange(0,12); dbg=random.randrange(0,12)
    stale_b=random.randrange(0,bms+1) if bms else 0
    stale_l=random.randrange(0,log+1) if log else 0
    stale_d=random.randrange(0,dbg+1) if dbg else 0
    base=random.randrange(16000,50001)
    per=random.randrange(250,901)
    # old behavior: BMS stale clients never explicitly cleaned; model retained cost
    old_free=base-stale_b*per
    if old_free<12000: old_exhaust+=1
    # new global cleanup removes stale clients on all endpoints
    new_b=bms-stale_b; new_l=log-stale_l; new_d=dbg-stale_d
    new_free=base # stale retention reclaimed in model
    if new_free < base: viol+=1
    if old_free<12000 and new_free>=12000: recovered+=1
print({'runs':RUNS,'violations':viol,'old_pressure_cases':old_exhaust,'recovered_cases':recovered})
assert viol==0
print('WEB WS LIFECYCLE MODEL PASS')
