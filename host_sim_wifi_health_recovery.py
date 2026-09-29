import random
def healthy(status,ip): return status=="CONNECTED" and ip!=0
r=random.Random(936); false_healthy=0
for _ in range(10_000_000):
 st="CONNECTED" if r.randrange(2) else "DISCONNECTED"; ip=0 if (st!="CONNECTED" or r.randrange(5)==0) else 0xC0A8B243
 if st=="CONNECTED" and ip==0 and healthy(st,ip): false_healthy+=1
assert false_healthy==0
soft,full,cool,ap=10000,30000,30000,120000; ds=1; lf=0; nr=0; fulls=[]; apseen=False
for now in range(1,150002,100):
 off=now-ds
 if off>=ap: apseen=True
 elif off>=full and (lf==0 or now-lf>=cool): fulls.append(now); lf=now; nr=now+soft
 elif now>=nr: nr=now+soft
assert len(fulls)>=3 and apseen
print({"random_states":10000000,"false_healthy":false_healthy,"first_full_restarts_ms":fulls[:3],"recovery_ap_seen":apseen})
