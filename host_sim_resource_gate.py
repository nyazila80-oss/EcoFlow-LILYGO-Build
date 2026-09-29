import random
for seed in range(100):
 r=random.Random(seed); owner=0; ble=False; cloud=False
 for _ in range(100000):
  op=r.randrange(6)
  if op==0 and not ble:
   if owner==0: owner=1; ble=True
  elif op==1 and ble: owner=0 if owner==1 else owner; ble=False
  elif op==2 and not cloud:
   if owner==0: owner=2; cloud=True
  elif op==3 and cloud: owner=0 if owner==2 else owner; cloud=False
  elif op==4: # failed BLE task creation releases reservation
   if owner==1 and ble: owner=0; ble=False
  elif op==5: # failed cloud worker creation releases reservation
   if owner==2 and cloud: owner=0; cloud=False
  assert not (ble and cloud)
  assert owner in (0,1,2)
  assert (owner==1)==ble
  assert (owner==2)==cloud
print({'runs':100,'steps':10000000,'violations':0})
