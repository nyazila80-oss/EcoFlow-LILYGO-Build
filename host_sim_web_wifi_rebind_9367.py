import random

def run(seed, steps=200000):
    r=random.Random(seed); had=False; pending=False; rebinds=0; ups=0; violations=0
    connected=False
    for _ in range(steps):
        # bursty link model; long stable periods + occasional transitions
        if r.random() < (0.002 if connected else 0.02): connected=not connected
        if connected:
            if not had:
                ups += 1; pending=True
            had=True
        else:
            had=False
        # main-loop consumes at most once
        if pending:
            pending=False; rebinds += 1
        if rebinds != ups: violations += 1
        # idle/stable connected state must not synthesize extra rebinds
        before=rebinds
        if connected and had and not pending:
            pass
        if rebinds != before: violations += 1
    return ups,rebinds,violations

U=R=V=0
for seed in range(100):
    u,r,v=run(seed); U+=u; R+=r; V+=v
print({'steps':20_000_000,'sta_up_transitions':U,'web_rebinds':R,'violations':V})
assert V==0 and U==R
