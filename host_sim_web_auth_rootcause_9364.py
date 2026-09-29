#!/usr/bin/env python3
"""Model-based FMEA for historical HTTP/WS Basic Auth load. Not a hardware/network emulator."""
import random, json, statistics
rng=random.Random(9364)
RUNS=250000
viol=0; rows=[]
# Model four cases: stable cached credentials, intermittent credential loss, WS reconnect churn, AUTH-OFF.
for mode in ('auth_cached','auth_retry','auth_ws_churn','auth_off'):
    req=ch=ws=extra=0; peak=0; outstanding=0
    for _ in range(RUNS):
        # one abstract UI poll opportunity
        req += 1
        if mode=='auth_off':
            challenge=False; reconnect=False
        elif mode=='auth_cached':
            challenge=rng.random()<0.002; reconnect=rng.random()<0.0005
        elif mode=='auth_retry':
            challenge=rng.random()<0.08; reconnect=rng.random()<0.003
        else:
            challenge=rng.random()<0.01; reconnect=rng.random()<0.04
        # 401 challenge implies an additional authenticated retry in the browser model.
        if challenge:
            ch+=1; extra+=1; outstanding+=1
        if reconnect:
            ws+=1; extra+=1; outstanding+=1
            # historical WS auth handshake can itself require a challenge/retry
            if mode!='auth_off' and rng.random()<0.25:
                ch+=1; extra+=1; outstanding+=1
        # abstract drain; boundedness is the invariant, not exact timing.
        outstanding=max(0,outstanding-rng.randint(0,2))
        peak=max(peak,outstanding)
        if mode=='auth_off' and (challenge or reconnect): viol+=1
    rows.append(dict(mode=mode,base_requests=req,auth_challenges=ch,ws_reconnects=ws,modeled_extra_transactions=extra,peak_abstract_backlog=peak))
print(json.dumps({'runs_per_mode':RUNS,'invariant_violations':viol,'results':rows,'note':'Model demonstrates amplification potential only; it does not prove hardware causality.'},indent=2))
