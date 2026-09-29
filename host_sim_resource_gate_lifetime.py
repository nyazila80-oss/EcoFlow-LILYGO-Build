import random
RUNS=100; STEPS=100000; violations=0; mismatches=0; acquisitions=0
for seed in range(RUNS):
 r=random.Random(seed+92800); owner=0; since=0; now=0
 for _ in range(STEPS):
  now=(now+r.randrange(0,1000))&0xffffffff
  op=r.randrange(7)
  if op in (0,1):
   want=op+1
   if owner==0: owner=want; since=now; acquisitions+=1
  elif op in (2,3):
   rel=op-1
   if owner==rel: owner=0; since=0
   else: mismatches+=1
  elif op==4:
   # diagnostics must never mutate/steal owner, even for huge ages
   before=owner; age=0 if owner==0 or since==0 else ((now-since)&0xffffffff)
   if owner!=before: violations+=1
  elif op==5 and owner:
   # emulate a hung operation: arbitrary time passes; lease must NOT be stolen
   before=owner; now=(now+0x70000000)&0xffffffff
   if owner!=before: violations+=1
  else:
   # reboot resets RAM atomics naturally
   owner=0; since=0
  if owner not in (0,1,2): violations+=1
print({'runs':RUNS,'checks':RUNS*STEPS,'acquisitions':acquisitions,'intentional_release_mismatches':mismatches,'violations':violations})
assert violations==0
