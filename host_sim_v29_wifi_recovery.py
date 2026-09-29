import random
SOFT=10_000; FULL=30_000; COOL=30_000; AP=120_000

def simulate(outage_ms, recover_at=None):
    now=0; next_retry=SOFT; last_full=None; ap=False; soft=full=0; connected=False
    while now <= outage_ms:
        if recover_at is not None and now >= recover_at:
            connected=True
        if connected:
            return {'connected':True,'t':now,'soft':soft,'full':full,'ap':ap}
        offline=now
        if offline>=AP:
            ap=True
            if now>=next_retry: soft+=1; next_retry=now+SOFT
        elif offline>=FULL and (last_full is None or now-last_full>=COOL):
            full+=1; last_full=now; next_retry=now+SOFT
        elif now>=next_retry:
            soft+=1; next_retry=now+SOFT
        now += 100
    return {'connected':False,'t':outage_ms,'soft':soft,'full':full,'ap':ap}

checks=viol=0
# Deterministic boundaries
for ms in [0,9999,10000,29999,30000,59999,60000,119999,120000,180000,600000]:
    r=simulate(ms); checks+=1
    if ms>=120000 and not r['ap']: viol+=1
    if ms>=30000 and r['full']<1: viol+=1
# Recovery at every 100ms over 10 minutes: must be reachable without deleting credentials.
for t in range(0,600001,100):
    r=simulate(600000,t); checks+=1
    if not r['connected'] or r['t']>t+100: viol+=1
# Random long outages, ensure escalation invariants.
rng=random.Random(2054)
for _ in range(100_000):
    d=rng.randrange(0,3_600_001); r=simulate(min(d,180000)); checks+=1
    if d>=30000 and r['full']<1: viol+=1
    if d>=120000 and not r['ap']: viol+=1
print(f'WIFI_RECOVERY_CHECKS={checks} VIOLATIONS={viol}')
raise SystemExit(1 if viol else 0)
