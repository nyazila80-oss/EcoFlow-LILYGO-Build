import random
STOP,RESUME=20,25
class M:
 def __init__(self): self.boot()
 def boot(self):
  self.valid=False; self.soc=50; self.mode=0; self.owned=False; self.original=None
  self.block=False; self.inflight=None; self.inflight_started_blocked=False; self.desired=None
  self.failed=False; self.can_silence=False; self.launch_violation=False; self.stale_launch=False
 def launch(self,mode):
  if not self.valid: self.stale_launch=True; return
  if mode==0 and self.block: self.launch_violation=True; return
  self.inflight=mode; self.inflight_started_blocked=self.block
 def reconcile(self):
  if not self.valid: return
  if not self.block and self.soc<=STOP: self.block=True
  elif self.block and self.soc>=RESUME: self.block=False
  if self.block:
   if not self.owned and self.mode!=1:
    self.original=self.mode; self.owned=True
   self.desired=1
  elif self.owned:
   self.desired=self.original
  else: self.desired=None
  if self.inflight is None and self.desired is not None:
   if self.mode==self.desired:
    if not self.block and self.owned: self.owned=False; self.original=None; self.desired=None
   else: self.launch(self.desired)
 def step(self,ev):
  typ,val=ev
  if typ=='reboot': self.boot(); return
  if typ=='valid': self.valid=val
  elif typ=='soc': self.soc=val
  elif typ=='mode': self.mode=val # external/user observation
  elif typ=='result' and self.inflight is not None:
   sent=self.inflight; self.inflight=None
   if val: self.mode=sent
   else: self.failed=True
  self.reconcile()
 def invariant(self):
  if self.launch_violation: return False,'new_supply_launched_while_blocked'
  if self.stale_launch: return False,'policy_command_launched_while_stale'
  if self.can_silence: return False,'policy_must_not_trigger_can_silence'
  if self.owned and self.original not in (0,1): return False,'ownership_without_original'
  if self.inflight==0 and self.inflight_started_blocked: return False,'supply_inflight_started_blocked'
  return True,''

def run(seed,runs=250000,steps=80):
 r=random.Random(seed); checks=0; bad=[]; stale_restore_windows=0
 for n in range(runs):
  m=M()
  for k in range(steps):
   t=r.randrange(7)
   if t==0: ev=('soc',r.randrange(0,101))
   elif t==1: ev=('valid',bool(r.getrandbits(1)))
   elif t==2: ev=('mode',r.randrange(2))
   elif t==3: ev=('result',bool(r.getrandbits(1)))
   elif t==4: ev=('reboot',None)
   elif t==5: ev=('soc',r.choice([18,19,20,21,24,25,26]))
   else: ev=('valid',True)
   before=(m.block,m.inflight)
   m.step(ev); checks+=1
   if m.block and m.inflight==0 and not m.inflight_started_blocked: stale_restore_windows+=1
   ok,why=m.invariant()
   if not ok:
    bad.append((n,k,ev,why,m.__dict__.copy())); return checks,bad,stale_restore_windows
 return checks,bad,stale_restore_windows
if __name__=='__main__':
 checks,bad,windows=run(0x20599)
 print({'runs':250000,'steps':80,'checks':checks,'violations':len(bad),'restore_inflight_then_reblock_windows':windows})
 if bad: print(bad[0]); raise SystemExit(1)
