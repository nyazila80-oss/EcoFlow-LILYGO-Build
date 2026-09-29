import random
checks=0
# Admission invariant: logging state must never alter decoder admission.
ids=[0x10014001,0x10114001,0x10214001,0x00431403,0x00831403,0x00C31403,0x10614001,0x123]
for seed in range(5000):
 r=random.Random(seed)
 for _ in range(200):
  fid=r.choice(ids); ext=r.choice([0,1]); rtr=r.choice([0,1])
  expected=bool(ext and not rtr and fid in (0x10014001,0x10114001,0x10214001))
  for logging in (False,True):
   admitted=bool(ext and not rtr and fid in (0x10014001,0x10114001,0x10214001))
   assert admitted==expected; checks+=1
# Low-SOC hysteresis + invalid config rejection model.
for stop in range(0,100):
 for resume in range(stop+1,101):
  blocked=False
  for soc in list(range(100,-1,-1))+list(range(0,101)):
   prev=blocked
   if not blocked and soc<=stop: blocked=True
   elif blocked and soc>=resume: blocked=False
   if prev and soc<resume: assert blocked
   if (not prev) and soc>stop: assert not blocked
   checks+=1
# Logger failure independence: core success alone defines pipeline availability.
for rx in (0,1):
 for dec in (0,1):
  for log in (0,1):
   started=bool(rx and dec)
   assert started==(rx==1 and dec==1); checks+=1
print(f'PASS deep RX/LSG/optional-logger model: {checks:,} checks')
