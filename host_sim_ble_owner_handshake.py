import random
# Abstract adversarial model of REQUESTED/GRANTED/DENIED/IDLE handshake.
IDLE,REQ,GRANT,DENY=range(4)
checks=viol=0
for seed in range(100):
 r=random.Random(seed); st=IDLE; reserved=False; adv=True; worker=False
 for _ in range(20000):
  op=r.randrange(5)
  if op==0 and not worker: # worker requests
   if st==IDLE: st=REQ; worker=True
  elif op==1 and st==REQ: # owner consumes, random environment validity
   valid=r.random()>.15
   if valid:
    adv=False; reserved=True; st=GRANT
   else:
    reserved=False; st=DENY; adv=True
  elif op==2 and worker: # worker observes / timeout withdrawal
   if st==GRANT: pass
   elif st==DENY: st=IDLE; worker=False
   elif st==REQ and r.random()<.1: st=IDLE; worker=False
  elif op==3 and reserved: # release
   reserved=False; st=IDLE; adv=True; worker=False
  elif op==4 and st==GRANT: # worker has acquired; keep until release
   pass
  checks+=3
  # Safety invariants: advertised and aux-reserved must never overlap; only GRANT owns slot.
  if reserved and adv: viol+=1
  if reserved and st!=GRANT: viol+=1
  if st==GRANT and not reserved: viol+=1
assert viol==0,(checks,viol)
print({'runs':100,'checks':checks,'violations':viol})
