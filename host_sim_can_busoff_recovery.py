import random
RUNS=100; STEPS=100000; violations=0; checks=0
for seed in range(RUNS):
    r=random.Random(seed); state='RUNNING'; ready=True; recovery_pending=False
    for _ in range(STEPS):
        x=r.random()
        if state=='RUNNING' and x<0.002:
            state='BUS_OFF'
            # BUS_OFF alert closes admission before any modeled subsequent TX.
            ready=False; recovery_pending=True; state='RECOVERING'
        elif state=='RECOVERING' and x<0.03:
            state='STOPPED' # BUS_RECOVERED semantics: recovery completed, driver stopped
            # restart succeeds most of the time; failure remains fail-closed
            if r.random()<0.97:
                state='RUNNING'; ready=True; recovery_pending=False
            else:
                ready=False; recovery_pending=False
        # invariant: admission iff driver has returned to RUNNING
        checks += 1
        if ready and state!='RUNNING': violations += 1
        # a failed restart must never self-open without a later explicit successful start
        if state=='STOPPED' and ready: violations += 1
print({'runs':RUNS,'checks':checks,'violations':violations})
assert violations==0
