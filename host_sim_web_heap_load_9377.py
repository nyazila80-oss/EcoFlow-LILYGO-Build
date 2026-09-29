import random
R=random.Random(9377)
viol=0; pressure=0; sum_old=sum_new=req_old=req_new=0
for run in range(20000):
    # deterministic latency function per timestamp so A/B sees same network conditions
    lat={t:(R.randint(20,180) if R.random()<0.985 else R.randint(900,5000)) for t in range(0,180000,1000)}
    def sim(vis,hid):
        active=[]; maxc=0; reqs=0
        for t in range(0,180000,100):
            hidden=((t//30000)%3)==2; period=hid if hidden else vis
            if t%period==0:
                # map to nearest second; conservative for 2/5 s schedule
                l=lat[(t//1000)*1000]; active.append(t+min(l,4000)); reqs+=1
            active=[x for x in active if x>t]; maxc=max(maxc,len(active))
        return reqs,maxc
    ro,mo=sim(1000,1000); rn,mn=sim(2000,5000)
    req_old+=ro;req_new+=rn;sum_old+=mo;sum_new+=mn
    if rn>ro or mn>mo: viol+=1
    if mn>5: pressure+=1
print({'runs':20000,'violations':viol,'pressure_new':pressure,'requests_old':req_old,'requests_new':req_new,'sum_max_concurrency_old':sum_old,'sum_max_concurrency_new':sum_new})
assert viol==0
