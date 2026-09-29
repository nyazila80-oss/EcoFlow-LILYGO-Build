import random

# Abstract model of the LAB2 admission/state policy. This does NOT emulate NimBLE/RF;
# it verifies safety invariants around one-shot admission, cooldown, failures and no auto retry.
class M:
    def __init__(self):
        self.enabled=False; self.worker=False; self.state='OFF'; self.cool=0
        self.auto_starts=0; self.accepted=0; self.completed=0
    def tick(self,t):
        if not self.enabled: self.state='OFF'; return
        if self.state in ('FAILED','CONFIRMED','COOLDOWN') and not self.worker:
            self.state='IDLE' if t>=self.cool else 'COOLDOWN'
    def request(self,t,wifi,heap,jk):
        if not self.enabled or self.worker or t<self.cool or not wifi or not heap or not jk: return False
        self.worker=True; self.state='QUEUED'; self.accepted+=1; return True
    def finish(self,t,ok):
        assert self.worker
        self.worker=False; self.completed+=1; self.state='CONFIRMED' if ok else 'FAILED'; self.cool=t+(2 if ok else 30)

random.seed(20591)
checks=0
for run in range(20000):
    m=M(); t=0; prevacc=0
    for step in range(500):
        t+=random.randint(0,3)
        if random.random()<.01 and not m.worker:
            m.enabled=not m.enabled; m.state='IDLE' if m.enabled else 'OFF'
        bw,ba=m.worker,m.accepted
        m.tick(t)
        # ticks alone must never create a worker or request
        assert m.worker==bw and m.accepted==ba
        checks+=1
        if random.random()<.08:
            prev=m.accepted
            ok=m.request(t,random.random()>.1,random.random()>.1,random.random()>.1)
            if ok: assert m.worker and m.accepted==prev+1
            else: assert m.accepted==prev
            prevacc=m.accepted
        else: prevacc=m.accepted
        if m.worker and random.random()<.12:
            m.finish(t,random.random()>.25); prevacc=m.accepted
        assert m.completed<=m.accepted
        assert not (m.state=='OFF' and m.enabled)
print({'runs':20000,'checks':checks,'violations':0})
