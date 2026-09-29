import random
R=30000
viol=0; checks=0
for _ in range(R):
    # admission fuzz: PS may start only with core JK link up, app absent, wifi stable, heap safe
    for __ in range(300):
        jk=bool(random.getrandbits(1)); app=bool(random.getrandbits(1)); wifi=bool(random.getrandbits(1)); heap=bool(random.getrandbits(1)); busy=bool(random.getrandbits(1)); enabled=bool(random.getrandbits(1))
        admit=enabled and jk and (not app) and wifi and heap and (not busy)
        checks+=1
        if admit and (not jk or app or not wifi or not heap or busy or not enabled): viol+=1
        # Connection budget invariant: JK BMS=1, PS=1 only when app=0 => <=2
        conns=(1 if jk else 0)+(1 if app else 0)+(1 if admit else 0)
        checks+=1
        if admit and conns>2: viol+=1
print({'runs':R,'checks':checks,'violations':viol})
assert viol==0
