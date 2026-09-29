#!/usr/bin/env python3
import random
STALE=3000
MASK=0xffffffff
def elapsed(now,then): return (now-then)&MASK
def gate(valid,last,now): return valid and last!=0 and elapsed(now,last)<=STALE
viol=0; checks=0
for seed in range(100):
 r=random.Random(seed); now=r.randrange(1,0xffffffff); last=now; valid=True
 for _ in range(100000):
  # loop may be stalled: snapshot.valid intentionally remains true while time advances
  now=(now+r.randrange(0,81))&MASK
  if r.random()<0.002: # fresh validated JK frame
   last=now; valid=True
  if r.random()<0.0002: valid=False
  allowed=gate(valid,last,now); checks+=1
  if allowed and (not valid or last==0 or elapsed(now,last)>STALE): viol+=1
assert viol==0
print({'runs':100,'checks':checks,'violations':viol})
