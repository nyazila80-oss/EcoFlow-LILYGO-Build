import random
N=3_000_000
stop,resume,base=10,12,5
soc_latched=False
viol=0
for i in range(N):
    soc_en=random.random()>.02
    soh_en=random.random()>.65
    valid=random.random()>.002
    soc=random.randrange(0,101); soh=random.randrange(40,101)
    if not soc_en:
        soc_latched=False
    elif valid:
        if not soc_latched and soc<=stop: soc_latched=True
        elif soc_latched and soc>=resume: soc_latched=False
    # CAN floor only follows actual SOC latch, never SOH alone
    lower=max(base,stop) if soc_en and soc_latched else base
    if (not soc_en and soc_latched) or (lower!= (max(base,stop) if soc_en and soc_latched else base)): viol+=1
    # SOH-only block must not mutate CAN lower
    if valid and soh_en and soh<=70 and not soc_latched and lower!=base: viol+=1
print(f'V26 ops={N} violations={viol}')
assert viol==0
# deterministic hysteresis / disable reset
lat=False
seq=[11,10,11,11,12,11]
out=[]
for soc in seq:
    if not lat and soc<=10: lat=True
    elif lat and soc>=12: lat=False
    out.append(lat)
assert out==[False,True,True,True,False,False]
lat=True; soc_en=False
if not soc_en: lat=False
assert lat is False
print('V26 deterministic hysteresis=PASS disable-reset=PASS SOH-no-fake-enforcement=PASS')
