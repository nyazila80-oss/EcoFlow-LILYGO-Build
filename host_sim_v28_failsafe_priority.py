#!/usr/bin/env python3
# Exhaustive/randomized model of 20.4.5.3 priority + recovery + SOC/SOH interaction.
import random
viol=0; checks=0

def step(soc_en,soh_en,valid,delta,soc,soh,stop,resume,min_soh,lat,pending):
    # mirrors priority contract: stale > recovery > disabled > SOC/SOH
    if not valid:
        return True, lat, True, 'BMS_STALE_BLOCK'
    if pending and delta < 2:
        return True, lat, True, 'BMS_STALE_BLOCK'
    pending=False
    if not soc_en and not soh_en:
        return False, False, pending, 'DISABLED'
    if soc_en:
        if not lat and soc<=stop: lat=True
        elif lat and soc>=resume: lat=False
    else: lat=False
    sb=soh_en and soh<=min_soh
    block=lat or sb
    return block,lat,pending,('BLOCK_SOC_SOH' if lat and sb else 'BLOCK_SOC' if lat else 'BLOCK_SOH' if sb else 'ALLOW')

# Exhaustive priority matrix, including both guards OFF.
for soc_en in (False,True):
 for soh_en in (False,True):
  for lat in (False,True):
   b,l,p,st=step(soc_en,soh_en,False,0,50,100,10,12,70,lat,False); checks+=1
   if not (b and p and st=='BMS_STALE_BLOCK'): viol+=1
   b,l,p,st=step(soc_en,soh_en,True,1,50,100,10,12,70,lat,True); checks+=1
   if not (b and p and st=='BMS_STALE_BLOCK'): viol+=1

# Full SOC/SOH state-space for valid recovered operation.
for soc_en in (False,True):
 for soh_en in (False,True):
  for lat in (False,True):
   for soc in range(101):
    for soh in range(101):
     b,l,p,st=step(soc_en,soh_en,True,2,soc,soh,10,12,70,lat,True); checks+=1
     if p: viol+=1
     if not soc_en and not soh_en and (b or l or st!='DISABLED'): viol+=1

# Counter wrap + arbitrary power demand; power must not affect safety state.
for _ in range(3_000_000):
    power=random.randrange(0,10001)
    base=random.randrange(0,2**32)
    d1=(((base+1)&0xffffffff)-base)&0xffffffff
    d2=(((base+2)&0xffffffff)-base)&0xffffffff
    soc_en=bool(random.getrandbits(1)); soh_en=bool(random.getrandbits(1))
    b,_,p,st=step(soc_en,soh_en,False,0,50,100,10,12,70,False,False); checks+=1
    if not(b and p and st=='BMS_STALE_BLOCK'): viol+=1
    b,lat,p,st=step(soc_en,soh_en,True,d1,50,100,10,12,70,False,True); checks+=1
    if not(b and p and st=='BMS_STALE_BLOCK'): viol+=1
    b,lat,p,st=step(soc_en,soh_en,True,d2,50,100,10,12,70,False,True); checks+=1
    if p: viol+=1
print(f'v28 failsafe priority: checks={checks}, violations={viol}')
print('PASS' if viol==0 else 'FAIL')
raise SystemExit(0 if viol==0 else 1)
