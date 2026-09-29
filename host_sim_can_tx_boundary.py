import random
R=random.Random(0x5930); checks=viol=aborts=0
for _ in range(1000000):
    n=R.randint(1,67); fail=R.randrange(n+3); first_fail=None; attempted=[]
    for i in range(n):
        ok=(i!=fail) and (R.random()>0.0005); attempted.append(i); checks+=1
        if not ok: first_fail=i; aborts+=1; break
    if first_fail is not None and any(i>first_fail for i in attempted): viol+=1
print({'messages':1000000,'fragment_checks':checks,'aborts':aborts,'violations':viol})
assert viol==0
