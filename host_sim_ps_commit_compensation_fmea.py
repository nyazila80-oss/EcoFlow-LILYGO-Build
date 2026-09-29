import random
STOP, RESUME = 20,25
# Abstract policy: storage=1 safe request; supply=0 restore only if BMS valid and SOC unblocked.
# A commit is non-atomic wrt telemetry. Post-commit recheck either compensates storage
# (when telemetry is valid+reblocked) or yields to BMS-stale CAN fail-closed.
class M:
    def __init__(self): self.reset()
    def reset(self):
        self.valid=False; self.recovery=False; self.soc=50; self.block=False; self.mode=0
        self.phase='IDLE'; self.target=None; self.comp=False; self.can_fail_closed=False
        self.bad_supply_commit=0; self.uncontained=0; self.acks=0; self.failures=0; self.supply_committed=False
    def guard_tick(self):
        if not self.valid or self.recovery:
            self.can_fail_closed=True; return
        self.can_fail_closed=False
        if not self.block and self.soc<=STOP: self.block=True
        elif self.block and self.soc>=RESUME: self.block=False
    def admissible(self,target):
        if not self.valid or self.recovery: return False
        return target==1 or not self.block
    def start(self,target):
        self.guard_tick()
        if not self.admissible(target): return False
        self.target=target; self.phase='PRE'; return True
    def event(self,e):
        typ,val=e
        if typ=='valid': self.valid=val
        elif typ=='recovery': self.recovery=val
        elif typ=='soc': self.soc=val
        elif typ=='disconnect': self.valid=False
        elif typ=='reboot': self.reset(); return
        self.guard_tick()
    def precommit(self):
        self.guard_tick()
        if not self.admissible(self.target): self.phase='ABORT'; return False
        self.phase='WRITE'; return True
    def commit_return(self,write_ok=True):
        if not write_ok: self.phase='FAILED'; self.failures+=1; return
        # remote may have accepted target
        self.mode=self.target
        if self.target==0: self.supply_committed=True
        self.guard_tick()
        if self.target==0 and (not self.valid or self.recovery):
            # cannot trust telemetry / issue compensation; hard stale CAN fail-closed owns safety
            self.phase='STALE_CONTAINED'; return
        if self.target==0 and self.block:
            # remote supply may have landed after SOC reblocked: compensate with storage
            self.comp=True; self.phase='COMP_PRE'; return
        self.phase='WAIT_ACK'
    def comp_precommit(self):
        self.guard_tick()
        if not self.valid or self.recovery:
            self.phase='STALE_CONTAINED'; return False
        self.phase='COMP_WRITE'; return True
    def comp_return(self,ok=True):
        if not ok:
            self.phase='COMP_FAILED'; self.failures+=1; return
        self.mode=1; self.phase='COMP_ACK'
    def invariant(self):
        # If valid and blocked after a supply commit, system must either be in compensation path,
        # already storage, or have recorded compensation failure. Stale is contained by CAN fail-closed.
        if (not self.valid or self.recovery) and not self.can_fail_closed:
            return False,'stale_without_can_fail_closed'
        if self.supply_committed and self.valid and not self.recovery and self.block and self.mode==0:
            if self.phase not in ('COMP_PRE','COMP_WRITE','COMP_FAILED'):
                return False,'blocked_supply_not_contained'
        return True,''

def run(seed=0x205910,runs=400000):
    r=random.Random(seed); checks=0; bad=[]; comp=0; stale=0; compfail=0
    for n in range(runs):
        m=M(); m.valid=True; m.soc=r.choice([25,26,30,50]); m.guard_tick()
        if not m.start(0): continue
        # changes before precommit
        for _ in range(r.randrange(4)):
            m.event(r.choice([('soc',r.choice([19,20,21,24,25,26])),('valid',bool(r.getrandbits(1))),('recovery',bool(r.getrandbits(1)))]))
        if not m.precommit():
            ok,why=m.invariant(); checks+=1
            if not ok: bad.append((n,why,m.__dict__.copy())); break
            continue
        # exact write window changes
        for _ in range(r.randrange(5)):
            m.event(r.choice([('soc',r.choice([18,19,20,21,24,25,26])),('valid',bool(r.getrandbits(1))),('recovery',bool(r.getrandbits(1))),('disconnect',None)]))
        m.commit_return(write_ok=(r.random()>0.03))
        if m.phase=='COMP_PRE':
            comp+=1
            # exact gap between supply return and compensating storage write
            for _ in range(r.randrange(4)):
                m.event(r.choice([('soc',r.choice([18,20,21,25,26])),('valid',bool(r.getrandbits(1))),('recovery',bool(r.getrandbits(1))),('disconnect',None)]))
            if m.comp_precommit():
                m.comp_return(ok=(r.random()>0.05))
                if m.phase=='COMP_FAILED': compfail+=1
        if m.phase=='STALE_CONTAINED': stale+=1
        ok,why=m.invariant(); checks+=1
        if not ok:
            bad.append((n,why,m.__dict__.copy())); break
    return {'runs':runs,'checks':checks,'violations':len(bad),'compensation_paths':comp,'stale_contained':stale,'compensation_write_failures':compfail},bad
if __name__=='__main__':
    out,bad=run(); print(out)
    if bad: print(bad[0]); raise SystemExit(1)
